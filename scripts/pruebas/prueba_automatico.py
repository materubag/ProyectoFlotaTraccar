# Prueba de integración en `odoo shell`, SOLO sobre la copia temporal. No hace commit.
# Inicio y cierre automáticos y alertas en curso, con la hora controlada por la prueba.
import json
import math
from datetime import timedelta

from odoo import fields

assert env.cr.dbname == 'prueba_flota', 'Solo se permite la base temporal prueba_flota'
LAT0, LON0 = -1.25, -78.62
M = 6371000 * math.pi / 180
resultados = []
marca = env['fleet.vehicle.model.brand'].create({'name': 'AU'})
modelo = env['fleet.vehicle.model'].create({'name': 'AU', 'brand_id': marca.id})
Rec = env['fleet.recorrido']
# Solo deben intervenir los recorridos creados por esta prueba.
Rec.search([('estado', 'in', ('programado', 'en_curso'))]).write({'estado': 'cancelado'})
T = fields.Datetime.now().replace(microsecond=0) - timedelta(hours=3)


def minutos(n):
    return T + timedelta(minutes=n)


def comprobar(codigo, caso, esperado, obtenido):
    resultados.append({'id': codigo, 'caso': caso, 'esperado': esperado, 'obtenido': obtenido,
                       'ok': esperado == obtenido})


def programar(codigo, simulado=False):
    ruta = env['fleet.ruta'].create({'name': codigo, 'code': codigo, 'origen': 'A', 'destino': 'B'})
    for i in range(4):
        env['fleet.parada'].create({
            'name': 'P%d' % (i + 1), 'ruta_id': ruta.id, 'secuencia': i + 1, 'latitud': LAT0,
            'longitud': LON0 + i * 1000 / (M * math.cos(math.radians(LAT0))),
            'hora_prevista': 8 + i * 5 / 60, 'radio_proximidad_m': 50, 'tolerancia_min': 5})
    veh = env['fleet.vehicle'].create({'model_id': modelo.id, 'license_plate': codigo,
                                       'traccar_tracking_enabled': True})
    return Rec.create({'ruta_id': ruta.id, 'vehicle_id': veh.id, 'fecha_inicio': T,
                       'simulado': simulado})


def gps(rec, minuto, x, evaluar=True):
    """Posición como llega del teléfono: se asigna al recorrido solo si ya está en curso."""
    p = env['fleet.posicion.gps'].create({
        'vehicle_id': rec.vehicle_id.id, 'timestamp': minutos(minuto), 'latitud': LAT0,
        'longitud': LON0 + x / (M * math.cos(math.radians(LAT0))),
        'recorrido_id': rec.id if rec.estado == 'en_curso' else False, 'fuente': 'traccar'})
    if evaluar and p.recorrido_id:
        p.detectar_desviacion()
    return p


def revisar(minuto):
    Rec.revisar_recorridos(ahora=minutos(minuto))
    env.flush_all()
    env.invalidate_all()


def inc(rec, tipo):
    return env['fleet.incidencia'].search([('recorrido_id', '=', rec.id), ('tipo', '=', tipo)])


def caso(funcion):
    env.cr.execute('SAVEPOINT au')
    try:
        funcion()
    except Exception as exc:
        resultados.append({'id': funcion.__name__, 'caso': 'error', 'esperado': 'sin error',
                           'obtenido': '%s: %s' % (type(exc).__name__, str(exc)[:200]), 'ok': False})
    finally:
        env.cr.execute('ROLLBACK TO SAVEPOINT au')
        env.clear()


def inicio():
    r = programar('AU1')
    gps(r, -20, 0)
    revisar(-2)
    comprobar('A1', 'Estar en el origen 20 min antes no inicia', 'programado', r.estado)
    gps(r, -3, 0)
    gps(r, 2, 500)
    revisar(3)
    comprobar('A2', 'En el origen a su hora: inicia con la hora del GPS', ['en_curso', True],
              [r.estado, r.fecha_inicio_real == minutos(-3)])
    comprobar('A3', 'Asigna las posiciones desde la salida', 2, len(r.posicion_ids))
    comprobar('A4', 'Registra la visita al origen', True,
              r.cumplimiento_parada_ids.filtered(lambda c: c.parada_id.secuencia == 1).cumplida)


def sin_iniciar():
    r = programar('AU2')
    revisar(4)
    comprobar('S1', 'A los 4 min aún no alerta', 0, len(inc(r, 'retraso')))
    revisar(8)
    revisar(9)
    comprobar('S2', 'Sin iniciar a los 8 min: una sola alerta', 1, len(inc(r, 'retraso')))
    gps(r, 12, 0)
    revisar(12)
    comprobar('S3', 'Al iniciar tarde no se duplica la alerta del origen', ['en_curso', 1],
              [r.estado, len(inc(r, 'retraso').filtered(lambda i: i.parada_id.name == 'P1'))])


def retraso():
    r = programar('AU3')
    gps(r, 0, 0)
    revisar(1)
    gps(r, 3, 500)
    revisar(9)
    comprobar('T1', 'A 4 min de retraso aún no alerta', 0, len(inc(r, 'retraso')))
    revisar(11)
    revisar(12)
    alerta = inc(r, 'retraso')
    comprobar('T2', 'Sin llegar a la parada 2: una alerta en curso', [1, 'P2', 'en_curso'],
              [len(alerta), alerta.parada_id.name, r.estado])
    gps(r, 13, 1000)
    env.flush_all()
    comprobar('T3', 'Al llegar se actualiza la misma alerta', [1, 8], [len(inc(r, 'retraso')),
              round(inc(r, 'retraso').valor_detectado)])


def omision():
    r = programar('AU4')
    gps(r, 0, 0)
    revisar(1)
    gps(r, 10, 2000)
    revisar(10)
    omitida = inc(r, 'parada_omitida')
    comprobar('P1', 'Pasa a la parada 3 sin la 2: omisión en curso', [1, 'P2'],
              [len(omitida), omitida.parada_id.name])
    gps(r, 11, 1000)
    env.flush_all()
    comprobar('P2', 'Si luego la visita, la omisión queda resuelta', True, inc(r, 'parada_omitida').resuelta)


def cierre_destino():
    r = programar('AU5')
    for m, x in ((0, 0), ):
        gps(r, m, x)
    revisar(1)
    for m, x in ((5, 1000), (21, 3000)):
        gps(r, m, x)
    despues = gps(r, 22, 3100)
    revisar(23)
    comprobar('C1', 'Llega al destino: cierra con la hora de llegada', ['con_incidencias', True],
              [r.estado, r.fecha_fin_real == minutos(21)])
    comprobar('C2', 'Las posiciones posteriores no pertenecen al recorrido', False,
              bool(despues.recorrido_id))
    comprobar('C3', 'Llegada final tarde: una sola alerta en el destino', 1,
              len(inc(r, 'retraso').filtered(lambda i: i.parada_id.name == 'P4')))
    comprobar('C4', 'La parada omitida no se duplica al cerrar', 1, len(inc(r, 'parada_omitida')))
    comprobar('C5', 'Calcula métricas', 1,
              env['fleet.metricas.recorrido'].search_count([('recorrido_id', '=', r.id)]))
    revisar(24)
    comprobar('C6', 'Revisar de nuevo no cambia nada', 1, len(inc(r, 'parada_omitida')))


def destino_prematuro():
    r = programar('AU6')
    gps(r, 0, 0)
    revisar(1)
    gps(r, 4, 3000)
    revisar(5)
    comprobar('C7', 'Pasar por el destino sin intermedias no cierra', 'en_curso', r.estado)


def vencido():
    r = programar('AU7')
    gps(r, 0, 0)
    revisar(1)
    gps(r, 70, 500)
    revisar(80)
    comprobar('C8', 'Vencido pero con señal reciente: sigue en curso', 'en_curso', r.estado)
    revisar(90)
    comprobar('C9', 'Vencido y sin señal: se cierra como incompleto', ['con_incidencias', 1],
              [r.estado, len(inc(r, 'incompleto'))])


def senal():
    r = programar('AU10')
    gps(r, 0, 0)
    revisar(1)
    revisar(2)
    comprobar('G1', '2 min sin posiciones: aún no alerta', 0, len(inc(r, 'senal_perdida')))
    revisar(3)
    revisar(4)
    comprobar('G2', 'Sin posiciones más de 2 min: una alerta en curso', [1, 'en_curso'],
              [len(inc(r, 'senal_perdida')), r.estado])


def exclusiones():
    r = programar('AU8', simulado=True)
    gps(r, 0, 0)
    revisar(10)
    comprobar('X1', 'Un recorrido simulado no se toca', ['programado', 0], [r.estado, len(r.incidencia_ids)])
    env['ir.config_parameter'].sudo().set_param('fleet_rutas.recorridos_automaticos', '0')
    s = programar('AU9')
    gps(s, 0, 0)
    revisar(8)
    comprobar('X2', 'Desactivado: no inicia pero sí alerta', ['programado', 1],
              [s.estado, len(inc(s, 'retraso'))])


def tarea():
    cron = env.ref('fleet_rutas.ir_cron_revisar_recorridos')
    comprobar('X3', 'Tarea programada cada minuto', [1, 'minutes'],
              [cron.interval_number, cron.interval_type])


for funcion in (inicio, sin_iniciar, retraso, omision, cierre_destino, destino_prematuro, vencido,
                senal, exclusiones, tarea):
    caso(funcion)
env.cr.rollback()
print('RESULT:' + json.dumps({'casos': resultados, 'informativo': {}}, ensure_ascii=False))
