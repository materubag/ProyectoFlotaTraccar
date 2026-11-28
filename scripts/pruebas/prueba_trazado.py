# Prueba de integración en `odoo shell`, SOLO sobre la copia temporal. No hace commit.
# OSRM se sustituye por respuestas simuladas; con OSRM_REAL=1 se consulta además el servicio.
import json
import os
import time
from datetime import timedelta
from types import SimpleNamespace

from odoo import fields
from odoo.exceptions import UserError
from odoo.addons.fleet_rutas.models import fleet_trazado

assert env.cr.dbname == 'prueba_flota', 'Solo se permite la base temporal prueba_flota'
resultados, informativo = [], {}


def comprobar(codigo, caso, esperado, obtenido):
    resultados.append({'id': codigo, 'caso': caso, 'esperado': esperado, 'obtenido': obtenido,
                       'ok': esperado == obtenido})


def falla(funcion):
    try:
        funcion()
        return False
    except UserError:
        return True


real = env['fleet.ruta'].search([('parada_ids', '!=', False)])
if os.environ.get('OSRM_REAL') == '1':
    for r in real[:3]:
        try:
            p = r.generar_trazado_osrm()
            informativo[r.name] = {k: p[k] for k in ('distancia_km', 'distancia_recta_km', 'paradas_lejanas')}
            informativo[r.name]['puntos'] = len(p['puntos'])
        except UserError as exc:
            informativo[r.name] = {'error': exc.args[0]}

ruta = env['fleet.ruta'].create({'name': 'PT', 'code': 'PT-1', 'origen': 'A', 'destino': 'B',
                                 'distancia_estimada_km': 1.0})
base_lat, base_lon = -1.25, -78.62
for i, este in enumerate((0, 0.01)):
    env['fleet.parada'].create({'name': 'P%d' % (i + 1), 'ruta_id': ruta.id, 'secuencia': i + 1,
                                'latitud': base_lat, 'longitud': base_lon + este, 'hora_prevista': 8 + i / 6})
comprobar('R1', 'Sin trazado usa las rectas entre paradas', 2, len(ruta.puntos_referencia()))

curva = [[base_lon, base_lat], [base_lon, base_lat + .003], [base_lon + .01, base_lat + .003],
         [base_lon + .01, base_lat]]
original = fleet_trazado.requests.get
fleet_trazado.requests.get = lambda *a, **k: SimpleNamespace(
    raise_for_status=lambda: None,
    json=lambda: {'code': 'Ok', 'routes': [{'geometry': {'coordinates': curva}}]})
propuesta = ruta.generar_trazado_osrm()
comprobar('R2', 'La propuesta OSRM no se guarda sola', False, ruta.trazado_vigente)
comprobar('R3', 'La propuesta convierte lon,lat a lat,lon', [base_lat + .003, base_lon], propuesta['puntos'][1])
ruta.guardar_trazado(propuesta['puntos'], 'osrm')
comprobar('R4', 'Guardar activa el trazado', [True, 4], [ruta.trazado_vigente, len(ruta.puntos_referencia())])
comprobar('R5', 'Actualiza la distancia estimada', propuesta['distancia_km'], round(ruta.distancia_estimada_km, 3))
fleet_trazado.requests.get = lambda *a, **k: SimpleNamespace(
    raise_for_status=lambda: None, json=lambda: {'code': 'NoRoute'})
comprobar('R6', 'Error de OSRM avisa y conserva el trazado', [True, True],
          [falla(ruta.generar_trazado_osrm), ruta.trazado_vigente])
fleet_trazado.requests.get = original
parada = ruta.parada_ids.sorted('secuencia')[1]
parada.longitud = base_lon + .011
comprobar('R7', 'Cambiar una parada deja el trazado sin vigencia', [False, 2],
          [ruta.trazado_vigente, len(ruta.puntos_referencia())])
parada.longitud = base_lon + .01
ruta.quitar_trazado()
comprobar('R8', 'Quitar trazado', False, bool(ruta.trazado))
comprobar('R9', 'Rechaza coordenadas inválidas', True,
          falla(lambda: ruta.guardar_trazado([[200, 0], [0, 0]], 'osrm')))

marca = env['fleet.vehicle.model.brand'].create({'name': 'PT'})
modelo = env['fleet.vehicle.model'].create({'name': 'PT', 'brand_id': marca.id})
veh = env['fleet.vehicle'].create({'model_id': modelo.id, 'license_plate': 'PT-1'})
inicio = fields.Datetime.now() - timedelta(hours=2)


def recorrido(puntos):
    rec = env['fleet.recorrido'].create({'ruta_id': ruta.id, 'vehicle_id': veh.id,
                                         'fecha_inicio': inicio, 'simulado': True})
    for i, (lat, lon) in enumerate(puntos):
        env['fleet.posicion.gps'].create({'recorrido_id': rec.id, 'vehicle_id': veh.id,
                                          'timestamp': inicio + timedelta(seconds=20 * i),
                                          'latitud': lat, 'longitud': lon, 'fuente': 'simulado'})
    return rec


camino = [(base_lat + .003 * min(i, 10) / 10, base_lon) for i in range(11)]
camino += [(base_lat + .003, base_lon + .001 * i) for i in range(1, 11)]
camino += [(base_lat + .003 - .0003 * i, base_lon + .01) for i in range(1, 11)]
referencia, corto = recorrido(camino), recorrido(camino[:8])


def desviadas(rec):
    rec.posicion_ids.detectar_desviacion()
    return len(rec.posicion_ids.filtered('es_desviacion'))


prueba = recorrido(camino)
sin_trazado = desviadas(prueba)
propuesta = ruta.trazado_desde_recorrido(referencia.id)
comprobar('G1', 'Trazado desde GPS conserva las esquinas', 4, len(propuesta['puntos']))
comprobar('G2', 'Marca que proviene de datos simulados', True, propuesta['simulado'])
comprobar('G3', 'Rechaza un recorrido que no llega a todas las paradas', True,
          falla(lambda: ruta.trazado_desde_recorrido(corto.id)))
ruta.guardar_trazado(propuesta['puntos'], 'gps', referencia.id)
comprobar('G4', 'Guarda el recorrido de referencia', referencia.id, ruta.trazado_recorrido_id.id)
otro = recorrido(camino)
comprobar('G5', 'Un viaje por la calle: falsos desvíos solo sin trazado', [True, 0],
          [sin_trazado > 0, desviadas(otro)])
ajena = env['fleet.ruta'].create({'name': 'PT2', 'code': 'PT-2', 'origen': 'A', 'destino': 'B'})
comprobar('G6', 'Rechaza un recorrido de otra ruta', True,
          falla(lambda: ajena.trazado_desde_recorrido(referencia.id)))

# Costo con un trazado largo (500 vértices) y 1000 posiciones
largo = [[base_lat + (.003 if i % 2 else 0), base_lon + .00002 * i] for i in range(500)]
largo[0], largo[-1] = [base_lat, base_lon], [base_lat, base_lon + .01]
ruta.guardar_trazado(largo, 'osrm')
masivo = recorrido([(base_lat, base_lon + .00001 * i) for i in range(1000)])
t = time.perf_counter()
env['fleet.metricas.recorrido'].calcular_para_recorrido(masivo.id)
informativo['metricas_ms_1000_posiciones_500_vertices'] = round((time.perf_counter() - t) * 1000)
env.cr.rollback()
print('RESULT:' + json.dumps({'casos': resultados, 'informativo': informativo}, ensure_ascii=False))
