"""Portable video assembly and native BCUT delivery from one measured timeline."""
import argparse,asyncio,collections,concurrent.futures,hashlib,importlib.util,json,math,os,pathlib,re,shutil,subprocess,sys,time
import bcut,captions
HERE=pathlib.Path(__file__).resolve().parent;ASSETS=HERE.parent/'assets'

def run(args,cwd=None):
    p=subprocess.run([str(x) for x in args],cwd=cwd,capture_output=True)
    if p.returncode:raise RuntimeError(p.stderr.decode('utf-8','replace')[-4000:])
    return p.stdout
def probe(p):return json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',p]))
def duration(p):return float(probe(p)['format']['duration'])
def digest(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def ident(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
def slug(s):return re.sub(r'[^\w-]','_',s)[:50] or 'video'
def joined(paths,p):
    p.write_text('\n'.join("file '"+str(pathlib.Path(x).resolve()).replace('\\','/').replace("'","'\\''")+"'" for x in paths),encoding='utf-8');return p
def encoder():
    try:
        run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=64x64:d=0.1','-frames:v',1,'-c:v','h264_nvenc','-f','null','-'])
        return ['-c:v','h264_nvenc','-preset','p5','-cq','19']
    except RuntimeError:return ['-c:v','libx264','-preset','medium','-crf','19']

def doctor(args):
    report={'platform':sys.platform,'python':sys.executable,'ffmpeg':shutil.which('ffmpeg'),'ffprobe':shutil.which('ffprobe'),'Pillow':bool(importlib.util.find_spec('PIL')),'edge_tts':bool(importlib.util.find_spec('edge_tts')),'bcut_dirs':bcut.installed_dirs(),'drafts_dir':str(pathlib.Path(args.drafts_dir).resolve() if args.drafts_dir else bcut.documents()/'Bcut Drafts'),'bundled_font':(ASSETS/'ShanghaiSerif-Bold.ttf').is_file(),'known_native_version':'3.11.25'}
    if args.bcut_dir:report['selected_bcut_dir']=str(bcut.app_dir(args.bcut_dir))
    report['detected_bcut_version']=bcut.app_version(bcut.app_dir(args.bcut_dir))
    print(json.dumps(report,ensure_ascii=False,indent=2))

def voice_complete(mp,events,text):
    try:
        return pathlib.Path(mp).stat().st_size>1000 and ''.join(captions.key(x['text']) for x in bcut.read(events))==captions.key(text)
    except (OSError,ValueError,TypeError,KeyError):return False

async def tts(text,voice,rate,mp,events):
    import edge_tts
    if rate and rate[0] not in '+-':rate='+'+rate
    for attempt in range(3):
        try:
            words=[];temp=mp.with_suffix('.part')
            with temp.open('wb') as f:
                async for event in edge_tts.Communicate(text,voice,rate=rate,boundary='WordBoundary').stream():
                    if event['type']=='audio':f.write(event['data'])
                    elif event['type']=='WordBoundary':words.append({k:event[k] for k in ['text','offset','duration']})
            assert words and temp.stat().st_size>1000,'Empty TTS response'
            assert ''.join(captions.key(x['text']) for x in words)==captions.key(text),'Incomplete TTS stream; retrying this segment'
            os.replace(temp,mp);bcut.write(events,words);return
        except Exception:
            if attempt==2:raise
            await asyncio.sleep(1+attempt)

def atempo(speed):
    assert .25<=speed<=4,'tempo must be 0.25 to 4'
    xs=[]
    while speed>2:xs.append('atempo=2');speed/=2
    while speed<.5:xs.append('atempo=0.5');speed*=2
    return ','.join(xs+[f'atempo={speed:.9f}'])

def prepare(job,base,out):
    fps=job.get('fps',30);size=job.get('size',[1920,1080]);assert len(size)==2 and all(x>0 and x%2==0 for x in size)
    voice=job.get('voice',{});tempo=float(voice.get('tempo',1));segments=[];subs=[];cursor=0;limit=job.get('subtitle',{}).get('max_chars',22)
    media=out/'media';voice_dir=media/'voice';voice_dir.mkdir(parents=True,exist_ok=True)
    for i,seg in enumerate(job['segments']):
        voice={**job.get('voice',{}),**seg.get('voice',{})};tempo=float(voice.get('tempo',1))
        text=seg.get('text','');sid=seg.get('id',f's{i+1}');chars=[];length=0;wav=None
        if text:
            sig=ident({'text':text,'voice':voice,'renderer':'voice1'})
            if 'audio' in seg:
                raw=(base/seg['audio']).resolve();ev=(base/seg['word_events']).resolve()
            else:
                raw=voice_dir/f'{sig}_raw.mp3';ev=voice_dir/f'{sig}_words.json'
                cache=base/'.bcut-cache/voice';cache.mkdir(parents=True,exist_ok=True)
                if not voice_complete(raw,ev,text):
                    if voice_complete(cache/raw.name,cache/ev.name,text):shutil.copy2(cache/raw.name,raw);shutil.copy2(cache/ev.name,ev)
                    else:asyncio.run(tts(text,voice.get('name','zh-CN-YunjianNeural'),voice.get('rate','0%'),raw,ev))
                for file in [raw,ev]:
                    shutil.copy2(file,cache/file.name)
            words=bcut.read(ev);fast=voice_dir/f'{sig}_fast.wav'
            run(['ffmpeg','-v','error','-y','-i',raw,'-af',atempo(tempo),'-ar','48000','-ac','2',fast]);raw_length=duration(fast)
            frames=math.ceil((raw_length+.4)*fps);requested=seg.get('duration')
            if requested is not None:
                assert round(requested*fps)>=frames,'Requested segment duration is shorter than spoken narration'
                frames=round(requested*fps)
            length=frames/fps;wav=voice_dir/f'{sig}_{frames}.wav'
            run(['ffmpeg','-v','error','-y','-i',fast,'-af',f'loudnorm=I=-17:TP=-2:LRA=7,aresample=48000,adelay=180:all=1,apad,atrim=end_sample={round(length*48000)}','-ar','48000','-ac','2',wav])
            for word in words:
                clean=captions.key(word['text'])
                for j,c in enumerate(clean):chars.append({'char':c,'time':cursor/fps+(word['offset']+word['duration']*j/max(1,len(clean)))/1e7/tempo+.18})
            assert captions.key(text)==''.join(x['char'] for x in chars),f'TTS word alignment mismatch in {sid}; align actual narration before proceeding'
            pos=0
            for chunk in captions.split(text,limit,seg.get('editorial_cuts')):
                start=chars[pos]['time'];pos+=len(captions.key(chunk));end=chars[pos]['time'] if pos<len(chars) else cursor/fps+raw_length+.18
                subs.append({'text':chunk,'start':round(start,4),'end':round(min(end,(cursor+frames)/fps-.04),4),'layer':0})
            # The portable delivery needs only processed voice, not synthesis cache.
        else:
            frames=round(float(seg['duration'])*fps);length=frames/fps
        assert frames>0
        segments.append(dict(id=sid,text=text,start_frame=cursor,end_frame=cursor+frames,chars=chars,voice_file=wav.relative_to(out).as_posix() if wav else None,design=seg));cursor+=frames
    return {'title':job['title'],'profile':job.get('profile','general'),'fps':fps,'size':size,'total_frames':cursor,'segments':segments,'captions':subs,'shots':[],'audio_tracks':[]}

def cue(seg,phrase,occurrence=1):
    clean=captions.key(seg['text']);needle=captions.key(phrase);pos=-1
    assert needle and occurrence>=1
    for _ in range(occurrence):pos=clean.find(needle,pos+1);assert pos>=0,f'Cue not found in {seg["id"]}: {phrase}'
    return seg['chars'][pos]['time']

def render_photo(asset,frames,size,fps,dest,enc):
    from PIL import Image,ImageFilter,ImageEnhance
    size=tuple(size);source=Image.open(asset['path']).convert('RGB');w,h=size;mode=asset.get('fit','contain');focus=asset.get('focus',[.5,.5]);zoom=asset.get('zoom',[1,1.025]);assert all(1<=z<=1.2 for z in zoom)
    def crop(im,sz,z=1,fo=(.5,.5)):
        dw,dh=sz;cw=min(im.width,im.height*dw/dh)/z;ch=cw*dh/dw;cx=max(cw/2,min(im.width-cw/2,im.width*fo[0]));cy=max(ch/2,min(im.height-ch/2,im.height*fo[1]));return im.transform(sz,Image.Transform.EXTENT,(cx-cw/2,cy-ch/2,cx+cw/2,cy+ch/2),Image.Resampling.BICUBIC)
    bg=ImageEnhance.Brightness(crop(source,size).filter(ImageFilter.GaussianBlur(max(12,w/70)))).enhance(.45)
    factor=min(w*.94/source.width,h*.88/source.height);dw,dh=round(source.width*factor),round(source.height*factor)
    p=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r',str(fps),'-i','-','-an','-frames:v',str(frames),*enc,'-pix_fmt','yuv420p',str(dest)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for i in range(frames):
            q=i/max(1,frames-1);q=q*q*(3-2*q);z=zoom[0]+(zoom[1]-zoom[0])*q
            if mode=='fill':im=crop(source,size,z,focus)
            else:im=bg.copy();im.paste(crop(source,(dw,dh),z),((w-dw)//2,(h-dh)//2))
            p.stdin.write(im.tobytes())
    finally:p.stdin.close()
    err=p.stderr.read();p.wait()
    if p.returncode:raise RuntimeError(err.decode('utf-8','replace'))

def render_clip(asset,frames,size,fps,dest,enc):
    w,h=size;seconds=frames/fps;start=float(asset.get('clip_in',0));selected=float(asset.get('clip_duration',seconds));speed=selected/seconds
    assert start>=0 and selected>0 and start+selected<=duration(asset['path'])+.05,'Selected source range is unavailable'
    if abs(speed-1)>.001:assert asset.get('retime',False),'Explicit retime=true required for changing archival footage speed'
    # Preserve full frame in a blurred surround; no automatic cropping of evidence.
    filt=f'[0:v]setpts=(PTS-STARTPTS)/{speed:.9f},split=2[b][f];[b]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=24,eq=brightness=-0.2[bg];[f]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={fps},setsar=1,tpad=stop_mode=clone:stop_duration=0.1[v]'
    run(['ffmpeg','-v','error','-y','-ss',start,'-t',selected,'-i',asset['path'],'-filter_complex',filt,'-map','[v]','-an','-frames:v',frames,*enc,'-pix_fmt','yuv420p',dest])

def source_window(asset,source_hash,seconds):
    origin=asset.get('source_range',{});rate=float(origin.get('rate',1));start=float(origin.get('start',0))+float(asset.get('clip_in',0))*rate
    selected=float(asset.get('clip_duration',seconds))
    assert rate>0 and start>=0 and selected>0,'Invalid original source range'
    return dict(id=origin.get('id',source_hash),start=start,end=start+selected*rate)

def source_overlaps(shots,fps):
    result=[]
    for i,x in enumerate(shots):
        a=x.get('source_range')
        if not a:continue
        for j,y in enumerate(shots[i+1:],i+1):
            b=y.get('source_range')
            if not b or a['id']!=b['id']:continue
            overlap=min(a['end'],b['end'])-max(a['start'],b['start'])
            if overlap>1/fps:
                result.append(dict(shots=[i,j],source_id=a['id'],overlap_seconds=round(overlap,6),reuse_reason=y.get('reuse_reason','')))
    return result

def export_captions(out,tl,job):
    from PIL import ImageFont
    w,h=tl['size'];font=out/'media/fonts/ShanghaiSerif-Bold.ttf';default_size=job.get('subtitle',{}).get('size',round(62*w/1920));default_y=job.get('subtitle',{}).get('y',round(h*.915))
    for x in tl['captions']:
        x.setdefault('size',default_size);x.setdefault('x',w/2);x.setdefault('y',default_y)
        x['stroke_level']=captions.stroke_level(x.get('stroke_level',job.get('subtitle',{}).get('stroke_level',captions.DEFAULT_STROKE_LEVEL)))
        assert x['start']>=0 and x['end']>x['start'] and x['end']<=tl['total_frames']/tl['fps']+.001
        f=ImageFont.truetype(str(font),x['size']);assert f.getlength(x['text'])<w*.91,f'Caption overflow: {x["text"]}'
        assert x['size']/2+3<x['y']<h-x['size']/2-3,'Caption vertical overflow'
    subs=[x for x in tl['captions'] if x['layer']==0]
    (out/'captions.srt').write_text('\n\n'.join(f'{i+1}\n{captions.stamp(x["start"])} --> {captions.stamp(x["end"])}\n{x["text"]}' for i,x in enumerate(subs)),encoding='utf-8-sig')
    head=f'[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\nScaledBorderAndShadow: yes\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Main,{bcut.FAMILY},{default_size},&H00FFFFFF,&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,2.5,1,5,20,20,0,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    rows=[]
    for x in tl['captions']:
        assert not any(c in x['text'] for c in '{}\\\n'),'ASS control characters are not caption text'
        # ASS uses output pixels; BCUT stores half its UI level, not ASS pixels.
        border=x['stroke_level']/4*w/1920
        code='{\\pos('+str(x['x'])+','+str(x['y'])+')\\fs'+str(x['size'])+'\\bord'+f'{border:.3f}'+'\\3c&H000000&\\3a&H00&\\fad(60,60)}'
        rows.append(f'Dialogue: {x["layer"]},{captions.stamp(x["start"],True)},{captions.stamp(x["end"],True)},Main,,0,0,0,,{code}{x["text"]}')
    (out/'captions.ass').write_text(head+'\n'.join(rows),encoding='utf-8-sig')

def delivery_variants(job):
    variants=job.get('variants',['配乐版'])
    if not isinstance(variants,list) or not variants or any(x not in ('配乐版','无配乐版') for x in variants) or len(variants)!=len(set(variants)):
        raise ValueError('variants must be a nonempty list of unique 配乐版 / 无配乐版 values')
    premixed_ids={a['id'] for a in job.get('assets',[]) if a.get('contains_music') is True}
    premixed=any(x['asset'] in premixed_ids for x in job.get('source_audio',[]))
    if premixed and '无配乐版' in variants:
        raise ValueError('原声音轨已含音乐，不能通过关闭独立 music 生成无配乐版；需先提供经核对的无音乐来源')
    if '配乐版' in variants and not job.get('music') and not premixed:
        raise ValueError('配乐版需要 music 配置；请选择合适音乐，只有用户明确要求无配乐时才设置 variants=["无配乐版"]')
    return variants

def audio_window(item,tl):
    """Resolve an audio insert against measured segment boundaries, in frames."""
    fps=tl['fps'];seg=None
    if 'segment' in item:
        seg=next((s for s in tl['segments'] if s['id']==item['segment']),None)
        if seg is None:raise ValueError('Unknown audio segment: '+item['segment'])
    start=(seg['start_frame'] if seg else 0)+round(float(item.get('start',0))*fps)
    if item.get('cue'):
        if seg is None:raise ValueError('Audio cue requires segment')
        start=round(cue(seg,item['cue'],item.get('occurrence',1))*fps)+round(float(item.get('start',0))*fps)
    if 'duration' in item:end=start+round(float(item['duration'])*fps)
    else:
        end=item.get('end','segment' if seg else 'end')
        if end=='end':end=tl['total_frames']
        elif end=='segment':
            if seg is None:raise ValueError('end=segment requires segment')
            end=seg['end_frame']
        else:end=(seg['start_frame'] if seg else 0)+round(float(end)*fps)
    if not 0<=start<end<=tl['total_frames']:raise ValueError('Audio range is outside timeline')
    return start,end

def insert_source_captions(tl):
    """Use reviewed local timings for original speech; never synthesize its voice."""
    for seg in tl['segments']:
        for row in seg['design'].get('source_captions',[]):
            start=float(row['start']);end=float(row['end'])
            if not 0<=start<end<=(seg['end_frame']-seg['start_frame'])/tl['fps']:
                raise ValueError('Original speech caption is outside segment '+seg['id'])
            text=captions.display(row['text'])
            if not text:raise ValueError('Empty original speech caption')
            tl['captions'].append(dict(text=text,start=seg['start_frame']/tl['fps']+start,end=seg['start_frame']/tl['fps']+end,layer=0))
    tl['captions'].sort(key=lambda x:(x['layer'],x['start']))
    main=[x for x in tl['captions'] if x['layer']==0]
    if any(a['end']>b['start']+.001 for a,b in zip(main,main[1:])):
        raise ValueError('Original speech and narration captions overlap; leave space for the original speaker')

def build(args):
    base=pathlib.Path(args.project).resolve().parent;job=bcut.read(args.project);variants=delivery_variants(job);out=(base/job.get('output','delivery')).resolve()
    if job.get('profile')=='history':assert job.get('claims'),'Historical narration requires a claims/source table in job.json'
    inputs=[x['path'] for x in job['assets']]+[s[k] for s in job['segments'] for k in ['audio','word_events'] if k in s]
    request_id=ident([job,[(p,digest((base/p).resolve())) for p in inputs]])
    if (out/'build-request.json').exists() and bcut.read(out/'build-request.json')['id']!=request_id:out=out.with_name(out.name+'-'+request_id[:12])
    out.mkdir(parents=True,exist_ok=True);bcut.write(out/'build-request.json',{'id':request_id})
    fontdir=out/'media/fonts';fontdir.mkdir(parents=True,exist_ok=True)
    for name in ['ShanghaiSerif-Bold.ttf','OFL.txt']:shutil.copy2(ASSETS/name,fontdir/name)
    assert shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg/ffprobe missing; run doctor and prepare runtime'
    enc=encoder();tl=prepare(job,base,out);fps=tl['fps'];total=tl['total_frames']/fps;size=tl['size'];assets={x['id']:dict(x) for x in job['assets']};hashes={}
    target=job.get('target_seconds');policy=job.get('duration_policy','soft');ratio=job.get('overrun_ratio',.1)
    if target is not None:assert total<=target*(1 if policy=='hard' else 1+ratio)+1/fps,f'Actual {total:.2f}s exceeds duration budget; edit narration rather than silently accelerating it'
    for a in assets.values():
        a['path']=str((base/a['path']).resolve());assert pathlib.Path(a['path']).is_file(),a['path'];hashes[a['id']]=digest(a['path'])
        if job.get('profile')=='history' and a['kind'] in ['image','video']:
            assert a.get('role') in ['archive','interview','illustration'],'Historical visual must declare archive, interview or illustration'
            assert a.get('source_url') and a.get('context'),'Historical assets need source_url and contextual limits'
            assert not (a.get('ai_generated') and a['role'] in ['archive','interview']),'Generated historical evidence prohibited'
    clips=out/'media/shots';clips.mkdir(parents=True,exist_ok=True);tasks=[];renderer=digest(pathlib.Path(__file__))
    for seg in tl['segments']:
        designs=seg['design']['shots'];assert designs and designs[0].get('cue') is None
        starts=[seg['start_frame'] if s.get('cue') is None else round(cue(seg,s['cue'],s.get('occurrence',1))*fps) for s in designs]
        for i,design in enumerate(designs):
            start=starts[i];end=starts[i+1] if i+1<len(starts) else seg['end_frame'];assert end>start,'Invalid shot cue ordering'
            a=dict(assets[design['asset']]);a.update({k:v for k,v in design.items() if k not in ['asset','cue','occurrence']});assert a['kind'] in ['image','video']
            sig=ident([hashes[design['asset']],a,end-start,size,fps,renderer]);dest=clips/f'{sig}.mp4'
            shot=dict(asset=design['asset'],source_hash=hashes[design['asset']],provenance_id=a.get('provenance_id',hashes[design['asset']]),kind=a['kind'],start_frame=start,end_frame=end,file=dest.relative_to(out).as_posix(),meaning=design.get('meaning',a.get('context','')))
            if a['kind']=='video':
                shot['source_range']=source_window(a,hashes[design['asset']],(end-start)/fps)
                if a.get('reuse_reason'):shot['reuse_reason']=a['reuse_reason']
            tl['shots'].append(shot);tasks.append((a,end-start,dest))
    def render(task):
        a,n,dest=task
        cache=base/'.bcut-cache/shots';cache.mkdir(parents=True,exist_ok=True)
        if not dest.exists() and (cache/dest.name).exists():shutil.copy2(cache/dest.name,dest)
        if dest.exists():
            try:
                p=probe(dest);v=next(s for s in p['streams'] if s['codec_type']=='video')
                if int(v['nb_frames'])==n and [v['width'],v['height']]==size:return
            except (RuntimeError,KeyError,ValueError):pass
        tmp=dest.with_name(dest.stem+'.render.mp4')
        (render_photo if a['kind']=='image' else render_clip)(a,n,size,fps,tmp,enc);os.replace(tmp,dest);shutil.copy2(dest,cache/dest.name)
    # Deduplicate identical rendered cache entries before parallel execution.
    unique={str(t[2]):t for t in tasks}
    with concurrent.futures.ThreadPoolExecutor(max_workers=job.get('workers',2)) as pool:list(pool.map(render,unique.values()))
    voice_clips=[dict(file=s['voice_file'],start_frame=s['start_frame'],end_frame=s['end_frame']) for s in tl['segments'] if s['voice_file']]
    if voice_clips:tl['audio_tracks'].append(dict(role='narration',clips=voice_clips))
    work=out/'.work';work.mkdir(exist_ok=True)
    for i,(asset,n,_) in enumerate(tasks):
        if not asset.get('keep_audio'):continue
        assert asset['kind']=='video';shot=tl['shots'][i];selected=float(asset.get('clip_duration',n/fps));speed=selected/(n/fps);dest=out/'media'/f'original_{i:03}.wav'
        run(['ffmpeg','-v','error','-y','-ss',asset.get('clip_in',0),'-t',selected,'-i',asset['path'],'-vn','-af',atempo(speed)+f',aresample=48000,volume={asset.get("audio_gain_db",0)}dB,apad,atrim=end_sample={round(n/fps*48000)}','-ar',48000,'-ac',2,dest])
        tl['audio_tracks'].append(dict(role='original',clips=[dict(file=dest.relative_to(out).as_posix(),start_frame=shot['start_frame'],end_frame=shot['end_frame'])]))
    for i,item in enumerate(job.get('source_audio',[])):
        asset=assets[item['asset']];start,end=audio_window(item,tl);length=(end-start)/fps;trim=float(item.get('trim',0))
        assert trim>=0 and trim+length<=duration(asset['path'])+.05,'Original audio source range unavailable'
        dest=out/'media'/f'source_audio_{i:03}.wav'
        run(['ffmpeg','-v','error','-y','-ss',trim,'-i',asset['path'],'-t',length,'-vn','-af',f'aresample=48000,volume={float(item.get("gain_db",0))}dB,apad,atrim=end_sample={round(length*48000)}','-ar',48000,'-ac',2,dest])
        tl['audio_tracks'].append(dict(role='original',clips=[dict(file=dest.relative_to(out).as_posix(),start_frame=start,end_frame=end)]))
    # Create an aligned speech/original sidechain before music.
    def mix(tracks,dest):
        cs=[c for tr in tracks for c in tr['clips']];samples=round(total*48000)
        if not cs:run(['ffmpeg','-v','error','-y','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',total,dest]);return
        inputs=[];filters=[];labels=[]
        for i,c in enumerate(cs):
            inputs+=['-i',out/c['file']];filters.append(f'[{i}:a]adelay={round(c["start_frame"]/fps*48000)}S:all=1[a{i}]');labels.append(f'[a{i}]')
        filters.append(''.join(labels)+f'amix=inputs={len(cs)}:normalize=0,alimiter=limit=0.89:level=0,apad,atrim=end_sample={samples}[a]')
        run(['ffmpeg','-v','error','-y',*inputs,'-filter_complex',';'.join(filters),'-map','[a]','-ar',48000,'-ac',2,dest])
    sidechain=work/'voice.wav';mix(tl['audio_tracks'],sidechain)
    for i,m in enumerate(job.get('music',[])):
        asset=assets[m['asset']];start,end=audio_window(m,tl);length=(end-start)/fps
        trim=m.get('trim',0);assert trim+length<=duration(asset['path'])+.05,'Music too short; select another range or explicit edited music'
        dry=work/f'music_dry{i}.wav';local=work/f'voice_local{i}.wav';dest=out/'media'/f'music_{i}.wav';fade_in=float(m.get('fade_in',min(2.5,length/3)));fade_out=float(m.get('fade_out',min(2.5,length/3)))
        assert 0<=fade_in<=length and 0<=fade_out<=length,'Music fade outside clip duration'
        run(['ffmpeg','-v','error','-y','-ss',trim,'-i',asset['path'],'-t',length,'-af',f'loudnorm=I={m.get("lufs",-29)}:TP=-9:LRA=7,aresample=48000,apad,atrim=end_sample={round(length*48000)}','-ar',48000,'-ac',2,dry])
        run(['ffmpeg','-v','error','-y','-i',sidechain,'-af',f'atrim=start={start/fps}:end={end/fps},asetpts=PTS-STARTPTS',local])
        fades=(f',afade=t=in:d={fade_in}' if fade_in else '')+(f',afade=t=out:st={length-fade_out}:d={fade_out}' if fade_out else '')
        run(['ffmpeg','-v','error','-y','-i',dry,'-i',local,'-filter_complex',f'[0:a][1:a]sidechaincompress=threshold=0.06:ratio=3:attack=20:release=400{fades},apad,atrim=end_sample={round(length*48000)}[a]','-map','[a]','-ar',48000,'-ac',2,dest])
        tl['audio_tracks'].append(dict(role='music',clips=[dict(file=dest.relative_to(out).as_posix(),start_frame=start,end_frame=end)]))
    byid={s['id']:s for s in tl['segments']}
    for overlay in job.get('overlays',[]):
        x=dict(overlay);seg=byid[x.pop('segment')] if 'segment' in x else None
        if seg:x['start']=cue(seg,x.pop('cue')) if x.get('cue') else seg['start_frame']/fps
        x.setdefault('start',0);x['end']=x.pop('end',x['start']+x.pop('duration',3))
        if x['end']=='end':x['end']=total
        elif x['end']=='segment':assert seg is not None;x['end']=seg['end_frame']/fps
        x['text']=captions.display(x['text']);x.setdefault('layer',1);tl['captions'].append(x)
    insert_source_captions(tl);export_captions(out,tl,job);bcut.write(out/'timeline.json',tl)
    snapshot=json.loads(json.dumps(job));snapshot['output']='rebuilt-delivery'
    if job.get('bundle_sources',True):
        originals=out/'source-media';originals.mkdir(exist_ok=True)
        for a in snapshot['assets']:
            source=pathlib.Path(assets[a['id']]['path']);dest=originals/(hashes[a['id']][:20]+source.suffix)
            if not dest.exists():shutil.copy2(source,dest)
            a['path']=dest.relative_to(out).as_posix()
        for segment in snapshot['segments']:
            for field in ['audio','word_events']:
                if field in segment:
                    source=(base/segment[field]).resolve();dest=originals/(digest(source)[:20]+source.suffix)
                    if not dest.exists():shutil.copy2(source,dest)
                    segment[field]=dest.relative_to(out).as_posix()
    bcut.write(out/'job-snapshot.json',snapshot)
    sources=[{k:v for k,v in a.items() if k!='path'}|{'input_file':pathlib.Path(a['path']).name,'sha256':hashes[a['id']]} for a in assets.values()]
    bcut.write(out/'sources.json',sources);(out/'narration.md').write_text('# '+job['title']+'\n\n'+'\n\n'.join(s['text'] for s in tl['segments']),encoding='utf-8')
    notes=['# 论断与素材来源','']
    for claim in job.get('claims',[]):notes+=['## '+claim['text'],'',claim.get('source_url',''),'',claim.get('context',''),'']
    for a in sources:notes+=['## 素材 '+a['id'],'',a.get('source_url','用户提供或项目内制作'),'',a.get('context',''),'',a.get('license','许可信息见原始来源'),'',f'文件 {a["input_file"]}  SHA256 {a["sha256"]}','']
    (out/'research.md').write_text('\n'.join(notes),encoding='utf-8')
    listing=joined([out/s['file'] for s in tl['shots']],work/'concat.txt');run(['ffmpeg','-v','error','-y','-f','concat','-safe',0,'-i',listing,'-c','copy',work/'silent.mp4'])
    log=subprocess.run(['ffmpeg','-hide_banner','-y','-i',str(work/'silent.mp4'),'-vf',"ass=filename='captions.ass':fontsdir='media/fonts'",'-an',*enc,'-frames:v',str(tl['total_frames']),str(work/'captioned.mp4')],cwd=out,capture_output=True)
    (work/'font-selection.log').write_bytes(log.stderr);assert log.returncode==0,log.stderr.decode('utf-8','replace')[-2500:]
    for variant in variants:
        mix([tr for tr in tl['audio_tracks'] if variant!='无配乐版' or tr['role']!='music'],out/'media'/f'mix_{variant}.wav')
        video=out/f'{slug(job["title"])}_{variant}.mp4';run(['ffmpeg','-v','error','-y','-i',work/'captioned.mp4','-i',out/'media'/f'mix_{variant}.wav','-c:v','copy','-c:a','aac','-b:a','256k','-t',total,'-movflags','+faststart',video])
        folder=bcut.generate(out,tl,variant,bcut.app_dir(args.bcut_dir));run(['ffmpeg','-v','error','-y','-ss',min(2,total/2),'-i',video,'-frames:v',1,'-vf','scale=960:540',folder/'cover.jpg'])
    bcut.portable(out);print(json.dumps({'delivery':str(out),'seconds':total,'shots':len(tl['shots']),'variants':variants},ensure_ascii=False),flush=True)

def verify(args):
    from PIL import Image,ImageDraw
    root=pathlib.Path(args.project).resolve();tl=bcut.read(root/'timeline.json');fps=tl['fps'];total=tl['total_frames']/fps;checks={};last=0
    for s in tl['shots']:
        assert s['start_frame']==last and s['end_frame']>last;last=s['end_frame'];p=probe(root/s['file']);v=next(x for x in p['streams'] if x['codec_type']=='video');assert int(v['nb_frames'])==s['end_frame']-s['start_frame']
    assert last==tl['total_frames']
    counts=collections.Counter(x['provenance_id'] for x in tl['shots'] if x['kind']=='image');maxreuse=max(counts.values(),default=0)
    warnings=[]
    if maxreuse>3:warnings.append('Same original image appears more than 3 times; review necessity')
    overlaps=source_overlaps(tl['shots'],fps)
    if any(not x['reuse_reason'] for x in overlaps):warnings.append('Original video ranges overlap without a reuse_reason; review source intervals and cuts')
    if tl['size']!=[1920,1080] or fps!=30:warnings.append('Native resolution/FPS differs from validated 1080p30 baseline; actual app verification required')
    for layer in set(x['layer'] for x in tl['captions']):
        caps=sorted((x for x in tl['captions'] if x['layer']==layer),key=lambda x:x['start'])
        for x,y in zip(caps,caps[1:]):assert x['end']<=y['start']+.00001,'Overlapping captions on same layer'
    expected=[x['text'] for x in tl['captions'] if x['layer']==0]
    for rec in bcut.read(root/'portable.json')['projects']:
        d=bcut.read(root/rec['project']);t=d['timelineWidget']['timeline'];assert len(t['videoTracks'])==1
        clips=t['videoTracks'][0]['clips'];assert len(clips)==len(tl['shots']);prev=0
        for c,s in zip(clips,tl['shots']):
            assert c['inPoint']==prev and c['outPoint']==round(s['end_frame']/fps*1000);assert pathlib.Path(c['sourcePath']).resolve()==(root/s['file']).resolve();assert pathlib.Path(c['sourcePath']).is_file();prev=c['outPoint']
        layers=sorted(set(x['layer'] for x in tl['captions']));assert len(layers)==len(t['captionTracks'])
        for track,layer in zip(t['captionTracks'],layers):
            rows=[c for c in tl['captions'] if c['layer']==layer]
            assert [c['captionText'] for c in track['captions']]==[c['text'] for c in rows]
            for native,row in zip(track['captions'],rows):
                if 'stroke_level' not in row:continue  # Do not impose new styling on legacy projects.
                expected_width=captions.stroke_level(row['stroke_level'])/2
                assert native.get('drawOutline') is True and native.get('outlineColor')==dict(r=0,g=0,b=0,a=1) and abs(native.get('outlineWidth',0)-expected_width)<.00001,'Native caption needs opaque black outline and the configured width'
        native_sub=t['captionTracks'][layers.index(0)]['captions'] if 0 in layers else []
        assert [x['captionText'] for x in native_sub]==expected
        for tr in t['captionTracks']:
            for c in tr['captions']:assert pathlib.Path(c['fontPackagePath']).is_file() and c['outPoint']>c['inPoint']
        for tr in t['audioTracks']:
            for c in tr['audioClips']:assert pathlib.Path(c['sourcePath']).is_file()
        variant=pathlib.Path(rec['project']).parent.name
        if variant=='无配乐版':assert len(t['audioTracks'])==sum(x['role']!='music' for x in tl['audio_tracks'])
        video=root/f'{slug(tl["title"])}_{variant}.mp4';p=probe(video);v=next(x for x in p['streams'] if x['codec_type']=='video');assert abs(float(p['format']['duration'])-total)<.05 and [v['width'],v['height']]==tl['size'] and int(v['nb_frames'])==tl['total_frames']
        r=subprocess.run(['ffmpeg','-hide_banner','-nostats','-i',str(video),'-vf','blackdetect=d=0.15:pix_th=0.10:pic_th=0.98','-af','loudnorm=I=-17:TP=-2:LRA=7:print_format=json','-f','null','-'],capture_output=True);log=r.stderr.decode('utf-8','replace');assert r.returncode==0
        black=re.findall(r'black_start:[^\r\n]+',log)
        if black:raise AssertionError('Black intervals need review/fix: '+str(black))
        loudness=json.loads(log[log.rfind('{'):log.rfind('}')+1]);assert float(loudness['input_tp'])<=-1,'Audio peaks need lowering'
        checks[variant]={'native_video_tracks':1,'native_caption_tracks':len(t['captionTracks']),'native_audio_tracks':len(t['audioTracks']),'frames':tl['total_frames'],'black_intervals':black,'audio':loudness}
    selected=next(iter(checks));video=root/f'{slug(tl["title"])}_{selected}.mp4';times=sorted(set([min(total-.05,max(0,x)) for x in [1,total*.25,total*.5,total*.75,total-1]]));sheet=Image.new('RGB',(960,300*math.ceil(len(times)/2)),(25,25,25));draw=ImageDraw.Draw(sheet)
    for i,t in enumerate(times):
        raw=run(['ffmpeg','-v','error','-ss',t,'-i',video,'-frames:v',1,'-vf','scale=480:270','-f','rawvideo','-pix_fmt','rgb24','-']);im=Image.frombytes('RGB',(480,270),raw);x=i%2*480;y=i//2*300;sheet.paste(im,(x,y));draw.text((x+8,y+276),f'{t:.2f}s',fill='white')
    sheet.save(root/'contact-sheet.jpg',quality=94)
    files={root/'timeline.json',root/'captions.ass',root/'captions.srt',root/'media/fonts/ShanghaiSerif-Bold.ttf'}
    files.update(root/s['file'] for s in tl['shots']);files.update(root/c['file'] for tr in tl['audio_tracks'] for c in tr['clips'])
    for rec in bcut.read(root/'portable.json')['projects']:
        files.add(root/rec['project']);files.add(root/f'{slug(tl["title"])}_{pathlib.Path(rec["project"]).parent.name}.mp4')
    report={'status':'code_checks_passed_visual_review_required','seconds':total,'shots':len(tl['shots']),'subtitles':len(expected),'maximum_image_reuses':maxreuse,'source_overlaps':overlaps,'variants':checks,'warnings':warnings,'artifact_sha256':{p.relative_to(root).as_posix():digest(p) for p in sorted(files)},'scope':'Automated structure/media checks and generated contact sheet; not GUI or provenance verification'};bcut.write(root/'verification.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['doctor','build','verify','relocate','register']);p.add_argument('project',nargs='?');p.add_argument('--bcut-dir');p.add_argument('--drafts-dir');args=p.parse_args()
    if args.command!='doctor':assert args.project,'Project job.json or delivery directory is required'
    if args.command=='doctor':doctor(args)
    elif args.command=='build':build(args)
    elif args.command=='verify':verify(args)
    elif args.command=='relocate':bcut.relocate(args.project,args.bcut_dir);print('RELOCATED')
    else:print(json.dumps(bcut.register(args.project,args.drafts_dir,args.bcut_dir),ensure_ascii=False,indent=2))

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
