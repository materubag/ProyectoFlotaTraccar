# Prueba de integración en `odoo shell`, SOLO sobre la copia temporal. No hace commit.
# Registro automático de dispositivos (con un Traccar simulado) y dirección web de Traccar.
import json
from types import SimpleNamespace

from odoo.addons.fleet_rutas.models.fleet_traccar_sync import traccar_browser_url

assert env.cr.dbname == 'prueba_flota', 'Solo se permite la base temporal prueba_flota'
Sync = env['fleet.traccar.sync']
Vehicle = env['fleet.vehicle'].with_context(active_test=False)
dispositivos = []
type(Sync)._get_traccar_service = lambda self: SimpleNamespace(get_devices=lambda: list(dispositivos))
resultados = []


def comprobar(codigo, caso, esperado, obtenido):
    resultados.append({'id': codigo, 'caso': caso, 'esperado': esperado, 'obtenido': obtenido,
                       'ok': esperado == obtenido})


def sincronizar():
    stats = Sync.sincronizar_dispositivos()
    env.flush_all()
    env.invalidate_all()
    return stats


def buscar(unico):
    return Vehicle.search([('traccar_unique_id', '=', unico)])


a = {'id': 700001, 'uniqueId': 'PD-A', 'name': 'Bus de prueba A', 'status': 'online'}
dispositivos.append(a)
sincronizar()
v = buscar('PD-A')
comprobar('D1', 'Dispositivo nuevo crea un vehículo', 1, len(v))
comprobar('D2', 'Usa el nombre de Traccar', ['Bus de prueba A', 'Bus de prueba A'],
          [v.license_plate, v.traccar_device_name])
comprobar('D3', 'Queda con seguimiento activo', True, v.traccar_tracking_enabled)
sincronizar()
comprobar('D4', 'Repetir no duplica', 1, len(buscar('PD-A')))
a['name'] = 'Nombre cambiado'
v.license_plate = 'ABC-1234'
sincronizar()
comprobar('D5', 'Actualiza el nombre sin pisar la matrícula', ['Nombre cambiado', 'ABC-1234'],
          [v.traccar_device_name, v.license_plate])
v.traccar_tracking_enabled = False
sincronizar()
comprobar('D6', 'Respeta el seguimiento desactivado', False, v.traccar_tracking_enabled)
v.traccar_tracking_enabled = True
dispositivos[:] = [{'id': 700002, 'uniqueId': 'PD-B', 'name': 'B', 'status': 'offline'}]
sincronizar()
comprobar('D7', 'Dispositivo ausente se señala', 'removed', v.traccar_device_status)
dispositivos.append(dict(a, id=700009))
sincronizar()
comprobar('D8', 'Recreado con otro ID: mismo vehículo', [1, 700009, 'online'],
          [len(buscar('PD-A')), v.traccar_device_id, v.traccar_device_status])
v.active = False
sincronizar()
comprobar('D9', 'Vehículo archivado no se duplica', 1, len(buscar('PD-A')))
manual = Vehicle.create({'model_id': v.model_id.id, 'license_plate': 'MAN-1', 'traccar_unique_id': 'PD-C'})
dispositivos.append({'id': 700003, 'uniqueId': 'PD-C', 'name': 'C', 'status': 'online'})
sincronizar()
comprobar('D10', 'Vehículo creado a mano se vincula y activa', [1, 700003, True],
          [len(buscar('PD-C')), manual.traccar_device_id, manual.traccar_tracking_enabled])
antes = manual.traccar_device_status
dispositivos[:] = []
sincronizar()
comprobar('D11', 'Respuesta vacía no marca nada', antes, manual.traccar_device_status)

web = 'http://192.168.1.20:8070/'
for codigo, caso, configurada, esperado in (
        ('U1', 'Automática: servidor de Odoo y puerto publicado', '', 'http://192.168.1.20:8083'),
        ('U2', 'Nombre interno de Docker no llega al navegador', 'http://traccar:8082', 'http://192.168.1.20:8083'),
        ('U3', 'localhost conserva su puerto', 'http://localhost:9999', 'http://192.168.1.20:9999'),
        ('U4', 'URL pública se respeta', 'https://gps.ejemplo.com/', 'https://gps.ejemplo.com')):
    comprobar(codigo, caso, esperado, traccar_browser_url(configurada, web, '8083'))
try:
    traccar_browser_url('http://usuario:clave@gps.ejemplo.com', web, '8083')
    rechazo = False
except Exception:
    rechazo = True
comprobar('U5', 'Rechaza credenciales en la URL', True, rechazo)
env.cr.rollback()
print('RESULT:' + json.dumps(resultados, ensure_ascii=False))
