# Segunda optimización: pipeline CPU de 1080p y objetivo de 30 FPS

Los resultados finales están en [reports/RESULTADOS_30FPS.md](reports/RESULTADOS_30FPS.md) y [reports/performance-v2-comparison.json](reports/performance-v2-comparison.json). No se modifica el servidor, no se hace push ni se despliega. La base existente no se abre para las pruebas: todos los renderizadores de prueba usan SQLite y archivos temporales.

## Cambios de implementación

1. **Profiling por etapa** con reloj monotónico de alta resolución y CPU del hilo: pintura total y sus capas, captura, copia/conversión, espera de codificación, JPEG, publicación y escritura HTTP. Los histogramas tienen memoria fija y percentiles con resolución de 0,05 ms; medias y máximos se acumulan sin redondear. En Windows el reloj de CPU del hilo tiene granularidad gruesa: un valor pequeño no significa que la operación no consuma CPU. Las etapas anidadas son inclusivas y no se deben sumar dos veces.
2. **Una misma función de composición** pinta tanto la ventana como los QImage de emisión. El camino de emisión ya no usa `QWidget.grab()` ni construye un QPixmap por frame. El render sigue en GUI; las operaciones de codificación y conversión están en el hilo codificador.
3. **Tres buffers RGB32 reutilizables** con propiedad exclusiva: uno puede pintarse, otro codificarse y otro quedar pendiente. Si el codificador se retrasa, se reemplaza el pendiente por el más reciente. Nunca se modifica la imagen que está leyendo el codificador. La memoria de imágenes queda acotada; los contadores `descartados_pendientes`, `sin_buffer` y `plazos_omitidos` dejan visible cualquier pérdida.
4. **Se omiten capas invisibles** únicamente cuando una capa frontal opaca cubre sus píxeles. Durante el pronóstico parcial se conserva el píxel del borde fraccional para obtener la misma mezcla. Un fondo PNT transparente mantiene el escenario inferior. Se cachea el gradiente estático, además de las fuentes, mapas y marca PNT ya cacheados.
5. **JPEG acelerado por SIMD en CPU** a través de Pillow/libjpeg-turbo. Se pinta en RGB32; después Qt reordena los canales a RGBX y Pillow comparte ese buffer, evitando una conversión completa RGB24. No se pinta directamente en RGBX: esa prueba alteró píxeles y fue rechazada. Se mantienen calidad 74, tablas y submuestreo: 4:2:0 hasta calidad 90 y 4:4:4 por encima. Las pruebas comparan tablas y píxeles JPEG decodificados con Qt en cinco calidades y tres escenas. Los archivos pueden diferir en metadatos, sin pérdida visual adicional en las muestras verificadas. `JPEG_ENCODER=qt` conserva el camino alternativo anterior.
6. **HTTP con menos operaciones por frame**, TCP_NODELAY y metadatos de ID/timestamp leídos atómicamente junto con el JPEG. Se envía cada ID una sola vez a cada cliente; no se inflan FPS repitiendo la última imagen. El envío se programa a 0,85 periodos del instante de captura (28,33 ms a 30 FPS), para evitar coincidir con el siguiente repintado. Si JPEG llega tarde se envía al estar listo y la pérdida de regularidad aparece en el reporte. `OUTPUT_DELAY_FRAMES=0` reduce esa espera, con mayor variación de entrega; aumentar el valor añade latencia y no resuelve un renderer lento.
7. **Reloj absoluto de captura**: no se genera una ráfaga para recuperar cuadros perdidos ni se añade un periodo completo arbitrario después de un retraso. Se cuenta cada plazo omitido. Cámara/panel/PNT conservan QVariantAnimation basada en tiempo; las fases de sol/nubes/lluvia se muestrean con `perf_counter` en el propio instante de captura, sin depender del número de callbacks.
8. Se conservan credenciales por Environment, autenticación cerrada por defecto, separación operador/receptor, validación de imágenes, límites HTTP/POST, WAL, cierre de conexiones y respaldo online. No se cambia el esquema SQLite ni los archivos privados existentes.

## Qué mostraron los experimentos

El profiling inicial volvió a medir unos 25,68 FPS: pintura media 21,00 ms, p95 35,72 ms; grab inclusivo 22,84 ms; QPixmap→QImage 0,003 ms y JPEG Qt 18,73 ms. El presupuesto de 30 FPS es **33,33 ms**. El cuello inicial no era convertir QPixmap a QImage, sino el coste de pintura y las colas temporales entre render, codec y HTTP.

Desactivar el threadpool interno de Qt (`QT_NO_GUI_THREADPOOL=1`) redujo CPU pero bajó a 21,90 FPS en la prueba realizada. No se activa en producción. El render directo RGBX también se rechazó por no conservar píxeles. No se ha aplicado reducción de resolución, calidad, ciudades, capas visibles ni frecuencia de animación para aparentar rendimiento.

La afinidad del proceso a dos CPU lógicas concretas mejoró el resultado en este equipo. Es una observación local, no una prueba de que cualquier par de CPU sirva. No cambia la afinidad del sistema ni de otras aplicaciones. Qt raster continúa usando paralelismo interno. Los números de CPU de Windows no deben copiarse a Ubuntu.

## Reproducir en Windows

Con las dependencias de `requirements-dev.txt` instaladas:

```powershell
python tools/validate.py
python tools/benchmark.py --seconds 900 --pnt-assets --affinity 0,2 --output tmp/prueba-30fps.json
```

`--affinity 0,2` reproduce el ensayo local y solo afecta al proceso del renderer. Omitirlo para medir la configuración normal del equipo. El receptor recupera la afinidad original para no ocupar exclusivamente esas dos CPU. El test rota por las 15 ciudades, cuatro condiciones actuales, cinco días, entrada/salida PNT y regreso a inicio. Usa un fondo de 1920×1080 y una marca PNG de 1200×1000 cuando se especifica `--pnt-assets`; no utiliza imágenes privadas ni consulta Open-Meteo.

El receptor HTTP corre en otro proceso y decodifica **cada JPEG** comprobando tamaño 1920×1080. Mide IDs únicos, repeticiones, intervalos p50/p95/p99/máximo, latencia captura→recepción y captura→fin de decodificación, CPU y RSS. No mide la presentación física del monitor ni la cola de CEF/vMix. CPU del servidor y del receptor se informan por separado, y se incluye la suma para facilitar interpretación. 100 % equivale a un núcleo. El máximo RSS está muestreado cada segundo, no es un máximo instantáneo de todas las asignaciones.

La ventana medida dura 900 segundos completos, después de cinco segundos de calentamiento explícito. El profiling se limita a esa ventana. Se conservan conteos de saltos y errores; no se excluyen frames lentos dentro de la ventana. Los nuevos resultados no son un A/B perfecto con el reporte anterior: el anterior incluía arranque, cuatro ciudades fijas y un lector en el mismo proceso que no decodificaba vídeo; el nuevo ensayo añade todas las ciudades, PNT con imágenes y decodificación independiente.

`test_pipeline.py` verifica 73 estados de imagen frente a la copia local de la primera optimización, incluyendo coordenadas de cámara, bordes fraccionales del pronóstico y PNT opaco/transparente; también prueba calidad JPEG, reemplazo del pendiente, retorno de buffers ante errores y profiling con memoria fija. Las copias históricas de referencia en `tmp/` son locales e ignoradas por Git; para ejecutar esa comparación en otra máquina hay que generar una referencia de la versión anterior con el mismo Qt/fuentes. Las pruebas de seguridad, secuencias y aplicación siguen disponibles por separado.

## Estrategia para Ubuntu sin GPU dedicada

- Mantener un renderer, `WEB_ONLY=1`, 1920×1080, OUTPUT_FPS=30, ANIMATION_FPS=30, JPEG_QUALITY=74, JPEG_ENCODER=pillow, CAPTURE_BACKEND=direct y OUTPUT_DELAY_FRAMES=0.85. Dejar OUTPUT_PROFILE=0 en emisión; activarlo para una prueba de diagnóstico.
- La imagen comprueba que Pillow dispone de libjpeg-turbo. Esa aceleración es de CPU/SIMD, no requiere GPU. Xvfb proporciona el display virtual; no convierte QPainter en un renderer GPU.
- Mantener inicialmente los límites Compose de 2 CPU y 2 GiB, **sin interpretarlos como certificación de 30 FPS**. Medir el presupuesto por frame y la cuota consumida con la carga de los demás servicios. Se necesita margen para picos; un promedio bajo de CPU no evita una pausa causada por cuota agotada o contención de memoria.
- Identificar CPU permitidas, carga por núcleo y disponibilidad real antes de configurar afinidad. `RENDER_CPU_AFFINITY` está vacío por defecto. En Linux admite una lista de IDs ya permitidos por el anfitrión; rechaza una lista fuera de esa máscara. Puede ayudar elegir CPU rápidas con poca contención o usar cpuset administrado por Docker, pero no reserva CPU en exclusiva ni desplaza otros servicios. No inventar IDs del servidor. Conservar la cuota global y comprobar `cpu.stat` (`nr_throttled`, `throttled_usec`) durante la prueba. Si la cuota produce saltos, ajustar recursos/ubicación en una ventana autorizada y medir otra vez.
- Vigilar RAM libre, swap, RSS y latencia de disco; no iniciar la emisión con presión de memoria. El test local tuvo memoria disponible baja en parte de la sesión, lo que impide atribuir todo jitter al código. Un límite de 2 GiB no es una reserva de RAM del host.
- Limitar receptores activos a lo necesario: cada cliente consume un flujo MJPEG independiente, aunque se comparte una sola compresión. Calcular ancho de banda con `network_mbps` del reporte; dos receptores aproximadamente duplican la carga útil de red. La cola propia del navegador/TCP no queda eliminada por el buffer de última imagen del servidor.
- Ejecutar el perfil Docker `benchmark` bajo XCB/Xvfb **antes** de emitir y repetirlo con carga representativa de los demás contenedores. El ejemplo de CPU affinity en Windows no reproduce cuotas CFS de Linux. Validar también apagado, reinicio, SQLite/volumen y Traefik de la instalación real. No se ha accedido a 172.20.16.195.
- En Domains de Dokploy mantener servicio `weather`, puerto interno 6670 y HTTPS; no publicar el puerto del host. Validar cómo ingresa credenciales el browser source de la versión concreta de vMix. Mantener uploads y SQLite con WAL/SHM en el mismo volumen local, sin múltiples réplicas de render.

## Ejecutar posteriormente el perfil Docker

El motor Docker Linux estaba apagado durante esta sesión; estos comandos quedan preparados, no ejecutados:

```text
docker compose config --quiet
docker build --target benchmark -t datos-tiempo-chroma-benchmark .
docker run --rm --cpus=2 --memory=2g -v chroma-benchmark-reports:/reports datos-tiempo-chroma-benchmark python /app/tools/benchmark.py --seconds 900 --pnt-assets --output /reports/performance-v2.json
docker run --rm --entrypoint cat -v chroma-benchmark-reports:/reports datos-tiempo-chroma-benchmark /reports/performance-v2.json
```

No montar el volumen de datos reales en el benchmark. La afinidad opcional debe probarse en otro ensayo con IDs válidos de ese host. La imagen normal excluye psutil y las herramientas de benchmarking; el target `benchmark` las añade. El puerto interno y los controles de seguridad se conservan.

## Transporte y hardware: decisiones

| Opción | Viabilidad | Decisión |
|---|---|---|
| MJPEG con buffers y JPEG SIMD | Conserva la página actual, un renderer y todos los controles; evita un codec temporal adicional | Implementado y medido. La salida JPEG sigue siendo opaca, como antes; se conserva la composición de PNG transparentes dentro de PNT. |
| OpenGL/QOpenGLWidget | Puede acelerar QPainter con GPU/driver compatibles; en un host sin GPU expuesta puede terminar en raster software | No activarlo a ciegas en Xvfb. Requiere mediciones y equivalencia visual; no se promete ganancia con llvmpipe. |
| H.264 por CPU, Stream/SRT de vMix | vMix documenta H.264 con RTSP/TS/SRT. Reduce potencialmente red, pero añade otro codec y buffers, y no acelera QPainter | Alternativa futura si la red es el límite. No se implementa ni se asignan cifras de FPS/latencia no medidas. Preservar calidad requiere comparación propia; SRT de vMix no conserva alfa. |
| H.264 por iGPU/Quick Sync/VAAPI | Podría ser viable sin GPU dedicada si realmente hay una iGPU accesible y drivers compatibles | No se conoce el hardware del servidor ni se expone `/dev/dri` automáticamente. Requiere validación autorizada posterior; no resuelve por sí solo el coste de pintar. |
| Render web en el receptor (Canvas/WebGL/DOM) | Traslada animación y composición a la máquina vMix y deja al servidor datos/control; evita JPEG y raster del servidor | Es la vía arquitectónica más eficiente si se exige 30 FPS con muy poca CPU de servidor. Requiere reconstruir y validar mapas, fuentes, posiciones, transparencias, PNT y sincronización. No se reemplaza el diseño actual sin esa equivalencia. |

El Web Browser de vMix usa CEF y admite HTML5/WebRTC y transparencia; eso no certifica que el flujo actual alcance 30 FPS en su versión/configuración concreta. Para el requisito estricto de emisión, revisar primero los percentiles y saltos del reporte, no solo redondear el FPS medio a 30. Si la prueba final no cumple, las medidas más eficientes son asegurar CPU y margen de planificación al pipeline CPU ya optimizado, o trasladar el render al receptor mediante una implementación web validada; cambiar a H.264 no elimina un cuello de pintura.

## Referencias oficiales consultadas

- [Qt: QPainter y rendimiento de sus formatos](https://doc.qt.io/qt-6/qpainter.html), [pintura acelerada con QOpenGLWidget](https://doc.qt.io/qt-6/qtopengl-2dpainting-example.html), [QImage y soporte de hilos](https://doc.qt.io/qt-6/threads-modules.html).
- [Qt 6.12: implementación del threadpool GUI](https://raw.githubusercontent.com/qt/qtbase/6.12/src/gui/kernel/qguiapplication.cpp). Su variable interna se evaluó, no se adopta como contrato estable.
- [Pillow: memoria compartida con Image.frombuffer](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.frombuffer).
- [Docker: límites de recursos CPU](https://docs.docker.com/engine/containers/resource_constraints/).
- [vMix Web Browser](https://www.vmix.com/help28/WebBrowser.html), [Stream/SRT](https://www.vmix.com/help28/Stream.html), [SRT y ausencia de alfa](https://www.vmix.com/help28/SRT.html).
- [FFmpeg: codificadores y aceleración](https://www.ffmpeg.org/ffmpeg-codecs.html).


## Siguiente paso si el deadline estricto sigue sin cumplirse

Primero repetir en Ubuntu sin presión de memoria y con CPU suficientes, midiendo `cpu.stat` y los percentiles. No usar prioridad de tiempo real agresiva en un servidor compartido: puede perjudicar otros servicios y no elimina el trabajo de pintar.

Si las pausas vienen del control/GUI, la evolución incremental que mejor conserva este diseño es un **proceso de render dedicado con QImage**, separado del control, SQLite y cargas de archivos. Mantendría las mismas rutinas QPainter, pero recibiría un snapshot inmutable del estado y trabajaría con reloj propio, assets QImage precargados y buffers compartidos de última imagen. Así una carga administrativa o el GIL del control no interrumpiría el reloj del renderer. No está implementado ni medido aquí; aún requiere validar la igualdad de píxeles, la vida de buffers y el reinicio supervisado. Separar procesos no reduce por sí solo el coste intrínseco de pintar ni elimina la contención del host.

Si el presupuesto de CPU disponible es demasiado pequeño para el raster de QPainter, el mayor ahorro arquitectónico lo ofrece el render web nativo en la máquina receptora. Es una migración visual completa, no un cambio de transporte de un día para otro. Se conserva esta implementación mientras no exista una alternativa visualmente equivalente y medida.

En la observación de recursos durante el test local se detectó aproximadamente 89–90 % de RAM del sistema en uso y unos 2 GiB de swap utilizado. Son observaciones puntuales (`reports/system-observations-v2.json`), no una demostración de que todos los saltos sean paging. No se modificaron afinidades de otras aplicaciones ni ajustes de energía/memoria del equipo.
