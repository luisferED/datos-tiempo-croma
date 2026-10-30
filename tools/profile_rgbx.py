import io,json,os,sys,tempfile,time,statistics
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as c
from jpeg_pipeline import encode_jpeg
from test_broadcast_sequence import DATOS
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage
from PIL import Image,ImageChops
qt=QApplication([]); c.cargar_fuentes(); results={}
with tempfile.TemporaryDirectory() as temp:
 c.RUTA_BASE_DATOS=Path(temp)/'db'; w=c.MapaMeteorologico(); w.resize(1920,1080); w.reloj_pulso.stop(); w.ciudad='La Paz'; w.datos=DATOS; w.panel_progreso=1; w.progreso=1; w.destino_geo=c.CIUDADES['La Paz']; w.zoom_destino=2.05
 pictures={}
 for format in (QImage.Format.Format_RGB32,QImage.Format.Format_RGBX8888):
  image=QImage(1920,1080,format); image.setDotsPerMeterX(round(w.logicalDpiX()/.0254)); image.setDotsPerMeterY(round(w.logicalDpiY()/.0254))
  times=[]; codec=[]
  for _ in range(40):
   start=time.perf_counter(); w.renderizar_imagen(image); times.append((time.perf_counter()-start)*1000)
   start=time.perf_counter(); data=encode_jpeg(image,74,'pillow',c.PERFIL); codec.append((time.perf_counter()-start)*1000)
  pictures[format.name]=image.copy()
  results[format.name]={'render_ms':statistics.mean(times),'encode_ms':statistics.mean(codec),'bytes':len(data)}
 a=pictures['Format_RGB32']; b=pictures['Format_RGBX8888']
 results['identical_raw_pixels']=a==b.convertToFormat(QImage.Format.Format_RGB32)
 old=Image.open(io.BytesIO(encode_jpeg(a,74,'qt',c.PERFIL))); new=Image.open(io.BytesIO(encode_jpeg(b,74,'pillow',c.PERFIL)))
 results['identical_decoded_jpeg_pixels']=ImageChops.difference(old,new).getbbox() is None
 print(json.dumps(results,indent=2)); Path('tmp/rgbx-profile.json').write_text(json.dumps(results,indent=2))
