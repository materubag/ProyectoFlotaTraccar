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
env.cr.commit()
