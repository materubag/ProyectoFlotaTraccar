"""Reglas de confirmación de episodios de desvío."""
from datetime import datetime, timedelta

from fleet_algoritmos import episodios_desvio

INICIO = datetime(2026, 11, 28, 8, 0, 0)


def serie(patron, cada=15):
    """'.' dentro del corredor, 'x' fuera."""
    return [(INICIO + timedelta(seconds=i * cada), c == 'x') for i, c in enumerate(patron)]


def test_sin_lecturas_fuera():
    assert episodios_desvio(serie('.....')) == []
    assert episodios_desvio([]) == []


def test_un_punto_aislado_no_confirma():
    assert episodios_desvio(serie('..x..')) == []


def test_dos_lecturas_cercanas_no_confirman():
    assert episodios_desvio(serie('..xx..')) == []


def test_tres_lecturas_seguidas_confirman():
    assert episodios_desvio(serie('..xxx..')) == [(2, 4)]


def test_dos_lecturas_separadas_60_segundos_confirman():
    assert episodios_desvio(serie('.xx.', cada=60)) == [(1, 2)]
    assert episodios_desvio(serie('.xx.', cada=59)) == []


def test_dos_episodios_separados():
    assert episodios_desvio(serie('.xxx....xxx.')) == [(1, 3), (8, 10)]


def test_una_lectura_dentro_no_divide_el_episodio():
    assert episodios_desvio(serie('.xxx.xxx..')) == [(1, 7)]


def test_puntos_aislados_alternos_no_confirman():
    assert episodios_desvio(serie('x.x.x.x', cada=60)) == []


def test_episodio_abierto_al_final():
    assert episodios_desvio(serie('..xxx')) == [(2, 4)]
