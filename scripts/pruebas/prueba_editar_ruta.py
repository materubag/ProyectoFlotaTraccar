# Prueba de integración en `odoo shell`, SOLO sobre la copia temporal. No hace commit.
# Edición de rutas que ya tienen recorridos registrados (hallazgo H08).
import json
from datetime import timedelta
from types import SimpleNamespace

from odoo import fields
from odoo.exceptions import UserError
from odoo.addons.fleet_rutas.controllers import mapa

assert env.cr.dbname == 'prueba_flota', 'Solo se permite la base temporal prueba_flota'
admin = env.ref('base.user_admin')
admin.groups_id = [(4, env.ref('fleet_rutas.group_fleet_admin').id)]
usuario = env(user=admin.id)
controlador = mapa.FleetMapa()
resultados = []
marca = env['fleet.vehicle.model.brand'].create({'name': 'ER'})
modelo = env['fleet.vehicle.model'].create({'name': 'ER', 'brand_id': marca.id})


def comprobar(codigo, caso, esperado, obtenido):
    resultados.append({'id': codigo, 'caso': caso, 'esperado': esperado, 'obtenido': obtenido,
                       'ok': esperado == obtenido})


def punto(i, lat=-1.25, nombre=None, tolerancia=5):
    return {'lat': lat, 'lng': -78.62 + i * 0.005, 'name': nombre or 'P%d' % (i + 1),
            'time': 8 + i / 6, 'tolerance': tolerancia, 'radio': 60}


def editar(puntos, ruta=None, nombre='Ruta ER'):
    """Misma petición que envía el editor."""
    cuerpo = {'route_id': ruta.id if ruta else 0, 'name': nombre, 'distance': 2, 'corridor': 60,
              'points': puntos}
    mapa.request = SimpleNamespace(env=usuario, httprequest=SimpleNamespace(data=json.dumps(cuerpo).encode()))
    try:
        respuesta = controlador.crear_ruta()
    except Exception as exc:
        return 'error: %s' % type(exc).__name__, None
    env.flush_all()
    env.invalidate_all()
    datos = json.loads(respuesta.get_data())
    return respuesta.status_code, env['fleet.ruta'].browse(datos['route_id']) if 'route_id' in datos else None


def paradas(ruta):
    return ruta.parada_ids.sorted('secuencia')


def preparar(codigo, estado='completado'):
    base = [punto(i) for i in range(4)]
    _, ruta = editar(base, nombre='Ruta %s' % codigo)
    veh = env['fleet.vehicle'].create({'model_id': modelo.id, 'license_plate': codigo,
                                       'traccar_tracking_enabled': True})
    rec = env['fleet.recorrido'].create({'ruta_id': ruta.id, 'vehicle_id': veh.id,
                                         'fecha_inicio': fields.Datetime.now() - timedelta(hours=1)})
    rec.action_iniciar()
    if estado == 'completado':
        rec.action_completar()
    env.flush_all()
    return base, ruta, rec


def caso(funcion):
    env.cr.execute('SAVEPOINT er')
    try:
        funcion()
    except Exception as exc:
        resultados.append({'id': funcion.__name__, 'caso': 'error', 'esperado': 'sin error',
                           'obtenido': '%s: %s' % (type(exc).__name__, str(exc)[:200]), 'ok': False})
    finally:
        env.cr.execute('ROLLBACK TO SAVEPOINT er')
        env.clear()


def sin_cambios():
    base, ruta, rec = preparar('E1')
    ids = paradas(ruta).ids
    estado, _ = editar(base, ruta)
    comprobar('E1', 'Guardar sin cambios conserva las paradas', [200, ids], [estado, paradas(ruta).ids])
    base[1]['name'] = 'Nuevo nombre'
    editar(base, ruta)
    comprobar('E2', 'Renombrar conserva la parada', [ids, 'Nuevo nombre'],
              [paradas(ruta).ids, paradas(ruta)[1].name])


def mover():
    base, ruta, rec = preparar('E3')
    vieja = paradas(ruta)[1]
    latitud = vieja.latitud
    base[1] = punto(1, lat=-1.251)
    estado, _ = editar(base, ruta)
    comprobar('E3', 'Mover una parada con historial guarda', [200, 4], [estado, len(paradas(ruta))])
    comprobar('E4', 'La anterior queda archivada con sus coordenadas', [False, round(latitud, 6)],
              [vieja.active, round(vieja.latitud, 6)])
    comprobar('E5', 'El recorrido conserva sus paradas originales', True,
              vieja in rec.paradas_del_recorrido() and len(rec.cumplimiento_parada_ids) == 4)
    nuevo = env['fleet.recorrido'].create({'ruta_id': ruta.id, 'vehicle_id': rec.vehicle_id.id,
                                           'fecha_inicio': fields.Datetime.now()})
    nuevo.action_iniciar()
    comprobar('E6', 'Un recorrido nuevo usa las paradas actuales', sorted(paradas(ruta).ids),
              sorted(nuevo.paradas_del_recorrido().ids))
    comprobar('E7', 'El total cuenta solo las activas', 4, ruta.total_paradas)


def quitar_y_agregar():
    base, ruta, rec = preparar('E8')
    quitada = paradas(ruta)[3]
    estado, _ = editar(base[:3], ruta)
    comprobar('E8', 'Quitar una parada con historial la archiva', [200, 3, True, False],
              [estado, len(paradas(ruta)), bool(quitada.exists()), quitada.active])
    estado, _ = editar(base[:3] + [punto(4)], ruta)
    comprobar('E9', 'Agregar una parada', [200, 4], [estado, len(paradas(ruta))])
    sin_uso = paradas(ruta)[3]
    editar(base[:3], ruta)
    comprobar('E10', 'Quitar una parada sin historial la borra', False, bool(sin_uso.exists()))


def en_curso():
    base, ruta, rec = preparar('E11', estado='en_curso')
    ids = paradas(ruta).ids
    movidas = [punto(0, lat=-1.26)] + base[1:]
    estado, _ = editar(movidas, ruta, nombre='No debe quedar')
    comprobar('E11', 'Con recorrido en curso se rechaza y no cambia nada', [400, 'Ruta E11', ids],
              [estado, ruta.name, paradas(ruta).ids])
    estado, _ = editar(base, ruta, nombre='Nombre permitido')
    comprobar('E12', 'En curso se puede renombrar la ruta', [200, 'Nombre permitido'], [estado, ruta.name])


def nativo():
    base, ruta, rec = preparar('E13')
    parada = paradas(ruta)[0]
    try:
        parada.write({'latitud': -1.3})
        rechazo = False
    except UserError:
        rechazo = True
    comprobar('E13', 'Edición directa de una parada con historial se rechaza', True, rechazo)
    parada.write({'name': 'Otro nombre', 'latitud': parada.latitud})
    comprobar('E14', 'Se permite cambiar el nombre', 'Otro nombre', parada.name)
    parada.unlink()
    env.flush_all()
    comprobar('E15', 'Borrado directo con historial archiva', [True, False],
              [bool(parada.exists()), parada.active])


def tolerancia():
    _, ruta = editar([punto(i, tolerancia=0) for i in range(2)], nombre='Ruta cero')
    comprobar('E16', 'Tolerancia cero se respeta', [0, 0], paradas(ruta).mapped('tolerancia_min'))
    estado, _ = editar([punto(0), {'lat': 'x', 'lng': 0}], ruta, nombre='Mala')
    comprobar('E17', 'Datos inválidos: error 400 sin cambios', [400, 'Ruta cero', 2],
              [estado, ruta.name, len(paradas(ruta))])


for funcion in (sin_cambios, mover, quitar_y_agregar, en_curso, nativo, tolerancia):
    caso(funcion)
env.cr.rollback()
print('RESULT:' + json.dumps(resultados, ensure_ascii=False))
