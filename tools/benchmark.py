"""Real 1080p synthetic benchmark with independent authenticated HTTP/JPEG decoding."""
import argparse,base64,json,os,statistics,subprocess,sys,tempfile,threading,time
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('OUTPUT_PROFILE','1')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as c
import psutil
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QImage,QPainter,QColor
from PyQt6.QtWidgets import QApplication
from test_broadcast_sequence import DATOS

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--seconds',type=int,default=900)
 parser.add_argument('--warmup',type=int,default=5)
 parser.add_argument('--output',default='tmp/performance-v2.json')
 parser.add_argument('--affinity',help='Optional logical CPU IDs for renderer process only, e.g. 0,2')
 parser.add_argument('--pnt-assets',action='store_true')
 args=parser.parse_args()
 if args.seconds<1: parser.error('seconds must be positive')
 original_affinity=psutil.Process().cpu_affinity() if hasattr(psutil.Process(),'cpu_affinity') else None
 if args.affinity: psutil.Process().cpu_affinity([int(value) for value in args.affinity.split(',')])
 with tempfile.TemporaryDirectory() as temp:
  c.RUTA_BASE_DATOS=Path(temp)/'test.sqlite3'; c.DIRECTORIO_CARGAS_WEB=Path(temp)/'uploads'
  c.USUARIO_CONTROL_WEB='test'; c.CLAVE_CONTROL_WEB='test-only'; c.USUARIO_VIDEO_WEB='test'; c.CLAVE_VIDEO_WEB='test-only'; c.PUERTO_SALIDA_VMIX=0
  qt=QApplication([]); c.cargar_fuentes()
  widget=c.MapaMeteorologico(); widget.resize(1920,1080); widget.show()
  if args.pnt_assets:
   background=QImage(1920,1080,QImage.Format.Format_RGB32); background.fill(QColor('#b7d9ed')); background.save(temp+'/background.jpg')
   brand=QImage(1200,1000,QImage.Format.Format_ARGB32_Premultiplied); brand.fill(QColor(0,0,0,0)); painter=QPainter(brand); painter.setBrush(QColor('#00a96b')); painter.drawRoundedRect(40,40,1120,920,100,100); painter.end(); brand.save(temp+'/brand.png')
   widget.configurar_pnt(temp+'/background.jpg',temp+'/brand.png')
  server=c.ServidorSalidaWeb(widget,0)
  original=c.ThreadingHTTPServer; c.ThreadingHTTPServer=lambda address,handler:original(('127.0.0.1',0),handler)
  server.iniciar(); port=server.servidores[0].server_port
  wall_start=time.perf_counter(); start=wall_start+args.warmup; end=start+args.seconds
  c.PERFIL.set_window(start,end)
  produced=[0]; capture_ids=[]; publish=server.almacen.actualizar
  def record(data,*metadata):
   now=time.perf_counter()
   if start<=now<end:
    produced[0]+=1
    if metadata: capture_ids.append(metadata[1])
   publish(data,*metadata)
  server.almacen.actualizar=record
  receiver_path=Path(temp)/'receiver.json'
  config={'url':f'http://127.0.0.1:{port}/stream.mjpg','authorization':'Basic '+base64.b64encode(b'test:test-only').decode(),'start':start,'end':end,'output':str(receiver_path),'affinity':original_affinity}
  child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('mjpeg_receiver.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  child.stdin.write(json.dumps(config)+'\n'); child.stdin.close()
  received=[0]; receiver_log=[]
  def monitor():
   for line in child.stdout:
    try:
     record=json.loads(line)
     if record.get('event')=='sample': received[0]=record['received']
     else: receiver_log.append(record)
    except ValueError: receiver_log.append(line.strip())
  reader=threading.Thread(target=monitor,daemon=True); reader.start()
  process=psutil.Process(); process.cpu_percent(); samples=[]; steps=[0]
  def sequence():
   n=steps[0]%8
   if n<4:
    city=list(c.CIUDADES)[((steps[0]//8)*4+n)%len(c.CIUDADES)]
    widget.mostrar_ciudad(city,dict(DATOS,codigo=[0,3,61,95][n]))
   elif n==4: widget.mostrar_extendido(True)
   elif n in (5,6): widget.alternar_pnt()
   else: widget.mostrar_inicio()
   steps[0]+=1
  seq=QTimer(); seq.setTimerType(c.Qt.TimerType.PreciseTimer); seq.timeout.connect(sequence); seq.start(4000); sequence()
  def sample():
   now=time.perf_counter(); cpu=process.cpu_percent()
   if start<=now<=end:
    samples.append({'seconds':now-start,'cpu_percent_one_core':cpu,'rss_mb':process.memory_info().rss/1048576,'produced':produced[0],'received_last_reported':received[0]})
   if len(samples) and len(samples)%60==0:
    print(json.dumps({'seconds':round(now-start),'produced':produced[0],'received_last_reported':received[0],'encoder_errors':server.metricas['errores']}),flush=True)
   if now>=end: qt.quit()
  timer=QTimer(); timer.setTimerType(c.Qt.TimerType.PreciseTimer); timer.timeout.connect(sample); timer.start(1000)
  qt.exec()
  child.wait(timeout=8); reader.join(2)
  server.detener()
  receiver=json.loads(receiver_path.read_text(encoding='utf-8'))
  cpu=statistics.mean(s['cpu_percent_one_core'] for s in samples) if samples else 0
  report={'schema':2,'renderer_affinity':psutil.Process().cpu_affinity() if original_affinity else None,'qt_gui_threadpool_disabled':bool(os.environ.get('QT_NO_GUI_THREADPOOL')),'platform':sys.platform,'python':sys.version,'qt':c.QT_VERSION_STR if hasattr(c,'QT_VERSION_STR') else __import__('PyQt6.QtCore',fromlist=['QT_VERSION_STR']).QT_VERSION_STR,'duration_seconds':args.seconds,'actual_wall_seconds':time.perf_counter()-wall_start,'warmup_seconds':args.warmup,'resolution':[1920,1080],'target_fps':c.FPS_SALIDA_WEB,'encoder':c.CODIFICADOR_JPEG,'capture_backend':'direct' if c.CAPTURA_DIRECTA else 'grab','jpeg_quality':c.CALIDAD_JPEG,'output_delay_frames':c.RETARDO_SALIDA_CUADROS,'pnt_assets':args.pnt_assets,'produced_fps':produced[0]/args.seconds,'delivered_fps':receiver['unique_frames']/args.seconds,'delivery_gap_p95_ms':receiver['receive_gap_ms']['p95'],'capture_to_local_client_p95_ms':receiver['capture_to_receive_ms']['p95'],'cpu_mean_one_core_percent':cpu,'cpu_receiver_mean_one_core_percent':receiver['cpu_mean_one_core_percent'],'cpu_total_mean_one_core_percent':cpu+receiver['cpu_mean_one_core_percent'],'rss_peak_mb':max((s['rss_mb'] for s in samples),default=0),'network_mbps':receiver['bytes']*8/args.seconds/1e6,'errors':receiver['errors'],'samples':samples,'receiver':receiver,'server_metrics':dict(server.metricas),'profile':c.PERFIL.snapshot(),'sequence_steps':steps[0],'latency_method':'Independent process, frame-correlated monotonic timestamps; every JPEG decoded at 1920x1080, no display/vMix timing','unique_produced':len(set(capture_ids))}
  output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,indent=2),encoding='utf-8')
  print(json.dumps({k:v for k,v in report.items() if k not in ('profile','samples','receiver')}),flush=True)
  if receiver['errors'] or child.returncode or server.metricas['errores']: raise SystemExit(1)
if __name__=='__main__': main()
