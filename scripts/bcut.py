"""BCUT 3.11.25 adapter. No GUI control and no implicit draft-index writes."""
import copy,ctypes,hashlib,json,os,pathlib,platform,shutil,subprocess,sys,time,uuid
ASSETS=pathlib.Path(__file__).resolve().parents[1]/'assets'
FAMILY='Shanghai History Serif'

def read(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def write(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_name(p.name+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,p)

def project_path(root,relative):
    root=pathlib.Path(root).resolve();p=(root/relative).resolve();p.relative_to(root)
    assert p.name=='project.bjson' and p.parent.parent==root/'drafts','Unexpected portable native project target'
    return p

def documents():
    if os.name=='nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as k:
                return pathlib.Path(os.path.expandvars(winreg.QueryValueEx(k,'Personal')[0]))
        except OSError:pass
    return pathlib.Path.home()/'Documents'

def installed_dirs():
    result=[]
    if os.name=='nt':
        import winreg
        for hive in [winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE]:
            for root in [r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall']:
                try:
                    with winreg.OpenKey(hive,root) as parent:
                        for i in range(winreg.QueryInfoKey(parent)[0]):
                            with winreg.OpenKey(parent,winreg.EnumKey(parent,i)) as child:
                                try:
                                    name=winreg.QueryValueEx(child,'DisplayName')[0]
                                    if '必剪' not in name and 'bcut' not in name.lower():continue
                                    try:p=pathlib.Path(winreg.QueryValueEx(child,'InstallLocation')[0])
                                    except OSError:p=pathlib.Path(winreg.QueryValueEx(child,'DisplayIcon')[0].split(',')[0].strip('"')).parent
                                    if p.is_dir():result.append(str(p.resolve()))
                                except OSError:pass
                except OSError:pass
    return list(dict.fromkeys(result))

def app_dir(explicit=None):
    if explicit:
        p=pathlib.Path(explicit).resolve();assert p.is_dir(),'bcut-dir does not exist';return p
    xs=installed_dirs();return pathlib.Path(xs[0]) if xs else None

def app_version(app):
    if os.name!='nt' or app is None or not (app/'BCUT.exe').is_file():return None
    env=os.environ.copy();env['BCUT_SKILL_EXE_PATH']=str(app/'BCUT.exe')
    p=subprocess.run(['powershell','-NoProfile','-Command','(Get-Item -LiteralPath $env:BCUT_SKILL_EXE_PATH).VersionInfo.FileVersion'],env=env,capture_output=True)
    import re
    m=re.search(r'\d+\.\d+\.\d+',p.stdout.decode('utf-8','replace'))
    return m.group() if m else None

def running():
    if os.name!='nt':return False
    p=subprocess.run(['tasklist','/FI','IMAGENAME eq BCUT.exe','/FO','CSV','/NH'],capture_output=True)
    return b'BCUT.exe' in p.stdout or b'BCUT.EXE' in p.stdout

def fresh(x):
    x=copy.deepcopy(x)
    def visit(v):
        if isinstance(v,dict):
            for k,z in v.items():
                if k in ['uid','idString']:v[k]=str(uuid.uuid4().int%9000000000000000000+1000000000000000000)
                else:visit(z)
        elif isinstance(v,list):
            for z in v:visit(z)
    visit(x);return x

def install_font(font):
    if os.name!='nt':return None
    import winreg
    dest=pathlib.Path(os.environ['LOCALAPPDATA'])/'Microsoft/Windows/Fonts/ShanghaiHistorySerif-Bold.ttf';dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists() or hashlib.sha256(dest.read_bytes()).digest()!=hashlib.sha256(pathlib.Path(font).read_bytes()).digest():shutil.copy2(font,dest)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows NT\CurrentVersion\Fonts') as k:
        winreg.SetValueEx(k,FAMILY+' Bold (TrueType)',0,winreg.REG_SZ,str(dest))
    ctypes.windll.gdi32.AddFontResourceExW(str(dest),0,0)
    result=ctypes.c_ulong();ctypes.windll.user32.SendMessageTimeoutW(0xFFFF,0x001D,0,0,2,1000,ctypes.byref(result))
    return str(dest)

def generate(root,timeline,variant,bcut_dir=None):
    root=pathlib.Path(root).resolve();d=fresh(read(ASSETS/'sanitized-template.bjson'));tl=d['timelineWidget']['timeline']
    vt=next(x for x in tl['videoTracks'] if x['clips']);at=tl['audioTracks'][0];ct=tl['captionTracks'][0]
    video_seed=vt['clips'][0];audio_seed=at['audioClips'][0];caption_seed=ct['captions'][0]
    fps=timeline['fps'];w,h=timeline['size'];tl['config']['videoFps']={'num':fps,'den':1};tl['config']['videoRes']={'width':w,'height':h}
    def clip(p,start,end,kind):
        c=fresh(video_seed if kind=='video' else audio_seed);duration=(end-start)/fps;p=str(pathlib.Path(p).resolve()).replace('\\','/')
        c.update(sourcePath=p,originalFilePath=p,inPoint=round(start/fps*1000),outPoint=round(end/fps*1000),trimIn=0,trimOut=round(duration*1000),speed=1)
        c['assetInfo'].update(srcPath=p,originSrcPath='',content=pathlib.Path(p).stem,displayName=pathlib.Path(p).stem,itemName=pathlib.Path(p).name,duration=round(duration*1000),width=w if kind=='video' else 0,height=h if kind=='video' else 0,frameRateNum=fps if kind=='video' else 0)
        return c
    vt=fresh(vt);vt.update(index=0,clips=[clip(root/x['file'],x['start_frame'],x['end_frame'],'video') for x in timeline['shots']]);tl['videoTracks']=[vt]
    audio=[]
    for i,track in enumerate(timeline['audio_tracks']):
        if track['role']=='music' and variant=='无配乐版':continue
        tr=fresh(at);tr.update(index=len(audio),audioClips=[clip(root/x['file'],x['start_frame'],x['end_frame'],'audio') for x in track['clips']]);audio.append(tr)
    tl['audioTracks']=audio
    resource=pathlib.Path(bcut_dir)/'res/subtt/huazi/default' if bcut_dir else None
    font=root/'media/fonts/ShanghaiSerif-Bold.ttf';tracks=[]
    for layer in sorted(set(x.get('layer',0) for x in timeline['captions'])):
        caps=[]
        for x in timeline['captions']:
            if x.get('layer',0)!=layer:continue
            c=fresh(caption_seed);c.update(captionText=x['text'],inPoint=round(x['start']*1000),outPoint=round(x['end']*1000),scaleX=x['size']/100,scaleY=x['size']/100,transX=(x['x']-w/2)/(w/2),transY=(h/2-x['y'])/(h/2),letterSpacing=0,drawOutline=True,drawShadowColor=True,fontName=FAMILY,defaultFontName=FAMILY,defaultFontPath=font.as_posix(),fontPackagePath=font.as_posix(),textBold=False)
            c['textFrameOriginRect']={'leftBottom':{'x':-w/2,'y':-h/2},'leftTop':{'x':-w/2,'y':h/2},'rightBottom':{'x':w/2,'y':-h/2},'rightTop':{'x':w/2,'y':h/2}}
            c['assetInfo'].update(content=x['text'],displayName=x['text'],duration=round((x['end']-x['start'])*1000),fontSrcPath=font.as_posix(),srcPath=resource.as_posix() if resource and resource.exists() else '')
            caps.append(c)
        tr=fresh(ct);tr.update(index=1+len(tracks),captions=caps);tracks.append(tr)
    tl['captionTracks']=tracks;tl['exportAreaInPoint']=-1;tl['exportAreaOutPoint']=-1
    ordered=tracks[::-1]+[vt]+audio
    widgets={'trackWidgetList':[dict(index=i+1,trackHeightLevel=0,trackWidgetWaveHeightLevel=0,uid=x['uid']) for i,x in enumerate(ordered)]}
    d['timelineWidget']['trackList']=widgets;d['timelineWidget']['trackListWidget']=copy.deepcopy(widgets)
    media={}
    for typ,trs,k in [(4,[vt],'clips'),(5,audio,'audioClips')]:
        for tr in trs:
            for c in tr[k]:
                a=c['assetInfo'];media[c['sourcePath']]=dict(duration=str(a['duration']),frameRateDen=1,frameRateNum=fps if typ==4 else 0,height=h if typ==4 else 0,width=w if typ==4 else 0,importTime='',recentlyUsedTime='',itemType=typ,shotClipId='',shotIndex=-1,srcPath=c['sourcePath'])
    d['mainWindow']['browserPanelFiles']=list(media.values());d['timelineWidget']['tracking']={}
    folder=root/'drafts'/variant;folder.mkdir(parents=True,exist_ok=True);write(folder/'project.bjson',d)
    return folder

PATH_KEYS={'sourcePath','originalFilePath','srcPath','originSrcPath','fontSrcPath','defaultFontPath','fontPackagePath','coverPath'}
def portable(root):
    root=pathlib.Path(root).resolve();records=[]
    def walk(x,parts,found):
        if isinstance(x,dict):
            for k,v in x.items():
                if k in PATH_KEYS and isinstance(v,str) and v:
                    try:rel=pathlib.Path(v).resolve().relative_to(root).as_posix();found.append({'json_path':parts+[k],'file':rel})
                    except ValueError:
                        if k=='srcPath' and '/res/subtt/' in v.replace('\\','/'):found.append({'json_path':parts+[k],'resource':'res/subtt/huazi/default'})
                        else:raise ValueError('Nonportable native dependency: '+v)
                else:walk(v,parts+[k],found)
        elif isinstance(x,list):
            for i,v in enumerate(x):walk(v,parts+[i],found)
    for p in sorted((root/'drafts').glob('*/project.bjson')):
        found=[];walk(read(p),[],found);records.append({'project':p.relative_to(root).as_posix(),'paths':found})
    write(root/'portable.json',{'schema':1,'projects':records})

def relocate(root,bcut_dir=None):
    root=pathlib.Path(root).resolve();app=app_dir(bcut_dir)
    for rec in read(root/'portable.json')['projects']:
        project=project_path(root,rec['project']);d=read(project)
        for entry in rec['paths']:
            if 'file' in entry:
                p=(root/entry['file']).resolve();p.relative_to(root);assert p.is_file(),str(p);value=str(p).replace('\\','/')
            else:value=str(app/entry['resource']) if app and (app/entry['resource']).exists() else ''
            target=d
            for k in entry['json_path'][:-1]:target=target[k]
            target[entry['json_path'][-1]]=value
        for track in d['timelineWidget']['timeline']['captionTracks']:
            for caption in track['captions']:
                resource=app/'res/subtt/huazi/default' if app else None
                caption['assetInfo']['srcPath']=resource.as_posix() if resource and resource.exists() else ''
        write(project,d)
    install_font(root/'media/fonts/ShanghaiSerif-Bold.ttf')

def register(root,drafts=None,bcut_dir=None):
    assert os.name=='nt','Native draft registration requires Windows'
    root=pathlib.Path(root).resolve();drafts=pathlib.Path(drafts).resolve() if drafts else documents()/'Bcut Drafts'
    assert not running(),'必剪正在运行 请保存退出后仅重试 register 已完成文件保留'
    verification=read(root/'verification.json');assert verification['status'].startswith('code_checks_passed'),'Run verify before registration'
    for name,expected in verification.get('artifact_sha256',{}).items():
        p=(root/name).resolve();p.relative_to(root)
        h=hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        assert h.hexdigest()==expected,'Verified artifact changed; run verify again: '+name
    assert verification.get('artifact_sha256'),'Verification report lacks artifact fingerprints; run verify again'
    idx=drafts/'draftInfo.json';assert idx.is_file(),'No draft index detected; inspect the current installation before registration'
    original=idx.read_bytes();index=json.loads(original);versions=set()
    app=app_dir(bcut_dir);version=app_version(app)
    assert version in [None,'3.11.25'],'Installed BCUT executable version requires a new adapter: '+str(version)
    for entry in index['draftInfos']:
        p=drafts/entry['id']/'project.bjson'
        if p.is_file():
            try:
                draft=read(p);versions.add(draft['draftCreatedVersion']);t=draft['timelineWidget']['timeline']
                assert all(isinstance(t[k],list) for k in ['videoTracks','audioTracks','captionTracks']) and isinstance(t['config'],dict),'Unexpected native track schema'
            except (KeyError,ValueError):pass
    assert versions and versions=={'3.11.25'},'Unknown/mixed BCUT draft versions; inspect schema and adapt before registration: '+repr(versions)
    relocate(root,bcut_dir);timeline=read(root/'timeline.json');marker=root/'registration.json';old=read(marker) if marker.exists() else {}
    machine_key=hashlib.sha256((platform.node()+'|'+str(drafts).casefold()).encode()).hexdigest();ids=old.get(machine_key,{})
    entries=[]
    for rec in read(root/'portable.json')['projects']:
        source=project_path(root,rec['project']);variant=source.parent.name;ident=ids.get(variant,str(uuid.uuid4()).upper())
        if ident in {x['id'] for x in index['draftInfos']}:
            current=drafts/ident/'project.bjson'
            if current.is_file() and current.read_bytes()!=source.read_bytes():ident=str(uuid.uuid4()).upper()
        ids[variant]=ident;folder=drafts/ident;shutil.copytree(source.parent,folder,dirs_exist_ok=True)
        entries.append(dict(cloud_draft_id='',cloud_draft_version='',duration=round(timeline['total_frames']/timeline['fps']*1000000),id=ident,modifyTime=int(time.time()*1000),name=timeline['title']+'｜'+variant,storyLineId='',video_slice_id=''))
    assert not running(),'必剪已启动 暂停索引写入 工程文件保留'
    assert idx.read_bytes()==original,'Draft index changed concurrently; retry after inspection'
    backup=root/'registration-backups';backup.mkdir(exist_ok=True);(backup/f'draftInfo-{time.time_ns()}.json').write_bytes(original)
    index['draftInfos']=entries+[x for x in index['draftInfos'] if x['id'] not in {e['id'] for e in entries}];write(idx,index)
    old[machine_key]=ids;write(marker,old)
    for rec in read(root/'portable.json')['projects']:
        verification['artifact_sha256'][rec['project']]=hashlib.sha256((root/rec['project']).read_bytes()).hexdigest()
    write(root/'verification.json',verification)
    assert all((drafts/e['id']/'project.bjson').is_file() for e in entries)
    return entries
