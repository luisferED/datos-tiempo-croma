import io, json, os, sys, tempfile, time, statistics
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as c
from test_broadcast_sequence import DATOS
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage
from PyQt6.QtCore import QByteArray,QBuffer,QIODevice
from PIL import Image,features
qt=QApplication([])
with tempfile.TemporaryDirectory() as temp:
 c.RUTA_BASE_DATOS=Path(temp)/'test.sqlite3'; c.cargar_fuentes(); w=c.MapaMeteorologico(); w.resize(1920,1080); w.show(); w.reloj_pulso.stop(); w.ciudad='La Paz'; w.datos=DATOS; w.progreso=1; w.panel_progreso=1
 image=w.grab().toImage()
 results={}
 for format in [image.format(),QImage.Format.Format_RGB32,QImage.Format.Format_RGB888]:
  conversion=[]; compression=[]; cpu=[]
  for _ in range(40):
   t=time.perf_counter(); converted=image.convertToFormat(format); conversion.append((time.perf_counter()-t)*1000)
   data=QByteArray(); b=QBuffer(data); b.open(QIODevice.OpenModeFlag.WriteOnly)
   t=time.perf_counter(); tc=time.thread_time(); converted.save(b,'JPG',c.CALIDAD_JPEG); cpu.append((time.thread_time()-tc)*1000); compression.append((time.perf_counter()-t)*1000); b.close()
  results[format.name]={'conversion_mean_ms':statistics.mean(conversion),'jpeg_mean_ms':statistics.mean(compression),'jpeg_cpu_mean_ms':statistics.mean(cpu),'bytes':len(data)}
 results['Pillow_turbo_available']=features.check_feature('libjpeg_turbo')
 Path('tmp/codec-profile.json').write_text(json.dumps(results,indent=2)); print(json.dumps(results,indent=2))
