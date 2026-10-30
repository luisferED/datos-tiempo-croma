# Resultados locales medidos

Windows, Qt offscreen, 1920×1080, objetivo 30 FPS, JPEG 74, datos sintéticos, un cliente MJPEG loopback. La línea base corresponde al código entregado, que ya tenía optimizaciones previas.

| Métrica | Antes (60.0 s) | Después (60.0 s) | Continuo (900.0 s) |
|---|---:|---:|---:|
| FPS producidos | 17.01 | 25.76 | 24.74 |
| FPS entregados al cliente | 17.00 | 25.75 | 24.74 |
| Intervalo p95 entre cuadros, ms | 107.20 | 81.89 | 83.47 |
| CPU media, 100 % por núcleo | 213.6 % | 141.0 % | 155.4 % |
| RAM RSS máxima, MiB | 202.3 | 204.2 | 205.5 |
| Carga útil JPEG, Mbps | 12.81 | 19.86 | 18.83 |
| Errores registrados por el cliente | 0 | 0 | 0 |

**No se alcanzó ni certificó una salida estable de 30 FPS.** El perfil de 60 FPS está preparado mediante Environment, pero no está validado. La estimación p95 de latencia local después es 68.68 ms y en la prueba continua 74.80 ms. No hay valor comparable antes; no es latencia de presentación en vMix.

La comparación corta indica un cambio de FPS de +51.5 % y de CPU media de -34.0 %. Son observaciones en esta máquina, sin aislamiento exclusivo de recursos. El aumento de tráfico acompaña el aumento de cuadros; no se cambió el transporte ni la calidad JPEG predeterminada.

La prueba continua ejecutó 226 pasos de secuencia. Comparando ventanas equivalentes de unos 256 s (ocho ciclos), los FPS fueron 24.72 al inicio y 25.53 al final (+3.3 %); la mediana RSS cambió -10.6 MiB. Esto describe la tendencia observada, sin demostrar ausencia de fugas a largo plazo. Las pruebas funcionales convivieron brevemente con la medición continua; la comparación corta final fue secuencial.

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
