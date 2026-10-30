"""Deterministic transition coverage across all cities and weather branches."""
import os, sys, tempfile, subprocess, sqlite3
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as c
from test_broadcast_sequence import DATOS
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QColor

def finish(animation): animation.setCurrentTime(animation.duration())
def main():
 qt=QApplication([]); c.cargar_fuentes()
 with tempfile.TemporaryDirectory() as temp:
  c.RUTA_BASE_DATOS=Path(temp)/'data.sqlite3'
  widget=c.MapaMeteorologico(); widget.resize(960,540); widget.show(); widget.reloj_pulso.stop()
  for city in c.ORDEN_RECORRIDO:
   widget.mostrar_ciudad(city,DATOS)
   if widget.panel_accion=='viajar': finish(widget.animacion_panel)
   finish(widget.animacion_camara); finish(widget.animacion_panel)
   assert widget.ciudad==city and widget.progreso==1 and widget.panel_progreso==1,city
   assert widget._camera_geo()==c.CIUDADES[city]
  widget.mostrar_extendido(True); finish(widget.animacion_panel); qt.processEvents(); finish(widget.animacion_panel)
  assert widget.modo_extendido and widget.panel_progreso==1
  assert not widget.grab().isNull()
  widget.mostrar_extendido(False); finish(widget.animacion_panel); qt.processEvents(); finish(widget.animacion_panel)
  assert not widget.modo_extendido
  for code in c.CONDICIONES:
   widget.datos=dict(DATOS,codigo=code)
   assert not widget.grab().isNull(),code
  image=QPixmap(100,100); image.fill(QColor('red')); image.save(temp+'/pnt.png')
  widget.configurar_pnt(temp+'/pnt.png',temp+'/pnt.png')
  for expected in [1,0,1,0]:
   widget.alternar_pnt(); finish(widget.animacion_pnt)
   assert widget.pnt_progreso==expected
   assert not widget.grab().isNull()
  widget.mostrar_inicio(); finish(widget.animacion_panel); finish(widget.animacion_camara)
  assert widget.datos is None and abs(widget._zoom_camara()-.92)<1e-9
  # Interrupt a camera move and verify the new origin matches its current position.
  widget.mostrar_ciudad(c.ORDEN_RECORRIDO[0],DATOS)
  widget.animacion_camara.setCurrentTime(widget.animacion_camara.duration()//2)
  position=widget._camera_geo()
  widget.mostrar_ciudad(c.ORDEN_RECORRIDO[-1],DATOS)
  assert widget.origen_geo==position
  widget.close()
  # Back up while a committed transaction remains in WAL.
  connection=sqlite3.connect(c.RUTA_BASE_DATOS)
  connection.execute('CREATE TABLE backup_probe (value TEXT)'); connection.execute("INSERT INTO backup_probe VALUES ('committed-in-wal')"); connection.commit()
  destination=Path(temp)/'backup.sqlite3'
  tool=Path(__file__).with_name('backup_db.py')
  subprocess.run([sys.executable,str(tool),str(c.RUTA_BASE_DATOS),str(destination)],check=True)
  with c.database(destination) as backup:
   assert backup.execute('SELECT value FROM backup_probe').fetchone()[0]=='committed-in-wal'
  connection.close()
  refusal=subprocess.run([sys.executable,str(tool),str(c.RUTA_BASE_DATOS),str(destination)],capture_output=True)
  assert refusal.returncode!=0
  print(f'PASS: {len(c.ORDEN_RECORRIDO)} cities, {len(c.CONDICIONES)} weather codes, forecast, PNT, camera interruption, online WAL backup, overwrite refusal')
if __name__=='__main__': main()

