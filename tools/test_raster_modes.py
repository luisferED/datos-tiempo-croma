"""Hash identical output across Qt raster threadpool configurations."""
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def child():
 import app as c
 from test_broadcast_sequence import DATOS
 from PyQt6.QtWidgets import QApplication
 from PyQt6.QtGui import QImage
 qt=QApplication([]); c.cargar_fuentes(); hashes={}
 with tempfile.TemporaryDirectory() as temp:
  c.RUTA_BASE_DATOS=Path(temp)/'db'
  widget=c.MapaMeteorologico(); widget.resize(1920,1080); widget.reloj_pulso.stop()
  image=QImage(1920,1080,QImage.Format.Format_RGB32); image.setDotsPerMeterX(round(widget.logicalDpiX()/.0254)); image.setDotsPerMeterY(round(widget.logicalDpiY()/.0254))
  for scene in ('actual','forecast','pnt','forecast_transition','pnt_transition'):
   widget.ciudad='La Paz'; widget.datos=DATOS; widget.destino_geo=c.CIUDADES['La Paz']; widget.zoom_destino=2.05; widget.progreso=.5
   widget.modo_extendido=scene.startswith('forecast'); widget.panel_progreso=.5 if scene=='forecast_transition' else 1
   widget.pnt_progreso={'pnt':1,'pnt_transition':.5}.get(scene,0); widget.fase_pulso=11; widget.fase_nubes=.2
   widget.renderizar_imagen(image); bits=image.constBits(); bits.setsize(image.sizeInBytes()); hashes[scene]=hashlib.sha256(memoryview(bits)).hexdigest()
 print(json.dumps(hashes))
def main():
 commands=[sys.executable,__file__,'--child']; env=dict(os.environ)
 env.pop('QT_NO_GUI_THREADPOOL',None)
 a=json.loads(subprocess.check_output(commands,env=env,text=True))
 env['QT_NO_GUI_THREADPOOL']='1'
 b=json.loads(subprocess.check_output(commands,env=env,text=True))
 assert a==b,(a,b)
 print('PASS: identical pixels with internal Qt raster parallelism enabled/disabled')
if __name__=='__main__':
 if '--child' in sys.argv: child()
 else: main()
