# `odoo shell` SOLO sobre la copia temporal: crea volúmenes simulados y un usuario de prueba.
import json
import os
import secrets
import time
from datetime import timedelta
from odoo import fields

assert env.cr.dbname == 'linea_base', 'Solo se permite la base temporal linea_base'
password = secrets.token_urlsafe(24)
grupos = [env.ref('base.group_user').id, env.ref('base.group_system').id,
          env.ref('fleet.fleet_group_manager').id, env.ref('fleet_rutas.group_fleet_admin').id]
env['res.users'].with_context(no_reset_password=True).create(
    {'name': 'Medicion', 'login': 'lb_medicion', 'password': password, 'groups_id': [(6, 0, grupos)]})

base = env['fleet.recorrido'].search([('ruta_id.parada_ids', '!=', False)], limit=1)
parada = base.ruta_id.parada_ids.sorted('secuencia')[0]
volumenes = {}
ingesta = {}
for n in (100, 1000, 10000):
    inicio = fields.Datetime.now() - timedelta(seconds=n * 5 + 600)
    rec = env['fleet.recorrido'].create({'ruta_id': base.ruta_id.id, 'vehicle_id': base.vehicle_id.id,
                                         'fecha_inicio': inicio, 'simulado': True})
    rec.write({'estado': 'completado', 'fecha_inicio_real': inicio,
               'fecha_fin_real': inicio + timedelta(seconds=n * 5)})
    rec.flush_recordset()
    env.cr.execute('''INSERT INTO fleet_posicion_gps
        (recorrido_id, vehicle_id, timestamp, latitud, longitud, velocidad_kmh, velocidad,
         es_desviacion, fuente, create_uid, create_date, write_uid, write_date)
        SELECT %s, %s, %s + (g * interval '5 second'), %s + g * 0.0000001, %s, 20, 20,
               false, 'simulado', 1, now(), 1, now() FROM generate_series(1, %s) g''',
                   (rec.id, base.vehicle_id.id, inicio, parada.latitud, parada.longitud, n))
    env.invalidate_all()
    volumenes[str(n)] = rec.id

    # Costo de calcular métricas
    tiempos = []
    for _ in range(10):
        env.invalidate_all()
        t = time.perf_counter()
        env['fleet.metricas.recorrido'].calcular_para_recorrido(rec.id)
        env.flush_all()
        tiempos.append((time.perf_counter() - t) * 1000)
    # Costo de ingerir una posición nueva cuando el recorrido ya tiene n
    t_ingesta = []
    for i in range(20):
        env.invalidate_all()
        t = time.perf_counter()
        pos = env['fleet.posicion.gps'].create({
            'recorrido_id': rec.id, 'vehicle_id': base.vehicle_id.id,
            'timestamp': inicio + timedelta(seconds=n * 5 + i), 'latitud': parada.latitud,
            'longitud': parada.longitud, 'fuente': 'simulado'})
        pos.detectar_desviacion()
        env.flush_all()
        t_ingesta.append((time.perf_counter() - t) * 1000)
    ingesta[str(n)] = {'metricas_ms': tiempos, 'ingesta_ms': t_ingesta}
env.cr.commit()
fd = os.open('/tmp/lb_cred.json', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    json.dump({'password': password, 'volumenes': volumenes}, f)
print('RESULT:' + json.dumps(ingesta))
