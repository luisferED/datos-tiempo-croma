# Segunda optimización: resultados medidos a 1920×1080

**No se alcanzó el criterio estricto de 30 FPS estables.** No se redondea la media a 30 ni se ocultan los saltos.

Prueba continua: **900 segundos completos** después de 5 segundos de calentamiento. JPEG 74, render RGB32 directo, Pillow/libjpeg-turbo, retardo de envío 0.85 periodos. Renderer limitado a las CPU lógicas [0, 2] de esta máquina Windows; no se modificó la afinidad del sistema. Qt 6.12.0, CPU sin aceleración gráfica del renderer.

| Métrica | Primera optimización, 60 s | Primera optimización, 900 s | Segunda, 900 s |
|---|---:|---:|---:|
| FPS producidos | 25.7649 | 24.7428 | 29.5378 |
| FPS recibidos únicos | 25.7482 | 24.7417 | 29.5344 |
| CPU servidor/media anterior, % de núcleo | 141.03 | 155.35 | 65.96 |
| CPU receptor separado, % de núcleo | — | — | 29.60 |
| CPU servidor + receptor, % de núcleo | — | — | 95.57 |
| RSS máximo muestreado del servidor, MiB | 204.17 | 205.50 | 264.61 |
| RSS máximo muestreado del receptor, MiB | — | — | 44.55 |
| Carga útil JPEG, Mbps | 19.86 | 18.83 | 22.44 |
| Intervalo recibido p95, ms | 81.891 | 83.474 | 35.345 |

100 % de CPU equivale a un núcleo. Los ensayos nuevos usan todas las ciudades, PNT con fondo 1920×1080 y marca PNG 1200×1000, y **decodifican cada JPEG en otro proceso**. La versión anterior solo leía el flujo en el proceso del renderer. Por tanto la comparación es una observación local de las configuraciones completas, no un A/B aislado de una sola variable. El receptor nuevo puede competir con el renderer por los recursos del mismo equipo; en producción vMix estará en otro equipo. La afinidad no reserva CPU en exclusiva.

## Regularidad y latencia por cuadro

| Magnitud | p50 | p95 | p99 | Máximo |
|---|---:|---:|---:|---:|
| Intervalo entre JPEG recibidos, ms | 33.355 | 35.345 | 56.202 | 291.239 |
| Captura→recepción HTTP completa, ms | 29.066 | 30.398 | 53.018 | 285.546 |
| Captura→JPEG decodificado, ms | 39.781 | 44.432 | 64.674 | 319.575 |

Se recibieron **26581 cuadros únicos**; duplicados: **0**; errores de recepción: **0**; errores de codificación: **0**. Intervalos mayores de 50 ms: 454; mayores de 66,67 ms: 131. Plazos de captura omitidos: 430 (este contador del servidor incluye también el calentamiento). Intentos de sustitución del pendiente registrados: 1; capturas sin buffer: 0.

La latencia usa el timestamp del **mismo ID de frame**, con reloj monotónico compartido entre procesos del mismo host. No es latencia de presentación de vMix, CEF, monitor ni red remota. Los valores de latencia de la primera optimización eran estimaciones sin correlación por frame y no se comparan directamente.

## Profiling del límite técnico

Tiempos de pared en ms. Las columnas nuevas son media / p50 / p95 / p99 / máximo. Los percentiles nuevos se cuantizan hacia arriba en pasos de 0,05 ms; las medias y máximos son exactos. La captura incluye la pintura; no sumar ambas filas como si fueran tareas separadas. La CPU de hilo en Windows tiene granularidad gruesa y no representa toda la CPU de los workers raster de Qt.

| Etapa | Antes, media / p95 | Después, media / p50 / p95 / p99 / máximo |
|---|---:|---:|
| QPainter/escena | 20.999 / 35.722 | 12.525 / 12.000 / 20.100 / 33.200 / 208.828 |
| Captura/render inclusivo | 22.843 / 37.434 | 12.557 / 12.050 / 20.150 / 33.200 / 208.957 |
| QPixmap→QImage (ya no se usa) | 0.003 / 0.004 | — |
| Conversión para JPEG | — | 1.707 / 1.600 / 2.650 / 4.150 / 30.773 |
| Compresión JPEG | 18.731 / 26.706 | 3.924 / 3.650 / 5.550 / 8.750 / 56.196 |
| Espera del pendiente | — | 0.081 / 0.100 / 0.150 / 0.250 / 4.505 |
| Escritura HTTP | 2.715 / 14.250 | 0.294 / 0.200 / 0.400 / 5.400 / 36.429 |
| Captura→publicación | — | 18.951 / 17.950 / 28.800 / 45.550 / 272.274 |
| Intervalo de captura | — | 33.854 / 33.400 / 34.950 / 61.600 / 262.027 |
| Retraso del reloj | — | 0.833 / 0.700 / 1.800 / 5.150 / 38.858 |
| Pronóstico extendido | 14.578 / 18.695 | 13.752 / 12.900 / 21.000 / 38.050 / 208.716 |
| Mapa | 10.104 / 12.942 | 5.574 / 5.250 / 10.000 / 16.250 / 68.033 |
| Fondo | 4.603 / 6.041 | 5.026 / 4.750 / 7.300 / 12.550 / 60.650 |
| PNT | 2.791 / 3.381 | 5.694 / 5.200 / 8.600 / 16.700 / 106.419 |

El pronóstico extendido registró un p99 de 38.050 ms y un máximo de 208.716 ms. Son tiempos de pared: incluyen posibles desprogramaciones y no prueban que toda la demora sea cálculo puro. El presupuesto es 33.333 ms por cuadro. El código ya no acumula una cola histórica ni repite frames para ocultar retrasos. Los percentiles y máximos de render/captura, la tardanza del reloj y las llegadas HTTP muestran qué parte excede ese presupuesto; el promedio de CPU no permite prometer un deadline. La medición mezcla Qt raster, planificación Windows, presión de memoria/carga externa y el receptor local. No se puede convertir este resultado en una garantía de 30 FPS en Ubuntu ni atribuir todo salto únicamente al código.

## Tendencia durante 15 minutos

Ventanas equivalentes de aproximadamente ocho ciclos: receptor 29.494 FPS al principio y 29.835 al final (+1.16 %). La mediana RSS del servidor cambió -36.04 MiB. Las ventanas recorren los mismos tipos de secuencia, con localidades que van rotando. No se demuestra ausencia de fugas más allá de esta prueba; el profiling y los buffers tienen almacenamiento acotado.

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
