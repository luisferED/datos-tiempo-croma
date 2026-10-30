"""Genera activos limpios a partir del manual y los mapas entregados.

Los PNG de entrada no se modifican. La salida conserva el contorno exacto
y los límites departamentales, pero elimina etiquetas y marca de agua.
"""

from pathlib import Path
from collections import deque

import numpy as np
from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)

MAPA_COLOR = Path(r"C:\Users\bulla\Downloads\28v.png")
MAPA_LINEAS = Path(r"C:\Users\bulla\Downloads\Bolivia.png")
PAGINA_LOGO = ROOT / "tmp" / "pdfs" / "manual_marca" / "logo_page.png"
ESCALA_SALIDA = 3


def guardar_alta_res(imagen, ruta):
    tamano = (imagen.width * ESCALA_SALIDA, imagen.height * ESCALA_SALIDA)
    imagen.resize(tamano, Image.Resampling.LANCZOS).save(ruta, optimize=True)


def crear_mapa():
    color = Image.open(MAPA_COLOR).convert("RGB")
    rgb = np.asarray(color)

    # La franja inferior queda fuera para excluir la firma de paintmaps.com.
    region = rgb[:1048, :1400]
    no_blanco = np.any(region < 246, axis=2)
    ys, xs = np.where(no_blanco)
    izquierda, derecha = int(xs.min()), int(xs.max()) + 1
    arriba, abajo = int(ys.min()), int(ys.max()) + 1
    caja = (izquierda, arriba, derecha, abajo)

    recorte_color = rgb[arriba:abajo, izquierda:derecha]
    alpha = np.where(np.any(recorte_color < 246, axis=2), 255, 0).astype(np.uint8)
    # Suaviza mínimamente el borde antialias sin alterar la silueta.
    alpha_img = Image.fromarray(alpha, "L").filter(ImageFilter.GaussianBlur(0.35))

    relleno = Image.new("RGBA", alpha_img.size, (55, 192, 207, 0))
    relleno.putalpha(alpha_img)
    guardar_alta_res(relleno, OUT / "bolivia_relleno.png")

    # Máscaras departamentales obtenidas de los colores sólidos del mapa
    # entregado. Se recolorean con el celeste secundario de EL DEBER.
    semillas = {
        "pando": (550, 180),
        "beni": (700, 320),
        "la_paz": (520, 490),
        "cochabamba": (650, 600),
        "oruro": (550, 745),
        "potosi": (580, 850),
        "chuquisaca": (800, 850),
        "tarija": (780, 950),
        "santa_cruz": (990, 665),
    }
    for nombre, (sx, sy) in semillas.items():
        color_objetivo = rgb[sy, sx]
        mascara = np.all(recorte_color == color_objetivo, axis=2).astype(np.uint8) * 255
        mascara_img = Image.fromarray(mascara, "L")
        mascara_img = mascara_img.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))
        capa = Image.new("RGBA", mascara_img.size, (120, 87, 255, 0))
        capa.putalpha(mascara_img)
        guardar_alta_res(capa, OUT / f"departamento_{nombre}.png")

    lineas = Image.open(MAPA_LINEAS).convert("RGB").crop(caja)
    gris = np.asarray(lineas.convert("L")).astype(np.int16)
    oscuros = gris < 205
    visitado = np.zeros(oscuros.shape, dtype=bool)
    mayor = []
    alto, ancho = oscuros.shape
    for inicio_y, inicio_x in np.argwhere(oscuros):
        if visitado[inicio_y, inicio_x]:
            continue
        cola = deque([(int(inicio_y), int(inicio_x))])
        visitado[inicio_y, inicio_x] = True
        componente = []
        while cola:
            cy, cx = cola.popleft()
            componente.append((cy, cx))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if (
                        0 <= ny < alto and 0 <= nx < ancho
                        and oscuros[ny, nx] and not visitado[ny, nx]
                    ):
                        visitado[ny, nx] = True
                        cola.append((ny, nx))
        if len(componente) > len(mayor):
            mayor = componente

    red_lineas = np.zeros(oscuros.shape, dtype=bool)
    if mayor:
        yy, xx = zip(*mayor)
        red_lineas[np.asarray(yy), np.asarray(xx)] = True
    intensidad_base = np.clip((225 - gris) * 4, 0, 255).astype(np.uint8)
    intensidad = np.where(red_lineas, intensidad_base, 0).astype(np.uint8)
    capa_lineas = Image.new("RGBA", lineas.size, (255, 255, 255, 0))
    capa_lineas.putalpha(Image.fromarray(intensidad, "L"))
    guardar_alta_res(capa_lineas, OUT / "bolivia_limites.png")

    (OUT / "bolivia_geo.txt").write_text(
        "min_lon=-69.65\nmax_lon=-57.45\nmin_lat=-22.90\nmax_lat=-9.65\n",
        encoding="utf-8",
    )
    print("mapa", caja, relleno.size)


def crear_logo():
    pagina = Image.open(PAGINA_LOGO).convert("RGB")
    w, h = pagina.size
    zona = np.asarray(pagina.crop((int(w * 0.18), int(h * 0.26), int(w * 0.93), int(h * 0.43))))
    r, g, b = zona[:, :, 0], zona[:, :, 1], zona[:, :, 2]
    verde = (g > 85) & (g > r * 1.35) & (g > b * 1.20)
    ys, xs = np.where(verde)
    margen = 8
    x1, x2 = max(0, int(xs.min()) - margen), min(zona.shape[1], int(xs.max()) + margen + 1)
    y1, y2 = max(0, int(ys.min()) - margen), min(zona.shape[0], int(ys.max()) + margen + 1)
    mascara = (verde[y1:y2, x1:x2] * 255).astype(np.uint8)
    mascara = Image.fromarray(mascara, "L").filter(ImageFilter.GaussianBlur(0.25))
    logo = Image.new("RGBA", mascara.size, (255, 255, 255, 0))
    logo.putalpha(mascara)
    logo.save(OUT / "logo_el_deber_blanco.png", optimize=True)
    print("logo", logo.size)


if __name__ == "__main__":
    crear_mapa()
    crear_logo()
