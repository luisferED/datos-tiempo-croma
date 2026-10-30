import io, json, os, sys, tempfile, threading, time, statistics
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as c
from test_broadcast_sequence import DATOS
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QByteArray,QBuffer,QIODevice
from PIL import Image, ImageChops
qt=QApplication([])
with tempfile.TemporaryDirectory() as temp:
 c.RUTA_BASE_DATOS=Path(temp)/'db'; w=c.MapaMeteorologico(); w.resize(1920,1080); w.show(); w.ciudad='La Paz'; w.datos=DATOS; w.panel_progreso=1
 im=w.grab().toImage(); bits=im.constBits(); bits.setsize(im.sizeInBytes()); view=memoryview(bits)
 def qtjpeg():
  data=QByteArray(); buffer=QBuffer(data); buffer.open(QIODevice.OpenModeFlag.WriteOnly); im.save(buffer,'JPG',74); buffer.close(); return bytes(data)
 def pillowjpeg():
  image=Image.frombuffer('RGB',(im.width(),im.height()),view,'raw','BGRX',im.bytesPerLine(),1); out=io.BytesIO(); image.save(out,'JPEG',quality=74,subsampling=2); return out.getvalue()
 results={}; encoded={}
 for name,encode in [('qt',qtjpeg),('pillow',pillowjpeg)]:
  gaps=[]; stop=threading.Event()
  def heartbeat():
   prev=time.perf_counter()
   while not stop.is_set():
    time.sleep(.001); now=time.perf_counter(); gaps.append((now-prev)*1000); prev=now
  thread=threading.Thread(target=heartbeat); thread.start(); durations=[]
  for _ in range(80):
   start=time.perf_counter(); encoded[name]=encode(); durations.append((time.perf_counter()-start)*1000)
  stop.set(); thread.join()
  results[name]={'mean_ms':statistics.mean(durations),'heartbeat_gap_p95_ms':sorted(gaps)[int(.95*(len(gaps)-1))],'heartbeat_max_gap_ms':max(gaps),'bytes':len(encoded[name])}
 a=Image.open(io.BytesIO(encoded['qt'])); b=Image.open(io.BytesIO(encoded['pillow'])); results['identical_quantization']=a.quantization==b.quantization; results['identical_decoded_pixels']=ImageChops.difference(a,b).getbbox() is None; results['identical_bytes']=encoded['qt']==encoded['pillow']
 Path('tmp/codec-gil-profile.json').write_text(json.dumps(results,indent=2)); print(json.dumps(results,indent=2))
