#!/usr/bin/env bash
set -euo pipefail

# Ejecutar desde la carpeta descomprimida de esta versión optimizada.
DESTINO="/opt/datos-tiempo-chroma"
SERVICIO="datos-tiempo-chroma"

if [[ $EUID -ne 0 ]]; then
  echo "Ejecute con sudo: sudo bash ACTUALIZAR_INSTALACION_EXISTENTE.sh"
  exit 1
fi

if [[ ! -d "$DESTINO" ]]; then
  echo "No existe $DESTINO. Revise la variable DESTINO dentro del script."
  exit 1
fi

# Detecta el entorno virtual existente. Algunas instalaciones usan venv y otras .venv.
if [[ -x "$DESTINO/venv/bin/python" ]]; then
  VENV="$DESTINO/venv"
elif [[ -x "$DESTINO/.venv/bin/python" ]]; then
  VENV="$DESTINO/.venv"
else
  echo "No se encontró venv ni .venv dentro de $DESTINO."
  echo "Cree uno antes de continuar: python3 -m venv $DESTINO/venv"
  exit 1
fi

systemctl stop "$SERVICIO" 2>/dev/null || true
MARCA="$(date +%Y%m%d-%H%M%S)"
RESPALDO="/var/backups/datos-tiempo-chroma/$MARCA"
mkdir -p "$RESPALDO"

if [[ -f "$DESTINO/datos_tiempo.sqlite3" ]]; then
  cp -a "$DESTINO/datos_tiempo.sqlite3" "$RESPALDO/"
fi
if [[ -d "$DESTINO/uploads_web" ]]; then
  cp -a "$DESTINO/uploads_web" "$RESPALDO/"
fi
cp -a "$DESTINO/app.py" "$RESPALDO/app.py.anterior" 2>/dev/null || true
cp -a "/etc/systemd/system/${SERVICIO}.service" "$RESPALDO/" 2>/dev/null || true

rsync -a --delete \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude 'datos_tiempo.sqlite3' \
  --exclude 'datos_tiempo.sqlite3-wal' \
  --exclude 'datos_tiempo.sqlite3-shm' \
  --exclude 'uploads_web/' \
  ./ "$DESTINO/"

chown -R luis:luis "$DESTINO"
"$VENV/bin/pip" install -r "$DESTINO/requirements.txt"

# Perfil recomendado para la VM. Se guarda como drop-in para no reemplazar
# credenciales ni otros ajustes del servicio principal.
mkdir -p "/etc/systemd/system/${SERVICIO}.service.d"
cat > "/etc/systemd/system/${SERVICIO}.service.d/optimizacion.conf" <<'DROPIN'
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
DROPIN

systemctl daemon-reload
systemctl start "$SERVICIO"
systemctl status "$SERVICIO" --no-pager

echo
echo "Respaldo creado en: $RESPALDO"
echo "Control web: http://IP_DEL_SERVIDOR:6670/control"
echo "Salida:      http://IP_DEL_SERVIDOR:6670/"
