# Prueba de integración en `odoo shell`, SOLO sobre la copia temporal. No hace commit.
# Reglas de desvío y de recorrido incompleto con el ORM real.
import json
import math
import time
from datetime import timedelta

from odoo import fields

assert env.cr.dbname == 'prueba_flota', 'Solo se permite la base temporal prueba_flota'
LAT0, LON0 = -1.25, -78.62
M = 6371000 * math.pi / 180
resultados, informativo = [], {}
marca = env['fleet.vehicle.model.brand'].create({'name': 'RG'})
modelo = env['fleet.vehicle.model'].create({'name': 'RG', 'brand_id': marca.id})


def geo(x, y=0):
    return LAT0 + y / M, LON0 + x / (M * math.cos(math.radians(LAT0)))


def comprobar(codigo, caso, esperado, obtenido):
    resultados.append({'id': codigo, 'caso': caso, 'esperado': esperado, 'obtenido': obtenido,
                       'ok': esperado == obtenido})


def preparar(codigo, xs=(0, 1000, 2000, 3000)):
    ruta = env['fleet.ruta'].create({'name': codigo, 'code': codigo, 'origen': 'A', 'destino': 'B'})
    for i, x in enumerate(xs):
        punto = x if isinstance(x, tuple) else (x, 0)
        lat, lon = geo(*punto)
        env['fleet.parada'].create({'name': 'P%d' % i, 'ruta_id': ruta.id, 'secuencia': i + 1,
                                    'latitud': lat, 'longitud': lon, 'hora_prevista': 8 + i / 12,
                                    'radio_proximidad_m': 50})
    veh = env['fleet.vehicle'].create({'model_id': modelo.id, 'license_plate': codigo,
                                       'traccar_tracking_enabled': True})
    rec = env['fleet.recorrido'].create({'ruta_id': ruta.id, 'vehicle_id': veh.id,
                                         'fecha_inicio': fields.Datetime.now()})
    rec.action_iniciar()
    inicio = fields.Datetime.now() - timedelta(seconds=900)
    rec.write({'fecha_inicio': inicio, 'fecha_inicio_real': inicio})
    return rec, inicio


def posicion(rec, inicio, segundo, x, y=0, evaluar=True):
    lat, lon = geo(x, y)
    p = env['fleet.posicion.gps'].create({
        'recorrido_id': rec.id, 'vehicle_id': rec.vehicle_id.id,
        'timestamp': inicio + timedelta(seconds=segundo), 'latitud': lat, 'longitud': lon,
        'fuente': 'simulado'})
    if evaluar:
        p.detectar_desviacion()
    return p


def incidencias(rec, tipo):
    env.flush_all()
    return env['fleet.incidencia'].search([('recorrido_id', '=', rec.id), ('tipo', '=', tipo)])


def caso(funcion):
    env.cr.execute('SAVEPOINT rg')
    try:
        funcion()
    except Exception as exc:
        resultados.append({'id': funcion.__name__, 'caso': 'error', 'esperado': 'sin error',
                           'obtenido': '%s: %s' % (type(exc).__name__, str(exc)[:200]), 'ok': False})
    finally:
        env.cr.execute('ROLLBACK TO SAVEPOINT rg')
        env.clear()


def episodios():
    rec, t = preparar('RG1')
    fuera = [posicion(rec, t, 100, 400), posicion(rec, t, 115, 450, 150)]
    comprobar('D1', 'Un punto aislado no genera incidencia', 0, len(incidencias(rec, 'desviacion')))
    posicion(rec, t, 130, 500, 250)
    comprobar('D2', 'Dos puntos en 15 s todavía no', 0, len(incidencias(rec, 'desviacion')))
    tercero = posicion(rec, t, 145, 550, 300)
    inc = incidencias(rec, 'desviacion')
    comprobar('D3', 'El tercero crea una incidencia desde el inicio del episodio', [1, True],
              [len(inc), inc.timestamp == fuera[1].timestamp])
    posicion(rec, t, 160, 600, 450)
    inc = incidencias(rec, 'desviacion')
    comprobar('D4', 'Se actualiza la distancia máxima y la severidad', [1, 450, 'alta'],
              [len(inc), round(inc.valor_detectado), inc.severidad])
    rec.posicion_ids.detectar_desviacion()
    comprobar('D5', 'Reprocesar no duplica', 1, len(incidencias(rec, 'desviacion')))
    inc.action_resolver()
    rec.posicion_ids.detectar_desviacion()
    comprobar('D6', 'Una incidencia resuelta no se vuelve a crear', 1, len(incidencias(rec, 'desviacion')))
    comprobar('D7', 'El recorrido figura con desvío', True, rec.tiene_desviacion)
    for s, x in ((175, 700), (190, 750), (205, 800)):
        posicion(rec, t, s, x)
    for s, x in ((300, 1500), (315, 1550), (330, 1600)):
        posicion(rec, t, s, x, 200)
    comprobar('D8', 'Un segundo episodio crea otra incidencia', 2, len(incidencias(rec, 'desviacion')))


def desorden():
    rec, t = preparar('RG2')
    for s, x in ((145, 550), (115, 450), (130, 500)):
        posicion(rec, t, s, x, 250)
    comprobar('O1', 'Posiciones que llegan desordenadas: una incidencia', 1,
              len(incidencias(rec, 'desviacion')))
    posicion(rec, t, 100, 400, 250)
    comprobar('O2', 'Una posición tardía anterior no duplica', 1, len(incidencias(rec, 'desviacion')))


def aislado_cumple():
    rec, t = preparar('RG3')
    for s in range(0, 901, 15):
        posicion(rec, t, s, s * 3000 / 900, 150 if s == 450 else 0)
    rec.action_completar()
    env.flush_all()
    metrica = env['fleet.metricas.recorrido'].search([('recorrido_id', '=', rec.id)])
    comprobar('C1', 'Un punto erróneo no quita el cumplimiento', [100.0, False, True],
              [metrica.pct_cumplimiento_ruta, rec.tiene_desviacion, metrica.pct_desviacion_ruta > 0])


def cierre(codigo, visitadas):
    rec, t = preparar(codigo)
    for i, x in enumerate(visitadas):
        posicion(rec, t, 200 * i, x)
    rec.action_completar()
    return [len(incidencias(rec, 'incompleto')), len(incidencias(rec, 'parada_omitida'))]


def incompleto():
    comprobar('I1', 'Omite una intermedia y llega: sin "incompleto"', [0, 1], cierre('RG4', (0, 1000, 3000)))
    comprobar('I2', 'No llega al destino: incompleto', [1, 1], cierre('RG5', (0, 1000, 2000)))
    comprobar('I3', 'Sin posiciones: incompleto', [1, 4], cierre('RG6', ()))


def circular():
    xs = (0, (1000, 0), (1000, 800), 0)
    rec, t = preparar('RG7', xs)
    posicion(rec, t, 0, 0)
    destino = rec.paradas_del_recorrido()[-1]
    registro = rec.cumplimiento_parada_ids.filtered(lambda c: c.parada_id == destino)
    comprobar('K1', 'Ruta circular: al salir no se da por llegado', False, registro.cumplida)
    posicion(rec, t, 300, 1000)
    posicion(rec, t, 600, 1000, 800)
    posicion(rec, t, 900, 0)
    comprobar('K2', 'Al volver se registra la llegada', [True, True],
              [registro.cumplida, registro.timestamp_llegada == t + timedelta(seconds=900)])
    rec.action_completar()
    comprobar('K3', 'Circular completa: sin "incompleto"', 0, len(incidencias(rec, 'incompleto')))


def costo():
    rec, t = preparar('RG8')
    lat, lon = geo(0, 0)
    env.cr.execute('''INSERT INTO fleet_posicion_gps (recorrido_id, vehicle_id, timestamp, latitud,
        longitud, velocidad_kmh, velocidad, es_desviacion, fuente, create_uid, create_date, write_uid, write_date)
        SELECT %s, %s, %s + g * interval '0.05 second', %s, %s, 0, 0, false, 'simulado', 1, now(), 1, now()
        FROM generate_series(1, 10000) g''', [rec.id, rec.vehicle_id.id, t, lat, lon])
    env.invalidate_all()
    for nombre, y in (('dentro', 0), ('fuera', 300)):
        tiempos = []
        for i in range(10):
            env.invalidate_all()
            inicio = time.perf_counter()
            posicion(rec, t, 600 + i + (100 if y else 0), 400, y)
            env.flush_all()
            tiempos.append((time.perf_counter() - inicio) * 1000)
        informativo['ingesta_ms_max_10000_%s' % nombre] = round(max(tiempos))


for funcion in (episodios, desorden, aislado_cumple, incompleto, circular, costo):
    caso(funcion)
env.cr.rollback()
print('RESULT:' + json.dumps({'casos': resultados, 'informativo': informativo}, ensure_ascii=False))
