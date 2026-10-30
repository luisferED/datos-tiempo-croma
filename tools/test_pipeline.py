"""Pixel and byte equivalence, bounded buffers, timestamp pairing and time-based movement."""
import gc, importlib.util, io, os, sys, tempfile, time, unittest
from PIL import Image,ImageChops,JpegImagePlugin

from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as c
from jpeg_pipeline import encode_jpeg
from test_broadcast_sequence import DATOS
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage,QPixmap,QColor
from PyQt6.QtCore import QByteArray,QBuffer,QIODevice

class PipelineTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.qt=QApplication.instance() or QApplication([]); c.cargar_fuentes()
  cls.temp=tempfile.TemporaryDirectory(); root=Path(cls.temp.name)
  c.RUTA_BASE_DATOS=root/'test.sqlite3'
  spec=importlib.util.spec_from_file_location('phase1',Path(__file__).resolve().parents[1]/'tmp/phase1_app.py')
  cls.before=importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.before)
  cls.before.ACTIVOS=c.ACTIVOS; cls.before.RUTA_BASE_DATOS=c.RUTA_BASE_DATOS
  cls.old=cls.before.MapaMeteorologico(); cls.new=c.MapaMeteorologico()
  for widget in (cls.old,cls.new):
   widget.resize(1920,1080); widget.show(); widget.reloj_pulso.stop()
   widget.animacion_camara.stop(); widget.animacion_panel.stop(); widget.animacion_pnt.stop()
   widget.fase_pulso=13.5; widget.fase_nubes=.7
  cls.image=QImage(1920,1080,QImage.Format.Format_RGB32)
  cls.image.setDotsPerMeterX(round(cls.new.logicalDpiX()/.0254)); cls.image.setDotsPerMeterY(round(cls.new.logicalDpiY()/.0254))
  mark=QPixmap(500,400); mark.fill(QColor('#abc123')); mark.save(str(root/'mark.png'))
  for name,alpha in [('opaque.png',255),('transparent.png',90),('opaque.jpg',255)]:
   bg=QImage(640,480,QImage.Format.Format_ARGB32); bg.fill(QColor(12,90,160,alpha)); bg.save(str(root/name))
 @classmethod
 def tearDownClass(cls):
  cls.old.close(); cls.new.close(); gc.collect(); cls.temp.cleanup()
 def setUp(self):
  for widget in (self.old,self.new):
   widget.fase_pulso=13.5; widget.fase_nubes=.7
 def match(self):
  self.image.fill(QColor('magenta'))  # expose any stale/unpainted buffer pixels
  self.new.renderizar_imagen(self.image)
  original=self.old.grab().toImage()
  self.assertEqual(original,self.image)
  return original
 def test_all_city_camera_positions(self):
  for city in c.ORDEN_RECORRIDO:
   for progress in (0,.37,1):
    for widget in (self.old,self.new):
     widget.ciudad=city; widget.datos=DATOS; widget.destino_geo=c.CIUDADES[city]; widget.zoom_destino=2.05
     widget.progreso=progress; widget.panel_progreso=progress; widget.pnt_progreso=0; widget.modo_extendido=False
    self.match()
 def test_forecast_transitions(self):
  for progress in (0,.123,.37,.75,1):
   for widget in (self.old,self.new):
    widget.datos=DATOS; widget.modo_extendido=True; widget.panel_progreso=progress; widget.pnt_progreso=0
   self.match()
 def test_pnt_transparent_and_opaque(self):
  for bg in ('','opaque.png','transparent.png','opaque.jpg'):
   for widget in (self.old,self.new):
    # Configure explicitly: the UI method intentionally retains old paths for empty arguments.
    widget.pnt_fondo=QPixmap(str(Path(self.temp.name)/bg)) if bg else QPixmap()
    widget.configurar_pnt('',str(Path(self.temp.name)/'mark.png'))
    widget.pnt_fondo=QPixmap(str(Path(self.temp.name)/bg)) if bg else QPixmap()
   for progress in (0,.123,.37,.75,1):
    for widget in (self.old,self.new): widget.pnt_progreso=progress
    self.match()
 def test_jpeg_quality_and_decoded_pixels(self):
  for scene in ('actual','forecast','pnt'):
   for widget in (self.old,self.new):
    widget.modo_extendido=scene=='forecast'; widget.panel_progreso=1
    widget.pnt_progreso=1 if scene=='pnt' else 0
   image=self.match()
   for quality in (45,74,90,91,92):
    qt=Image.open(io.BytesIO(encode_jpeg(image,quality,'qt',c.PERFIL)))
    pillow=Image.open(io.BytesIO(encode_jpeg(self.image,quality,'pillow',c.PERFIL)))
    self.assertEqual(qt.quantization,pillow.quantization)
    self.assertEqual(JpegImagePlugin.get_sampling(qt),JpegImagePlugin.get_sampling(pillow))
    self.assertIsNone(ImageChops.difference(qt,pillow).getbbox(),(scene,quality))
 def test_atomic_metadata(self):
  store=c.AlmacenFotogramaWeb(); store.actualizar(b'one',1.5,17); store.actualizar(b'latest',2.5,20)
  self.assertEqual(store.esperar_detalle(-1,0),(2,b'latest',2.5,20))
  self.assertEqual(store.esperar(-1,0),(2,b'latest'))
 def test_latest_pending_replacement_and_failure_release(self):
  server=c.ServidorSalidaWeb(self.new,0); server.activo=True
  encoder=c.encode_jpeg
  try:
   for _ in range(6): server._capturar()
   server.timer.stop()
   self.assertEqual(server.cola_codificacion.qsize(),1)
   self.assertEqual(server.buffers_libres.qsize(),2)
   self.assertEqual(server.metricas['descartados_pendientes'],5)
   latest=server.cola_codificacion.get_nowait(); self.assertEqual(latest[2],6)
   server.cola_codificacion.put_nowait(latest)
   def fail(*args):
    server.activo=False
    raise RuntimeError('Expected test failure')
   c.encode_jpeg=fail
   server._codificar_fotogramas()
   self.assertEqual(server.metricas['errores'],1)
   self.assertEqual(server.buffers_libres.qsize(),3)
  finally:
   server.activo=False; server.timer.stop(); c.encode_jpeg=encoder
 def test_profiler_constant_memory(self):
  from pipeline_profile import StageProfiler
  profiler=StageProfiler(True)
  for index in range(10000): profiler.record('test',float(index%20))
  stat=profiler.snapshot()['test']['wall_ms']
  self.assertEqual(stat['count'],10000); self.assertEqual(stat['max'],19)
  self.assertAlmostEqual(stat['mean'],9.5)
  self.assertLessEqual(stat['p95'],18.05)
  self.assertEqual(len(profiler.values['test'][0].bins),20001)
 def test_elapsed_time_not_tick_count(self):
  old=c.time.perf_counter
  try:
   c.time.perf_counter=lambda: self.new._inicio_movimiento+4.0
   self.new._pulso(); phase=self.new.fase_pulso
   for _ in range(10): self.new._pulso()
   self.assertEqual(self.new.fase_pulso,phase)
   self.assertAlmostEqual(phase,4*60/c.CICLO_ICONOS_SEGUNDOS)
  finally: c.time.perf_counter=old
if __name__=='__main__': unittest.main()

