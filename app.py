import base64
from pipeline_profile import StageProfiler
from jpeg_pipeline import encode_jpeg
import signal
import uuid
from collections import OrderedDict
from runtime_support import database, BoundedHTTPServer as ThreadingHTTPServer, validate_image, configure_render_affinity
import hmac
import json
import math
import os
import re
import queue
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from functools import lru_cache
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from PyQt6.QtCore import (
    QAbstractAnimation,
    QByteArray,
    QBuffer,
    QEasingCurve,
    QIODevice,
    QObject,
    QPointF,
    QRunnable,
    QRectF,
    Qt,
    QThreadPool,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QTransform,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


RAIZ = Path(__file__).resolve().parent
ACTIVOS = RAIZ / "assets"
DIRECTORIO_DATOS = Path(os.environ.get("DATA_DIR", str(RAIZ)))
RUTA_BASE_DATOS = DIRECTORIO_DATOS / "datos_tiempo.sqlite3"
INTERVALO_ACTUALIZACION = 12 * 60 * 60
PUERTO_SALIDA_WEB = int(os.environ.get("HTTP_PORT", "6670"))
PUERTO_SALIDA_VMIX = PUERTO_SALIDA_WEB
def _entorno_float(nombre, predeterminado, minimo, maximo):
    try:
        valor = float(os.environ.get(nombre, predeterminado))
    except (TypeError, ValueError):
        valor = float(predeterminado)
    return max(float(minimo), min(float(maximo), valor))


def _entorno_int(nombre, predeterminado, minimo, maximo):
    try:
        valor = int(os.environ.get(nombre, predeterminado))
    except (TypeError, ValueError):
        valor = int(predeterminado)
    return max(int(minimo), min(int(maximo), valor))


def _entorno_bool(nombre, predeterminado=False):
    valor = os.environ.get(nombre)
    if valor is None:
        return bool(predeterminado)
    return valor.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


# Perfil equilibrado para Ubuntu Server/Xvfb. Es preferible una salida estable a
# 30 fps que intentar 59,94 fps y saturar un núcleo con JPEG duplicados.
FPS_SALIDA_WEB = _entorno_float("OUTPUT_FPS", 30.0, 10.0, 60.0)
FPS_SALIDA_REPOSO = _entorno_float("IDLE_OUTPUT_FPS", 2.0, 0.5, 10.0)
FPS_ANIMACION = _entorno_float("ANIMATION_FPS", 30.0, 20.0, 60.0)
CALIDAD_JPEG = _entorno_int("JPEG_QUALITY", 74, 45, 92)
DURACION_CAMARA_MS = _entorno_int("CAMERA_DURATION_MS", 1600, 500, 5000)
DURACION_PANEL_MS = _entorno_int("PANEL_DURATION_MS", 520, 200, 2000)
DURACION_PNT_MS = _entorno_int("PNT_DURATION_MS", 520, 200, 2000)
CICLO_ICONOS_SEGUNDOS = _entorno_float("ICON_CYCLE_SECONDS", 1.6, 0.6, 5.0)
ALTO_MAXIMO_MAPA = _entorno_int("MAP_MAX_HEIGHT", 1800, 900, 2937)
MODO_SOLO_WEB = _entorno_bool("WEB_ONLY", True)
PERFIL = StageProfiler(_entorno_bool("OUTPUT_PROFILE", False))
RETARDO_SALIDA_CUADROS = _entorno_float("OUTPUT_DELAY_FRAMES", 0.85, 0.0, 2.0)
CODIFICADOR_JPEG = os.environ.get("JPEG_ENCODER", "pillow").lower()
if CODIFICADOR_JPEG not in {"pillow", "qt"}:
    raise ValueError("JPEG_ENCODER must be pillow or qt")
CAPTURA_DIRECTA = os.environ.get("CAPTURE_BACKEND", "direct").lower() == "direct"
ANCHO_SALIDA_WEB = _entorno_int("OUTPUT_WIDTH", 1920, 960, 3840)
ALTO_SALIDA_WEB = _entorno_int("OUTPUT_HEIGHT", 1080, 540, 2160)
DIRECTORIO_CARGAS_WEB = Path(os.environ.get("UPLOAD_DIR", str(DIRECTORIO_DATOS / "uploads_web")))
MAX_CARGA_WEB = 20 * 1024 * 1024
USUARIO_CONTROL_WEB = os.environ.get("CONTROL_USER", "").strip()
CLAVE_CONTROL_WEB = os.environ.get("CONTROL_PASSWORD", "")
USUARIO_VIDEO_WEB = os.environ.get("VIDEO_USER", "").strip()
CLAVE_VIDEO_WEB = os.environ.get("VIDEO_PASSWORD", "")


CIUDADES = {
    "Santa Cruz de la Sierra": (-17.78, -63.18),
    "La Paz": (-16.50, -68.15),
    "Sucre": (-19.03, -65.26),
    "Cochabamba": (-17.38, -66.15),
    "Oruro": (-17.98, -67.15),
    "Potosí": (-19.58, -65.75),
    "Tarija": (-21.53, -64.73),
    "Trinidad": (-14.83, -64.90),
    "Cobija": (-11.02, -68.74),
    "Samaipata": (-18.18, -63.87),
    "Vallegrande": (-18.48, -64.10),
    "Mairana": (-18.11, -63.95),
    "Montero": (-17.34, -63.25),
    "Roboré": (-18.33, -59.75),
    "San Ignacio de Velasco": (-16.37, -60.95),
}

ORDEN_RECORRIDO = [
    "La Paz",
    "Cochabamba",
    "Santa Cruz de la Sierra",
    "Samaipata",
    "Vallegrande",
    "Mairana",
    "Montero",
    "Roboré",
    "San Ignacio de Velasco",
    "Sucre",
    "Tarija",
    "Potosí",
    "Oruro",
    "Trinidad",
    "Cobija",
]

DEPARTAMENTO_CIUDAD = {
    "La Paz": "la_paz",
    "Cochabamba": "cochabamba",
    "Santa Cruz de la Sierra": "santa_cruz",
    "Samaipata": "santa_cruz",
    "Vallegrande": "santa_cruz",
    "Mairana": "santa_cruz",
    "Montero": "santa_cruz",
    "Roboré": "santa_cruz",
    "San Ignacio de Velasco": "santa_cruz",
    "Sucre": "chuquisaca",
    "Tarija": "tarija",
    "Potosí": "potosi",
    "Oruro": "oruro",
    "Trinidad": "beni",
    "Cobija": "pando",
}

# Códigos WMO usados por Open-Meteo: (icono, descripción).
CONDICIONES = {
    0: ("☀️", "Despejado"),
    1: ("🌤️", "Mayormente despejado"),
    2: ("⛅", "Parcialmente nublado"),
    3: ("☁️", "Nublado"),
    45: ("🌫️", "Niebla"),
    48: ("🌫️", "Niebla con escarcha"),
    51: ("🌦️", "Llovizna ligera"),
    53: ("🌦️", "Llovizna"),
    55: ("🌧️", "Llovizna intensa"),
    56: ("🌧️", "Llovizna helada ligera"),
    57: ("🌧️", "Llovizna helada intensa"),
    61: ("🌦️", "Lluvia ligera"),
    63: ("🌧️", "Lluvia"),
    65: ("🌧️", "Lluvia intensa"),
    66: ("🌧️", "Lluvia helada ligera"),
    67: ("🌧️", "Lluvia helada intensa"),
    71: ("🌨️", "Nevada ligera"),
    73: ("🌨️", "Nevada"),
    75: ("❄️", "Nevada intensa"),
    77: ("❄️", "Granos de nieve"),
    80: ("🌦️", "Chubascos ligeros"),
    81: ("🌧️", "Chubascos"),
    82: ("🌧️", "Chubascos intensos"),
    85: ("🌨️", "Chubascos de nieve"),
    86: ("🌨️", "Chubascos de nieve intensos"),
    95: ("⛈️", "Tormenta"),
    96: ("⛈️", "Tormenta con granizo"),
    99: ("⛈️", "Tormenta fuerte con granizo"),
}


def inicializar_base_datos():
    RUTA_BASE_DATOS.parent.mkdir(parents=True, exist_ok=True)
    with database(RUTA_BASE_DATOS) as conexion:
        conexion.execute("PRAGMA journal_mode=WAL")
        conexion.executescript(
            """
            CREATE TABLE IF NOT EXISTS clima_cache (
                ciudad TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                actualizado_en REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS clima_historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ciudad TEXT NOT NULL,
                payload TEXT NOT NULL,
                actualizado_en REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_historial_ciudad_fecha
                ON clima_historial(ciudad, actualizado_en DESC);
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            );
            """
        )


def guardar_clima_local(ciudad, datos, actualizado_en=None):
    marca = float(actualizado_en or time.time())
    payload = json.dumps(datos, ensure_ascii=False)
    with database(RUTA_BASE_DATOS, timeout=3) as conexion:
        conexion.execute(
            "INSERT INTO clima_cache(ciudad,payload,actualizado_en) VALUES(?,?,?) "
            "ON CONFLICT(ciudad) DO UPDATE SET payload=excluded.payload, actualizado_en=excluded.actualizado_en",
            (ciudad, payload, marca),
        )
        conexion.execute(
            "INSERT INTO clima_historial(ciudad,payload,actualizado_en) VALUES(?,?,?)",
            (ciudad, payload, marca),
        )


def leer_clima_local(ciudad):
    with database(RUTA_BASE_DATOS) as conexion:
        fila = conexion.execute(
            "SELECT payload,actualizado_en FROM clima_cache WHERE ciudad=?", (ciudad,)
        ).fetchone()
    if not fila:
        return None
    datos = json.loads(fila[0])
    datos["_actualizado_en"] = float(fila[1])
    return datos


def cache_necesita_actualizacion():
    with database(RUTA_BASE_DATOS) as conexion:
        fila = conexion.execute(
            "SELECT COUNT(*), MIN(actualizado_en) FROM clima_cache"
        ).fetchone()
    cantidad, mas_antiguo = fila
    return cantidad < len(CIUDADES) or not mas_antiguo or time.time() - mas_antiguo >= INTERVALO_ACTUALIZACION


def guardar_configuracion(clave, valor):
    with database(RUTA_BASE_DATOS) as conexion:
        conexion.execute(
            "INSERT INTO configuracion(clave,valor) VALUES(?,?) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
            (clave, valor),
        )


def leer_configuracion(clave, predeterminado=""):
    with database(RUTA_BASE_DATOS) as conexion:
        fila = conexion.execute(
            "SELECT valor FROM configuracion WHERE clave=?", (clave,)
        ).fetchone()
    return fila[0] if fila else predeterminado


def consultar_clima_remoto(ciudad, latitud, longitud):
    parametros = urllib.parse.urlencode(
        {
            "latitude": latitud,
            "longitude": longitud,
            "current": "temperature_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "timezone": "America/La_Paz",
            "forecast_days": 5,
        }
    )
    solicitud = urllib.request.Request(
        f"https://api.open-meteo.com/v1/forecast?{parametros}",
        headers={"User-Agent": "ElDeberTiempo/2.0"},
    )
    with urllib.request.urlopen(solicitud, timeout=12) as respuesta:
        contenido = json.load(respuesta)
    diario = contenido["daily"]
    actual = contenido["current"]
    codigo = int(actual.get("weather_code", diario["weather_code"][0]))
    icono, descripcion = CONDICIONES.get(codigo, ("🌡️", "Condición variable"))
    pronostico = []
    for i, fecha in enumerate(diario["time"]):
        codigo_dia = int(diario["weather_code"][i])
        icono_dia, descripcion_dia = CONDICIONES.get(codigo_dia, ("🌡️", "Condición variable"))
        pronostico.append(
            {
                "fecha": fecha,
                "codigo": codigo_dia,
                "icono": icono_dia,
                "descripcion": descripcion_dia,
                "min": round(float(diario["temperature_2m_min"][i]), 1),
                "max": round(float(diario["temperature_2m_max"][i]), 1),
            }
        )
    return {
        "icono": icono,
        "codigo": codigo,
        "descripcion": descripcion,
        "actual": round(float(actual["temperature_2m"]), 1),
        "min": round(float(diario["temperature_2m_min"][0]), 1),
        "max": round(float(diario["temperature_2m_max"][0]), 1),
        "hora": datetime.now().strftime("%H:%M"),
        "pronostico": pronostico,
    }


class Comunicador(QObject):
    cambiar_ciudad = pyqtSignal(str, dict)
    control_web = pyqtSignal(str, object)
    mostrar_inicio = pyqtSignal()
    mostrar_panel = pyqtSignal()
    alternar_vista = pyqtSignal()
    alternar_pantalla = pyqtSignal()
    configurar_pnt = pyqtSignal(str, str)
    alternar_pnt = pyqtSignal()


comunicador = Comunicador()


class EstadoControlWeb:
    # Estado pequeño y seguro para mostrarlo desde los hilos HTTP.

    def __init__(self):
        self._bloqueo = threading.Lock()
        self._datos = {
            "ciudad": "",
            "indice": -1,
            "estado": "Aplicación iniciando…",
            "pronostico_extendido": False,
            "pnt_visible": False,
            "actualizando": False,
            "fondo_pnt": "",
            "marca_pnt": "",
        }

    def actualizar(self, **cambios):
        with self._bloqueo:
            self._datos.update(cambios)

    def obtener(self):
        with self._bloqueo:
            datos = dict(self._datos)
        datos["ciudades"] = list(ORDEN_RECORRIDO)
        datos["hora_servidor"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        return datos


ESTADO_CONTROL_WEB = EstadoControlWeb()
DETENER_TRABAJADORES = threading.Event()


def _autorizacion_control_valida(cabecera):
    if not USUARIO_CONTROL_WEB or not CLAVE_CONTROL_WEB:
        return False
    esperado = "Basic " + base64.b64encode(
        f"{USUARIO_CONTROL_WEB}:{CLAVE_CONTROL_WEB}".encode("utf-8")
    ).decode("ascii")
    return hmac.compare_digest((cabecera or "").encode(), esperado.encode())


def _guardar_imagen_web(nombre, contenido_base64):
    nombre = Path(nombre or "imagen.png").name
    extension = Path(nombre).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        raise ValueError("Formato no permitido. Use PNG, JPG, WEBP o BMP.")
    if "," in contenido_base64:
        contenido_base64 = contenido_base64.split(",", 1)[1]
    try:
        datos = base64.b64decode(contenido_base64, validate=True)
    except Exception as exc:
        raise ValueError("El archivo recibido no es una imagen válida.") from exc
    if not datos or len(datos) > MAX_CARGA_WEB:
        raise ValueError("La imagen está vacía o supera 20 MB.")
    validate_image(datos, extension)
    nombre_seguro = re.sub(r"[^A-Za-z0-9._-]+", "_", nombre)
    DIRECTORIO_CARGAS_WEB.mkdir(parents=True, exist_ok=True)
    destino = DIRECTORIO_CARGAS_WEB / f"{uuid.uuid4().hex}_{nombre_seguro}"
    destino.write_bytes(datos)
    return str(destino.resolve())


def pagina_control_web():
    autenticacion = "protegido con usuario y contraseña" if USUARIO_CONTROL_WEB else "sin autenticación"
    return f'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Control web · Datos del Tiempo</title>
<style>
:root{{--fondo:#071522;--panel:#0d2235;--panel2:#112c43;--texto:#eef8ff;--muted:#9bb7c9;--verde:#00a96b;--violeta:#785cff;--celeste:#00bddb;--amaranto:#ff3d71;--borde:#24445a}}
*{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(145deg,#06111c,#102a40);color:var(--texto);font-family:Arial,sans-serif;min-height:100vh}}
header{{display:flex;align-items:center;justify-content:space-between;padding:16px 22px;background:#071522dd;border-bottom:1px solid var(--borde);position:sticky;top:0;z-index:10}}
h1{{font-size:21px;margin:0}} .badge{{font-size:12px;color:var(--muted);border:1px solid var(--borde);padding:7px 10px;border-radius:20px}}
main{{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(330px,.7fr);gap:18px;padding:18px;max-width:1700px;margin:auto}}
.card{{background:#0d2235e8;border:1px solid var(--borde);border-radius:18px;box-shadow:0 18px 50px #0006;overflow:hidden}}
.preview{{aspect-ratio:16/9;background:#000;position:relative}} .preview img{{width:100%;height:100%;object-fit:contain;display:block}}
.preview .label{{position:absolute;left:12px;top:12px;background:#000b;padding:7px 10px;border-radius:8px;font-size:12px}}
.content{{padding:16px}} .state{{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;background:#071522;padding:12px;border-radius:12px;margin-bottom:14px}}
.state strong{{font-size:18px}} .state span{{color:var(--muted);font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}} button,select,.upload{{width:100%;border:1px solid var(--borde);border-radius:11px;padding:12px;background:#132f47;color:var(--texto);font-weight:700;font-size:14px;cursor:pointer}}
button:hover,.upload:hover{{filter:brightness(1.18)}} button.primary{{background:var(--violeta)}} button.green{{background:var(--verde)}} button.cyan{{background:#087f98}} button.pink{{background:#b52855}}
select{{margin-bottom:10px;background:#071522}} .wide{{grid-column:1/-1}} .section{{margin-top:16px;border-top:1px solid var(--borde);padding-top:14px}}
.section h2{{font-size:15px;margin:0 0 10px;color:#cbe6f6}} input[type=file]{{display:none}} .upload{{display:block;text-align:center;background:#17364f}}
.small{{font-size:12px;color:var(--muted);line-height:1.45;margin-top:10px}} #mensaje{{min-height:22px;color:#8ce7ba;font-size:13px;margin-top:10px}}
.links{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}} .links a{{color:#aee9f2;text-decoration:none;border:1px solid var(--borde);padding:8px 10px;border-radius:8px;font-size:12px}}
@media(max-width:950px){{main{{grid-template-columns:1fr}} header{{align-items:flex-start;gap:8px;flex-direction:column}}}}
</style>
</head>
<body>
<header><h1>EL DEBER · Control web de Datos del Tiempo</h1><div class="badge">Puerto {PUERTO_SALIDA_VMIX} · {autenticacion}</div></header>
<main>
<section class="card"><div class="preview"><span class="label">PREVISUALIZACIÓN EN VIVO</span><img src="/stream.mjpg" alt="Salida al aire"></div></section>
<aside class="card"><div class="content">
<div class="state"><div><strong id="ciudad">Mapa general</strong><br><span id="estado">Conectando…</span></div><span id="hora"></span></div>
<select id="selector"><option value="">Seleccione una ciudad…</option></select>
<div class="grid">
<button class="green wide" onclick="accion('iniciar')">INICIAR RECORRIDO</button>
<button onclick="accion('anterior')">◀ ANTERIOR</button><button onclick="accion('siguiente')">SIGUIENTE ▶</button>
<button class="cyan" onclick="accion('inicio')">MAPA INICIAL</button><button class="primary" id="btnPronostico" onclick="accion('pronostico')">PRONÓSTICO 5 DÍAS</button>
<button class="pink wide" id="btnPnt" onclick="accion('pnt')">MOSTRAR / OCULTAR PNT</button>
<button class="wide" onclick="accion('actualizar')">ACTUALIZAR DATOS DEL CLIMA</button>
</div>
<div class="section"><h2>Imágenes del escenario PNT</h2><div class="grid">
<label class="upload"><input type="file" accept="image/*" onchange="subir(this,'subir_fondo')">CARGAR FONDO PNT</label>
<label class="upload"><input type="file" accept="image/*" onchange="subir(this,'subir_marca')">CARGAR MARCA / PRODUCTO</label>
</div><div class="small" id="archivos">Sin información de imágenes.</div></div>
<div id="mensaje"></div>
<div class="links"><a href="/" target="_blank">Abrir salida limpia</a><a href="/frame.jpg" target="_blank">Fotograma JPG</a></div>
<div class="small">El panel controla la aplicación PyQt que se ejecuta en el servidor. No hace falta abrir VNC. Para producción, limite el puerto a la red interna y configure credenciales.</div>
</div></aside>
</main>
<script>
const selector=document.getElementById('selector'), mensaje=document.getElementById('mensaje');
async function api(cuerpo){{
  mensaje.textContent='Procesando…';
  const r=await fetch('/api/control',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(cuerpo)}});
  const j=await r.json().catch(()=>({{ok:false,error:'Respuesta inválida'}}));
  if(!r.ok||!j.ok) throw new Error(j.error||'No se pudo completar la acción');
  mensaje.textContent=j.mensaje||'Acción enviada'; setTimeout(()=>mensaje.textContent='',2500);
}}
function accion(nombre,valor=null){{api({{accion:nombre,valor}}).catch(e=>mensaje.textContent='Error: '+e.message)}}
selector.addEventListener('change',()=>{{if(selector.value) accion('ciudad',selector.value)}});
function subir(input,accionNombre){{
 const f=input.files[0]; if(!f)return; if(f.size>20*1024*1024){{mensaje.textContent='La imagen supera 20 MB';return;}}
 const reader=new FileReader(); reader.onload=()=>api({{accion:accionNombre,nombre:f.name,contenido:reader.result}}).catch(e=>mensaje.textContent='Error: '+e.message); reader.readAsDataURL(f);
}}
async function actualizarEstado(){{
 try{{const r=await fetch('/api/estado',{{cache:'no-store'}}); if(!r.ok)return; const e=await r.json();
 document.getElementById('ciudad').textContent=e.ciudad||'Mapa general'; document.getElementById('estado').textContent=e.estado||''; document.getElementById('hora').textContent=e.hora_servidor||'';
 document.getElementById('btnPronostico').textContent=e.pronostico_extendido?'VOLVER A VISTA ACTUAL':'PRONÓSTICO 5 DÍAS'; document.getElementById('btnPnt').textContent=e.pnt_visible?'OCULTAR ESCENARIO PNT':'MOSTRAR ESCENARIO PNT';
 document.getElementById('archivos').textContent='Fondo: '+(e.fondo_pnt||'no cargado')+' · Marca: '+(e.marca_pnt||'no cargada');
 if(selector.options.length<=1){{e.ciudades.forEach(c=>selector.add(new Option(c,c)));}} if(e.ciudad) selector.value=e.ciudad;
 }}catch(_){{}}}}
actualizarEstado(); setInterval(actualizarEstado,1200);
</script>
</body></html>'''.encode("utf-8")


class SenalesConsulta(QObject):
    completada = pyqtSignal(str, dict)
    error = pyqtSignal(str, str)


class ConsultaClima(QRunnable):
    def __init__(self, ciudad, latitud, longitud):
        super().__init__()
        self.ciudad = ciudad
        self.latitud = latitud
        self.longitud = longitud
        self.senales = SenalesConsulta()

    def run(self):
        try:
            datos = consultar_clima_remoto(self.ciudad, self.latitud, self.longitud)
            guardar_clima_local(self.ciudad, datos)
            self.senales.completada.emit(self.ciudad, datos)
        except Exception as exc:
            self.senales.error.emit(self.ciudad, str(exc))


class SenalesActualizacion(QObject):
    progreso = pyqtSignal(int, int, str)
    ciudad_actualizada = pyqtSignal(str, dict)
    error = pyqtSignal(str, str)
    terminada = pyqtSignal(int, int)


class ActualizacionMasiva(QRunnable):
    def __init__(self):
        super().__init__()
        self.senales = SenalesActualizacion()

    def run(self):
        correctas = 0
        total = len(CIUDADES)
        for indice, (ciudad, (latitud, longitud)) in enumerate(CIUDADES.items(), start=1):
            if DETENER_TRABAJADORES.is_set(): break
            self.senales.progreso.emit(indice, total, ciudad)
            try:
                datos = consultar_clima_remoto(ciudad, latitud, longitud)
                guardar_clima_local(ciudad, datos)
                correctas += 1
                self.senales.ciudad_actualizada.emit(ciudad, datos)
            except Exception as exc:
                self.senales.error.emit(ciudad, str(exc))
        self.senales.terminada.emit(correctas, total)


# Identidad visual oficial (Manual de marca EL DEBER, octubre de 2023).
COLOR_MARCA = QColor("#008f58")
COLOR_BLANCO = QColor("#ffffff")
COLOR_CELESTE = QColor("#00b8d9")
COLOR_AMARILLO = QColor("#ffc928")
COLOR_AMARANTO = QColor("#ff3d71")
COLOR_VIOLETA = QColor("#6c4bff")
COLOR_FONDO = QColor("#edf8ff")
COLOR_TINTA = QColor("#15304a")

FUENTE_TITULOS = "Roboto Slab"
FUENTE_TEXTO = "Roboto"
FUENTE_APOYO = "Raleway"


# QPixmap usa memoria sin comprimir. La versión anterior cargaba las mismas
# capas de 2580x2937 dos veces (salida local + render web), superando 700 MB.
# Este caché comparte las imágenes entre widgets y las reduce una sola vez a
# una resolución suficiente para una salida 1920x1080 con zoom.
_CACHE_PIXMAP = OrderedDict()


def cargar_pixmap_compartido(ruta, alto_maximo=None):
    ruta = str(ruta)
    clave = (ruta, int(alto_maximo or 0))
    pixmap = _CACHE_PIXMAP.get(clave)
    if pixmap is not None:
        return pixmap
    pixmap = QPixmap(ruta)
    if (
        alto_maximo
        and not pixmap.isNull()
        and pixmap.height() > int(alto_maximo)
    ):
        pixmap = pixmap.scaledToHeight(
            int(alto_maximo),
            Qt.TransformationMode.SmoothTransformation,
        )
    _CACHE_PIXMAP[clave] = pixmap
    if len(_CACHE_PIXMAP) > 32:
        _CACHE_PIXMAP.popitem(last=False)
    return pixmap


def cargar_fuentes():
    for nombre in (
        "Roboto-Variable.ttf",
        "RobotoSlab-Variable.ttf",
        "Raleway-Variable.ttf",
    ):
        QFontDatabase.addApplicationFont(str(ACTIVOS / "fonts" / nombre))


@lru_cache(maxsize=192)
def fuente(familia, tamano, peso=QFont.Weight.Normal):
    return QFont(familia, max(1, int(tamano)), peso)


class MapaMeteorologico(QWidget):
    """Salida broadcast con cámara geográfica y dos vistas meteorológicas."""

    MIN_LON, MAX_LON = -69.65, -57.45
    MIN_LAT, MAX_LAT = -22.90, -9.65
    CENTRO_PAIS = (-16.45, -64.30)
    DIAS = ("LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM")

    def __init__(self, parent=None):
        super().__init__(parent)
        inicializar_base_datos()
        self.setMinimumSize(960, 540)
        self.ciudad = ""
        self.datos = None
        self.origen_geo = self.CENTRO_PAIS
        self.destino_geo = self.CENTRO_PAIS
        self.progreso = 0.0
        self.zoom_origen = 0.92
        self.zoom_destino = 0.92
        self.primer_viaje = True
        self.fase_pulso = 0.0
        self.fase_nubes = 0.0
        self._inicio_movimiento = time.perf_counter()
        self.modo_extendido = False
        self.panel_progreso = 0.0
        self.panel_accion = None
        self.vista_pendiente = None
        self.ciudad_pendiente = None
        self.datos_pendientes = None
        self.modo_pnt = False
        self.pnt_progreso = 0.0
        self.ruta_pnt_fondo = leer_configuracion("pnt_fondo")
        self.ruta_pnt_marca = leer_configuracion("pnt_marca")
        self.pnt_fondo = QPixmap(self.ruta_pnt_fondo) if self.ruta_pnt_fondo else QPixmap()
        self.pnt_marca = QPixmap(self.ruta_pnt_marca) if self.ruta_pnt_marca else QPixmap()
        self.pnt_marca_reflejo = self.pnt_marca.transformed(QTransform().scale(1, -1)) if not self.pnt_marca.isNull() else QPixmap()

        self.mapa_relleno = cargar_pixmap_compartido(
            ACTIVOS / "bolivia_relleno.png", ALTO_MAXIMO_MAPA
        )
        self.mapa_limites = cargar_pixmap_compartido(
            ACTIVOS / "bolivia_limites.png", ALTO_MAXIMO_MAPA
        )
        self.logo = cargar_pixmap_compartido(ACTIVOS / "logo_el_deber_blanco.png")
        self.mapas_departamentos = {
            nombre: cargar_pixmap_compartido(
                ACTIVOS / f"departamento_{nombre}.png", ALTO_MAXIMO_MAPA
            )
            for nombre in set(DEPARTAMENTO_CIUDAD.values())
        }

        self.animacion_camara = QVariantAnimation(self)
        self.animacion_camara.setDuration(DURACION_CAMARA_MS)
        self.animacion_camara.setStartValue(0.0)
        self.animacion_camara.setEndValue(1.0)
        self.animacion_camara.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animacion_camara.valueChanged.connect(self._animar_camara)
        self.animacion_camara.finished.connect(self._viaje_terminado)

        self.animacion_panel = QVariantAnimation(self)
        self.animacion_panel.setDuration(DURACION_PANEL_MS)
        self.animacion_panel.setStartValue(0.0)
        self.animacion_panel.setEndValue(1.0)
        self.animacion_panel.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animacion_panel.valueChanged.connect(self._animar_panel)
        self.animacion_panel.finished.connect(self._panel_terminado)

        self.animacion_pnt = QVariantAnimation(self)
        self.animacion_pnt.setDuration(DURACION_PNT_MS)
        self.animacion_pnt.setStartValue(0.0)
        self.animacion_pnt.setEndValue(1.0)
        self.animacion_pnt.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animacion_pnt.valueChanged.connect(self._animar_pnt)

        self.reloj_pulso = QTimer(self)
        self.reloj_pulso.setTimerType(Qt.TimerType.PreciseTimer)
        self.reloj_pulso.setInterval(max(1, round(1000.0 / FPS_ANIMACION)))
        self.reloj_pulso.timeout.connect(self._pulso)
        self.reloj_pulso.start()

    def _solicitar_repintado(self):
        if not getattr(self, "captura_dirigida", False) and self.isVisible():
            self.update()

    def configurar_pnt(self, fondo, marca):
        self.ruta_pnt_fondo = fondo or self.ruta_pnt_fondo
        self.ruta_pnt_marca = marca or self.ruta_pnt_marca
        self.pnt_fondo = QPixmap(self.ruta_pnt_fondo) if self.ruta_pnt_fondo else QPixmap()
        self.pnt_marca = QPixmap(self.ruta_pnt_marca) if self.ruta_pnt_marca else QPixmap()
        self.pnt_marca_reflejo = self.pnt_marca.transformed(QTransform().scale(1, -1)) if not self.pnt_marca.isNull() else QPixmap()
        self._solicitar_repintado()

    def alternar_pnt(self):
        self.modo_pnt = not self.modo_pnt
        self.animacion_pnt.stop()
        self.animacion_pnt.setStartValue(float(self.pnt_progreso))
        self.animacion_pnt.setEndValue(1.0 if self.modo_pnt else 0.0)
        self.animacion_pnt.start()

    def mostrar_inicio(self):
        self.ciudad_pendiente = None
        self.datos_pendientes = None
        self.vista_pendiente = None
        self.animacion_camara.stop()
        if self.datos and self.panel_progreso > 0.01:
            self._animar_panel_hacia(0.0, "inicio")
        else:
            self._iniciar_inicio()

    def _iniciar_inicio(self):
        self.origen_geo = self._camera_geo()
        self.destino_geo = self.CENTRO_PAIS
        self.zoom_origen = self._zoom_camara()
        self.zoom_destino = 0.92
        self.ciudad = ""
        self.datos = None
        self.modo_extendido = False
        self.panel_progreso = 0.0
        self.progreso = 0.0
        self.animacion_camara.stop()
        self.animacion_panel.stop()
        self.animacion_camara.start()
        self._solicitar_repintado()

    def mostrar_ciudad(self, ciudad, datos):
        self.ciudad_pendiente = ciudad
        self.datos_pendientes = datos
        self.animacion_camara.stop()
        if self.datos and self.panel_progreso > 0.01:
            self._animar_panel_hacia(0.0, "viajar")
        else:
            self._iniciar_viaje()

    def _iniciar_viaje(self):
        if not self.ciudad_pendiente or not self.datos_pendientes:
            return
        posicion_actual = self._camera_geo()
        zoom_actual = self._zoom_camara()
        self.origen_geo = posicion_actual
        self.destino_geo = CIUDADES[self.ciudad_pendiente]
        self.zoom_origen = zoom_actual
        self.zoom_destino = 2.05
        self.ciudad = self.ciudad_pendiente
        self.datos = self.datos_pendientes
        self.ciudad_pendiente = None
        self.datos_pendientes = None
        self.modo_extendido = False
        self.progreso = 0.0
        self.panel_progreso = 0.0
        self.animacion_camara.stop()
        self.animacion_panel.stop()
        self.animacion_camara.start()
        self._solicitar_repintado()

    def mostrar_extendido(self, activar=None):
        if (
            not self.datos
            or self.animacion_camara.state() == QAbstractAnimation.State.Running
            or self.panel_accion == "viajar"
        ):
            return
        destino = (not self.modo_extendido) if activar is None else bool(activar)
        if destino == self.modo_extendido:
            return
        self.vista_pendiente = destino
        self._animar_panel_hacia(0.0, "vista")

    def _animar_panel_hacia(self, destino, accion=None):
        self.panel_accion = accion
        self.animacion_panel.stop()
        self.animacion_panel.setStartValue(float(self.panel_progreso))
        self.animacion_panel.setEndValue(float(destino))
        self.animacion_panel.start()

    def _panel_terminado(self):
        accion = self.panel_accion
        self.panel_accion = None
        if accion == "viajar":
            self._iniciar_viaje()
        elif accion == "inicio":
            self._iniciar_inicio()
        elif accion == "vista" and self.vista_pendiente is not None:
            self.modo_extendido = self.vista_pendiente
            self.vista_pendiente = None
            # Reiniciar la misma animación fuera de su callback finished evita
            # reentradas del motor de animación de Qt.
            QTimer.singleShot(0, lambda: self._animar_panel_hacia(1.0))

    def _viaje_terminado(self):
        self.primer_viaje = False
        if self.datos:
            self._animar_panel_hacia(1.0)

    def _animar_camara(self, valor):
        self.progreso = float(valor)
        self._solicitar_repintado()

    def _animar_panel(self, valor):
        self.panel_progreso = float(valor)
        self._solicitar_repintado()

    def _animar_pnt(self, valor):
        self.pnt_progreso = float(valor)
        self._solicitar_repintado()

    def _pulso(self):
        self._actualizar_fases()
        self._solicitar_repintado()

    def _actualizar_fases(self, ahora=None):
        # Tiempo real, no cantidad de callbacks. Si la CPU se ocupa, la
        # animación no queda en cámara lenta: solo omite cuadros intermedios.
        transcurrido = (time.perf_counter() if ahora is None else ahora) - self._inicio_movimiento
        self.fase_pulso = transcurrido * (60.0 / CICLO_ICONOS_SEGUNDOS)
        self.fase_nubes = transcurrido * (0.012 / 0.045)

    def _camera_geo(self):
        t = self.progreso
        lat = self.origen_geo[0] + (self.destino_geo[0] - self.origen_geo[0]) * t
        lon = self.origen_geo[1] + (self.destino_geo[1] - self.origen_geo[1]) * t
        return lat, lon

    def _zoom_camara(self):
        return self.zoom_origen + (self.zoom_destino - self.zoom_origen) * self.progreso

    def _rect_mapa_base(self):
        area_w = self.width() * 0.96
        area_h = self.height() * 0.79
        relacion = self.mapa_relleno.width() / max(1, self.mapa_relleno.height())
        alto = min(area_h, area_w / relacion)
        ancho = alto * relacion
        return QRectF(
            (self.width() - ancho) / 2,
            self.height() * 0.13 + (area_h - alto) / 2,
            ancho,
            alto,
        )

    def _proyectar(self, geo, rect):
        latitud, longitud = geo
        x = rect.left() + (longitud - self.MIN_LON) / (self.MAX_LON - self.MIN_LON) * rect.width()
        y = rect.top() + (self.MAX_LAT - latitud) / (self.MAX_LAT - self.MIN_LAT) * rect.height()
        return QPointF(x, y)

    def _transformacion_camara(self, rect):
        punto_camara = self._proyectar(self._camera_geo(), rect)
        centro = QPointF(self.width() * 0.50, self.height() * 0.56)
        zoom = self._zoom_camara()
        transformacion = QTransform()
        transformacion.translate(centro.x(), centro.y())
        transformacion.scale(zoom, zoom)
        transformacion.translate(-punto_camara.x(), -punto_camara.y())
        return transformacion

    @PERFIL.decorate("paintEvent")
    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self._pintar_escena(painter)
        finally:
            painter.end()

    @PERFIL.decorate("render.scene")
    def _pintar_escena(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # Only omit layers when an opaque foreground covers every output pixel.
        pnt_opaco = self.pnt_progreso >= 1.0 and (
            self.pnt_fondo.isNull() or not self.pnt_fondo.hasAlphaChannel())
        extendido_opaco = self.datos and self.modo_extendido and self.panel_progreso >= 1.0
        if not pnt_opaco:
            if not extendido_opaco:
                painter.save()
                if self.datos and self.modo_extendido:
                    # The forecast paints an opaque translated rectangle. Keep
                    # the fractional boundary pixel underneath for exact blending.
                    visible = math.ceil((1.0 - self.panel_progreso) * self.height())
                    painter.setClipRect(QRectF(0, 0, self.width(), visible), Qt.ClipOperation.IntersectClip)
                self._dibujar_fondo(painter)
                transformacion = self._dibujar_mapa(painter)
                self._dibujar_cabecera(painter)
                if self.datos:
                    self._dibujar_destino(painter, transformacion)
                    if not self.modo_extendido:
                        self._dibujar_actual(painter)
                else:
                    self._dibujar_espera(painter)
                painter.restore()
            if self.datos and self.modo_extendido:
                self._dibujar_extendido(painter)
        if self.pnt_progreso > 0.001:
            painter.save()
            painter.setOpacity(self.pnt_progreso)
            self._dibujar_pnt(painter)
            painter.restore()

    @PERFIL.decorate("render.direct_rgb32")
    def renderizar_imagen(self, imagen):
        painter = QPainter(imagen)
        try:
            self._pintar_escena(painter)
        finally:
            painter.end()
        return imagen

    @staticmethod
    def _dibujar_pixmap_cover(painter, pixmap, destino):
        if pixmap.isNull():
            return
        proporcion_destino = destino.width() / max(1.0, destino.height())
        proporcion_imagen = pixmap.width() / max(1.0, pixmap.height())
        if proporcion_imagen > proporcion_destino:
            ancho_fuente = pixmap.height() * proporcion_destino
            fuente = QRectF((pixmap.width() - ancho_fuente) / 2, 0, ancho_fuente, pixmap.height())
        else:
            alto_fuente = pixmap.width() / proporcion_destino
            fuente = QRectF(0, (pixmap.height() - alto_fuente) / 2, pixmap.width(), alto_fuente)
        painter.drawPixmap(destino, pixmap, fuente)

    @PERFIL.decorate("_dibujar_pnt")
    def _dibujar_pnt(self, painter):
        pantalla = QRectF(self.rect())
        if not self.pnt_fondo.isNull():
            self._dibujar_pixmap_cover(painter, self.pnt_fondo, pantalla)
            velo = QLinearGradient(0, 0, self.width(), self.height())
            velo.setColorAt(0, QColor(15, 66, 112, 105))
            velo.setColorAt(0.55, QColor(69, 75, 180, 55))
            velo.setColorAt(1, QColor(0, 188, 212, 95))
            painter.fillRect(self.rect(), velo)
        else:
            fondo = QLinearGradient(0, 0, self.width(), self.height())
            fondo.setColorAt(0, QColor("#dff8ff"))
            fondo.setColorAt(0.48, QColor("#bdd7ff"))
            fondo.setColorAt(1, QColor("#dac8ff"))
            painter.fillRect(self.rect(), fondo)
            painter.setPen(Qt.PenStyle.NoPen)
            desplazamiento = math.sin(self.fase_pulso / 60.0 * math.tau) * 24
            painter.setBrush(QColor(0, 185, 214, 62))
            painter.drawEllipse(QPointF(self.width() * 0.18 + desplazamiento, self.height() * 0.36), self.height() * 0.28, self.height() * 0.28)
            painter.setBrush(QColor(108, 75, 255, 52))
            painter.drawEllipse(QPointF(self.width() * 0.80 - desplazamiento, self.height() * 0.30), self.height() * 0.36, self.height() * 0.36)

        # Piso virtual y profundidad de escenario.
        piso = QPolygonF(
            [
                QPointF(0, self.height() * 0.72),
                QPointF(self.width(), self.height() * 0.62),
                QPointF(self.width(), self.height()),
                QPointF(0, self.height()),
            ]
        )
        gradiente_piso = QLinearGradient(0, self.height() * 0.62, 0, self.height())
        gradiente_piso.setColorAt(0, QColor(255, 255, 255, 212))
        gradiente_piso.setColorAt(1, QColor(224, 244, 255, 242))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradiente_piso)
        painter.drawPolygon(piso)

        margen = self.width() * 0.045
        logo_rect = QRectF(margen, self.height() * 0.04, self.width() * 0.15, self.height() * 0.07)
        painter.setBrush(COLOR_MARCA)
        painter.drawRoundedRect(logo_rect, 8, 8)
        if not self.logo.isNull():
            painter.drawPixmap(logo_rect.adjusted(18, 12, -18, -12), self.logo, QRectF(self.logo.rect()))

        # Pieza comercial flotante: mayor escala, perspectiva, sombra y reflejo.
        if not self.pnt_marca.isNull():
            clave = (self.pnt_marca.cacheKey(), self.width(), self.height())
            if getattr(self, "_pnt_escala_clave", None) != clave:
                self._pnt_escalada = self.pnt_marca.scaled(
                    int(self.width() * 0.57), int(self.height() * 0.60),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                self._pnt_escala_clave = clave
            escalada = self._pnt_escalada
            ancho = float(escalada.width())
            alto = float(escalada.height())
            x = self.width() * 0.39 + (self.width() * 0.57 - ancho) / 2
            y = self.height() * 0.105 + (self.height() * 0.60 - alto) / 2
            destino = QRectF(x, y, ancho, alto)

            # Pantalla frontal tipo TV: marco y base totalmente rectangulares.
            marco = destino.adjusted(-8, -8, 8, 8)
            for dx, dy, alfa in ((10, 14, 42), (18, 24, 26), (28, 36, 12)):
                sombra = marco.translated(dx, dy)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(18, 39, 68, alfa))
                painter.drawRoundedRect(sombra, 10, 10)
            painter.setPen(QPen(QColor(225, 239, 247, 235), 3))
            painter.setBrush(QColor(18, 31, 48, 245))
            painter.drawRoundedRect(marco, 9, 9)
            painter.drawPixmap(destino, escalada, QRectF(escalada.rect()))

            # Reflejo corto sobre el piso, invertido y desvanecido.
            base_y = destino.bottom() + self.height() * 0.012
            alto_reflejo = min(alto * 0.22, self.height() * 0.14)
            reflejo = QRectF(destino.left(), base_y, destino.width(), alto_reflejo)
            if not self.pnt_marca_reflejo.isNull():
                painter.save()
                painter.setOpacity(0.17)
                painter.drawPixmap(reflejo, self.pnt_marca_reflejo, QRectF(self.pnt_marca_reflejo.rect()))
                painter.restore()
                velo_reflejo = QLinearGradient(0, base_y, 0, base_y + alto_reflejo)
                velo_reflejo.setColorAt(0, QColor(235, 248, 255, 28))
                velo_reflejo.setColorAt(1, QColor(235, 248, 255, 238))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(velo_reflejo)
                painter.drawRect(reflejo)

    @PERFIL.decorate("_dibujar_fondo")
    def _dibujar_fondo(self, painter):
        clave = (self.width(), self.height())
        if getattr(self, "_fondo_cache_clave", None) != clave:
            self._fondo_cache = QImage(self.width(), self.height(), QImage.Format.Format_RGB32)
            cache = QPainter(self._fondo_cache)
            gradiente = QLinearGradient(0, 0, self.width(), self.height())
            gradiente.setColorAt(0, QColor("#f7fcff"))
            gradiente.setColorAt(0.48, QColor("#def3ff"))
            gradiente.setColorAt(1, QColor("#eee7ff"))
            cache.fillRect(self.rect(), gradiente)
            cache.end()
            self._fondo_cache_clave = clave
        painter.drawImage(0, 0, self._fondo_cache)

        painter.setPen(Qt.PenStyle.NoPen)
        fase = self.fase_nubes
        painter.setBrush(QColor(0, 184, 217, 28))
        painter.drawEllipse(
            QPointF(self.width() * 0.14 + math.sin(fase) * 12, self.height() * 0.72),
            self.height() * 0.32,
            self.height() * 0.32,
        )
        painter.setBrush(QColor(108, 75, 255, 24))
        painter.drawEllipse(
            QPointF(self.width() * 0.82 + math.cos(fase) * 15, self.height() * 0.22),
            self.height() * 0.38,
            self.height() * 0.38,
        )
        painter.setPen(QPen(QColor(21, 48, 74, 12), 1))
        paso = max(58, int(self.width() / 24))
        for x in range(-self.height(), self.width(), paso):
            painter.drawLine(x, self.height(), x + self.height(), 0)

    @PERFIL.decorate("_dibujar_cabecera")
    def _dibujar_cabecera(self, painter):
        margen = self.width() * 0.043
        alto = self.height() * 0.065
        logo_rect = QRectF(margen, self.height() * 0.032, self.width() * 0.15, alto)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(COLOR_MARCA)
        painter.drawRoundedRect(logo_rect, 6, 6)
        if not self.logo.isNull():
            interior = logo_rect.adjusted(18, 12, -18, -12)
            painter.drawPixmap(interior, self.logo, QRectF(self.logo.rect()))

        painter.setPen(COLOR_TINTA)
        painter.setFont(fuente(FUENTE_APOYO, self.height() * 0.036, QFont.Weight.Bold))
        painter.drawText(QPointF(margen + self.width() * 0.175, self.height() * 0.076), "DATOS DEL TIEMPO")

    @PERFIL.decorate("_dibujar_mapa")
    def _dibujar_mapa(self, painter):
        rect = self._rect_mapa_base()
        transformacion = self._transformacion_camara(rect)
        zoom = self._zoom_camara()
        painter.save()
        painter.setClipRect(QRectF(0, self.height() * 0.105, self.width(), self.height() * 0.895), Qt.ClipOperation.IntersectClip)
        painter.setTransform(transformacion)

        painter.setOpacity(0.30)
        painter.drawPixmap(rect.translated(12 / zoom, 16 / zoom), self.mapa_relleno, QRectF(self.mapa_relleno.rect()))
        painter.setOpacity(1.0)
        painter.drawPixmap(rect, self.mapa_relleno, QRectF(self.mapa_relleno.rect()))
        departamento = DEPARTAMENTO_CIUDAD.get(self.ciudad)
        capa_departamento = self.mapas_departamentos.get(departamento)
        if capa_departamento and not capa_departamento.isNull():
            painter.setOpacity(0.88 + 0.12 * abs(math.sin(self.fase_pulso / 60.0 * math.tau)))
            painter.drawPixmap(rect, capa_departamento, QRectF(capa_departamento.rect()))
            painter.setOpacity(1.0)
        painter.drawPixmap(rect, self.mapa_limites, QRectF(self.mapa_limites.rect()))

        for nombre, geo in CIUDADES.items():
            punto = self._proyectar(geo, rect)
            activo = nombre == self.ciudad
            if activo:
                continue
            radio = 2.7 / zoom
            painter.setPen(QPen(QColor(255, 255, 255, 215), 1.2 / zoom))
            painter.setBrush(QColor(255, 255, 255, 205))
            painter.drawEllipse(punto, radio, radio)
        painter.restore()
        return transformacion

    @PERFIL.decorate("_dibujar_destino")
    def _dibujar_destino(self, painter, transformacion):
        rect = self._rect_mapa_base()
        destino = transformacion.map(self._proyectar(self.destino_geo, rect))
        fase = self.fase_pulso / 60.0 * math.tau
        rebote = abs(math.sin(fase)) * 5.0
        punta = QPointF(destino.x(), destino.y() - rebote)
        pulso = 15 + 8 * abs(math.sin(fase))

        painter.setPen(QPen(QColor(255, 255, 255, 100), 1.8))
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawEllipse(destino, pulso, pulso * 0.45)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 75))
        painter.drawEllipse(QPointF(destino.x() + 3, destino.y() + 4), 12, 4)

        x, y = punta.x(), punta.y()
        pin = QPainterPath(QPointF(x, y))
        pin.cubicTo(x - 5, y - 8, x - 18, y - 15, x - 18, y - 29)
        pin.cubicTo(x - 18, y - 41, x - 10, y - 50, x, y - 50)
        pin.cubicTo(x + 10, y - 50, x + 18, y - 41, x + 18, y - 29)
        pin.cubicTo(x + 18, y - 15, x + 5, y - 8, x, y)
        gradiente_pin = QLinearGradient(x - 16, y - 48, x + 16, y - 5)
        gradiente_pin.setColorAt(0, QColor("#ff5476"))
        gradiente_pin.setColorAt(1, COLOR_AMARANTO)
        painter.setPen(QPen(Qt.GlobalColor.white, 2.2))
        painter.setBrush(gradiente_pin)
        painter.drawPath(pin)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawEllipse(QPointF(x, y - 31), 6.5, 6.5)

        if self.progreso > 0.72:
            etiqueta = self.ciudad.split(" (")[0].upper()
            painter.setFont(fuente(FUENTE_APOYO, self.height() * 0.014, QFont.Weight.Bold))
            ancho = max(145, painter.fontMetrics().horizontalAdvance(etiqueta) + 34)
            limite_panel = self.width() * 0.62
            if destino.x() + 28 + ancho < limite_panel:
                x = destino.x() + 28
            else:
                x = destino.x() - ancho - 28
            y = max(self.height() * 0.12, destino.y() - 48)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(4, 24, 23, 232))
            painter.drawRoundedRect(QRectF(x, y, ancho, 40), 20, 20)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(QRectF(x, y, ancho, 40), Qt.AlignmentFlag.AlignCenter, etiqueta)

    @staticmethod
    def _codigo_desde_datos(datos):
        if "codigo" in datos:
            return int(datos["codigo"])
        texto = datos.get("descripcion", "").lower()
        if "torment" in texto:
            return 95
        if "nieve" in texto or "nevada" in texto:
            return 71
        if "lluv" in texto or "chubasco" in texto:
            return 63
        if "niebla" in texto:
            return 45
        if "nubl" in texto:
            return 3
        return 0

    def _dibujar_icono_clima(self, painter, rect, codigo, desfase=0):
        """Iconografía vectorial animada inspirada en motion graphics broadcast."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        unidad = min(rect.width(), rect.height()) / 100.0
        fase = (self.fase_pulso / 60.0 * math.tau) + desfase
        cx, cy = rect.center().x(), rect.center().y()

        def sol(x, y, escala=1.0):
            radio = 18 * unidad * escala
            rotacion = fase * 0.45
            painter.setPen(QPen(QColor(253, 199, 21, 185), 3.2 * unidad, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for i in range(10):
                angulo = rotacion + i * math.tau / 10
                r1, r2 = radio * 1.32, radio * 1.70
                painter.drawLine(
                    QPointF(x + math.cos(angulo) * r1, y + math.sin(angulo) * r1),
                    QPointF(x + math.cos(angulo) * r2, y + math.sin(angulo) * r2),
                )
            brillo = QRadialGradient(x - radio * 0.28, y - radio * 0.30, radio * 1.35)
            brillo.setColorAt(0, QColor("#fff4a8"))
            brillo.setColorAt(0.48, COLOR_AMARILLO)
            brillo.setColorAt(1, QColor("#f39b18"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(brillo)
            pulso = 1.0 + math.sin(fase) * 0.035
            painter.drawEllipse(QPointF(x, y), radio * pulso, radio * pulso)

        def nube(x, y, escala=1.0):
            balanceo = math.sin(fase * 0.8) * 2.5 * unidad
            x += balanceo
            w, h = 62 * unidad * escala, 28 * unidad * escala
            gradiente = QLinearGradient(x, y - h, x, y + h)
            gradiente.setColorAt(0, QColor("#ffffff"))
            gradiente.setColorAt(1, QColor("#b9d4df"))
            painter.setPen(QPen(QColor(112, 157, 181, 190), 1.2 * unidad))
            painter.setBrush(QColor(0, 0, 0, 45))
            painter.drawRoundedRect(QRectF(x - w / 2 + 3 * unidad, y + 3 * unidad, w, h), h / 2, h / 2)
            painter.setBrush(gradiente)
            painter.drawRoundedRect(QRectF(x - w / 2, y, w, h), h / 2, h / 2)
            painter.drawEllipse(QPointF(x - 19 * unidad * escala, y + 2 * unidad), 15 * unidad * escala, 17 * unidad * escala)
            painter.drawEllipse(QPointF(x + 2 * unidad * escala, y - 7 * unidad), 21 * unidad * escala, 23 * unidad * escala)
            painter.drawEllipse(QPointF(x + 22 * unidad * escala, y + 3 * unidad), 14 * unidad * escala, 16 * unidad * escala)

        es_lluvia = codigo in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82)
        es_nieve = codigo in (71, 73, 75, 77, 85, 86)
        es_tormenta = codigo in (95, 96, 99)
        es_niebla = codigo in (45, 48)

        if codigo in (0, 1):
            sol(cx, cy, 1.0)
        elif codigo == 2:
            sol(cx - 18 * unidad, cy - 12 * unidad, 0.75)
            nube(cx + 6 * unidad, cy + 4 * unidad, 0.94)
        elif es_niebla:
            nube(cx, cy - 18 * unidad, 0.78)
            painter.setPen(QPen(QColor(210, 235, 238, 190), 4 * unidad, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            desplazamiento = math.sin(fase) * 8 * unidad
            for i in range(3):
                y = cy + (12 + i * 13) * unidad
                painter.drawLine(QPointF(cx - 31 * unidad + desplazamiento * (i % 2), y), QPointF(cx + 31 * unidad + desplazamiento * (i % 2), y))
        elif es_lluvia or es_tormenta or es_nieve:
            nube(cx, cy - 19 * unidad, 0.98)
            ciclo = ((fase / math.tau) % 1.0)
            if es_tormenta:
                brillo = 0.45 + 0.55 * max(0.0, math.sin(fase * 2.4))
                painter.setOpacity(brillo)
                rayo = QPolygonF(
                    [
                        QPointF(cx + 3 * unidad, cy - 1 * unidad),
                        QPointF(cx - 9 * unidad, cy + 23 * unidad),
                        QPointF(cx + 2 * unidad, cy + 21 * unidad),
                        QPointF(cx - 5 * unidad, cy + 43 * unidad),
                        QPointF(cx + 18 * unidad, cy + 14 * unidad),
                        QPointF(cx + 6 * unidad, cy + 15 * unidad),
                    ]
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(COLOR_AMARILLO)
                painter.drawPolygon(rayo)
                painter.setOpacity(1.0)
            elif es_nieve:
                painter.setPen(QPen(QColor(235, 250, 255), 2.1 * unidad, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                for i in range(5):
                    px = cx + (-28 + i * 14) * unidad
                    py = cy + (9 + ((ciclo + i * 0.19) % 1.0) * 34) * unidad
                    painter.drawLine(QPointF(px - 4 * unidad, py), QPointF(px + 4 * unidad, py))
                    painter.drawLine(QPointF(px, py - 4 * unidad), QPointF(px, py + 4 * unidad))
            else:
                painter.setPen(QPen(COLOR_CELESTE, 3.2 * unidad, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                for i in range(5):
                    px = cx + (-27 + i * 14) * unidad
                    py = cy + (7 + ((ciclo + i * 0.17) % 1.0) * 37) * unidad
                    painter.drawLine(QPointF(px + 4 * unidad, py), QPointF(px - 2 * unidad, py + 9 * unidad))
        else:
            nube(cx, cy - 5 * unidad, 1.0)

        painter.restore()

    @PERFIL.decorate("_dibujar_actual")
    def _dibujar_actual(self, painter):
        ancho = self.width() * 0.34
        alto = self.height() * 0.66
        x_final = self.width() * 0.625
        x = x_final + (1.0 - self.panel_progreso) * (ancho + self.width() * 0.04)
        y = self.height() * 0.19
        painter.save()
        painter.setOpacity(1.0)
        tarjeta = QRectF(x, y, ancho, alto)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 67, 98, 30))
        painter.drawRoundedRect(tarjeta.translated(10, 14), 32, 32)
        painter.setPen(QPen(QColor("#d4e5f1"), 1.5))
        painter.setBrush(QColor(255, 255, 255, 252))
        painter.drawRoundedRect(tarjeta, 30, 30)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(COLOR_VIOLETA)
        painter.drawRoundedRect(QRectF(x, y, ancho, 10), 5, 5)

        margen = ancho * 0.075
        painter.setPen(COLOR_TINTA)
        painter.setFont(fuente(FUENTE_TITULOS, self.height() * 0.041, QFont.Weight.Bold))
        painter.drawText(
            QRectF(x + margen, y + 31, ancho - 2 * margen, alto * 0.18),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self.ciudad.upper(),
        )

        icono_y = y + alto * 0.24
        self._dibujar_icono_clima(
            painter,
            QRectF(x + margen, icono_y, ancho * 0.43, alto * 0.29),
            self._codigo_desde_datos(self.datos),
        )
        painter.setPen(QColor("#71879a"))
        painter.setFont(fuente(FUENTE_TEXTO, self.height() * 0.014, QFont.Weight.Bold))
        painter.drawText(
            QRectF(x + ancho * 0.48, icono_y + 2, ancho * 0.44, 24),
            Qt.AlignmentFlag.AlignCenter,
            "ACTUAL",
        )
        painter.setPen(COLOR_TINTA)
        painter.setFont(fuente(FUENTE_APOYO, self.height() * 0.094, QFont.Weight.Bold))
        painter.drawText(
            QRectF(x + ancho * 0.45, icono_y + 18, ancho * 0.48, alto * 0.24),
            Qt.AlignmentFlag.AlignCenter,
            f'{self.datos["actual"]:.0f}°',
        )

        fila_y = y + alto * 0.60
        separacion = 16
        mitad = (ancho - 2 * margen - separacion) / 2
        cuerpo_h = alto * 0.29
        for i, (titulo, valor, color) in enumerate(
            (("MÍNIMA", self.datos["min"], COLOR_CELESTE), ("MÁXIMA", self.datos["max"], COLOR_AMARANTO))
        ):
            rx = x + margen + i * (mitad + separacion)
            modulo = QRectF(rx, fila_y, mitad, cuerpo_h)
            painter.setPen(QPen(QColor("#d5e3ec"), 1))
            painter.setBrush(QColor("#f1f6fa"))
            painter.drawRoundedRect(modulo, 17, 17)

            cabecera_h = cuerpo_h * 0.34
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(COLOR_CELESTE if i == 0 else COLOR_AMARANTO)
            painter.drawRoundedRect(QRectF(rx, fila_y, mitad, cabecera_h + 8), 17, 17)
            painter.drawRect(QRectF(rx, fila_y + 17, mitad, cabecera_h - 9))
            painter.setPen(Qt.GlobalColor.white)
            painter.setFont(fuente(FUENTE_APOYO, self.height() * 0.020, QFont.Weight.Bold))
            painter.drawText(QRectF(rx, fila_y, mitad, cabecera_h), Qt.AlignmentFlag.AlignCenter, titulo)

            painter.setPen(color)
            painter.setFont(fuente(FUENTE_APOYO, self.height() * 0.046, QFont.Weight.Bold))
            painter.drawText(
                QRectF(rx, fila_y + cabecera_h, mitad, cuerpo_h - cabecera_h),
                Qt.AlignmentFlag.AlignCenter,
                f"{valor:.0f}°",
            )
        painter.restore()

    def _dibujar_nubes_fondo_extendido(self, painter):
        """Nubes ambientales lentas, siempre detrás de la información."""
        fase = self.fase_nubes

        def nube(cx, cy, escala, alfa):
            unidad = self.height() * 0.050 * escala
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(76, 137, 180, max(8, alfa // 3)))
            painter.drawRoundedRect(
                QRectF(cx - unidad * 1.55 + 9, cy + unidad * 0.10 + 10, unidad * 3.1, unidad * 0.78),
                unidad * 0.38,
                unidad * 0.38,
            )
            painter.setPen(QPen(QColor(132, 184, 216, max(12, alfa // 2)), 1.5))
            painter.setBrush(QColor(194, 224, 241, alfa))
            painter.drawEllipse(QPointF(cx - unidad * 0.75, cy + unidad * 0.12), unidad * 0.82, unidad * 0.70)
            painter.drawEllipse(QPointF(cx, cy - unidad * 0.12), unidad, unidad * 0.94)
            painter.drawEllipse(QPointF(cx + unidad * 0.82, cy + unidad * 0.14), unidad * 0.76, unidad * 0.64)
            painter.drawRoundedRect(
                QRectF(cx - unidad * 1.55, cy + unidad * 0.06, unidad * 3.1, unidad * 0.78),
                unidad * 0.38,
                unidad * 0.38,
            )
            painter.restore()

        nube(
            self.width() * (0.12 + 0.045 * math.sin(fase * 0.72)),
            self.height() * 0.23,
            1.35,
            112,
        )
        nube(
            self.width() * (0.79 + 0.055 * math.sin(fase * 0.58 + 2.1)),
            self.height() * 0.40,
            1.75,
            98,
        )
        nube(
            self.width() * (0.36 + 0.065 * math.sin(fase * 0.47 + 4.0)),
            self.height() * 0.73,
            1.90,
            86,
        )
        nube(
            self.width() * (0.91 + 0.035 * math.sin(fase * 0.83 + 5.2)),
            self.height() * 0.79,
            1.15,
            76,
        )

    @PERFIL.decorate("_dibujar_extendido")
    def _dibujar_extendido(self, painter):
        pronostico = self.datos.get("pronostico", [])[:5]
        if not pronostico:
            return
        painter.save()
        painter.translate(0, (1.0 - self.panel_progreso) * self.height())
        painter.setOpacity(1.0)

        fondo = QLinearGradient(0, 0, self.width(), self.height())
        fondo.setColorAt(0, QColor("#f8fcff"))
        fondo.setColorAt(0.55, QColor("#e4f5ff"))
        fondo.setColorAt(1, QColor("#eee8ff"))
        painter.fillRect(self.rect(), fondo)
        self._dibujar_nubes_fondo_extendido(painter)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(COLOR_VIOLETA)
        painter.drawRect(QRectF(0, 0, self.width(), 10))

        margen_x = self.width() * 0.045
        logo_rect = QRectF(margen_x, self.height() * 0.035, self.width() * 0.15, self.height() * 0.067)
        painter.setBrush(COLOR_MARCA)
        painter.drawRoundedRect(logo_rect, 6, 6)
        if not self.logo.isNull():
            interior = logo_rect.adjusted(18, 12, -18, -12)
            painter.drawPixmap(interior, self.logo, QRectF(self.logo.rect()))

        painter.setPen(COLOR_TINTA)
        painter.setFont(fuente(FUENTE_TITULOS, self.height() * 0.041, QFont.Weight.Bold))
        painter.drawText(
            QPointF(margen_x + self.width() * 0.18, self.height() * 0.083),
            "PRONÓSTICO EXTENDIDO · 5 DÍAS",
        )
        painter.setPen(COLOR_VIOLETA)
        painter.setFont(fuente(FUENTE_APOYO, self.height() * 0.023, QFont.Weight.Bold))
        painter.drawText(
            QRectF(self.width() * 0.56, self.height() * 0.115, self.width() * 0.395, self.height() * 0.045),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self.ciudad.upper(),
        )

        x = self.width() * 0.04
        ancho = self.width() * 0.92
        separacion = self.width() * 0.012
        tarjeta_w = (ancho - separacion * 4) / 5
        tarjeta_y = self.height() * 0.18
        tarjeta_h = self.height() * 0.72
        for i, dia in enumerate(pronostico):
            fecha = datetime.strptime(dia["fecha"], "%Y-%m-%d")
            rx = x + i * (tarjeta_w + separacion)
            destacado = i == 0
            painter.setPen(QPen(COLOR_VIOLETA if destacado else QColor("#ccdce8"), 3 if destacado else 1.5))
            painter.setBrush(QColor(238, 234, 255, 242) if destacado else QColor(255, 255, 255, 244))
            painter.drawRoundedRect(QRectF(rx, tarjeta_y, tarjeta_w, tarjeta_h), 24, 24)

            painter.setPen(COLOR_VIOLETA if destacado else COLOR_TINTA)
            painter.setFont(fuente(FUENTE_APOYO, self.height() * 0.028, QFont.Weight.Bold))
            titulo = "HOY" if i == 0 else self.DIAS[fecha.weekday()]
            painter.drawText(QRectF(rx, tarjeta_y + 25, tarjeta_w, 40), Qt.AlignmentFlag.AlignCenter, titulo)
            painter.setPen(QColor("#71879a"))
            painter.setFont(fuente(FUENTE_TEXTO, self.height() * 0.016))
            painter.drawText(
                QRectF(rx, tarjeta_y + 68, tarjeta_w, 25),
                Qt.AlignmentFlag.AlignCenter,
                fecha.strftime("%d/%m"),
            )
            self._dibujar_icono_clima(
                painter,
                QRectF(rx + tarjeta_w * 0.13, tarjeta_y + tarjeta_h * 0.19, tarjeta_w * 0.74, tarjeta_h * 0.29),
                self._codigo_desde_datos(dia),
                i * 0.72,
            )
            painter.setPen(COLOR_TINTA)
            painter.setFont(fuente(FUENTE_TEXTO, self.height() * 0.018, QFont.Weight.Bold))
            painter.drawText(
                QRectF(rx + 14, tarjeta_y + tarjeta_h * 0.50, tarjeta_w - 28, tarjeta_h * 0.11),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                dia["descripcion"].upper(),
            )

            valores_y = tarjeta_y + tarjeta_h * 0.68
            valores_h = tarjeta_h * 0.21
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#f0f5fa"))
            painter.drawRoundedRect(QRectF(rx + 14, valores_y, tarjeta_w - 28, valores_h), 16, 16)

            painter.setFont(fuente(FUENTE_APOYO, self.height() * 0.047, QFont.Weight.Bold))
            painter.setPen(COLOR_AMARANTO)
            painter.drawText(
                QRectF(rx + 14, valores_y + 8, (tarjeta_w - 28) / 2, valores_h * 0.62),
                Qt.AlignmentFlag.AlignCenter,
                f'{dia["max"]:.0f}°',
            )
            painter.setPen(COLOR_CELESTE)
            painter.drawText(
                QRectF(rx + 14 + (tarjeta_w - 28) / 2, valores_y + 8, (tarjeta_w - 28) / 2, valores_h * 0.62),
                Qt.AlignmentFlag.AlignCenter,
                f'{dia["min"]:.0f}°',
            )
            painter.setFont(fuente(FUENTE_TEXTO, self.height() * 0.012, QFont.Weight.Bold))
            painter.setPen(QColor("#71879a"))
            painter.drawText(
                QRectF(rx + 14, valores_y + valores_h * 0.68, (tarjeta_w - 28) / 2, 20),
                Qt.AlignmentFlag.AlignCenter,
                "MÁX",
            )
            painter.drawText(
                QRectF(rx + 14 + (tarjeta_w - 28) / 2, valores_y + valores_h * 0.68, (tarjeta_w - 28) / 2, 20),
                Qt.AlignmentFlag.AlignCenter,
                "MÍN",
            )
        painter.restore()

    def _dibujar_espera(self, painter):
        # La apertura muestra únicamente el país completo y la cabecera.
        return


class AlmacenFotogramaWeb:
    def __init__(self):
        self.condicion = threading.Condition()
        self.fotograma = b""
        self.secuencia = 0
        self.clientes_stream = 0
        self.capturado_en = 0.0
        self.cerrado = False
        self.frame_id = 0

    def conectar_stream(self):
        with self.condicion:
            self.clientes_stream += 1

    def desconectar_stream(self):
        with self.condicion:
            self.clientes_stream = max(0, self.clientes_stream - 1)

    def tiene_clientes_stream(self):
        with self.condicion:
            return self.clientes_stream > 0

    def actualizar(self, fotograma, capturado_en=None, frame_id=None):
        with self.condicion:
            self.fotograma = fotograma
            if capturado_en is not None: self.capturado_en = capturado_en
            self.frame_id = self.secuencia + 1 if frame_id is None else frame_id
            self.secuencia += 1
            self.condicion.notify_all()

    def esperar(self, secuencia_anterior, espera=1.0):
        with self.condicion:
            self.condicion.wait_for(lambda: self.cerrado or self.secuencia != secuencia_anterior, timeout=espera)
            return self.secuencia, self.fotograma

    def esperar_detalle(self, secuencia_anterior, espera=1.0):
        with self.condicion:
            self.condicion.wait_for(lambda: self.cerrado or self.secuencia != secuencia_anterior, timeout=espera)
            return self.secuencia, self.fotograma, self.capturado_en, self.frame_id


class ServidorSalidaWeb(QObject):
    """Espejo MJPEG de la salida al aire para navegadores y browser sources."""

    def __init__(self, widget_salida, puerto=PUERTO_SALIDA_WEB, parent=None):
        super().__init__(parent)
        self.widget_salida = widget_salida
        self.widget_salida.captura_dirigida = True
        self.metricas = {"capturados": 0, "producidos": 0, "entregados": 0, "bytes_entregados": 0, "errores": 0, "captura_ms": 0.0, "jpeg_ms": 0.0, "latencia_ms": 0.0}
        self.inicio_metricas = time.perf_counter()
        self.lock_metricas = threading.Lock()
        self.limite_post = threading.BoundedSemaphore(2)
        self.puerto = puerto
        self.puertos = tuple(dict.fromkeys((puerto, PUERTO_SALIDA_VMIX)))
        self.almacen = AlmacenFotogramaWeb()
        self.servidores = []
        self.hilos = []
        self.activo = False
        self.siguiente_fotograma = 0.0
        self.cola_codificacion = queue.Queue(maxsize=1)
        self.hilo_codificador = None
        self.buffers_libres = queue.Queue(maxsize=3)
        for _ in range(3): self.buffers_libres.put(QImage())
        self.frame_id = 0
        self.metricas.update({"descartados_pendientes": 0, "intentos_reemplazo": 0, "sin_buffer": 0, "plazos_omitidos": 0})
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._capturar)

    def iniciar(self):
        almacen = self.almacen
        owner = self

        class Manejador(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            disable_nagle_algorithm = True

            def _enviar_bytes(self, codigo, contenido, tipo):
                self.send_response(codigo)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(contenido)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(contenido)

            def _enviar_json(self, codigo, payload):
                contenido = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self._enviar_bytes(codigo, contenido, "application/json; charset=utf-8")

            def _exigir_control(self):
                if _autorizacion_control_valida(self.headers.get("Authorization")):
                    return True
                return self._denegar("Control")

            def _denegar(self, realm):
                self.send_response(401)
                self.send_header("WWW-Authenticate", f'Basic realm="{realm}", charset="UTF-8"')
                self.send_header("Content-Length", "0")
                self.end_headers()
                self.close_connection = True
                return False

            def _exigir_video(self):
                if _autorizacion_control_valida(self.headers.get("Authorization")): return True
                expected = "Basic " + base64.b64encode(f"{USUARIO_VIDEO_WEB}:{CLAVE_VIDEO_WEB}".encode()).decode()
                if USUARIO_VIDEO_WEB and CLAVE_VIDEO_WEB and hmac.compare_digest(self.headers.get("Authorization", "").encode(), expected.encode()):
                    return True
                return self._denegar("Video")

            def do_GET(self):
                ruta = urllib.parse.urlparse(self.path).path
                if ruta == "/healthz":
                    age = time.perf_counter() - almacen.capturado_en if almacen.capturado_en else float("inf")
                    self._enviar_json(200 if owner.activo and age < 10 else 503, {"ok": owner.activo and age < 10})
                    return
                if ruta == "/api/metricas":
                    if not self._exigir_control(): return
                    with owner.lock_metricas:
                        result = dict(owner.metricas)
                    result["segundos"] = time.perf_counter() - owner.inicio_metricas
                    self._enviar_json(200, result)
                    return
                if ruta in {"/", "/index.html", "/frame.jpg", "/stream.mjpg"} and not self._exigir_video(): return
                if ruta in ("/", "/index.html"):
                    pagina = b"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Datos del Tiempo - Salida</title>
<style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#000}
img{display:block;width:100%;height:100%;object-fit:contain}</style></head>
<body><img src="/stream.mjpg" alt="Salida al aire"></body></html>"""
                    self._enviar_bytes(200, pagina, "text/html; charset=utf-8")
                    return
                if ruta in ("/control", "/panel", "/control/"):
                    if not self._exigir_control():
                        return
                    self._enviar_bytes(200, pagina_control_web(), "text/html; charset=utf-8")
                    return
                if ruta == "/api/estado":
                    if not self._exigir_control():
                        return
                    self._enviar_json(200, ESTADO_CONTROL_WEB.obtener())
                    return
                if ruta == "/frame.jpg":
                    _, fotograma = almacen.esperar(-1, 0.2)
                    if not fotograma:
                        self.send_error(503, "La salida todavia no esta lista")
                        return
                    self._enviar_bytes(200, fotograma, "image/jpeg")
                    return
                if ruta == "/mostrar-panel":
                    self.send_response(302)
                    self.send_header("Location", "/control")
                    self.send_header("Content-Length", "0")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return
                if ruta == "/restaurar-panel-local":
                    if not self._exigir_control(): return
                    comunicador.mostrar_panel.emit()
                    respuesta = b"Panel local restaurado"
                    self._enviar_bytes(200, respuesta, "text/plain; charset=utf-8")
                    return
                if ruta == "/stream.mjpg":
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                    self.send_header("Pragma", "no-cache")
                    self.end_headers()
                    secuencia = -1
                    almacen.conectar_stream()
                    try:
                        while owner.activo:
                            anterior = secuencia
                            secuencia, fotograma, capturado, frame_id = almacen.esperar_detalle(secuencia)
                            if secuencia == anterior: continue
                            if not fotograma:
                                continue
                            inicio_espera = PERFIL.start()
                            demora = capturado + RETARDO_SALIDA_CUADROS / FPS_SALIDA_WEB - time.perf_counter()
                            if demora > 0: time.sleep(demora)
                            PERFIL.finish("http.pacing_wait", inicio_espera)
                            inicio_http = PERFIL.start()
                            cabecera = (f"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {len(fotograma)}\r\n"
                                f"X-Frame-Id: {frame_id}\r\nX-Capture-Monotonic: {capturado:.9f}\r\n\r\n").encode("ascii")
                            self.wfile.write(cabecera + fotograma + b"\r\n")
                            PERFIL.finish("http.write", inicio_http)
                            with owner.lock_metricas:
                                owner.metricas["entregados"] += 1
                                owner.metricas["bytes_entregados"] += len(fotograma)
                    except (OSError, TimeoutError):
                        pass
                    finally:
                        almacen.desconectar_stream()
                    return
                self.send_error(404)

            def do_POST(self):
                if not owner.limite_post.acquire(blocking=False):
                    self.close_connection = True
                    self._enviar_json(429, {"ok": False, "error": "Control ocupado"})
                    return
                try:
                    self._procesar_post()
                finally:
                    owner.limite_post.release()

            def _procesar_post(self):
                ruta = urllib.parse.urlparse(self.path).path
                if ruta != "/api/control":
                    self.send_error(404)
                    return
                if not self._exigir_control():
                    return
                origin = self.headers.get("Origin")
                if origin and urllib.parse.urlsplit(origin).netloc != self.headers.get("Host"):
                    self._enviar_json(403, {"ok": False, "error": "Origin rejected"})
                    self.close_connection = True
                    return
                try:
                    longitud = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    longitud = 0
                if longitud <= 0 or longitud > MAX_CARGA_WEB * 2:
                    self.close_connection = True
                    self._enviar_json(400, {"ok": False, "error": "Tamaño de solicitud inválido"})
                    return
                try:
                    payload = json.loads(self.rfile.read(longitud).decode("utf-8"))
                    accion = str(payload.get("accion", "")).strip()
                    valor = payload.get("valor")
                    if accion in {"subir_fondo", "subir_marca"}:
                        ruta_archivo = _guardar_imagen_web(
                            payload.get("nombre", "imagen.png"), payload.get("contenido", "")
                        )
                        valor = ruta_archivo
                    acciones_validas = {
                        "inicio", "iniciar", "anterior", "siguiente", "ciudad",
                        "pronostico", "pnt", "actualizar", "subir_fondo", "subir_marca",
                    }
                    if accion not in acciones_validas:
                        raise ValueError("Acción web no reconocida")
                    if accion == "ciudad" and valor not in ORDEN_RECORRIDO:
                        raise ValueError("La ciudad seleccionada no es válida")
                    comunicador.control_web.emit(accion, valor)
                    self._enviar_json(200, {"ok": True, "mensaje": "Acción enviada al sistema"})
                except Exception as exc:
                    self._enviar_json(400, {"ok": False, "error": str(exc)})

            def log_message(self, formato, *args):
                # Never log Authorization, payloads or query strings.
                if len(args) > 1 and str(args[1]).isdigit() and int(args[1]) >= 400:
                    print(json.dumps({"event": "http_error", "status": str(args[1]),
                        "route": urllib.parse.urlsplit(self.path).path}), flush=True)

        errores = []
        for puerto in self.puertos:
            try:
                servidor = ThreadingHTTPServer((os.environ.get("HTTP_BIND", "127.0.0.1"), puerto), Manejador)
                servidor.daemon_threads = True
            except OSError as exc:
                errores.append(f"{puerto}: {exc}")
                continue
            hilo = threading.Thread(
                target=servidor.serve_forever,
                name=f"salida-web-{puerto}",
                daemon=True,
            )
            hilo.start()
            self.servidores.append(servidor)
            self.hilos.append(hilo)
        if not self.servidores:
            return "SALIDA WEB NO DISPONIBLE · " + " · ".join(errores)
        self.activo = True
        self.hilo_codificador = threading.Thread(
            target=self._codificar_fotogramas,
            name="codificador-web",
            daemon=True,
        )
        self.hilo_codificador.start()
        self.siguiente_fotograma = time.perf_counter()
        QTimer.singleShot(0, self._capturar)
        return (
            f"SALIDA WEB ACTIVA · vMix: http://127.0.0.1:{PUERTO_SALIDA_VMIX} "
            f"· control: http://127.0.0.1:{PUERTO_SALIDA_VMIX}/control "
            f"· respaldo: :{self.puerto} · {FPS_SALIDA_WEB:.2f} fps · JPEG {CALIDAD_JPEG}"
        )

    def _capturar(self):
        if not self.activo: return
        if self.widget_salida.isVisible():
            inicio = time.perf_counter()
            if hasattr(self, "_ultima_captura"):
                PERFIL.record("capture.interval", (inicio - self._ultima_captura) * 1000)
            PERFIL.record("scheduler.lateness", max(0.0, (inicio - self.siguiente_fotograma) * 1000))
            self._ultima_captura = inicio
            self.widget_salida._actualizar_fases(inicio)
            imagen = None
            if CAPTURA_DIRECTA:
                try:
                    imagen = self.buffers_libres.get_nowait()
                except queue.Empty:
                    with self.lock_metricas: self.metricas["sin_buffer"] += 1
                if imagen is not None:
                    ancho, alto = self.widget_salida.width(), self.widget_salida.height()
                    if imagen.width() != ancho or imagen.height() != alto:
                        imagen = QImage(ancho, alto, QImage.Format.Format_RGB32)
                        imagen.setDotsPerMeterX(round(self.widget_salida.logicalDpiX() / .0254))
                        imagen.setDotsPerMeterY(round(self.widget_salida.logicalDpiY() / .0254))
                    self.widget_salida.renderizar_imagen(imagen)
            else:
                inicio_grab = PERFIL.start()
                pixmap = self.widget_salida.grab()
                PERFIL.finish("capture.grab_inclusive_paint", inicio_grab)
                inicio_conversion = PERFIL.start()
                imagen = pixmap.toImage()
                PERFIL.finish("capture.pixmap_to_image", inicio_conversion)
            if imagen is not None and not imagen.isNull():
                self.frame_id += 1
                trabajo = (imagen, inicio, self.frame_id, time.perf_counter())
                # Replace the pending image; never queue an older frame behind it.
                try:
                    self.cola_codificacion.put_nowait(trabajo)
                except queue.Full:
                    try:
                        anterior = self.cola_codificacion.get_nowait()
                    except queue.Empty:
                        anterior = None
                    if anterior is not None:
                        if CAPTURA_DIRECTA: self.buffers_libres.put_nowait(anterior[0])
                        with self.lock_metricas: self.metricas["descartados_pendientes"] += 1
                    # The encoder can consume the pending image between Full and get().
                    # In that case a replacement was attempted, but no image was dropped.
                    with self.lock_metricas: self.metricas["intentos_reemplazo"] += 1
                    self.cola_codificacion.put_nowait(trabajo)
                with self.lock_metricas:
                    self.metricas["capturados"] += 1
                    self.metricas["captura_ms"] = (time.perf_counter() - inicio) * 1000
        fps = FPS_SALIDA_WEB if self.almacen.tiene_clientes_stream() else FPS_SALIDA_REPOSO
        periodo = 1.0 / fps
        ahora = time.perf_counter()
        self.siguiente_fotograma += periodo
        if self.siguiente_fotograma <= ahora:
            omitidos = int((ahora - self.siguiente_fotograma) / periodo) + 1
            self.siguiente_fotograma += omitidos * periodo
            with self.lock_metricas: self.metricas["plazos_omitidos"] += omitidos
        self.timer.start(max(1, math.ceil((self.siguiente_fotograma - ahora) * 1000)))

    def _codificar_fotogramas(self):
        while self.activo:
            try:
                trabajo = self.cola_codificacion.get(timeout=0.25)
            except queue.Empty:
                continue
            if trabajo is None: break
            imagen, capturado, frame_id, encolado = trabajo
            buffer_original = imagen
            PERFIL.record("encode.queue_wait", (time.perf_counter() - encolado) * 1000)
            inicio_jpeg = time.perf_counter()
            try:
                if imagen.width() != ANCHO_SALIDA_WEB or imagen.height() != ALTO_SALIDA_WEB:
                    inicio_escala = PERFIL.start()
                    imagen = imagen.scaled(ANCHO_SALIDA_WEB, ALTO_SALIDA_WEB,
                        Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    PERFIL.finish("encode.resize", inicio_escala)
                datos = encode_jpeg(imagen, CALIDAD_JPEG, CODIFICADOR_JPEG, PERFIL)
                if not datos: raise RuntimeError("Empty JPEG")
                self.almacen.actualizar(datos, capturado, frame_id)
                PERFIL.record("capture_to_publish", (time.perf_counter() - capturado) * 1000)
                with self.lock_metricas:
                    self.metricas["producidos"] += 1
                    self.metricas["jpeg_ms"] = (time.perf_counter() - inicio_jpeg) * 1000
                    self.metricas["latencia_ms"] = (time.perf_counter() - capturado) * 1000
            except Exception as exc:
                with self.lock_metricas: self.metricas["errores"] += 1
                print(json.dumps({"event": "encoder_error", "type": type(exc).__name__}), flush=True)
            finally:
                if CAPTURA_DIRECTA: self.buffers_libres.put_nowait(buffer_original)

    def detener(self):
        self.activo = False
        with self.almacen.condicion:
            self.almacen.cerrado = True
            self.almacen.condicion.notify_all()
        self.timer.stop()
        try:
            self.cola_codificacion.put_nowait(None)
        except queue.Full:
            pass
        for servidor in self.servidores:
            servidor.shutdown()
            servidor.server_close()
        self.servidores.clear()
        self.hilos.clear()
        if self.hilo_codificador is not None:
            self.hilo_codificador.join(timeout=1.0)
            self.hilo_codificador = None


class PantallaChroma(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EL TIEMPO EN BOLIVIA - SALIDA EN VIVO")
        self.resize(1280, 720)
        self.setMinimumSize(900, 560)
        self.mapa = MapaMeteorologico(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.mapa)
        comunicador.cambiar_ciudad.connect(self.actualizar)
        comunicador.mostrar_inicio.connect(self.mapa.mostrar_inicio)
        comunicador.alternar_vista.connect(self.mapa.mostrar_extendido)
        comunicador.alternar_pantalla.connect(self.alternar_pantalla_completa)
        comunicador.configurar_pnt.connect(self.mapa.configurar_pnt)
        comunicador.alternar_pnt.connect(self.mapa.alternar_pnt)

    def actualizar(self, ciudad, datos):
        self.mapa.mostrar_ciudad(ciudad, datos)

    def alternar_pantalla_completa(self):
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self.alternar_pantalla_completa()
        elif event.key() == Qt.Key.Key_F10:
            comunicador.mostrar_panel.emit()
        elif event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showMaximized()
        else:
            super().keyPressEvent(event)


class PanelOperador(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PANEL DE CONTROL DEL OPERADOR")
        self.resize(1100, 780)
        self.indice = -1
        self.pool = QThreadPool.globalInstance()
        self.actualizacion_activa = None
        self.errores_actualizacion = []
        self.setStyleSheet(
            "QWidget {background-color:#edf7ff;color:#17304a;font-family:Roboto;} "
            "QPushButton {background-color:#ffffff;border:2px solid #6c4bff;padding:14px;"
            "border-radius:12px;font-weight:bold;font-size:17px;min-height:30px;color:#24385b;} "
            "QPushButton:hover {background-color:#6c4bff;color:white;border-color:#6c4bff;} "
            "QPushButton:disabled {background-color:#dce5ed;color:#8b9bad;border-color:#bcc9d4;} "
            "QListWidget {background-color:#ffffff;border:1px solid #b7d4e8;padding:8px;font-size:17px;border-radius:12px;} "
            "QListWidget::item {padding:8px;border-bottom:1px solid #e3edf5;color:#1b3854;} "
            "QListWidget::item:selected {background-color:#6c4bff;color:white;border-radius:6px;}"
        )
        self.modo_extendido_web = False
        self.modo_pnt_web = False
        self._crear_interfaz()
        self._publicar_estado_web()
        self.timer_revision_cache = QTimer(self)
        self.timer_revision_cache.setInterval(60 * 60 * 1000)
        self.timer_revision_cache.timeout.connect(self.actualizar_si_corresponde)
        self.timer_revision_cache.start()

    def mostrar_panel(self):
        self.showMaximized()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        # Evita perder el control durante una emisión; F10 lo recupera.
        event.ignore()
        self.showMinimized()

    def _crear_interfaz(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(14)
        titulo = QLabel("Control de gráficos del tiempo")
        titulo.setFont(fuente(FUENTE_TITULOS, 28, QFont.Weight.Bold))
        layout.addWidget(titulo)

        self.estado = QLabel("Pantalla inicial lista. Pulse INICIAR RECORRIDO.")
        self.estado.setWordWrap(True)
        self.estado.setMinimumHeight(58)
        self.estado.setStyleSheet(
            "background:#ffffff;color:#315471;font-size:16px;font-weight:600;"
            "padding:12px;border-radius:10px;border:1px solid #cce2f1;"
        )
        layout.addWidget(self.estado)

        self.estado_web = QLabel(f"Preparando salida web en el puerto {PUERTO_SALIDA_WEB}…")
        self.estado_web.setStyleSheet(
            "background:#dff8ff;color:#075d75;font-size:15px;font-weight:800;"
            "padding:10px;border-radius:10px;border:1px solid #78d6e8;"
        )
        layout.addWidget(self.estado_web)

        self.lista = QListWidget()
        self.lista.addItems(ORDEN_RECORRIDO)
        self.lista.itemClicked.connect(lambda item: self.seleccionar(item.text()))
        layout.addWidget(self.lista)

        botones = QGridLayout()
        botones.setHorizontalSpacing(14)
        botones.setVerticalSpacing(12)
        self.btn_mapa_inicio = QPushButton("INICIO")
        self.btn_inicio = QPushButton("INICIAR RECORRIDO")
        self.btn_anterior = QPushButton("ANTERIOR")
        self.btn_siguiente = QPushButton("SIGUIENTE")
        self.btn_actualizar = QPushButton("ACTUALIZAR BASE LOCAL AHORA")
        self.btn_vista = QPushButton("PLAY PRONÓSTICO 5 DÍAS")
        self.btn_pantalla = QPushButton("Pantalla completa (F11)")
        self.btn_pnt_fondo = QPushButton("Cargar fondo PNT")
        self.btn_pnt_marca = QPushButton("Cargar imagen de marca")
        self.btn_pnt_mostrar = QPushButton("MOSTRAR / OCULTAR ESCENARIO PNT")
        self.btn_mapa_inicio.clicked.connect(self.volver_inicio)
        self.btn_inicio.clicked.connect(self.iniciar_recorrido)
        self.btn_anterior.clicked.connect(lambda: self.navegar(-1))
        self.btn_siguiente.clicked.connect(lambda: self.navegar(1))
        self.btn_actualizar.clicked.connect(lambda: self.actualizar_base_local(forzar=True))
        self.btn_vista.clicked.connect(self.alternar_vista)
        self.btn_pantalla.clicked.connect(comunicador.alternar_pantalla.emit)
        self.btn_pnt_fondo.clicked.connect(self.seleccionar_fondo_pnt)
        self.btn_pnt_marca.clicked.connect(self.seleccionar_marca_pnt)
        self.btn_pnt_mostrar.clicked.connect(self.alternar_pnt)
        botones.addWidget(self.btn_mapa_inicio, 0, 0)
        botones.addWidget(self.btn_inicio, 0, 1)
        botones.addWidget(self.btn_anterior, 1, 0)
        botones.addWidget(self.btn_siguiente, 1, 1)
        botones.addWidget(self.btn_actualizar, 2, 0, 1, 2)
        botones.addWidget(self.btn_vista, 3, 0, 1, 2)
        botones.addWidget(self.btn_pantalla, 4, 0, 1, 2)
        botones.addWidget(self.btn_pnt_fondo, 5, 0)
        botones.addWidget(self.btn_pnt_marca, 5, 1)
        botones.addWidget(self.btn_pnt_mostrar, 6, 0, 1, 2)
        layout.addLayout(botones)

    def _publicar_estado_web(self):
        ESTADO_CONTROL_WEB.actualizar(
            ciudad=ORDEN_RECORRIDO[self.indice] if 0 <= self.indice < len(ORDEN_RECORRIDO) else "",
            indice=self.indice,
            estado=self.estado.text(),
            pronostico_extendido=getattr(self, "modo_extendido_web", False),
            pnt_visible=getattr(self, "modo_pnt_web", False),
            actualizando=self.actualizacion_activa is not None,
            fondo_pnt=Path(leer_configuracion("pnt_fondo")).name if leer_configuracion("pnt_fondo") else "",
            marca_pnt=Path(leer_configuracion("pnt_marca")).name if leer_configuracion("pnt_marca") else "",
        )

    def alternar_vista(self):
        self.modo_extendido_web = not getattr(self, "modo_extendido_web", False)
        comunicador.alternar_vista.emit()
        self._publicar_estado_web()

    def alternar_pnt(self):
        self.modo_pnt_web = not getattr(self, "modo_pnt_web", False)
        comunicador.alternar_pnt.emit()
        self._publicar_estado_web()

    def ejecutar_control_web(self, accion, valor=None):
        if accion == "inicio":
            self.volver_inicio()
        elif accion == "iniciar":
            self.iniciar_recorrido()
        elif accion == "anterior":
            self.navegar(-1)
        elif accion == "siguiente":
            self.navegar(1)
        elif accion == "ciudad" and valor in ORDEN_RECORRIDO:
            self.seleccionar(valor)
        elif accion == "pronostico":
            self.alternar_vista()
        elif accion == "pnt":
            self.alternar_pnt()
        elif accion == "actualizar":
            self.actualizar_base_local(forzar=True)
        elif accion == "subir_fondo" and valor:
            guardar_configuracion("pnt_fondo", str(valor))
            comunicador.configurar_pnt.emit(str(valor), "")
            self.estado.setText(f"Fondo PNT cargado desde web: {Path(valor).name}")
            self._publicar_estado_web()
        elif accion == "subir_marca" and valor:
            guardar_configuracion("pnt_marca", str(valor))
            comunicador.configurar_pnt.emit("", str(valor))
            self.estado.setText(f"Imagen de marca PNT cargada desde web: {Path(valor).name}")
            self._publicar_estado_web()

    def volver_inicio(self):
        self.indice = -1
        self.lista.setCurrentRow(-1)
        comunicador.mostrar_inicio.emit()
        self.modo_extendido_web = False
        self.estado.setText("Mapa general de Bolivia en pantalla.")
        self._publicar_estado_web()

    def seleccionar(self, ciudad):
        self.indice = ORDEN_RECORRIDO.index(ciudad)
        self.lista.setCurrentRow(self.indice)
        self.modo_extendido_web = False
        self._consultar(ciudad)
        self._publicar_estado_web()

    def iniciar_recorrido(self):
        self.indice = 0
        self.lista.setCurrentRow(0)
        self.modo_extendido_web = False
        self._consultar(ORDEN_RECORRIDO[0])
        self._publicar_estado_web()

    def navegar(self, direccion):
        if self.indice < 0:
            self.indice = 0 if direccion >= 0 else len(ORDEN_RECORRIDO) - 1
        else:
            self.indice = (self.indice + direccion) % len(ORDEN_RECORRIDO)
        ciudad = ORDEN_RECORRIDO[self.indice]
        self.lista.setCurrentRow(self.indice)
        self.modo_extendido_web = False
        self._consultar(ciudad)
        self._publicar_estado_web()

    def actualizar_actual(self):
        fila = self.lista.currentRow()
        if fila < 0:
            fila = 0 if self.indice < 0 else self.indice
            self.lista.setCurrentRow(fila)
        self.indice = fila
        self._consultar(ORDEN_RECORRIDO[fila])

    def _consultar(self, ciudad):
        datos = leer_clima_local(ciudad)
        if not datos:
            self.estado.setText(
                f"No hay datos locales para {ciudad}.\n"
                "Pulse ACTUALIZAR BASE LOCAL AHORA para crear el respaldo."
            )
            return
        comunicador.cambiar_ciudad.emit(ciudad, datos)
        self._mostrar_estado_datos(ciudad, datos)

    def _mostrar_estado_datos(self, ciudad, datos):
        marca = datos.get("_actualizado_en", time.time())
        fecha = datetime.fromtimestamp(marca).strftime("%d/%m/%Y %H:%M")
        edad_horas = max(0.0, (time.time() - marca) / 3600)
        self.estado.setText(
            f"BASE LOCAL · Open-Meteo · guardado {fecha} · antigüedad {edad_horas:.1f} h\n"
            f"{ciudad}: actual {datos['actual']:.0f} °C  •  "
            f"mín. {datos['min']:.0f} °C  •  máx. {datos['max']:.0f} °C"
        )
        self._publicar_estado_web()

    def actualizar_si_corresponde(self):
        if cache_necesita_actualizacion():
            self.actualizar_base_local(forzar=False)

    def actualizar_base_local(self, forzar=False):
        if self.actualizacion_activa is not None:
            return
        if not forzar and not cache_necesita_actualizacion():
            return
        self.errores_actualizacion = []
        tarea = ActualizacionMasiva()
        tarea.senales.progreso.connect(self._actualizacion_progreso)
        tarea.senales.ciudad_actualizada.connect(self._ciudad_actualizada)
        tarea.senales.error.connect(self._actualizacion_error)
        tarea.senales.terminada.connect(self._actualizacion_terminada)
        self.actualizacion_activa = tarea
        self.btn_actualizar.setEnabled(False)
        self.estado.setText("Actualizando respaldo meteorológico local…")
        self._publicar_estado_web()
        self.pool.start(tarea)

    def _actualizacion_progreso(self, indice, total, ciudad):
        self.estado.setText(f"Actualizando base local {indice}/{total}: {ciudad}…")

    def _ciudad_actualizada(self, ciudad, datos):
        if 0 <= self.indice < len(ORDEN_RECORRIDO) and ORDEN_RECORRIDO[self.indice] == ciudad:
            datos_locales = leer_clima_local(ciudad)
            if datos_locales:
                comunicador.cambiar_ciudad.emit(ciudad, datos_locales)

    def _actualizacion_error(self, ciudad, detalle):
        self.errores_actualizacion.append((ciudad, detalle))

    def _actualizacion_terminada(self, correctas, total):
        self.actualizacion_activa = None
        self.btn_actualizar.setEnabled(True)
        if self.errores_actualizacion:
            self.estado.setText(
                f"Base local actualizada: {correctas}/{total}. "
                f"Se conservó el respaldo anterior para {len(self.errores_actualizacion)} localidades."
            )
        else:
            self.estado.setText(
                f"Base local actualizada correctamente: {correctas}/{total}. Próxima consulta en 12 horas."
            )
        if 0 <= self.indice < len(ORDEN_RECORRIDO):
            ciudad = ORDEN_RECORRIDO[self.indice]
            datos = leer_clima_local(ciudad)
            if datos:
                comunicador.cambiar_ciudad.emit(ciudad, datos)
                self._mostrar_estado_datos(ciudad, datos)
        self._publicar_estado_web()

    def seleccionar_fondo_pnt(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar fondo del escenario PNT",
            self.ruta_inicial_pnt(),
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if ruta:
            guardar_configuracion("pnt_fondo", ruta)
            comunicador.configurar_pnt.emit(ruta, "")
            self.estado.setText(f"Fondo PNT cargado: {Path(ruta).name}")
            self._publicar_estado_web()

    def seleccionar_marca_pnt(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen de marca o producto",
            self.ruta_inicial_pnt(),
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if ruta:
            guardar_configuracion("pnt_marca", ruta)
            comunicador.configurar_pnt.emit("", ruta)
            self.estado.setText(f"Imagen de marca PNT cargada: {Path(ruta).name}")
            self._publicar_estado_web()

    @staticmethod
    def ruta_inicial_pnt():
        fondo = leer_configuracion("pnt_fondo")
        marca = leer_configuracion("pnt_marca")
        existente = fondo or marca
        return str(Path(existente).parent) if existente else str(RAIZ)

    def _consulta_lista(self, ciudad, datos):
        guardar_clima_local(ciudad, datos)
        self._consultar(ciudad)

    def _consulta_error(self, ciudad, detalle):
        datos = leer_clima_local(ciudad)
        if datos:
            self.estado.setText(
                f"Sin conexión para actualizar {ciudad}; se mantiene el respaldo local. ({detalle})"
            )
            comunicador.cambiar_ciudad.emit(ciudad, datos)
        else:
            self.estado.setText(f"No se pudo obtener {ciudad} y aún no existe respaldo local. ({detalle})")

def main():
    configure_render_affinity(os.environ.get("RENDER_CPU_AFFINITY", ""))
    app = QApplication(sys.argv)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal_timer = QTimer(app)
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(250)
    app.setApplicationName("EL DEBER - El Tiempo en Bolivia")
    cargar_fuentes()
    inicializar_base_datos()
    app.setFont(fuente(FUENTE_TEXTO, 10))
    operador = PanelOperador()
    comunicador.mostrar_panel.connect(operador.mostrar_panel)
    comunicador.control_web.connect(operador.ejecutar_control_web)

    # Ubuntu Server usa el panel /control, por lo que no necesita dibujar una
    # segunda salida local detrás del panel. WEB_ONLY=1 deja un único mapa
    # 1920x1080 y reduce aproximadamente a la mitad el trabajo de QPainter.
    chroma = None
    if not MODO_SOLO_WEB:
        chroma = PantallaChroma()
        operador.showMaximized()
        pantallas = app.screens()
        if len(pantallas) > 1:
            chroma.setGeometry(pantallas[1].geometry())
            chroma.showFullScreen()
        else:
            chroma.showMaximized()
    else:
        operador.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

    salida_web_1920 = PantallaChroma()
    salida_web_1920.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    salida_web_1920.setFixedSize(ANCHO_SALIDA_WEB, ALTO_SALIDA_WEB)
    salida_web_1920.show()
    app.processEvents()
    servidor_web = ServidorSalidaWeb(salida_web_1920.mapa, PUERTO_SALIDA_WEB, app)
    operador.estado_web.setText(servidor_web.iniciar())
    app.aboutToQuit.connect(servidor_web.detener)
    def detener_trabajadores():
        DETENER_TRABAJADORES.set()
        pool = QThreadPool.globalInstance()
        pool.clear()
        pool.waitForDone(16000)
    app.aboutToQuit.connect(detener_trabajadores)
    app.servidor_web = servidor_web
    app.salida_web_1920 = salida_web_1920
    app.chroma_local = chroma
    operador.lista.setCurrentRow(-1)
    if not MODO_SOLO_WEB:
        operador.raise_()
    QTimer.singleShot(800, operador.actualizar_si_corresponde)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
