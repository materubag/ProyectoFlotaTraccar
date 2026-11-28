"""Pruebas de los algoritmos del trazado vial y la distancia geodésica."""
from datetime import datetime, timedelta

import pytest

from fleet_algoritmos import (calcular_distancia_total_km, distancia_geodesica_m,
                              elegir_secuencia_minima,
                              haversine_distance_m, limpiar_posiciones_gps,
                              longitud_polilinea_m, simplificar_polilinea)

M_LAT = 110574.0  # metros por grado de latitud cerca del ecuador
INICIO = datetime(2026, 11, 28, 8, 0, 0)


def fijo(segundo, norte_m=0.0, este_m=0.0, precision=5.0):
    return {'latitud': -1.25 + norte_m / M_LAT, 'longitud': -78.62 + este_m / 111320.0,
            'timestamp': INICIO + timedelta(seconds=segundo), 'precision_m': precision}


def test_geodesica_un_grado_meridional_en_el_ecuador():
    assert distancia_geodesica_m(-0.5, -78, 0.5, -78) == pytest.approx(110574.3, abs=1)


def test_geodesica_un_grado_sobre_el_ecuador():
    assert distancia_geodesica_m(0, 0, 0, 1) == pytest.approx(111319.49, abs=0.1)


def test_geodesica_mismo_punto_es_cero():
    assert distancia_geodesica_m(-1.25, -78.62, -1.25, -78.62) == 0


def test_geodesica_antipodas_usa_respaldo():
    assert distancia_geodesica_m(0, 0, 0, 180) == pytest.approx(haversine_distance_m(0, 0, 0, 180), rel=.01)


def test_distancia_total_es_geodesica():
    puntos = [{'latitud': -0.5, 'longitud': -78}, {'latitud': 0.5, 'longitud': -78}]
    assert calcular_distancia_total_km(puntos) == pytest.approx(110.5743, abs=.001)


def test_longitud_de_polilinea_vacia_o_de_un_punto():
    assert longitud_polilinea_m([]) == 0
    assert longitud_polilinea_m([(-1.25, -78.62)]) == 0


def test_simplificar_elimina_puntos_alineados_y_conserva_esquinas():
    recta = [(-1.25, -78.62 + i * 0.0001) for i in range(11)]
    esquina = recta + [(-1.25 + i * 0.0001, recta[-1][1]) for i in range(1, 11)]
    assert simplificar_polilinea(esquina, 5) == [esquina[0], recta[-1], esquina[-1]]


def test_simplificar_conserva_un_circuito_cerrado():
    circuito = [(-1.25, -78.62), (-1.249, -78.62), (-1.249, -78.619), (-1.25, -78.62)]
    assert simplificar_polilinea(circuito, 5) == circuito


def test_simplificar_polilinea_larga_sin_recursion():
    zigzag = [(-1.25 + (i % 2) * 0.001, -78.62 + i * 0.0001) for i in range(3000)]
    assert len(simplificar_polilinea(zigzag, 5)) == 3000


def test_limpieza_descarta_imprecisos_saltos_y_repetidos():
    puntos = [fijo(0), fijo(10, este_m=60), fijo(20, este_m=62),  # repetido: a 2 m
              fijo(30, este_m=120, precision=80),                # impreciso
              fijo(40, norte_m=5000, este_m=180),                # salto imposible
              fijo(50, este_m=240)]
    limpios = limpiar_posiciones_gps(puntos)
    assert len(limpios) == 3
    assert limpios[-1][1] == pytest.approx(fijo(50, este_m=240)['longitud'])


def test_limpieza_acepta_precision_desconocida_y_ordena_por_hora():
    puntos = [fijo(30, este_m=200, precision=0), fijo(0, precision=0)]
    assert limpiar_posiciones_gps(puntos)[0][1] == pytest.approx(-78.62)


def test_limpieza_descarta_un_primer_punto_erroneo():
    puntos = [fijo(0, norte_m=9000), fijo(10), fijo(20, este_m=60), fijo(30, este_m=120)]
    assert len(limpiar_posiciones_gps(puntos)) == 3


def test_secuencia_minima_evita_la_calzada_contraria():
    # Parada 1: candidato 0. Parada 2: 1 (sentido contrario) o 2 (correcto). Parada 3: 3.
    matriz = [[0, 9000, 600, 1500], [9000, 0, 20, 900], [9000, 20, 0, 900], [0, 0, 0, 0]]
    assert elegir_secuencia_minima([1, 2, 1], matriz) == [0, 2, 3]


def test_secuencia_minima_mira_el_recorrido_completo():
    # El tramo inicial más corto (hacia 1) obliga a un rodeo después.
    matriz = [[0, 100, 200, None], [None, 0, None, 9000], [None, None, 0, 300], [None, None, None, 0]]
    assert elegir_secuencia_minima([1, 2, 1], matriz) == [0, 2, 3]


def test_secuencia_minima_sin_camino():
    assert elegir_secuencia_minima([1, 1], [[0, None], [None, 0]]) is None
    assert elegir_secuencia_minima([], []) is None
