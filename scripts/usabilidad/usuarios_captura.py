# `odoo shell` SOLO sobre la copia temporal: crea los usuarios usados para las capturas.
import os

assert env.cr.dbname == 'ui_capturas', 'Solo se permite la base temporal ui_capturas'
clave = os.environ['UI_PASSWORD']
Users = env['res.users'].with_context(no_reset_password=True)
admin = [env.ref(x).id for x in ('base.group_user', 'base.group_system', 'fleet.fleet_group_manager',
                                 'fleet_rutas.group_fleet_admin')]
Users.create({'name': 'Administrador de prueba', 'login': 'ui_admin', 'password': clave,
              'lang': env.user.lang, 'tz': 'America/Guayaquil', 'groups_id': [(6, 0, admin)]})
pasajero = Users.create({'name': 'Pasajero de prueba', 'login': 'ui_pasajero', 'password': clave,
                         'tz': 'America/Guayaquil', 'groups_id': [(6, 0, [
                             env.ref('base.group_portal').id, env.ref('fleet_rutas.group_mobile_user').id])]})
env['fleet.ruta'].search([]).write({'mobile_user_ids': [(4, pasajero.id)]})
if os.environ.get('UI_EN_VIVO') == '1':
    # Recorrido SIMULADO en curso, solo en la copia, para ver la estimación de llegada.
    from datetime import timedelta
    from odoo import fields
    ruta = env['fleet.ruta'].search([('name', 'ilike', 'Centro')], limit=1)
    veh = env['fleet.vehicle'].search([('license_plate', '=', '1-MER-001')], limit=1)
    ahora = fields.Datetime.now()
    inicio = ahora - timedelta(minutes=2)  # llegan posiciones mientras se captura
    rec = env['fleet.recorrido'].create({'ruta_id': ruta.id, 'vehicle_id': veh.id,
                                         'fecha_inicio': inicio, 'simulado': True})
    rec.action_iniciar(momento=inicio)
    a, b = ruta.parada_ids.sorted('secuencia')[:2]
    for i in range(33):
        f = i / 24 * 0.5
        env['fleet.posicion.gps'].create({
            'recorrido_id': rec.id, 'vehicle_id': veh.id,
            'timestamp': inicio + timedelta(seconds=15 * i),
            'latitud': a.latitud + f * (b.latitud - a.latitud),
            'longitud': a.longitud + f * (b.longitud - a.longitud),
            'fuente': 'simulado'}).detectar_desviacion()
env.cr.commit()
