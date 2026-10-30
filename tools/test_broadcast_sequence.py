"""Prueba rápida de la realización: salida, viaje, entrada y vista de 5 días."""

import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as clima


DATOS = {
    "codigo": 3,
    "icono": "",
    "descripcion": "Nublado",
    "actual": 18.0,
    "min": 15.0,
    "max": 22.0,
    "hora": "15:00",
    "pronostico": [
        {
            "fecha": f"2026-07-0{i + 2}",
            "codigo": codigo,
            "icono": "",
            "descripcion": "Variable",
            "min": 10 + i,
            "max": 20 + i,
        }
        for i, codigo in enumerate((3, 61, 2, 0, 95))
    ],
}


def main():
    qapp = QApplication([])
    clima.cargar_fuentes()
    mapa = clima.MapaMeteorologico()
    mapa.animacion_camara.setDuration(180)
    mapa.animacion_panel.setDuration(70)
    mapa.mostrar_ciudad("Santa Cruz de la Sierra", DATOS)

    def segunda_ciudad():
        assert mapa.panel_progreso > 0.95
        mapa.mostrar_ciudad("La Paz", dict(DATOS, actual=10.0))

    def vista_extendida():
        assert mapa.ciudad == "La Paz"
        assert mapa.panel_progreso > 0.95
        assert not mapa.modo_extendido
        mapa.mostrar_extendido()

    def finalizar():
        assert mapa.modo_extendido
        assert mapa.panel_progreso > 0.95
        mapa.alternar_pnt()
        mapa.animacion_pnt.setCurrentTime(mapa.animacion_pnt.duration())
        assert mapa.pnt_progreso > 0.95
        mapa.alternar_pnt()
        mapa.animacion_pnt.setCurrentTime(mapa.animacion_pnt.duration())
        assert mapa.pnt_progreso < 0.05
        mapa.mostrar_inicio()
        mapa.animacion_panel.setCurrentTime(mapa.animacion_panel.duration())
        mapa.animacion_camara.setCurrentTime(mapa.animacion_camara.duration())
        assert mapa.datos is None
        assert abs(mapa._zoom_camara() - 0.92) < 0.01
        print(
            "secuencia_ok",
            "inicio=mapa_general",
            f"zoom={mapa._zoom_camara():.2f}",
            "extendido_solo_play=True",
            "pnt_transicion=True",
        )
        qapp.quit()

    QTimer.singleShot(320, segunda_ciudad)
    QTimer.singleShot(680, vista_extendida)
    QTimer.singleShot(920, finalizar)
    QTimer.singleShot(3000, qapp.quit)
    qapp.exec()


if __name__ == "__main__":
    main()
