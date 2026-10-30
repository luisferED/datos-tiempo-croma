> Continuación actual: [OPTIMIZACION_30FPS.md](OPTIMIZACION_30FPS.md). Añade render directo, buffers reutilizables, JPEG SIMD, recepción independiente y nuevos resultados. Las cifras y detalles del pipeline que siguen describen la primera optimización.

# Optimización local y preparación para Dokploy

## Alcance y estado

Se conserva QPainter, la composición de 1920×1080, las ciudades, las fuentes, los colores, las transiciones de cámara/panel/PNT y los cinco días. No se accedió al servidor 172.20.16.195, no se hizo push y no se desplegó. Docker Compose se valida localmente; construir y ejecutar la imagen Linux requiere el motor Docker, que estaba apagado en esta sesión. No hay garantía de 30 o 60 FPS: consulte `reports/performance-comparison.json` y `reports/RESULTADOS.md`.

## Auditoría técnica

- `MapaMeteorologico.paintEvent` dibuja fondo, mapa transformado, cabecera, destino, panel actual/extendido y PNT. Las capas PNG y las fuentes ya tenían caché; las animaciones QVariantAnimation ya usan el reloj de Qt. `_pulso` obtiene fases con `perf_counter`, evitando que el movimiento se vuelva lento al perder callbacks. Estas interpolaciones se conservan.
- El hilo GUI ejecuta QPainter, `grab()` y la conversión a QImage. Eso debe permanecer en GUI; la compresión QImage/JPEG se ejecuta en un hilo dedicado. Las consultas remotas ya se ejecutaban mediante QRunnable. No se mueve QPixmap ni QWidget a hilos secundarios.
- Había repintados solicitados por cada animación y por el pulso, además del repintado de `grab()`. La salida capturada ahora solicita pintura únicamente al capturar; las ventanas locales visibles conservan su actualización. Se evita solicitar repintados en mapas ocultos. Las fases siguen avanzando con tiempo real.
- PNT escalaba la marca con interpolación suave en cada cuadro. Ahora conserva una sola versión escalada por tamaño y `cacheKey`, invalidada al cambiar imagen o resolución. El caché compartido de mapas queda limitado a 32 entradas y el de fuentes sigue limitado a 192.
- El codificador ya tenía cola de capacidad uno. Se conserva: como máximo un QImage pendiente y otro en proceso, además del último JPEG publicado. No hay cola histórica por receptor. Un receptor lento puede acumular datos en TCP o en su propio navegador; esta implementación no garantiza la latencia de vMix ni de una red remota.
- `_exigir_control` devolvía True y el verificador aceptaba credenciales ausentes. Ambos fallos se corrigen. Control y vídeo fallan cerrados si faltan sus credenciales. Control puede ver el vídeo para conservar la previsualización; las credenciales de vídeo no autorizan administración.
- Se protegen `/control`, `/panel`, `/api/estado`, `/api/control`, `/api/metricas` y la restauración del panel local. Vídeo, `/`, `/index.html`, `/frame.jpg` y `/stream.mjpg` requieren receptor u operador autorizado. `/healthz` solo devuelve disponibilidad, sin datos privados.
- Se comprueba Origin en POST, se limita el cuerpo a 40 MiB y el archivo decodificado a 20 MiB. Pillow verifica formato real/extensión y un máximo de 20 megapíxeles antes de cargarlo en Qt. Nombres aleatorios evitan colisiones y no se aceptan rutas proporcionadas por el cliente. Como máximo se procesan dos POST simultáneamente para acotar la memoria de las subidas. Las conexiones HTTP concurrentes están limitadas (24 por defecto), con timeout de socket de 10 s. No se registran credenciales, cuerpos ni parámetros de consulta.
- `with sqlite3.connect(...)` gestiona transacciones, pero no cierra por sí mismo la conexión. El nuevo context manager cierra explícitamente todas las conexiones. Se conserva WAL y el esquema existente; el timeout de escrituras queda en 3 s. Lecturas locales y pequeñas escrituras de configuración todavía ocurren en GUI y podrían causar una pausa durante contención excepcional de SQLite. Las consultas meteorológicas y sus escrituras masivas siguen fuera de GUI.
- El historial no se purga: seguirá creciendo según las actualizaciones. El operador debe vigilar disco y decidir una política de retención. Tampoco se eliminan automáticamente imágenes antiguas, para conservar archivos referidos por la configuración.
- El apagado detiene captura y HTTP, despierta streams y une el codificador; SIGTERM/SIGINT cierran Qt. La actualización masiva comprueba cancelación entre ciudades, se descartan tareas pendientes y se espera la consulta en curso. El entrypoint transmite la señal a Python antes de detener Xvfb. El cierre normal de las conexiones permite el checkpoint automático de SQLite; no se borran WAL/SHM manualmente.

## Windows

Desde PowerShell en la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
$env:CONTROL_USER='operador'
$env:CONTROL_PASSWORD=Read-Host 'Clave del operador'
$env:VIDEO_USER='receptor'
$env:VIDEO_PASSWORD=Read-Host 'Clave del receptor'
$env:WEB_ONLY='1'
python app.py
```

Abrir `http://127.0.0.1:6670/control` e ingresar como operador; para la salida limpia, `http://127.0.0.1:6670/`. En Windows el bind predeterminado es solo loopback. `WEB_ONLY=0` habilita las ventanas locales. Se conserva la base local existente cuando DATA_DIR no está configurado. `.env` no se carga automáticamente al ejecutar Python: use variables del proceso. Read-Host en este ejemplo evita escribir claves literales en el historial, aunque muestra la entrada; use un gestor de secretos si el entorno lo requiere.

El puerto 6667 anterior deja de abrirse por defecto; Chromium lo restringe. El puerto único configurable es `HTTP_PORT=6670`. Los scripts/documentos antiguos que mencionan 6667 o systemd no corresponden al despliegue nuevo.

## Pruebas reproducibles sin datos de producción

```powershell
python tools/test_system.py
python tools/test_all_sequences.py
python tools/test_application.py
python tools/run_isolated.py tools/test_broadcast_sequence.py
python tools/run_isolated.py tools/render_broadcast_qa.py
python tools/benchmark.py --seconds 900 --output tmp/performance.json
```

`test_system.py` usa una base y uploads temporales. El wrapper aísla también las pruebas antiguas. El benchmark ejecuta una sola instancia de mapa con datos sintéticos, un cliente MJPEG HTTP en loopback y secuencias de cuatro ciudades con sol/nubes/lluvia/tormenta, extendido, PNT y retorno a inicio cada 32 s. No consulta Open-Meteo ni abre la base real. Usa render Qt offscreen; no reproduce XCB/Xvfb ni vMix.

`tools/compare_visual.py` compara píxeles con `tmp/app_before.py`, una copia local ignorada por Git creada antes de cambiar el código. Es una comprobación de esta sesión, no una referencia distribuible. Compara cinco estados fijos, incluidas marca y fondo PNT sintéticos, no todos los fotogramas posibles de una animación.

CPU de psutil: 100 % equivale a un núcleo; puede superar 100 %. RAM es RSS. Tráfico es carga útil JPEG calculada, sin sobrecarga HTTP/TCP. FPS entregados son JPEG completos leídos por un cliente local, no cuadros presentados en un monitor. El intervalo p95 entre cuadros refleja irregularidad de entrega. La latencia registrada es una estimación local desde inicio de captura al cliente, usando el timestamp del último cuadro publicado en el mismo proceso; no es una medición de extremo a extremo ni tiene identificación por cuadro. El original no tenía timestamp y su latencia se informa como null. Las muestras cada segundo permiten comparar ventanas y detectar tendencias, no demostrar ausencia de fugas a largo plazo.

## Imagen y Compose

Dependencias fijadas a las versiones verificadas localmente; la disponibilidad de sus ruedas Linux debe confirmarse al construir. Base compatible Debian Bookworm con Python 3.12, Qt6/XCB, Xvfb y fuentes; no se exige que la base del contenedor coincida con Ubuntu anfitrión. Un solo proceso Python de renderizado, sin múltiples workers web. Usuario sin root, init, límites de CPU/RAM/PIDs, healthcheck y rotación de logs. Xvfb solo abre socket Unix.

```powershell
Copy-Item .env.example .env
# Editar .env y establecer las cuatro credenciales; no versionarlo.
docker compose config --quiet
# Solo cuando el motor Linux esté disponible:
docker compose build
```

Compose no publica puertos del host, no usa host networking ni nombres de contenedor globales. `expose: 6670` permite a Traefik alcanzar el servicio en `dokploy-network`; no abre 0.0.0.0:6670 en Ubuntu. Los límites iniciales de 2 CPU/2 GiB deben ajustarse con mediciones de recursos disponibles del servidor compartido, sin desplazar otras aplicaciones. El healthcheck considera saludable un render publicado hace menos de 10 s; Docker marca unhealthy, pero restart unless-stopped solo reinicia un proceso que termina, no uno unhealthy. Configure alertas/recuperación en Dokploy si necesita esa política.

## Despliegue posterior en Dokploy (no ejecutado)

1. Crear el proyecto/servicio Compose y proporcionar únicamente el código y assets; `.dockerignore` usa lista permitida para evitar copiar bases, uploads, copias de app, temporales y secretos a la imagen.
2. Establecer CONTROL_USER, CONTROL_PASSWORD, VIDEO_USER y VIDEO_PASSWORD en Environment. Usar claves largas e independientes. No colocar claves en URLs, Git ni capturas.
3. Confirmar que existe `dokploy-network` y conservar una sola réplica. No añadir ports ni cambiar a modo host.
4. En Domains de Dokploy seleccionar servicio `weather`, puerto **6670**, dominio elegido y HTTPS. Dokploy genera las etiquetas Traefik. No se inventa un dominio para la IP privada. Basic Auth requiere HTTPS fuera de loopback; el HTTP interno se reserva a la red Docker de confianza. Restringir adicionalmente la entrada a la red/receptores autorizados si corresponde.
5. Persistir **todo `/data`** en el volumen: base, WAL, SHM y `/data/uploads_web`. No montar solamente el archivo sqlite3. Un volumen vacío crea una base vacía; no migra los datos de Windows automáticamente.
6. Antes de arrancar con datos reales, generar respaldo consistente con la herramienta indicada abajo, copiarlo al volumen como `/data/datos_tiempo.sqlite3` y copiar uploads. Dar acceso al UID/GID 10001. Comprobar `PRAGMA integrity_check` en el respaldo, cantidad de ciudades y PNT antes de emitir.
7. Las rutas PNT guardadas en la configuración pueden ser absolutas de Windows. En la copia de destino deben apuntar a `/data/uploads_web/...`; puede volver a cargar las mismas imágenes desde el control para actualizar las rutas. No se modificó la base original para esta migración. Conservar el respaldo original como punto de retorno.
8. Validar arranque, apagado, reinicio, datos persistentes, healthcheck, seguridad, transición/ciudades/PNT, tipografías y vídeo en vMix; repetir 15 minutos bajo Xvfb con los recursos compartidos reales. Falta ejecutar estas validaciones en Ubuntu.

## Respaldo y SQLite

```powershell
python tools/backup_db.py datos_tiempo.sqlite3 tmp/respaldo-consistente.sqlite3
```

La herramienta usa la API online de SQLite y comprueba integridad; rechaza sobrescribir un destino. Puede respaldar una base en WAL sin omitir transacciones confirmadas. Copiar uploads por separado, preferiblemente con el operador sin subir archivos durante el respaldo; la herramienta no crea un snapshot transaccional de base e imágenes. Guardar respaldos fuera de Git y de la imagen Docker. En restauración usar una carpeta de datos detenida/vacía: no combinar un respaldo con WAL/SHM anteriores. No eliminar archivos de una instancia activa. SQLite WAL requiere almacenamiento local compartido por sus procesos, no un volumen de red entre hosts.

## Transporte y vMix

| Alternativa | Ventajas | Diferencias y validación pendiente |
|---|---|---|
| MJPEG actual | Integración simple con HTML img, cuadros independientes, transporte conservado | Mucho tráfico; JPEG ya carecía de alfa, usa la escena opaca actual. No se garantiza 30 FPS ni presentación sin saltos. |
| H.264 baja latencia | Puede reducir tráfico con codificador adecuado | H.264 convencional no conserva alfa; aparecen compresión temporal, buffering y necesidad de reproductor/protocolo. RTSP no se reproduce directamente en un img de Chromium; WebRTC requiere otra infraestructura. No implementado ni medido. |
| Render web nativo | Evita capturar y comprimir en el servidor; posible alfa CSS/canvas/WebGL | Reescribir Qt obliga a validar tipografía, píxeles, temporización y funciones; la carga pasa al receptor. No implementado para conservar el diseño. |

Para vMix Web Browser usar la página `/` de tamaño 1920×1080. Es necesario comprobar en su versión concreta cómo autenticar el browser source y si conserva credenciales; no se ha probado vMix y no se habilitó salida anónima para eludirlo. Validar también reconexión, latencia visual y acceso a través de Traefik. Un perfil de 60 FPS se configura con OUTPUT_FPS=60 y ANIMATION_FPS=60; es opcional y queda sin certificar.

## Fuentes técnicas

- [Qt: soporte de hilos y QImage](https://doc.qt.io/qt-6/threads-modules.html).
- [SQLite: WAL y ficheros asociados](https://www.sqlite.org/wal.html), [API online backup](https://www.sqlite.org/backup.html).
- [Dokploy: Domains para Compose](https://docs.dokploy.com/docs/core/docker-compose/domains).


## Medir posteriormente bajo Xvfb en Docker

El target opcional `benchmark` añade psutil y únicamente las dos herramientas necesarias. No se incluye en el target predeterminado de producción. Ejecutar estos comandos solo en un entorno Docker autorizado, sin montar `/data` de producción:

```text
docker build --target benchmark -t datos-tiempo-chroma-benchmark .
docker run --rm --cpus=2 --memory=2g -v chroma-benchmark-reports:/reports datos-tiempo-chroma-benchmark
docker run --rm --entrypoint cat -v chroma-benchmark-reports:/reports datos-tiempo-chroma-benchmark /reports/performance.json
```

El primer run realiza 900 segundos de render XCB/Xvfb con datos temporales y un cliente local. El volumen conserva el JSON. Este perfil comparte los límites iniciales de CPU/RAM de Compose, pero no sustituye la comprobación del flujo real a través de Traefik hacia vMix. El render y el cliente de prueba deben competir también con el resto de carga real; programar una ventana apropiada. Estos comandos no se ejecutaron en esta sesión porque el motor Docker Linux estaba apagado.
