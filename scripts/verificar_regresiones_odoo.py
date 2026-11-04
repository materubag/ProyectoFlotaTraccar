"""Ejecutar por stdin de `odoo shell`; cada caso revierte su transacción.

No realiza llamadas a Traccar, no elimina registros y no conserva datos de prueba.
"""
import json
from datetime import datetime, timedelta
from odoo.exceptions import UserError


class RollbackCase(Exception):
    pass


results = []
Vehicle = env['fleet.vehicle'].sudo()
Ruta = env['fleet.ruta'].sudo()
Recorrido = env['fleet.recorrido'].sudo()
Gps = env['fleet.posicion.gps'].sudo()
Sync = env['fleet.traccar.sync'].sudo()
vehicle = Vehicle.search([], limit=1)
route = Ruta.search([('total_paradas', '>=', 2)], limit=1)
assert vehicle and route, 'Se requieren un vehículo y una ruta existente para la prueba transaccional'
models = ['fleet.vehicle', 'fleet.ruta', 'fleet.parada', 'fleet.recorrido', 'fleet.posicion.gps', 'fleet.incidencia', 'fleet.metricas.recorrido']
before = {m: env[m].sudo().search_count([]) for m in models}


def make_trip():
    return Recorrido.create({'ruta_id': route.id, 'vehicle_id': vehicle.id,
                             'simulado': True, 'fecha_inicio': datetime(2026, 11, 4, 19),
                             'fecha_inicio_real': datetime(2026, 11, 4, 19),
                             'estado': 'en_curso'})


def manual_fixes():
    for second in (0, 30):
        Gps.create({'vehicle_id': vehicle.id, 'timestamp': datetime(2026, 11, 4, 19, 0, second),
                    'latitud': -1.2, 'longitud': -78.6, 'fuente': 'simulado'})


def bad_batch():
    trip = make_trip()
    free_id = max(Gps.search([], order='traccar_position_id desc', limit=1).traccar_position_id, 0) + 100000
    positions = [dict(id=free_id+i, latitude=-1.2, longitude=-78.6,
                      fixTime='2026-11-04T19:00:00Z', speed=s) for i, s in [(1, 'bad'), (2, 10)]]
    stats = dict(errores=0, nuevos=0)
    records = Sync._insertar_posiciones_bulk(positions, trip, vehicle, stats)
    assert len(records) == 1 and stats == dict(errores=1, nuevos=1), stats
    assert abs(records[0].velocidad_kmh - 18.52) < .01


def shifted_schedule():
    trip = make_trip()
    stops = route.parada_ids.sorted('secuencia')
    stops[0].hora_prevista = 8
    stops[1].hora_prevista = 8.25
    trip._inicializar_cumplimiento_paradas()
    point = Gps.create({'vehicle_id': vehicle.id, 'recorrido_id': trip.id,
                        'timestamp': datetime(2026, 11, 4, 19, 23), 'latitud': stops[1].latitud,
                        'longitud': stops[1].longitud, 'fuente': 'simulado'})
    point._verificar_paradas(trip, point)
    compliance = trip.cumplimiento_parada_ids.filtered(lambda c: c.parada_id == stops[1])
    assert compliance.cumplida and compliance.retraso_min == 8, compliance.retraso_min


def signal_tail():
    trip = make_trip()
    trip.fecha_fin_real = trip.fecha_inicio_real + timedelta(minutes=10)
    assert Sync.verificar_perdida_senal(trip.id) == 1
    assert Sync.verificar_perdida_senal(trip.id) == 0


def empty_trip_metrics():
    trip = make_trip()
    trip.fecha_fin_real = trip.fecha_inicio_real + timedelta(minutes=10)
    metric = env['fleet.metricas.recorrido'].sudo().calcular_para_recorrido(trip.id)
    assert metric.integridad_gps_pct == 0
    assert metric.duracion_gaps_seg == 600


def incomplete_configuration():
    # Patch the parameter reads, without writing to ir.config_parameter.
    from unittest.mock import patch
    with patch.object(type(Sync), '_get_traccar_service') as service:
        service.side_effect = UserError('Configure la integración')
        stats = Sync.sincronizar_ultima_posicion(vehicle_ids=Vehicle.search([('traccar_tracking_enabled', '=', True)], limit=1).ids)
    assert stats['errores'] >= 1


for name, check in [('GPS manual múltiple', manual_fixes), ('Lote con número inválido', bad_batch),
                    ('Horario de otro turno', shifted_schedule), ('Conteo e idempotencia de silencio final', signal_tail),
                    ('Integridad de recorrido sin GPS', empty_trip_metrics), ('Error global de sincronización', incomplete_configuration)]:
    try:
        with env.cr.savepoint():
            check()
            raise RollbackCase()
    except RollbackCase:
        results.append({'caso': name, 'resultado': 'aprobado'})
    except Exception as exc:
        results.append({'caso': name, 'resultado': 'fallo', 'error': type(exc).__name__ + ': ' + str(exc)[:250]})

after = {m: env[m].sudo().search_count([]) for m in models}
env.cr.rollback()
print('AUDIT_RESULT=' + json.dumps({'casos': results, 'conteos_antes': before, 'conteos_despues': after,
                                  'conteos_conservados': before == after}, ensure_ascii=True))
if any(r['resultado'] != 'aprobado' for r in results) or before != after:
    raise RuntimeError('Hay regresiones ORM pendientes; revisar AUDIT_RESULT')
