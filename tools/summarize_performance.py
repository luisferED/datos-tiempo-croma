"""Consolidate actual measurements, keeping unknown latency and limitations explicit."""
import json, statistics
from pathlib import Path
root=Path(__file__).resolve().parents[1]
read=lambda name:json.loads((root/'tmp'/name).read_text(encoding='utf-8'))
before=read('before.json'); after=read('after-clean.json'); soak=read('after-15min.json')

def window(samples,start,end):
 points=[p for p in samples if start<=p['seconds']<=end]
 if len(points)<2: return None
 first,last=points[0],points[-1]
 return {'seconds':last['seconds']-first['seconds'],'delivered_fps':(last['delivered']-first['delivered'])/(last['seconds']-first['seconds']),'rss_median_mb':statistics.median(p['rss_mb'] for p in points),'cpu_mean_one_core_percent':statistics.mean(p['cpu_percent_one_core'] for p in points)}
first=window(soak['samples'],128,384); last=window(soak['samples'],640,896)
stability={'first_window':first,'last_window':last,'fps_change_percent':(last['delivered_fps']/first['delivered_fps']-1)*100,'rss_median_change_mb':last['rss_median_mb']-first['rss_median_mb'],'interpretation':'Observation over this synthetic local test only; not proof of leak absence or broadcast certification.'}
comparison={'before_60s':before,'after_60s':after,'after_15min':soak,'stability':stability,'changes_percent':{key:(after[key]/before[key]-1)*100 for key in ['delivered_fps','cpu_mean_one_core_percent','delivery_gap_p95_ms','network_mbps']},'limitations':['Windows Qt offscreen, Python 3.14; container uses Python 3.12 and XCB/Xvfb, not validated.','One local synthetic MJPEG client; no vMix, Traefik or remote network measurement.','15-minute run coexisted briefly with functional and image tests; short clean run was sequential.','Latency is an estimate using latest published timestamp, not frame-correlated or end-to-end. Original latency is unavailable.','No 60 FPS test. No 30 FPS certification.','Minor HTTP limits/logging/shutdown edits occurred during the soak; render and encoder code remained the same.'], 'target_30fps_certified':False}
reports=root/'reports'; reports.mkdir(exist_ok=True)
(reports/'performance-comparison.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
for name,data in [('before-60s.json',before),('after-60s.json',after),('after-15min.json',soak)]: (reports/name).write_text(json.dumps(data,indent=2),encoding='utf-8')
text=f'''# Resultados locales medidos

Windows, Qt offscreen, 1920×1080, objetivo 30 FPS, JPEG 74, datos sintéticos, un cliente MJPEG loopback. La línea base corresponde al código entregado, que ya tenía optimizaciones previas.

| Métrica | Antes ({before['duration_seconds']:.1f} s) | Después ({after['duration_seconds']:.1f} s) | Continuo ({soak['duration_seconds']:.1f} s) |
|---|---:|---:|---:|
| FPS producidos | {before['produced_fps']:.2f} | {after['produced_fps']:.2f} | {soak['produced_fps']:.2f} |
| FPS entregados al cliente | {before['delivered_fps']:.2f} | {after['delivered_fps']:.2f} | {soak['delivered_fps']:.2f} |
| Intervalo p95 entre cuadros, ms | {before['delivery_gap_p95_ms']:.2f} | {after['delivery_gap_p95_ms']:.2f} | {soak['delivery_gap_p95_ms']:.2f} |
| CPU media, 100 % por núcleo | {before['cpu_mean_one_core_percent']:.1f} % | {after['cpu_mean_one_core_percent']:.1f} % | {soak['cpu_mean_one_core_percent']:.1f} % |
| RAM RSS máxima, MiB | {before['rss_peak_mb']:.1f} | {after['rss_peak_mb']:.1f} | {soak['rss_peak_mb']:.1f} |
| Carga útil JPEG, Mbps | {before['network_mbps']:.2f} | {after['network_mbps']:.2f} | {soak['network_mbps']:.2f} |
| Errores registrados por el cliente | {len(before['errors'])} | {len(after['errors'])} | {len(soak['errors'])} |

**No se alcanzó ni certificó una salida estable de 30 FPS.** El perfil de 60 FPS está preparado mediante Environment, pero no está validado. La estimación p95 de latencia local después es {after['capture_to_local_client_p95_ms']:.2f} ms y en la prueba continua {soak['capture_to_local_client_p95_ms']:.2f} ms. No hay valor comparable antes; no es latencia de presentación en vMix.

La comparación corta indica un cambio de FPS de {comparison['changes_percent']['delivered_fps']:+.1f} % y de CPU media de {comparison['changes_percent']['cpu_mean_one_core_percent']:+.1f} %. Son observaciones en esta máquina, sin aislamiento exclusivo de recursos. El aumento de tráfico acompaña el aumento de cuadros; no se cambió el transporte ni la calidad JPEG predeterminada.

La prueba continua ejecutó {soak['sequence_steps']} pasos de secuencia. Comparando ventanas equivalentes de unos 256 s (ocho ciclos), los FPS fueron {first['delivered_fps']:.2f} al inicio y {last['delivered_fps']:.2f} al final ({stability['fps_change_percent']:+.1f} %); la mediana RSS cambió {stability['rss_median_change_mb']:+.1f} MiB. Esto describe la tendencia observada, sin demostrar ausencia de fugas a largo plazo. Las pruebas funcionales convivieron brevemente con la medición continua; la comparación corta final fue secuencial.

## Verificaciones ejecutadas

- Seguridad/API/subidas/persistencia: siete pruebas automatizadas.
- Recorrido por 15 ciudades y 28 condiciones meteorológicas; extendido, entrada/salida PNT, inicio e interrupción de cámara.
- Respaldo online con transacciones confirmadas en WAL y rechazo de sobrescritura.
- Aplicación completa: arranque, healthcheck, JPEG autenticado 1920×1080, cierre Qt y persistencia tras reiniciar.
- Secuencia temporal existente y generación de cinco imágenes QA con base temporal.
- Igualdad de píxeles con la referencia anterior en cinco estados fijos, incluidas imágenes PNT sintéticas.
- Análisis AST: todos los métodos de dibujo se conservan, salvo reutilizar el mismo escalado PNT.
- Compilación Python y `docker compose config --quiet`.
- SQLite existente: lectura solamente, `quick_check=ok`, WAL, 15 ciudades y 3.619 registros históricos. No se cambiaron sus datos.

Los estados y tiempos de las pruebas se guardan en `test-results.json`; las series por segundo están en `performance-comparison.json` y en los JSON individuales.

## Pendiente

Construir/arrancar contenedor y validar XCB/Xvfb, señales Linux, volumen real, Traefik y autenticación del browser source en vMix. El motor Docker Linux estaba apagado. No se accedió al servidor, no hubo despliegue ni push. La latencia de extremo a extremo, los 30/60 FPS en Ubuntu y H.264/render web quedan sin medir. Consulte `../OPTIMIZACION_DOKPLOY.md` para instrucciones y diferencias de transporte.
'''
(reports/'RESULTADOS.md').write_text(text,encoding='utf-8')
print(json.dumps({'short_after_fps':after['delivered_fps'],'short_cpu':after['cpu_mean_one_core_percent'],'soak_fps':soak['delivered_fps'],'soak_cpu':soak['cpu_mean_one_core_percent'],'stability':stability},indent=2))
