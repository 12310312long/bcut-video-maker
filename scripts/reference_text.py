"""Transcribe a local reference or audit excerpt with FFmpeg and local Whisper."""
import argparse,hashlib,json,pathlib,shutil,subprocess,time

def stamp(seconds):
    ms=round(seconds*1000);hours,ms=divmod(ms,3600000);minutes,ms=divmod(ms,60000);secs,ms=divmod(ms,1000)
    return f'{hours:02}:{minutes:02}:{secs:02},{ms:03}'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=pathlib.Path)
    parser.add_argument('--output',required=True,type=pathlib.Path)
    parser.add_argument('--model',default='small')
    parser.add_argument('--language',default='zh')
    parser.add_argument('--prompt',default=None,help='Known names/terms; does not verify their factual meaning')
    parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--duration',type=float)
    parser.add_argument('--threads',type=int,default=8)
    parser.add_argument('--cache-dir',type=pathlib.Path,default=pathlib.Path.home()/'.cache/bcut-video-maker/whisper')
    args=parser.parse_args();source=args.source.resolve();out=args.output.resolve()
    if not source.is_file():parser.error('source must be an existing local audio/video file')
    if args.start<0 or (args.duration is not None and args.duration<=0) or args.threads<1:parser.error('Invalid range or thread count')
    if not shutil.which('ffmpeg'):parser.error('FFmpeg is required')
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError:parser.error('Install scripts/requirements-asr.txt in a project environment')
    command=['ffmpeg','-v','error','-ss',str(args.start),'-i',str(source)]
    if args.duration is not None:command+=['-t',str(args.duration)]
    command+=['-vn','-f','f32le','-ar','16000','-ac','1','-']
    decoded=subprocess.run(command,capture_output=True)
    if decoded.returncode:raise RuntimeError(decoded.stderr.decode('utf-8','replace')[-2000:])
    audio=np.frombuffer(decoded.stdout,dtype=np.float32).copy()
    if not len(audio):raise ValueError('No audio in selected range')
    print('Loading local ASR model; first use may download model files',flush=True)
    model=WhisperModel(args.model,device='cpu',compute_type='int8',cpu_threads=args.threads,download_root=str(args.cache_dir))
    started=time.monotonic()
    segments,info=model.transcribe(audio,language=args.language if args.language!='auto' else None,beam_size=3,vad_filter=True,word_timestamps=True,initial_prompt=args.prompt)
    rows=[]
    for segment in segments:
        rows.append(dict(start=segment.start,end=segment.end,text=segment.text.strip(),avg_logprob=segment.avg_logprob,
                         words=[dict(text=w.word,start=w.start,end=w.end,probability=w.probability) for w in (segment.words or [])]))
        if len(rows)%25==0:print(f'Transcribed {segment.end:.1f}/{len(audio)/16000:.1f} seconds',flush=True)
    if not rows:raise ValueError('No speech recognized; inspect the source instead of inventing text')
    result=dict(source=str(source),source_start_seconds=args.start,selected_seconds=len(audio)/16000,
                model=args.model,language=info.language,processing_seconds=round(time.monotonic()-started,3),
                audio_sha256=hashlib.sha256(decoded.stdout).hexdigest(),timing_basis='seconds relative to the selected excerpt',
                scope='Automatic speech recognition; names numbers quotes and meaning require review',segments=rows)
    out.mkdir(parents=True,exist_ok=True)
    (out/'transcript.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'transcript.txt').write_text('\n'.join(f'[{s["start"]:.2f}—{s["end"]:.2f}] {s["text"]}' for s in rows)+'\n',encoding='utf-8')
    (out/'transcript.srt').write_text('\n\n'.join(f'{i+1}\n{stamp(s["start"])} --> {stamp(s["end"])}\n{s["text"]}' for i,s in enumerate(rows)),encoding='utf-8-sig')
    print(json.dumps(dict(output=str(out),segments=len(rows),selected_seconds=result['selected_seconds'],processing_seconds=result['processing_seconds']),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
