# Prueba de integración en `odoo shell`, SOLO sobre la copia temporal. No hace commit.
# Reproduce el reenvío de Traccar con id=0 y su cruce con el cron y el historial.
import json
from datetime import timedelta
from types import SimpleNamespace

from odoo import fields
from odoo.addons.fleet_rutas.controllers import traccar_webhook

assert env.cr.dbname == 'prueba_posiciones', 'Solo se permite la base temporal prueba_posiciones'
traccar_webhook.request = SimpleNamespace(env=env)
controlador = traccar_webhook.TraccarWebhookController()
Pos = env['fleet.posicion.gps']
Sync = env['fleet.traccar.sync']
marca = env['fleet.vehicle.model.brand'].create({'name': 'PP'})
modelo = env['fleet.vehicle.model'].create({'name': 'PP', 'brand_id': marca.id})
ruta = env['fleet.ruta'].create({'name': 'PP', 'code': 'PP-RUTA', 'origen': 'A', 'destino': 'B'})
base = fields.Datetime.now().replace(microsecond=0) - timedelta(hours=1)
resultados = []


def vehiculo(n):
    return env['fleet.vehicle'].create({'model_id': modelo.id, 'license_plate': 'PP-%d' % n,
                                        'traccar_tracking_enabled': True, 'traccar_device_id': 800000 + n})


def punto(veh, i, traccar_id=0, lat=-1.25):
    return {'id': traccar_id, 'deviceId': veh.traccar_device_id, 'latitude': lat + i * 0.0001,
            'longitude': -78.62, 'speed': 10.0, 'valid': True,
            'fixTime': (base + timedelta(seconds=5 * i)).strftime('%Y-%m-%dT%H:%M:%S.250+00:00')}


def webhook(*puntos):
    for p in puntos:  # Traccar envía una posición por petición
        controlador._process_positions([p])


def cron(veh, p):
    stats = {'nuevos': 0, 'duplicados': 0, 'errores': 0}
    with env.cr.savepoint():
        Sync._procesar_posicion_ultima(pos=p, device_vehicle_map={veh.traccar_device_id: veh},
                                       vehicle_recorrido_map={}, existing_ids=set(), stats=stats)


def filas(veh):
    env.flush_all()
    env.invalidate_all()
    return Pos.search([('vehicle_id', '=', veh.id)], order='timestamp, id')


def comprobar(codigo, nombre, esperado, obtenido):
    resultados.append({'id': codigo, 'caso': nombre, 'esperado': esperado, 'obtenido': obtenido,
                       'ok': esperado == obtenido})


def caso(funcion):
    env.cr.execute('SAVEPOINT pp')
    try:
        funcion()
    except Exception as exc:
        resultados.append({'id': funcion.__name__, 'caso': 'error', 'esperado': 'sin error',
                           'obtenido': '%s: %s' % (type(exc).__name__, str(exc)[:150]), 'ok': False})
    finally:
        env.cr.execute('ROLLBACK TO SAVEPOINT pp')
        env.clear()


def reenvio():
    v = vehiculo(1)
    puntos = [punto(v, i) for i in range(10)]
    webhook(*puntos)
    comprobar('C1', '10 posiciones reenviadas con id=0', 10, len(filas(v)))
    webhook(*puntos)
    comprobar('C2', 'Reenviar las mismas 10 no duplica', 10, len(filas(v)))
    cron(v, dict(puntos[-1], id=700010))
    f = filas(v)
    comprobar('C3', 'El cron trae la última con id real: no duplica', 10, len(f))
    comprobar('C3b', 'La fila conserva el id real de Traccar', 700010, f[-1].traccar_position_id)
    rec = env['fleet.recorrido'].create({'ruta_id': ruta.id, 'vehicle_id': v.id, 'fecha_inicio': base})
    stats = {'nuevos': 0, 'duplicados': 0, 'errores': 0}
    Sync._insertar_posiciones_bulk([dict(p, id=700001 + i) for i, p in enumerate(puntos[:9])], rec, v, stats)
    f = filas(v)
    comprobar('C4', 'Importar historial de las otras 9: no duplica', 10, len(f))
    comprobar('C4b', 'Las 9 quedan asignadas al recorrido', 9, len(f.filtered(lambda p: p.recorrido_id == rec)))


def cron_primero():
    v = vehiculo(2)
    cron(v, punto(v, 0, 700200))
    webhook(punto(v, 0))
    comprobar('C5', 'Primero el cron y luego el reenvío: una sola', 1, len(filas(v)))


def ids_distintos():
    v = vehiculo(3)
    webhook(punto(v, 0, 700300), punto(v, 0, 700301))
    comprobar('C6', 'Dos id reales distintos a la misma hora: se conservan', 2, len(filas(v)))


def lugares_distintos():
    v = vehiculo(4)
    webhook(punto(v, 0), punto(v, 0, 0, lat=-1.30))
    comprobar('C7', 'Misma hora y distinto lugar sin id: se conservan', 2, len(filas(v)))


for funcion in (reenvio, cron_primero, ids_distintos, lugares_distintos):
    caso(funcion)
env.cr.rollback()
print('RESULT:' + json.dumps(resultados, ensure_ascii=False))
