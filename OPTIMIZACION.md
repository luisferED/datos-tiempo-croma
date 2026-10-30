# Versión optimizada para Ubuntu Server

Esta edición está orientada a una VM Ubuntu Server con Xvfb y control web.

## Cambios principales

- La salida MJPEG baja de 59,94 fps a 30 fps estables por defecto.
- El codificador no captura cuadros si el cuadro anterior todavía está en proceso.
- Cuando nadie está viendo `/stream.mjpg`, la captura baja a 2 fps para ahorrar CPU.
- Las animaciones usan tiempo real; si la CPU se ocupa, no quedan en cámara lenta.
- El viaje entre ciudades baja de 3 segundos a 1,6 segundos.
- El panel y PNT cambian en aproximadamente 0,52 segundos.
- El sol, la lluvia y las nubes se actualizan a 30 fps y con un ciclo más rápido.
- Las imágenes grandes del mapa se cargan una sola vez y se comparten entre widgets.
- Las capas del mapa se reducen en memoria a una resolución adecuada para 1080p.
- En servidor se usa un solo render 1920x1080 (`WEB_ONLY=1`).

## Actualizar la instalación

Desde la carpeta descomprimida:

```bash
sudo bash ACTUALIZAR_INSTALACION_EXISTENTE.sh
```

El script conserva:

- `datos_tiempo.sqlite3`
- `uploads_web/`
- `venv/` o `.venv/`
- credenciales y ajustes existentes del servicio

Además crea un respaldo en `/var/backups/datos-tiempo-chroma/FECHA-HORA/`.

## Ajustes disponibles

Se guardan en:

```text
/etc/systemd/system/datos-tiempo-chroma.service.d/optimizacion.conf
```

Valores recomendados:

```ini
[Service]
Environment=WEB_ONLY=1
Environment=OUTPUT_FPS=30
Environment=IDLE_OUTPUT_FPS=2
Environment=ANIMATION_FPS=30
Environment=JPEG_QUALITY=74
Environment=CAMERA_DURATION_MS=1600
Environment=PANEL_DURATION_MS=520
Environment=PNT_DURATION_MS=520
Environment=ICON_CYCLE_SECONDS=1.6
Environment=MAP_MAX_HEIGHT=1800
```

Después de cambiar un valor:

```bash
sudo systemctl daemon-reload
sudo systemctl restart datos-tiempo-chroma
```

## Perfiles rápidos

### Más fluidez, mayor CPU

```ini
Environment=OUTPUT_FPS=40
Environment=ANIMATION_FPS=40
Environment=JPEG_QUALITY=74
```

### Menor consumo

```ini
Environment=OUTPUT_FPS=25
Environment=ANIMATION_FPS=25
Environment=JPEG_QUALITY=68
Environment=MAP_MAX_HEIGHT=1500
```
