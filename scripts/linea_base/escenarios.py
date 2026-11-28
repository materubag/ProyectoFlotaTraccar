# Ejecutar con `odoo shell` SOLO sobre la copia temporal. No hace commit.
import json
import math
from datetime import timedelta
from odoo import fields

assert env.cr.dbname == 'linea_base', 'Solo se permite la base temporal linea_base'
cfg_all = json.load(open('/scripts/linea_base/escenarios.json', encoding='utf-8'))
cfg = cfg_all['configuracion']
LAT0, LON0 = cfg['origen']
M_LAT = 6371000 * math.pi / 180
M_LON = M_LAT * math.cos(math.radians(LAT0))


def geo(x, y):
    return LAT0 + y / M_LAT, LON0 + x / M_LON


def interpolar(puntos, t):
    for (t0, x0, y0), (t1, x1, y1) in zip(puntos, puntos[1:]):
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0)
            return x0 + f * (x1 - x0), y0 + f * (y1 - y0)
    raise ValueError(t)


brand = env['fleet.vehicle.model.brand'].create({'name': 'LB'})
model = env['fleet.vehicle.model'].create({'name': 'LB', 'brand_id': brand.id})


def nueva_ruta(codigo):
    ruta = env['fleet.ruta'].create({'name': codigo, 'code': codigo, 'origen': 'A', 'destino': 'B',
                                     'distancia_estimada_km': 3.0, 'duracion_estimada_min': 15})
    for i, (x, minuto) in enumerate(zip(cfg['paradas_x_m'], cfg['paradas_minuto'])):
        lat, lon = geo(x, 0)
        env['fleet.parada'].create({'name': 'P%d' % (i + 1), 'ruta_id': ruta.id, 'secuencia': i + 1,
                                    'latitud': lat, 'longitud': lon, 'hora_prevista': 8 + minuto / 60,
                                    'radio_proximidad_m': cfg['radio_parada_m'],
                                    'tolerancia_min': cfg['tolerancia_min']})
    return ruta


def nuevo_recorrido(codigo, n):
    ruta = nueva_ruta(codigo)
    veh = env['fleet.vehicle'].create({'model_id': model.id, 'license_plate': codigo,
                                       'traccar_tracking_enabled': True, 'traccar_device_id': 900000 + n,
                                       'traccar_unique_id': codigo})
    rec = env['fleet.recorrido'].create({'ruta_id': ruta.id, 'vehicle_id': veh.id,
                                         'fecha_inicio': fields.Datetime.now(), 'simulado': True})
    rec.action_iniciar()
    return rec


def conteo(rec):
    out = {}
    for inc in env['fleet.incidencia'].search([('recorrido_id', '=', rec.id)]):
        out[inc.tipo] = out.get(inc.tipo, 0) + 1
    return out


resultados = []
for n, esc in enumerate(cfg_all['escenarios']):
    env.cr.execute('SAVEPOINT lb')
    try:
        rec = nuevo_recorrido('LB-' + esc['id'], n)
        # "via" es la calle real del escenario; solo se usa si el sistema admite trazados.
        if esc.get('via') and 'trazado' in rec.ruta_id._fields:
            rec.ruta_id.guardar_trazado([geo(x, y) for x, y in esc['via']], 'osrm')
        fin = esc['puntos'][-1][0]
        inicio = fields.Datetime.now() - timedelta(seconds=fin)
        rec.write({'fecha_inicio': inicio, 'fecha_inicio_real': inicio,
                   'fecha_fin_estimada': inicio + timedelta(minutes=cfg['paradas_minuto'][-1])})
        enviados = 0
        for t in range(0, fin + 1, cfg['intervalo_gps_s']):
            hueco = esc.get('hueco')
            if hueco and hueco[0] < t < hueco[1]:
                continue
            x, y = interpolar(esc['puntos'], t)
            if esc.get('atipico') and t == esc['atipico'][0]:
                y = esc['atipico'][1]
            lat, lon = geo(x, y)
            pos = env['fleet.posicion.gps'].create({
                'recorrido_id': rec.id, 'vehicle_id': rec.vehicle_id.id,
                'timestamp': inicio + timedelta(seconds=t), 'latitud': lat, 'longitud': lon,
                'velocidad_kmh': 12.0, 'fuente': 'simulado'})
            pos.detectar_desviacion()
            enviados += 1
        # Lo que hace el cron de señal mientras el recorrido sigue en curso.
        env['fleet.traccar.sync'].verificar_perdida_senal(rec.id)
        antes = conteo(rec)
        metricas = {}
        if esc.get('cerrar', True):
            rec.action_completar()
            m = env['fleet.metricas.recorrido'].search([('recorrido_id', '=', rec.id)])
            metricas = {k: m[k] for k in ('pct_cumplimiento_ruta', 'pct_puntualidad', 'pct_desviacion_ruta',
                                          'pct_paradas_cumplidas', 'integridad_gps_pct', 'distancia_real_km')}
        resultados.append({'id': esc['id'], 'nombre': esc['nombre'], 'posiciones': enviados,
                           'esperado': esc['esperado'], 'en_curso': antes, 'obtenido': conteo(rec),
                           'metricas': metricas})
    finally:
        env.cr.execute('ROLLBACK TO SAVEPOINT lb')
        env.clear()

# ---- Reproducción de defectos de integridad (se revierte) ----
defectos = {}
brand = env['fleet.vehicle.model.brand'].create({'name': 'LB2'})
model = env['fleet.vehicle.model'].create({'name': 'LB2', 'brand_id': brand.id})
env.cr.execute('SAVEPOINT lbd')
rec = nuevo_recorrido('LB-H07', 100)
otra = nueva_ruta('LB-H07B')
original = rec.ruta_id
rec.write({'ruta_id': otra.id})  # misma escritura que hace /fleet_rutas/asignar_ruta
rec.flush_recordset()
defectos['H07_ruta_de_recorrido_en_curso_modificable'] = rec.ruta_id == otra and \
    all(c.parada_id.ruta_id == original for c in rec.cumplimiento_parada_ids)
try:
    with env.cr.savepoint():
        original.parada_ids.unlink()  # lo que hace editar ruta
        env.flush_all()
    defectos['H08_editar_ruta_con_historial_falla'] = False
except Exception as exc:
    defectos['H08_editar_ruta_con_historial_falla'] = type(exc).__name__
env.cr.execute('ROLLBACK TO SAVEPOINT lbd')
env.clear()
defectos['H09_bus_sendone_existe'] = hasattr(env['bus.bus'], 'sendone')
import os
defectos['H06_secreto_webhook_configurado'] = bool(
    env['ir.config_parameter'].sudo().get_param('fleet_rutas.webhook_secret')
    or os.getenv('TRACCAR_WEBHOOK_SECRET'))
env.cr.rollback()
print('RESULT:' + json.dumps({'escenarios': resultados, 'defectos': defectos}, ensure_ascii=False))
