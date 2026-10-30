#!/bin/sh
set -eu
mkdir -p "${DATA_DIR:-/data}" "${UPLOAD_DIR:-/data/uploads_web}"
export DISPLAY=:99
Xvfb "$DISPLAY" -screen 0 1920x1080x24 -dpi 96 -nolisten tcp &
xvfb_pid=$!
app_pid=
cleanup() {
  if [ -n "$app_pid" ]; then
    kill -TERM "$app_pid" 2>/dev/null || true
    wait "$app_pid" 2>/dev/null || true
  fi
  kill -TERM "$xvfb_pid" 2>/dev/null || true
  wait "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
# Wait for Xvfb's Unix socket, without opening a TCP listener.
i=0
while [ ! -S /tmp/.X11-unix/X99 ]; do
  kill -0 "$xvfb_pid" 2>/dev/null || exit 1
  i=$((i + 1))
  [ "$i" -lt 100 ] || exit 1
  sleep 0.1
done
if [ "$#" -eq 0 ]; then
  set -- python /app/app.py
fi
"$@" &
app_pid=$!
status=0
wait "$app_pid" || status=$?
app_pid=
exit "$status"
