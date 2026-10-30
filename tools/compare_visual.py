"""Compare deterministic pixels against the local pre-change source snapshot."""
import gc, importlib.util, os, sys, tempfile
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as after
from test_broadcast_sequence import DATOS
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QColor

def main():
 root=Path(__file__).resolve().parents[1]
 spec=importlib.util.spec_from_file_location('before',root/'tmp/app_before.py'); before=importlib.util.module_from_spec(spec); spec.loader.exec_module(before)
 qt=QApplication([]); after.cargar_fuentes()
 with tempfile.TemporaryDirectory() as temp:
  image=QPixmap(700,500); image.fill(QColor('#abcdef')); image.save(temp+'/brand.png')
  for module in (before,after): module.RAIZ=root; module.ACTIVOS=root/'assets'; module.RUTA_BASE_DATOS=Path(temp)/'test.sqlite3'
  maps=[m.MapaMeteorologico() for m in (before,after)]
  for widget in maps:
   widget.resize(1920,1080); widget.show(); widget.reloj_pulso.stop()
   widget.animacion_camara.stop(); widget.animacion_panel.stop(); widget.animacion_pnt.stop()
   widget.ciudad='La Paz'; widget.datos=DATOS; widget.progreso=1; widget.panel_progreso=1; widget.fase_pulso=12; widget.fase_nubes=.4
   widget.configurar_pnt(temp+'/brand.png',temp+'/brand.png')
  for scene in ['inicio','actual','extendido','pnt','pnt_transicion']:
   for widget in maps:
    widget.datos=None if scene=='inicio' else DATOS
    widget.modo_extendido=scene=='extendido'; widget.pnt_progreso={'pnt':1,'pnt_transicion':.5}.get(scene,0)
   images=[widget.grab().toImage() for widget in maps]
   assert images[0]==images[1],scene
   print(scene+': identical pixels',flush=True)
  for widget in maps: widget.close()
  gc.collect()  # Close cyclic SQLite objects retained by the original reference code.
if __name__=='__main__': main()

