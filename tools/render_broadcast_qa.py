"""Renderiza las dos vistas principales para control visual local."""

import sys
from datetime import date, timedelta
from pathlib import Path

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as clima


def datos_prueba():
    iconos = ["☁️", "🌦️", "🌤️", "☀️", "⛈️"]
    descripciones = ["Nublado", "Lluvia ligera", "Parcialmente nublado", "Despejado", "Tormenta"]
    pronostico = []
    for i in range(5):
        pronostico.append(
            {
                "fecha": (date.today() + timedelta(days=i)).isoformat(),
                "icono": iconos[i],
                "descripcion": descripciones[i],
                "min": 15.2 + i,
                "max": 22.0 + i,
            }
        )
    return {
        "icono": "☁️",
        "descripcion": "Nublado",
        "actual": 18.0,
        "min": 15.2,
        "max": 22.0,
        "hora": "14:20",
        "pronostico": pronostico,
    }


def main():
    print("qa_inicio", flush=True)
    qapp = QApplication([])
    clima.cargar_fuentes()
    qa = Path(__file__).resolve().parents[1] / "tmp" / "qa"
    qa.mkdir(parents=True, exist_ok=True)

    inicio = clima.PantallaChroma()
    inicio.resize(1920, 1080)
    inicio.show()
    qapp.processEvents()
    inicio.grab().save(str(qa / "vista_inicio.png"))
    inicio.close()

    salida = clima.PantallaChroma()
    salida.resize(1920, 1080)
    salida.show()
    salida.actualizar("Santa Cruz de la Sierra", datos_prueba())
    salida.mapa.animacion_camara.stop()
    salida.mapa.animacion_panel.stop()
    salida.mapa.progreso = 1.0
    salida.mapa.panel_progreso = 1.0
    qapp.processEvents()

    salida.grab().save(str(qa / "vista_actual.png"))
    print("qa_actual", flush=True)

    salida.close()

    extendida = clima.PantallaChroma()
    extendida.resize(1920, 1080)
    extendida.show()
    extendida.actualizar("Santa Cruz de la Sierra", datos_prueba())
    extendida.mapa.animacion_camara.stop()
    extendida.mapa.animacion_panel.stop()
    extendida.mapa.progreso = 1.0
    extendida.mapa.panel_progreso = 1.0
    extendida.mapa.modo_extendido = True
    qapp.processEvents()
    extendida.grab().save(str(qa / "vista_5_dias.png"))
    print("qa_extendida", flush=True)
    extendida.close()
    operador = clima.PanelOperador()
    operador.resize(1920, 1080)
    operador.show()
    qapp.processEvents()
    operador.grab().save(str(qa / "panel_operador.png"))
    operador.close()
    pnt = clima.PantallaChroma()
    pnt.resize(1920, 1080)
    pnt.show()
    pnt.mapa.modo_pnt = True
    pnt.mapa.pnt_progreso = 1.0
    qapp.processEvents()
    pnt.grab().save(str(qa / "escenario_pnt.png"))
    pnt.close()
    extendida.deleteLater()
    salida.deleteLater()
    inicio.deleteLater()
    operador.deleteLater()
    pnt.deleteLater()
    qapp.processEvents()
    print(qa)


if __name__ == "__main__":
    main()
