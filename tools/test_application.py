"""Black-box startup, 1080p HTTP output, normal Qt shutdown and restart persistence."""
import io, json, os, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def child():
 import app as c
 from test_broadcast_sequence import DATOS
 from PyQt6.QtCore import QTimer
 c.inicializar_base_datos()
 for city in c.CIUDADES: c.guardar_clima_local(city,DATOS)
 marker=c.leer_configuracion('restart_probe')
 c.guardar_configuracion('restart_probe','persisted')
 original=c.QApplication
 class TimedApplication(original):
  def exec(self):
   QTimer.singleShot(6000,self.quit)
   return super().exec()
 c.QApplication=TimedApplication
 result=c.main()
 assert not c.ESTADO_CONTROL_WEB.obtener().get('actualizando')
 print(json.dumps({'exit':result,'previous_marker':marker}),flush=True)
 raise SystemExit(result)

def main():
 from PIL import Image
 with tempfile.TemporaryDirectory() as temp:
  env=dict(os.environ,DATA_DIR=temp,QT_QPA_PLATFORM='offscreen',WEB_ONLY='1',CONTROL_USER='test',CONTROL_PASSWORD='secret',VIDEO_USER='video',VIDEO_PASSWORD='secret',HTTP_BIND='127.0.0.1')
  for iteration in range(2):
   with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
   env['HTTP_PORT']=str(port)
   process=subprocess.Popen([sys.executable,__file__,'--child'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   try:
    ready=False
    for _ in range(80):
     try:
      with urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz',timeout=.5) as response: ready=response.status==200
      if ready: break
     except OSError: time.sleep(.05)
    assert ready,'Renderer did not become healthy'
    req=urllib.request.Request(f'http://127.0.0.1:{port}/frame.jpg',headers={'Authorization':'Basic dmlkZW86c2VjcmV0'})
    with urllib.request.urlopen(req,timeout=3) as response: data=response.read()
    with Image.open(io.BytesIO(data)) as image: assert image.size==(1920,1080),image.size
    stdout,stderr=process.communicate(timeout=15)
    assert process.returncode==0,(stdout,stderr)
    record=json.loads(stdout.strip().splitlines()[-1])
    if iteration: assert record['previous_marker']=='persisted',record
   finally:
    if process.poll() is None: process.kill(); process.communicate()
 print('PASS: full app startup, health, authenticated 1920x1080 JPEG, Qt shutdown, restart persistence')
if __name__=='__main__':
 if '--child' in sys.argv: child()
 else: main()
