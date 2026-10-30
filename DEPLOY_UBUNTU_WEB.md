# Despliegue en Ubuntu Server sin usar VNC

Esta versión mantiene la salida de video existente y agrega un panel de control web.

## Direcciones

- Salida limpia para vMix/navegador: `http://IP_DEL_SERVIDOR:6670/`
- Panel de control web: `http://IP_DEL_SERVIDOR:6670/control`
- La ruta anterior `/mostrar-panel` redirige al control web.
- Puerto de respaldo: `6667` (Chromium suele bloquearlo, por eso se recomienda 6670).

## Funciones disponibles desde el navegador

- Iniciar recorrido.
- Ir a anterior o siguiente.
- Seleccionar cualquier ciudad.
- Volver al mapa inicial.
- Mostrar/ocultar el pronóstico de cinco días.
- Mostrar/ocultar el escenario PNT.
- Cargar fondo PNT e imagen de marca desde el navegador.
- Actualizar la base meteorológica local.
- Ver una previsualización en vivo de la salida.

## Base de datos

La aplicación usa SQLite en `datos_tiempo.sqlite3`. Al actualizar una instalación existente:

1. Detenga el servicio.
2. Mantenga el archivo `datos_tiempo.sqlite3` de la instalación actual.
3. No copie una base vacía sobre la existente.
4. Mantenga la misma ruta de instalación para conservar las rutas PNT almacenadas.

## Dependencias

```bash
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip sqlite3 \
  xvfb xauth libgl1 libegl1 libxkbcommon-x11-0 \
  libxcb-cursor0 libxcb-xinerama0 libxcb-icccm4 \
  libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
  libxcb-randr0 libxcb-shape0 libxcb-xfixes0
```

Dentro del proyecto:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

## Servicio systemd con pantalla virtual

No hace falta mantener una sesión VNC. `Xvfb` crea la pantalla virtual requerida por PyQt.

Copie `datos-tiempo-chroma.service.example` a:

```bash
sudo cp datos-tiempo-chroma.service.example /etc/systemd/system/datos-tiempo-chroma.service
sudo nano /etc/systemd/system/datos-tiempo-chroma.service
```

Cambie usuario, ruta y contraseña. Luego:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now datos-tiempo-chroma
sudo systemctl status datos-tiempo-chroma --no-pager
```

Registros:

```bash
sudo journalctl -u datos-tiempo-chroma -f
```

Puertos:

```bash
sudo ss -lntp | grep -E ':6667|:6670'
```

## Seguridad

El panel admite autenticación básica mediante:

- `CONTROL_USER`
- `CONTROL_PASSWORD`

La salida `/` sigue visible para vMix, pero `/control` y `/api/*` exigen credenciales cuando esas variables están configuradas.

La autenticación básica no cifra la contraseña. Si se accede desde Internet, publique el panel mediante HTTPS con Nginx/Traefik y no exponga directamente el puerto 6670. En una red interna, limite el firewall a la subred autorizada.
