"""Passenger access, scoped route assignments and durable Web Push delivery."""
import base64
import importlib.util
import json
import logging
from datetime import timedelta
from urllib.parse import urlsplit
from requests.exceptions import RequestException

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError

_logger = logging.getLogger(__name__)


def valid_push_endpoint(endpoint):
    """Never allow a client-controlled push endpoint to reach the internal network."""
    try:
        url = urlsplit(endpoint)
        host = url.hostname or ''
        allowed = (host == 'fcm.googleapis.com' or host == 'updates.push.services.mozilla.com'
                   or host.endswith('.notify.windows.com') or host == 'web.push.apple.com'
                   or host.endswith('.push.apple.com'))
        return bool(allowed and url.scheme == 'https' and url.port in (None, 443)
                    and not url.username and not url.password and not url.fragment)
    except (ValueError, TypeError):
        return False


class FleetMobileRuta(models.Model):
    _inherit = 'fleet.ruta'

    mobile_user_ids = fields.Many2many(
        'res.users', 'fleet_ruta_mobile_user_rel', 'ruta_id', 'user_id',
        string='Usuarios de la aplicación', groups='fleet_rutas.group_fleet_admin',
        help='Solo estos usuarios pueden consultar la ruta y recibir sus incidencias.')

    @api.constrains('mobile_user_ids')
    def _check_mobile_assignees(self):
        for route in self:
            if any(not u.has_group('fleet_rutas.group_mobile_user') for u in route.mobile_user_ids):
                raise ValidationError(_('Asigna únicamente usuarios con el rol Usuario de la aplicación.'))


class FleetMobileUser(models.Model):
    _inherit = 'res.users'

    @api.constrains('groups_id')
    def _check_mobile_role(self):
        app = self.env.ref('fleet_rutas.group_mobile_user')
        internal = self.env.ref('base.group_user')
        for user in self:
            if app in user.groups_id and internal in user.groups_id:
                raise ValidationError(_('El usuario de la aplicación debe ser de tipo Portal, sin acceso interno.'))


class FleetMobileSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mobile_vapid_public = fields.Char(string='Clave pública Web Push',
        config_parameter='fleet_rutas.vapid_public', groups='base.group_system')
    mobile_vapid_private = fields.Char(string='Clave privada Web Push',
        config_parameter='fleet_rutas.vapid_private', groups='base.group_system')
    mobile_vapid_subject = fields.Char(string='Contacto Web Push (mailto:)',
        config_parameter='fleet_rutas.vapid_subject', groups='base.group_system')

    def action_generate_mobile_keys(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Solo el administrador puede generar claves.'))
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param('fleet_rutas.vapid_private'):
            raise ValidationError(_('Ya existen claves. No se reemplazan para conservar las suscripciones.'))
        key = ec.generate_private_key(ec.SECP256R1())
        public = key.public_key().public_bytes(serialization.Encoding.X962,
                                               serialization.PublicFormat.UncompressedPoint)
        private = key.private_bytes(serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        encode = lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip('=')
        params.set_param('fleet_rutas.vapid_public', encode(public))
        params.set_param('fleet_rutas.vapid_private', encode(private))
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class FleetMobilePush(models.Model):
    _name = 'fleet.mobile.push'
    _description = 'Dispositivo de notificaciones de Flota'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    endpoint = fields.Char(required=True, index=True)
    subscription = fields.Text(required=True)
    active = fields.Boolean(default=True)
    _sql_constraints = [('endpoint_unique', 'unique(endpoint)', 'El dispositivo ya está registrado.')]


class FleetMobileDelivery(models.Model):
    _name = 'fleet.mobile.delivery'
    _description = 'Cola de notificaciones de incidencias'

    push_id = fields.Many2one('fleet.mobile.push', required=True, ondelete='cascade')
    incidence_id = fields.Many2one('fleet.incidencia', required=True, ondelete='cascade')
    attempts = fields.Integer(default=0)
    state = fields.Selection([('pending', 'Pendiente'), ('sent', 'Enviada'),
                              ('discarded', 'Descartada')], default='pending', index=True)
    next_try = fields.Datetime(default=fields.Datetime.now, index=True)
    _sql_constraints = [('delivery_unique', 'unique(push_id, incidence_id)', 'Aviso ya encolado.')]

    @api.model
    def _send_pending(self):
        if not importlib.util.find_spec('pywebpush'):
            return
        from pywebpush import webpush, WebPushException
        params = self.env['ir.config_parameter'].sudo()
        private = params.get_param('fleet_rutas.vapid_private')
        subject = params.get_param('fleet_rutas.vapid_subject')
        if not private or not subject or not subject.startswith('mailto:'):
            return
        now = fields.Datetime.now()
        # Row locking prevents duplicate deliveries from overlapping workers.
        self.env.cr.execute("""SELECT id FROM fleet_mobile_delivery
            WHERE state = 'pending' AND next_try <= NOW() AT TIME ZONE 'UTC'
            ORDER BY id LIMIT 10 FOR UPDATE SKIP LOCKED""")
        for delivery in self.browse([row[0] for row in self.env.cr.fetchall()]):
            push, inc = delivery.push_id, delivery.incidence_id
            user = push.user_id
            if (not push.active or not user.active or inc.resuelta or
                inc.validacion == 'falso' or now - delivery.create_date > timedelta(hours=24) or
                user not in inc.ruta_id.mobile_user_ids or
                not user.has_group('fleet_rutas.group_mobile_user') or
                not valid_push_endpoint(push.endpoint)):
                delivery.state = 'discarded'
                continue
            try:
                webpush(subscription_info=json.loads(push.subscription),
                    data=json.dumps({'title': 'Incidencia en tu ruta',
                        'body': inc.ruta_id.name + ': ' + dict(inc._fields['tipo'].selection).get(inc.tipo, inc.tipo),
                        'tag': 'incidence-%s' % inc.id}),
                    vapid_private_key=private, vapid_claims={'sub': subject},
                    timeout=5, ttl=300)
                delivery.state = 'sent'
            except (WebPushException, RequestException) as exc:
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                if status in (404, 410):
                    push.active = False
                    delivery.state = 'discarded'
                else:
                    delivery.attempts += 1
                    delivery.next_try = now + timedelta(minutes=2 ** delivery.attempts)
                    if delivery.attempts >= 5:
                        delivery.state = 'discarded'
                    _logger.warning('Web Push delivery %s failed (HTTP %s)', delivery.id, status)
            except (ValueError, TypeError):
                delivery.state = 'discarded'
                _logger.warning('Invalid subscription for Web Push delivery %s', delivery.id)


class FleetMobileIncidence(models.Model):
    _inherit = 'fleet.incidencia'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        deliveries = []
        for inc in records:
            if inc.resuelta or inc.validacion == 'falso':
                continue
            users = inc.sudo().ruta_id.mobile_user_ids.filtered(
                lambda u: u.active and u.has_group('fleet_rutas.group_mobile_user'))
            for push in self.env['fleet.mobile.push'].sudo().search([('user_id', 'in', users.ids)]):
                deliveries.append({'push_id': push.id, 'incidence_id': inc.id})
        if deliveries:
            self.env['fleet.mobile.delivery'].sudo().create(deliveries)
        return records
