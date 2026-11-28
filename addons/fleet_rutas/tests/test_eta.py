"""Proyección del vehículo y de las paradas sobre el trazado."""
import math

import pytest

from fleet_algoritmos import progresos_paradas, proyectar_en_polilinea

M = 6371000 * math.pi / 180


def p(x, y=0):
    """Punto a x metros al este e y metros al norte cerca del ecuador."""
    return (-1.25 + y / M, -78.62 + x / (M * math.cos(math.radians(-1.25))))


def test_punto_junto_a_la_linea():
    avance, separacion = proyectar_en_polilinea(*p(400, 30), [p(0), p(1000)])
    assert avance == pytest.approx(400, abs=1) and separacion == pytest.approx(30, abs=1)


def test_antes_y_despues_de_los_extremos():
    assert proyectar_en_polilinea(*p(-50), [p(0), p(1000)])[0] == pytest.approx(0, abs=1)
    assert proyectar_en_polilinea(*p(1200), [p(0), p(1000)])[0] == pytest.approx(1000, abs=1)


def test_vertice_cercano_no_resta_avance():
    avance, _ = proyectar_en_polilinea(*p(510), [p(0), p(500), p(1000)])
    assert avance == pytest.approx(510, abs=1)


def test_ida_y_vuelta_respeta_el_avance_minimo():
    linea = [p(0), p(1000), p(0, 5)]
    assert proyectar_en_polilinea(*p(300), linea)[0] == pytest.approx(300, abs=2)
    assert proyectar_en_polilinea(*p(300), linea, desde_m=1000)[0] == pytest.approx(1700, abs=2)


def test_linea_sin_segmentos():
    assert proyectar_en_polilinea(*p(0), [p(0)])[0] is None


def test_paradas_en_orden_en_una_ruta_circular():
    linea = [p(0), p(1000), p(1000, 800), p(0)]
    avances = progresos_paradas([p(0), p(1000), p(1000, 800), p(0)], linea)
    assert avances[0] == pytest.approx(0, abs=1)
    assert avances == sorted(avances)
    assert avances[-1] == pytest.approx(1000 + 800 + math.hypot(1000, 800), abs=3)
