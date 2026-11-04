"""Regresiones de la revisión del PDF: métodos reales y entradas controladas."""
import ast
import json
import logging
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional
from unittest.mock import MagicMock

import pytest
import pytz
from fleet_algoritmos import calcular_metricas_recorrido
from traccar_service import TraccarService

MODELS = Path(__file__).resolve().parents[1] / 'models'


def method(file, name):
    tree = ast.parse((MODELS / file).read_text(encoding='utf-8'))
    node = next(n for cls in tree.body if isinstance(cls, ast.ClassDef)
                for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    namespace = dict(datetime=datetime, timedelta=timedelta, pytz=pytz, json=json,
                     List=List, Dict=Dict, Optional=Optional, _logger=logging.getLogger(__name__),
                     fields=SimpleNamespace(Datetime=SimpleNamespace(now=lambda: datetime(2026, 11, 4, 8))),
                     UserError=RuntimeError)
    # Relative imports in methods resolve to the real pure algorithm module.
    import fleet_algoritmos
    namespace['__name__'] = 'audit_models.method'
    import sys
    sys.modules['audit_models.fleet_algoritmos'] = fleet_algoritmos
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(MODELS / file), 'exec'), namespace)
    return namespace[name]


def test_history_preserves_different_ids_at_same_time():
    positions = [dict(id=i, latitude=-1.2, longitude=-78.6, fixTime='2026-11-04T13:00:00Z') for i in (1, 2)]
    actual = method('fleet_traccar_sync.py', '_filtrar_posiciones_duplicadas')(positions)
    assert [p['id'] for p in actual] == [1, 2]


def test_history_preserves_valid_zero_coordinates():
    point = dict(id=1, latitude=0, longitude=0, valid=True, fixTime='2026-11-04T13:00:00Z')
    assert method('fleet_traccar_sync.py', '_filtrar_posiciones_duplicadas')([point]) == [point]


def test_history_deduplicates_id_even_with_different_timestamps():
    points = [dict(id=7, latitude=-1, longitude=-78, fixTime=t) for t in ('2026-11-04T13:00:00Z', '2026-11-04T13:00:01Z')]
    assert len(method('fleet_traccar_sync.py', '_filtrar_posiciones_duplicadas')(points)) == 1


def test_bulk_bad_number_does_not_discard_good_position():
    model = MagicMock()
    model.sudo.return_value = model
    model.create.side_effect = lambda vals: SimpleNamespace(**vals)
    env = MagicMock()
    env.__getitem__.return_value = model
    env.cr.savepoint.side_effect = nullcontext
    parser = method('fleet_traccar_sync.py', '_parse_iso_datetime')
    obj = SimpleNamespace(env=env, _parse_iso_datetime=parser)
    points = [dict(id=i, deviceId=1, latitude=-1, longitude=-78,
                   fixTime='2026-11-04T13:00:00Z', speed=s) for i, s in [(1, 'bad'), (2, 10)]]
    stats = {'errores': 0, 'nuevos': 0}
    result = method('fleet_traccar_sync.py', '_insertar_posiciones_bulk')(
        obj, points, SimpleNamespace(id=1), SimpleNamespace(id=1), stats)
    assert len(result) == 1
    assert stats == {'errores': 1, 'nuevos': 1}


def test_signal_loss_returns_number_of_created_tail_incidents():
    rec = SimpleNamespace(fecha_inicio_real=datetime(2026, 11, 4, 8),
                          fecha_fin_real=datetime(2026, 11, 4, 8, 10))
    rec.exists = lambda: True
    models = {name: MagicMock() for name in ['fleet.recorrido', 'fleet.posicion.gps', 'fleet.incidencia']}
    for model in models.values():
        model.sudo.return_value = model
    models['fleet.recorrido'].browse.return_value = rec
    models['fleet.posicion.gps'].search.return_value = []
    models['fleet.incidencia'].search_count.return_value = 0
    obj = SimpleNamespace(env=models, _check_sync_access=lambda: None)
    assert method('fleet_traccar_sync.py', 'verificar_perdida_senal')(obj, 1) == 1


def test_integrity_includes_start_and_end_of_trip():
    start = datetime(2026, 11, 4, 8)
    points = [dict(latitud=-1, longitud=-78, timestamp=start + timedelta(minutes=m)) for m in (4, 5)]
    import inspect
    window = dict(inicio_recorrido=start, fin_recorrido=start + timedelta(minutes=10)) if 'inicio_recorrido' in inspect.signature(calcular_metricas_recorrido).parameters else {}
    result = calcular_metricas_recorrido(points, [], [], **window)
    assert result['integridad_gps_pct'] == 10
    assert result['num_gaps'] == 2


def test_history_does_not_silently_truncate_received_positions():
    svc = TraccarService('http://example.test', 'user', 'password')
    points = [dict(id=i, fixTime='2026-11-04T13:00:00Z') for i in range(11)]
    svc._get = MagicMock(return_value=points)
    actual = svc.get_position_history(1, datetime(2026, 11, 4), datetime(2026, 11, 5), max_records=10)
    assert len(actual) == 11


class Records(list):
    def __getitem__(self, key):
        result = super().__getitem__(key)
        return Records(result) if isinstance(key, slice) else result

    def __getattr__(self, key):
        return getattr(self[0], key)

    def sorted(self, key):
        return Records(sorted(self, key=lambda r: getattr(r, key)))

    def filtered(self, predicate):
        return Records(r for r in self if predicate(r))


def test_stop_schedule_follows_assigned_shift():
    first = SimpleNamespace(hora_prevista=8, secuencia=1)
    stop = SimpleNamespace(hora_prevista=8.25, secuencia=2, latitud=-1, longitud=-78,
                           radio_proximidad_m=50, tolerancia_min=5, name='Parada')
    compliance = SimpleNamespace(cumplida=False, parada_id=stop, timestamp_llegada=False)
    compliance.write = lambda vals: compliance.__dict__.update(vals)
    rec = SimpleNamespace(id=1, name='Turno de tarde', fecha_inicio=datetime(2026, 11, 4, 19),
                          ruta_id=SimpleNamespace(zona_horaria='America/Guayaquil', parada_ids=Records([first, stop])),
                          cumplimiento_parada_ids=Records([compliance]))
    pos = SimpleNamespace(id=1, latitud=-1, longitud=-78, timestamp=datetime(2026, 11, 4, 19, 23))
    method('fleet_posicion_gps.py', '_verificar_paradas')(SimpleNamespace(env=MagicMock()), rec, pos)
    assert compliance.retraso_min == 8


def test_missing_credentials_report_configuration_instead_of_network_error():
    icp = MagicMock()
    icp.sudo.return_value = icp
    icp.get_param.side_effect = lambda key, default='': default
    obj = SimpleNamespace(env={'ir.config_parameter': icp})
    with pytest.raises(RuntimeError, match='Configure'):
        method('fleet_traccar_sync.py', '_get_traccar_service')(obj)


@pytest.mark.parametrize('stats,message', [({}, 'API failure'), ({'errores': 1}, '')])
def test_sync_errors_cannot_be_reported_as_success(stats, message):
    log = MagicMock()
    log.sudo.return_value = log
    method('fleet_traccar_sync.py', '_finalizar_log')(SimpleNamespace(), log, stats, message)
    values = log.write.call_args.args[0]
    assert values['estado'] == 'error'
    assert values['registros_error'] >= 1


def test_empty_trip_records_full_signal_gap():
    start = datetime(2026, 11, 4, 8)
    res = calcular_metricas_recorrido([], [], [], inicio_recorrido=start, fin_recorrido=start + timedelta(minutes=10))
    assert res['integridad_gps_pct'] == 0
    assert res['duracion_gaps_seg'] == 600
    assert res['num_gaps'] == 1
