"""Independent HTTP/JPEG receiver. Configuration arrives over stdin, never CLI credentials."""
import io,json,statistics,sys,time,urllib.request
from pathlib import Path
import psutil
from PIL import Image

def describe(data):
 if not data: return None
 values=sorted(data)
 return {'count':len(values),'mean':statistics.mean(values),'p50':values[int((len(values)-1)*.5)],'p95':values[int((len(values)-1)*.95)],'p99':values[int((len(values)-1)*.99)],'max':values[-1]}
def main():
 cfg=json.loads(sys.stdin.readline()); frames=[]; errors=[]; samples=[]; duplicate=0; ids=set()
 process=psutil.Process();
 if cfg.get('affinity') and hasattr(process,'cpu_affinity'): process.cpu_affinity(cfg['affinity'])
 process.cpu_percent(); next_sample=time.perf_counter()+1
 req=urllib.request.Request(cfg['url'],headers={'Authorization':cfg['authorization']})
 try:
  with urllib.request.urlopen(req,timeout=5) as response:
   while time.perf_counter()<cfg['end']:
    line=response.readline()
    if not line: raise RuntimeError('Unexpected end of stream')
    if line.strip()!=b'--frame': continue
    headers={}
    while True:
     line=response.readline()
     if not line: raise RuntimeError('Truncated multipart header')
     if line==b'\r\n': break
     name,value=line.decode('ascii').split(':',1); headers[name.lower()]=value.strip()
    size=int(headers['content-length']); data=response.read(size)
    if len(data)!=size: raise RuntimeError('Truncated JPEG')
    received=time.perf_counter(); captured=float(headers['x-capture-monotonic']); identity=int(headers['x-frame-id'])
    with Image.open(io.BytesIO(data)) as image:
     if image.size!=(1920,1080): raise RuntimeError('Unexpected resolution')
     image.load()
    decoded=time.perf_counter()
    if cfg['start']<=received<cfg['end']:
     if identity in ids: duplicate+=1
     ids.add(identity); frames.append((received,size,identity,captured,decoded))
    if received>=next_sample:
     sample={'seconds':received-cfg['start'],'received':len(frames),'cpu_percent_one_core':process.cpu_percent(),'rss_mb':process.memory_info().rss/1048576}
     samples.append(sample)
     print(json.dumps({'event':'sample',**sample}),flush=True); next_sample=received+1
 except Exception as exc: errors.append(type(exc).__name__+': '+str(exc))
 gaps=[(b[0]-a[0])*1000 for a,b in zip(frames,frames[1:])]
 measured=[sample for sample in samples if 0<=sample['seconds']<=cfg['end']-cfg['start']]
 report={'frames':len(frames),'unique_frames':len(ids),'duplicates':duplicate,'bytes':sum(f[1] for f in frames),'receive_gap_ms':describe(gaps),'capture_to_receive_ms':describe([(f[0]-f[3])*1000 for f in frames]),'capture_to_decode_ms':describe([(f[4]-f[3])*1000 for f in frames]),'gaps_over_50ms':sum(gap>50 for gap in gaps),'gaps_over_66_7ms':sum(gap>1000/15 for gap in gaps),'cpu_mean_one_core_percent':statistics.mean(s['cpu_percent_one_core'] for s in measured) if measured else 0,'rss_peak_mb':max((s['rss_mb'] for s in measured),default=0),'errors':errors,'samples':samples}
 Path(cfg['output']).write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps({'event':'complete','frames':len(frames),'errors':errors}),flush=True)
 if errors: raise SystemExit(1)
if __name__=='__main__': main()
