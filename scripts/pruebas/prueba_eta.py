# Prueba de integración en `odoo shell`, SOLO sobre la copia temporal. No hace commit.
# Estimación de llegada: casos de comportamiento y error medio en viajes SIMULADOS.
import json
import math
import random
import statistics
import time
from datetime import timedelta

from odoo import fields
from odoo.addons.fleet_rutas.controllers.mobile import arrivals

assert env.cr.dbname == 'prueba_flota', 'Solo se permite la base temporal prueba_flota'
LAT0, LON0 = -1.25, -78.62
M = 6371000 * math.pi / 180
resultados, informativo = [], {}
marca = env['fleet.vehicle.model.brand'].create({'name': 'ET'})
modelo = env['fleet.vehicle.model'].create({'name': 'ET', 'brand_id': marca.id})
T = fields.Datetime.now().replace(microsecond=0) - timedelta(hours=5)


def geo(x, y=0):
    return LAT0 + y / M, LON0 + x / (M * math.cos(math.radians(LAT0)))


def comprobar(codigo, caso, esperado, obtenido):
    resultados.append({'id': codigo, 'caso': caso, 'esperado': esperado, 'obtenido': obtenido,
                       'ok': esperado == obtenido})


def preparar(codigo):
    """Cuatro paradas cada 1 km; el horario prevé 5 minutos por tramo (12 km/h)."""
    ruta = env['fleet.ruta'].create({'name': codigo, 'code': codigo, 'origen': 'A', 'destino': 'B'})
    for i in range(4):
        lat, lon = geo(i * 1000)
        env['fleet.parada'].create({'name': 'P%d' % (i + 1), 'ruta_id': ruta.id, 'secuencia': i + 1,
                                    'latitud': lat, 'longitud': lon, 'hora_prevista': 8 + i * 5 / 60,
                                    'radio_proximidad_m': 50, 'tolerancia_min': 5})
    veh = env['fleet.vehicle'].create({'model_id': modelo.id, 'license_plate': codigo,
                                       'traccar_tracking_enabled': True})
    rec = env['fleet.recorrido'].create({'ruta_id': ruta.id, 'vehicle_id': veh.id, 'fecha_inicio': T,
                                         'simulado': True})
    rec.action_iniciar(momento=T)
    return rec


def gps(rec, segundo, x, y=0):
    lat, lon = geo(x, y)
    pos = env['fleet.posicion.gps'].create({
        'recorrido_id': rec.id, 'vehicle_id': rec.vehicle_id.id,
        'timestamp': T + timedelta(seconds=segundo), 'latitud': lat, 'longitud': lon,
        'fuente': 'simulado'})
    pos.detectar_desviacion()


def estimar(rec, segundo):
    return rec.estimar_llegadas(ahora=T + timedelta(seconds=segundo))


def proxima(resultado):
    return next((f for f in resultado['paradas'] if f['estimada']), None)


def caso(funcion):
    env.cr.execute('SAVEPOINT et')
    try:
        funcion()
    except Exception as exc:
        resultados.append({'id': funcion.__name__, 'caso': 'error', 'esperado': 'sin error',
                           'obtenido': '%s: %s' % (type(exc).__name__, str(exc)[:200]), 'ok': False})
    finally:
        env.cr.execute('ROLLBACK TO SAVEPOINT et')
        env.clear()


def comportamiento():
    rec = preparar('ET1')
    comprobar('E1', 'Sin posiciones no hay estimación', ['Sin posiciones todavía', None],
              [estimar(rec, 0)['motivo'], proxima(estimar(rec, 0))])
    for s in range(0, 151, 15):
        gps(rec, s, s * 1000 / 300)
    r = estimar(rec, 150)
    p = proxima(r)
    error = abs((p['estimada'] - T - timedelta(seconds=300)).total_seconds())
    comprobar('E2', 'A velocidad prevista estima la parada 2 (error < 20 s)', ['P2', True],
              [p['nombre'], error < 20])
    comprobar('E3', 'Las siguientes conservan el intervalo del horario', [300, 600],
              [int((f['estimada'] - p['estimada']).total_seconds()) for f in r['paradas'][2:]])
    comprobar('E4', 'La primera figura visitada', 'visitada', r['paradas'][0]['estado'])
    comprobar('E5', 'Señal antigua: sin estimación', 'Señal sin actualizar', estimar(rec, 400)['motivo'])
    gps(rec, 165, 550, 400)
    comprobar('E6', 'Fuera de la ruta: sin estimación', 'El vehículo está fuera de la ruta',
              estimar(rec, 165)['motivo'])
    gps(rec, 600, 2000)
    r = estimar(rec, 600)
    comprobar('E7', 'Parada saltada figura sin visita y la próxima es la 4', ['omitida', 'P4'],
              [r['paradas'][1]['estado'], proxima(r)['nombre']])
    gps(rec, 900, 3000)
    comprobar('E8', 'En el destino no quedan estimaciones', 'El vehículo ya llegó al destino',
              estimar(rec, 900)['motivo'])


def detenido():
    rec = preparar('ET2')
    for s in range(0, 61, 15):
        gps(rec, s, s * 1000 / 300)
    for s in range(75, 601, 15):
        gps(rec, s, 200)
    p = proxima(estimar(rec, 600))
    comprobar('E9', 'Detenido: usa la velocidad prevista y anuncia atraso', [True, True],
              [200 < (p['estimada'] - T).total_seconds() - 600 < 260, p['retraso_min'] > 5])
    datos = arrivals(rec, T + timedelta(seconds=600))
    comprobar('E10', 'La app recibe solo datos públicos de las paradas',
              ['arrived', 'delay', 'estimated', 'id', 'late', 'minutes', 'name', 'scheduled', 'state'],
              sorted(datos['stops'][0]))
    comprobar('E11', 'La app marca la parada como atrasada', True, datos['stops'][1]['late'])


PERFILES = {
    'puntual': {'minutos_km': [5, 5, 5]},
    'inicio_6_min_tarde': {'minutos_km': [5, 5, 5], 'salida': 360},
    'lento': {'minutos_km': [8, 8, 8]},
    'rapido': {'minutos_km': [3.5, 3.5, 3.5]},
    'con_detenciones_60s': {'minutos_km': [4, 4, 4], 'detencion': 60},
    'congestion_tramo_2': {'minutos_km': [5, 10, 5]},
}


def precision():
    azar = random.Random(2026)
    todos, tiempos = [], []
    informativo['perfiles'] = {}
    for n, (nombre, perfil) in enumerate(PERFILES.items()):
        rec = preparar('ETP%d' % n)
        tramos, reloj = [], perfil.get('salida', 0)
        for i, minutos in enumerate(perfil['minutos_km']):
            fin = reloj + minutos * 60
            tramos.append((reloj, fin, i * 1000))
            reloj = fin + perfil.get('detencion', 0)
        for s in range(0, int(tramos[-1][1]) + 16, 15):
            x = 0
            for ini, fin, origen in tramos:
                if s >= ini:
                    x = origen + 1000 * min(1, (s - ini) / (fin - ini))
            gps(rec, s, x + azar.uniform(-5, 5), azar.uniform(-5, 5))
        inicio = time.perf_counter()
        errores = rec.evaluar_estimaciones()
        tiempos.append((time.perf_counter() - inicio) * 1000 / max(len(rec.posicion_ids), 1))
        todos += errores
        informativo['perfiles'][nombre] = {
            'muestras': len(errores),
            'mae_estimacion_min': round(statistics.mean(e[0] for e in errores) / 60, 2),
            'mae_horario_min': round(statistics.mean(e[1] for e in errores) / 60, 2)}
    cerca = [e for e in todos if e[2] <= 300]
    informativo['total'] = {
        'muestras': len(todos),
        'mae_estimacion_min': round(statistics.mean(e[0] for e in todos) / 60, 2),
        'mae_horario_min': round(statistics.mean(e[1] for e in todos) / 60, 2),
        'p90_estimacion_min': round(sorted(e[0] for e in todos)[int(.9 * len(todos))] / 60, 2),
        'mae_estimacion_a_5_min_o_menos': round(statistics.mean(e[0] for e in cerca) / 60, 2),
        'ms_por_estimacion': round(statistics.mean(tiempos), 1)}
    comprobar('M1', 'Error medio total dentro de la meta de 3 min', True,
              informativo['total']['mae_estimacion_min'] <= 3)


for funcion in (comportamiento, detenido, precision):
    caso(funcion)
env.cr.rollback()
print('RESULT:' + json.dumps({'casos': resultados, 'informativo': informativo}, ensure_ascii=False))
