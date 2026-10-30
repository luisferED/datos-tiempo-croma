import base64, io, json, os, sys, tempfile, unittest, urllib.request, urllib.error
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as c
from PyQt6.QtWidgets import QApplication
from PIL import Image

class SystemTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(); c.RUTA_BASE_DATOS=Path(cls.temp.name)/'data.sqlite3'; c.DIRECTORIO_CARGAS_WEB=Path(cls.temp.name)/'uploads'
  cls.qt=QApplication.instance() or QApplication([])
  c.USUARIO_CONTROL_WEB='operator'; c.CLAVE_CONTROL_WEB='secret'; c.USUARIO_VIDEO_WEB='receiver'; c.CLAVE_VIDEO_WEB='video'
  c.PUERTO_SALIDA_VMIX=0
  cls.widget=c.MapaMeteorologico(); cls.widget.resize(1920,1080); cls.widget.show()
  cls.server=c.ServidorSalidaWeb(cls.widget,0); cls.server.iniciar()
  cls.url=f'http://127.0.0.1:{cls.server.servidores[0].server_port}'
 @classmethod
 def tearDownClass(cls):
  cls.server.detener(); cls.widget.close(); cls.temp.cleanup()
 def request(self,path,auth=None,data=None,headers=None):
  h=headers or {}
  if auth: h['Authorization']='Basic '+base64.b64encode(auth.encode()).decode()
  if data is not None: h['Content-Type']='application/json'; data=json.dumps(data).encode()
  try:
   with urllib.request.urlopen(urllib.request.Request(self.url+path,data=data,headers=h),timeout=3) as response: return response.status,response.read()
  except urllib.error.HTTPError as exc: result = (exc.code,exc.read()); exc.close(); return result
 def test_protected_routes(self):
  for path in ['/control','/panel','/api/estado','/api/metricas','/restaurar-panel-local','/','/frame.jpg','/stream.mjpg']:
   self.assertEqual(self.request(path)[0],401,path)
  self.assertEqual(self.request('/api/control',data={'accion':'inicio'})[0],401)
  self.assertEqual(self.request('/control','receiver:video')[0],401)
  self.assertEqual(self.request('/control','operator:secret')[0],200)
  self.assertEqual(self.request('/','receiver:video')[0],200)
 def test_fail_closed(self):
  previous=c.CLAVE_CONTROL_WEB
  c.CLAVE_CONTROL_WEB=''
  try: self.assertFalse(c._autorizacion_control_valida(''))
  finally: c.CLAVE_CONTROL_WEB=previous
 def test_actions_and_origin(self):
  for action in ['inicio','iniciar','anterior','siguiente','pronostico','pnt','actualizar']:
   self.assertEqual(self.request('/api/control','operator:secret',{'accion':action})[0],200)
  self.assertEqual(self.request('/api/control','operator:secret',{'accion':'invalid'})[0],400)
  self.assertEqual(self.request('/api/control','operator:secret',{'accion':'inicio'}, {'Origin':'https://evil.invalid'})[0],403)
 def test_upload(self):
  with self.assertRaises(ValueError): c._guardar_imagen_web('x.png',base64.b64encode(b'not image').decode())
  image=io.BytesIO(); Image.new('RGB',(10,10),'red').save(image,format='PNG')
  data=base64.b64encode(image.getvalue()).decode()
  paths=[Path(c._guardar_imagen_web('../../image.png',data)) for _ in range(2)]
  self.assertNotEqual(paths[0],paths[1]); self.assertEqual(paths[0].parent,c.DIRECTORIO_CARGAS_WEB.resolve())
  with self.assertRaises(ValueError): c._guardar_imagen_web('x.jpg',data)
 def test_persistence(self):
  c.guardar_configuracion('test','persisted'); self.assertEqual(c.leer_configuracion('test'),'persisted')
  c.guardar_clima_local('test',{'actual':12}); self.assertEqual(c.leer_clima_local('test')['actual'],12)
  with c.database(c.RUTA_BASE_DATOS) as connection: self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0],'ok')
 def test_latest_frame(self):
  store=c.AlmacenFotogramaWeb(); store.actualizar(b'first'); store.actualizar(b'last')
  self.assertEqual(store.esperar(-1,0),(2,b'last'))
 def test_health_stale(self): self.assertEqual(self.request('/healthz')[0],503)

if __name__=='__main__': unittest.main()

