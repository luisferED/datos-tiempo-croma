"""Generate the second-round comparison from actual saved measurements only."""
import hashlib,json,math,statistics
from pathlib import Path
root=Path(__file__).resolve().parents[1]; reports=root/'reports'
read=lambda p:json.loads((root/p).read_text(encoding='utf-8-sig'))
current=read('reports/performance-v2-15min.json')
legacy=read('reports/after-15min.json'); short=read('reports/after-60s.json'); baseline=read('tmp/profile-phase1.json')
receiver=current['receiver']; budget=1000/current['target_fps']
def window(data,begin,end,key):
 samples=[sample for sample in data if begin<=sample['seconds']<=end]
 if len(samples)<2: return None
 a,b=samples[0],samples[-1]
 return {'from_second':a['seconds'],'to_second':b['seconds'],'fps':(b[key]-a[key])/(b['seconds']-a['seconds']),'rss_median_mb':statistics.median(s['rss_mb'] for s in samples),'cpu_mean_one_core_percent':statistics.mean(s['cpu_percent_one_core'] for s in samples)}
first=window(receiver['samples'],128,384,'received'); last=window(receiver['samples'],640,896,'received')
memfirst=window(current['samples'],128,384,'produced'); memlast=window(current['samples'],640,896,'produced')
stability={'receiver_early':first,'receiver_late':last,'server_early':memfirst,'server_late':memlast,'received_fps_change_percent':(last['fps']/first['fps']-1)*100,'server_rss_median_change_mb':memlast['rss_median_mb']-memfirst['rss_median_mb']}
checks={'at_least_target_frames_minus_one':receiver['unique_frames']>=math.floor(current['duration_seconds']*current['target_fps'])-1,'gap_p99_at_most_40ms':receiver['receive_gap_ms']['p99']<=40,'max_gap_at_most_two_periods':receiver['receive_gap_ms']['max']<=2*budget,'native_1080p_no_encoder_resize':'encode.resize' not in current['profile'],'no_duplicates':receiver['duplicates']==0,'no_errors':not current['errors'] and not current['server_metrics']['errores']}
comparison={'schema':2,'first_optimization_short':short,'first_optimization_15min':legacy,'profiled_first_optimization_60s':baseline,'second_optimization_15min':current,'stability':stability,'acceptance_checks':checks,'strict_30fps_pass':all(checks.values()),'criteria_note':'Conservative local acceptance: all criteria must pass. This is not vMix/display certification. No rounded FPS, duplicate frames, reduced resolution or lower JPEG quality.','limitations':['Windows Qt offscreen, not Linux XCB/Xvfb. Docker engine unavailable.','Second run has explicit warmup, all 15 cities, synthetic full-size PNT assets and a separate process decoding every JPEG; first run used a simpler in-process reader and fixed cities.','Second renderer is bound to logical CPUs 0 and 2 on this Windows machine only; CPU IDs and affinity behavior do not transfer to Ubuntu.','CPU server and receiver are separate; original CPU included the reader but not JPEG decoding.','Latency is frame-correlated same-host monotonic timing to complete HTTP receive/decode, not monitor or vMix presentation.','Profiler stage percentiles are histogram upper bounds at 0.05 ms; stage nesting is inclusive.','Host CPU/memory and other applications were not isolated; affinity does not reserve CPUs.'], 'host_observations':read('reports/system-observations-v2.json'),'measured_source_sha256':read('reports/measured-sources-v2.json'),'post_measurement_change':'Diagnostics-only queue counter race guard. Painting, encoding, timing and all measured FPS/latency are unchanged. Raw soak replacement counter denotes attempts.','source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['app.py','runtime_support.py','jpeg_pipeline.py','pipeline_profile.py','tools/benchmark.py','tools/mjpeg_receiver.py']}}
(reports/'performance-v2-comparison.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
for source,target in [('tmp/profile-phase1.json','profile-v1-baseline-60s.json'),('tmp/profile-phase2-direct.json','profile-v2-direct-60s.json'),('tmp/profile-phase2-pillow.json','profile-v2-pillow-60s.json'),('tmp/profile-phase2-paced.json','profile-v2-pnt-60s.json'),('tmp/profile-phase2-serial-raster.json','profile-v2-rejected-serial-60s.json'),('tmp/profile-phase2-two-cpus.json','profile-v2-two-cpus-60s.json'),('tmp/profile-phase2-paced085.json','profile-v2-paced085-60s.json'),('tmp/codec-gil-profile.json','codec-comparison-v2.json')]:
 (reports/target).write_text(json.dumps(read(source),indent=2),encoding='utf-8')
profile=current['profile']
rows=[]
for label,oldkey,newkey in [('QPainter/escena','paintEvent','render.scene'),('Captura/render inclusivo','capture.grab_inclusive_paint','render.direct_rgb32'),('QPixmap→QImage (ya no se usa)','capture.pixmap_to_image',None),('Conversión para JPEG',None,'convert.rgb32_to_rgbx'),('Compresión JPEG','encode.qt_jpeg_including_internal_conversion','jpeg.pillow'),('Espera del pendiente',None,'encode.queue_wait'),('Escritura HTTP','http.write','http.write'),('Captura→publicación',None,'capture_to_publish'),('Intervalo de captura',None,'capture.interval'),('Retraso del reloj',None,'scheduler.lateness'),('Pronóstico extendido','_dibujar_extendido','_dibujar_extendido'),('Mapa','_dibujar_mapa','_dibujar_mapa'),('Fondo','_dibujar_fondo','_dibujar_fondo'),('PNT','_dibujar_pnt','_dibujar_pnt')]:
 old=baseline['profile'].get(oldkey,{}).get('wall_ms',{}) if oldkey else {}
 new=profile.get(newkey,{}).get('wall_ms',{}) if newkey else {}
 oldtext=f"{old['mean']:.3f} / {old['p95']:.3f}" if old else '—'
 newtext=' / '.join(f"{new[key]:.3f}" for key in ['mean','p50','p95','p99','max']) if new else '—'
 rows.append(f'| {label} | {oldtext} | {newtext} |')
passed=comparison['strict_30fps_pass']
status='Pasa los criterios locales declarados, sin certificar vMix ni Ubuntu.' if passed else '**No se alcanzó el criterio estricto de 30 FPS estables.** No se redondea la media a 30 ni se ocultan los saltos.'
text=f'''# Segunda optimización: resultados medidos a 1920×1080

{status}

Prueba continua: **{current['duration_seconds']} segundos completos** después de {current['warmup_seconds']} segundos de calentamiento. JPEG {current['jpeg_quality']}, render RGB32 directo, Pillow/libjpeg-turbo, retardo de envío {current['output_delay_frames']} periodos. Renderer limitado a las CPU lógicas {current['renderer_affinity']} de esta máquina Windows; no se modificó la afinidad del sistema. Qt {current['qt']}, CPU sin aceleración gráfica del renderer.

| Métrica | Primera optimización, 60 s | Primera optimización, 900 s | Segunda, 900 s |
|---|---:|---:|---:|
| FPS producidos | {short['produced_fps']:.4f} | {legacy['produced_fps']:.4f} | {current['produced_fps']:.4f} |
| FPS recibidos únicos | {short['delivered_fps']:.4f} | {legacy['delivered_fps']:.4f} | {current['delivered_fps']:.4f} |
| CPU servidor/media anterior, % de núcleo | {short['cpu_mean_one_core_percent']:.2f} | {legacy['cpu_mean_one_core_percent']:.2f} | {current['cpu_mean_one_core_percent']:.2f} |
| CPU receptor separado, % de núcleo | — | — | {current['cpu_receiver_mean_one_core_percent']:.2f} |
| CPU servidor + receptor, % de núcleo | — | — | {current['cpu_total_mean_one_core_percent']:.2f} |
| RSS máximo muestreado del servidor, MiB | {short['rss_peak_mb']:.2f} | {legacy['rss_peak_mb']:.2f} | {current['rss_peak_mb']:.2f} |
| RSS máximo muestreado del receptor, MiB | — | — | {receiver['rss_peak_mb']:.2f} |
| Carga útil JPEG, Mbps | {short['network_mbps']:.2f} | {legacy['network_mbps']:.2f} | {current['network_mbps']:.2f} |
| Intervalo recibido p95, ms | {short['delivery_gap_p95_ms']:.3f} | {legacy['delivery_gap_p95_ms']:.3f} | {receiver['receive_gap_ms']['p95']:.3f} |

100 % de CPU equivale a un núcleo. Los ensayos nuevos usan todas las ciudades, PNT con fondo 1920×1080 y marca PNG 1200×1000, y **decodifican cada JPEG en otro proceso**. La versión anterior solo leía el flujo en el proceso del renderer. Por tanto la comparación es una observación local de las configuraciones completas, no un A/B aislado de una sola variable. El receptor nuevo puede competir con el renderer por los recursos del mismo equipo; en producción vMix estará en otro equipo. La afinidad no reserva CPU en exclusiva.

## Regularidad y latencia por cuadro

| Magnitud | p50 | p95 | p99 | Máximo |
|---|---:|---:|---:|---:|
| Intervalo entre JPEG recibidos, ms | {receiver['receive_gap_ms']['p50']:.3f} | {receiver['receive_gap_ms']['p95']:.3f} | {receiver['receive_gap_ms']['p99']:.3f} | {receiver['receive_gap_ms']['max']:.3f} |
| Captura→recepción HTTP completa, ms | {receiver['capture_to_receive_ms']['p50']:.3f} | {receiver['capture_to_receive_ms']['p95']:.3f} | {receiver['capture_to_receive_ms']['p99']:.3f} | {receiver['capture_to_receive_ms']['max']:.3f} |
| Captura→JPEG decodificado, ms | {receiver['capture_to_decode_ms']['p50']:.3f} | {receiver['capture_to_decode_ms']['p95']:.3f} | {receiver['capture_to_decode_ms']['p99']:.3f} | {receiver['capture_to_decode_ms']['max']:.3f} |

Se recibieron **{receiver['unique_frames']} cuadros únicos**; duplicados: **{receiver['duplicates']}**; errores de recepción: **{len(receiver['errors'])}**; errores de codificación: **{current['server_metrics']['errores']}**. Intervalos mayores de 50 ms: {receiver['gaps_over_50ms']}; mayores de 66,67 ms: {receiver['gaps_over_66_7ms']}. Plazos de captura omitidos: {current['server_metrics']['plazos_omitidos']} (este contador del servidor incluye también el calentamiento). Intentos de sustitución del pendiente registrados: {current['server_metrics']['descartados_pendientes']}; capturas sin buffer: {current['server_metrics']['sin_buffer']}.

La latencia usa el timestamp del **mismo ID de frame**, con reloj monotónico compartido entre procesos del mismo host. No es latencia de presentación de vMix, CEF, monitor ni red remota. Los valores de latencia de la primera optimización eran estimaciones sin correlación por frame y no se comparan directamente.

## Profiling del límite técnico

Tiempos de pared en ms. Las columnas nuevas son media / p50 / p95 / p99 / máximo. Los percentiles nuevos se cuantizan hacia arriba en pasos de 0,05 ms; las medias y máximos son exactos. La captura incluye la pintura; no sumar ambas filas como si fueran tareas separadas. La CPU de hilo en Windows tiene granularidad gruesa y no representa toda la CPU de los workers raster de Qt.

| Etapa | Antes, media / p95 | Después, media / p50 / p95 / p99 / máximo |
|---|---:|---:|
'''+ '\n'.join(rows)+f'''

El pronóstico extendido registró un p99 de {profile["_dibujar_extendido"]["wall_ms"]["p99"]:.3f} ms y un máximo de {profile["_dibujar_extendido"]["wall_ms"]["max"]:.3f} ms. Son tiempos de pared: incluyen posibles desprogramaciones y no prueban que toda la demora sea cálculo puro. El presupuesto es {budget:.3f} ms por cuadro. El código ya no acumula una cola histórica ni repite frames para ocultar retrasos. Los percentiles y máximos de render/captura, la tardanza del reloj y las llegadas HTTP muestran qué parte excede ese presupuesto; el promedio de CPU no permite prometer un deadline. La medición mezcla Qt raster, planificación Windows, presión de memoria/carga externa y el receptor local. No se puede convertir este resultado en una garantía de 30 FPS en Ubuntu ni atribuir todo salto únicamente al código.

## Tendencia durante 15 minutos

Ventanas equivalentes de aproximadamente ocho ciclos: receptor {first['fps']:.3f} FPS al principio y {last['fps']:.3f} al final ({stability['received_fps_change_percent']:+.2f} %). La mediana RSS del servidor cambió {stability['server_rss_median_change_mb']:+.2f} MiB. Las ventanas recorren los mismos tipos de secuencia, con localidades que van rotando. No se demuestra ausencia de fugas más allá de esta prueba; el profiling y los buffers tienen almacenamiento acotado.

## Verificaciones y límites

- Quince pruebas unittest (ocho de pipeline y siete de seguridad/API/persistencia) aprobadas, además de secuencias y aplicación completa.
- 73 estados de imagen comparados con la primera optimización, PNT opaco/transparente y bordes fraccionales; JPEG decodificado idéntico en 15 combinaciones de escena/calidad comprobadas.
- Recorrido por 15 ciudades y 28 códigos, pronóstico, PNT, interrupción de cámara, backup WAL, reinicio y autenticación aprobados.
- Modo raster paralelo/serie produce los mismos píxeles; el modo serie se rechazó por rendimiento. El render directo RGBX se rechazó por diferencias visuales. No se aplican esos experimentos.
- Sintaxis Python y `docker compose config --quiet` comprobados. Motor Docker Linux apagado: construcción, XCB/Xvfb real, quotas CFS, señales/volúmenes Linux, Traefik y vMix pendientes.
- Base existente sin abrir/modificar; solo datos temporales. Sin push y sin despliegue.

## Recomendación de producción

Mantener el pipeline CPU optimizado y la seguridad, validar bajo Xvfb con la carga real y asignar CPU/margen de planificación según mediciones de ese servidor. No reducir calidad o tamaño para aparentar 30 FPS. Verificar afinidad permitida y throttling antes de copiar cualquier ajuste. Si el requisito sigue sin cumplirse con recursos disponibles, el render web en la máquina receptora es la alternativa arquitectónica que elimina más CPU de servidor, pero requiere reconstrucción y equivalencia visual antes de sustituir Qt. Si el control/GUI causa pausas, un renderer QImage en proceso dedicado conserva mejor estas rutinas QPainter y aísla cargas administrativas/GIL; es una propuesta pendiente de implementar y medir. H.264 puede aliviar red y aprovechar una iGPU realmente disponible; por sí solo no elimina el coste de QPainter ni garantiza calidad/latencia idénticas.

Consulte [OPTIMIZACION_30FPS.md](../OPTIMIZACION_30FPS.md) para comandos, estrategia Ubuntu, diferencias de transporte y fuentes oficiales. Después de medir se corrigió únicamente el contador diagnóstico de reemplazos para no contar como descarte una carrera donde el encoder ya consumió la imagen. El JSON conserva hashes de la fuente medida y de la fuente entregada; las rutinas de pintura, codec y temporización son iguales. Los datos completos y criterios conservadores de aceptación están en `performance-v2-comparison.json` y las pruebas en `test-results-v2.json`.
'''
(reports/'RESULTADOS_30FPS.md').write_text(text,encoding='utf-8')
print(json.dumps({'strict_30fps_pass':passed,'produced_fps':current['produced_fps'],'received_fps':current['delivered_fps'],'server_cpu':current['cpu_mean_one_core_percent'],'receive_gap_ms':receiver['receive_gap_ms'],'latency_p95':receiver['capture_to_receive_ms']['p95'],'stability':stability,'checks':checks},indent=2))
