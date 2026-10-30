> Segunda optimización y pruebas de 30 FPS: [OPTIMIZACION_30FPS.md](OPTIMIZACION_30FPS.md).

> Configuración actual: consulte [OPTIMIZACION_DOKPLOY.md](OPTIMIZACION_DOKPLOY.md). La salida usa un solo puerto 6670, exige autenticación y los FPS se verifican con mediciones. Las referencias inferiores a acceso abierto, 6667 y 30 FPS estables describen la instalación anterior.

# Datos del Tiempo Bolivia

Aplicación de escritorio para televisión con dos ventanas: salida al aire y panel de operador. Presenta el mapa de Bolivia, condiciones actuales, pronóstico de cinco días y un escenario virtual para PNT o menciones comerciales.

## Datos y respaldo local

- Los datos de todas las localidades se guardan en `datos_tiempo.sqlite3`.
- La aplicación consulta Open-Meteo como máximo cada 12 horas.
- Durante el recorrido al aire solo lee la base local, evitando consultas externas repetidas.
- Cada actualización se conserva también en un historial de respaldo.
- El botón **ACTUALIZAR BASE LOCAL AHORA** permite forzar una consulta manual.
- Si internet falla, continúa disponible el último dato guardado.

## Operación

1. Ejecute `instalar.bat` una sola vez.
2. Ejecute `iniciar.bat`.
3. Espere a que el panel confirme que la base local está actualizada.
4. Use **INICIAR RECORRIDO**, **ANTERIOR** o **SIGUIENTE** para controlar la salida.
5. Use **PLAY PRONÓSTICO 5 DÍAS** para activar la vista extendida a pantalla completa.

La salida se abre maximizada o a pantalla completa en el segundo monitor. `F11` alterna el modo de pantalla completa.

## Escenario virtual PNT

- **Cargar fondo PNT** selecciona la imagen que ambienta el escenario.
- **Cargar imagen de marca** selecciona el producto, logo o pieza comercial.
- **MOSTRAR / OCULTAR ESCENARIO PNT** conmuta la salida al aire.
- Las rutas seleccionadas se guardan y vuelven a cargarse al iniciar la aplicación.

Se recomiendan imágenes PNG de alta resolución, idealmente 1920×1080 para fondos y PNG transparente para productos o marcas.

## Salida para navegador

La aplicación publica automáticamente un espejo MJPEG de la salida al aire con una cadencia estable de 30 fps por defecto:

- vMix y navegadores Chromium: `http://127.0.0.1:6670/`
- salida solicitada/respaldo: `http://127.0.0.1:6667/`

También puede usarse `http://IP-DEL-EQUIPO:6670/` desde la red local si el firewall lo permite.

La señal para navegador se renderiza internamente a **1920×1080**, sin depender de la resolución del monitor del operador. Si el panel se minimiza o se cierra accidentalmente, pulse `F10` sobre la salida o visite `http://127.0.0.1:6670/mostrar-panel`.

Los navegadores Chromium bloquean normalmente el puerto 6667 por estar reservado para IRC. Ejecute `abrir_salida_web_6667.bat` para abrir Edge o Chrome con ese puerto autorizado expresamente.

## Control completo desde navegador (versión servidor)

Esta edición agrega un panel web en:

- `http://IP-DEL-SERVIDOR:6670/control`

También puede utilizarse `http://IP-DEL-SERVIDOR:6670/mostrar-panel`, que ahora redirige al panel web. El control funciona sin abrir VNC. En Ubuntu Server se recomienda ejecutar la aplicación con Xvfb y systemd; consulte `DEPLOY_UBUNTU_WEB.md`.


## Rendimiento en Ubuntu Server

La versión optimizada evita generar cuadros duplicados, usa animaciones basadas en tiempo real, comparte las capas grandes del mapa y permite ajustar FPS, calidad JPEG y velocidad mediante variables de entorno. Consulte `OPTIMIZACION.md`.
