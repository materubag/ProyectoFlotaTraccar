"""Regression tests run without Odoo; controller methods extracted from their AST.

These tests cover pure algorithms and parsing/authentication boundaries. They do
not replace installation, transaction or live Traccar integration tests.
"""
import ast
import hmac
import logging
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fleet_algoritmos import calcular_retraso_min, validar_parada, calcular_metricas_recorrido
from fleet_algoritmos import posicion_coincide_con_origen

ROOT = Path(__file__).resolve().parents[1]


def controller_method(name):
    tree = ast.parse((ROOT / 'controllers/traccar_webhook.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    method.decorator_list = []
    module = ast.Module(body=[method], type_ignores=[])
    namespace = {'hmac': hmac, '_logger': logging.getLogger(__name__)}
    exec(compile(ast.fix_missing_locations(module), '<controller-method>', 'exec'), namespace)
    return namespace[name]


@pytest.mark.parametrize('stored,incoming,expected', [
    ('', '', False), ('secret', '', False), ('secret', 'wrong', False),
    ('secret', 'secret', True), ('', 'anything', False),
])
def test_webhook_requires_configured_secret(stored, incoming, expected):
    obj = SimpleNamespace(_get_webhook_secret=lambda: stored)
    assert controller_method('_validate_secret')(obj, incoming) is expected


@pytest.mark.parametrize('raw,expected', [
    ('2026-10-30T08:00:00-05:00', datetime(2026, 10, 30, 13)),
    ('2026-10-30T13:00:00.000Z', datetime(2026, 10, 30, 13)),
    ('invalid', None), ('', None),
])
def test_gps_timestamp_normalizes_utc(raw, expected):
    assert controller_method('_parse_iso_datetime')(raw) == expected


def test_decimal_time_rounding_does_not_create_minute_60():
    result = calcular_retraso_min(8.9999, date(2026, 10, 30), datetime(2026, 10, 30, 9))
    assert result['retraso_min'] == 0


def test_zero_tolerance_boundary():
    result = calcular_retraso_min(8, date(2026, 10, 30), datetime(2026, 10, 30, 8, 0, 1), 0)
    assert result['es_retraso']


def test_first_arrival_is_not_replaced_by_closer_later_fix():
    first = {'latitud': 0.0001, 'longitud': 0, 'timestamp': datetime(2026, 10, 30, 8)}
    later = {'latitud': 0, 'longitud': 0, 'timestamp': datetime(2026, 10, 30, 8, 10)}
    assert validar_parada(0, 0, 50, [later, first])['posicion_cumplimiento'] == first


def test_no_gps_is_not_perfect_integrity():
    assert calcular_metricas_recorrido([], [], [])['integridad_gps_pct'] == 0


@pytest.mark.parametrize('latitude,expected', [(-1.25, True), (-1.20, False)])
def test_sync_accuracy_compares_received_data(latitude, expected):
    raw = {'latitude': -1.25, 'longitude': -78.6, 'speed': 10, 'fixTime': '2026-10-30T08:00:00-05:00'}
    assert posicion_coincide_con_origen(latitude, -78.6, 18.52, datetime(2026, 10, 30, 13), raw) is expected


@pytest.mark.parametrize('hour,tolerance', [(-1, 5), (24, 5), (8, -1)])
def test_invalid_schedule_rejected(hour, tolerance):
    with pytest.raises(ValueError):
        calcular_retraso_min(hour, date(2026, 10, 30), datetime(2026, 10, 30, 8), tolerance)
