# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    traccar_device_id = fields.Integer(
        string='ID Dispositivo Traccar',
        help='Identificador único numérico asignado al dispositivo en Traccar.',
        copy=False,
        index=True
    )
    traccar_unique_id = fields.Char(
        string='Identificador Único (IMEI/ID)',
        help='Identificador único reportado por el rastreador GPS (ej. IMEI o ID de Traccar Client).',
        copy=False
    )
    traccar_tracking_enabled = fields.Boolean(
        string='Seguimiento GPS Habilitado',
        default=False,
        help='Indica si el vehículo tiene activo el seguimiento en tiempo real mediante Traccar.'
    )
    traccar_last_latitude = fields.Float(
        string='Última Latitud',
        digits=(10, 7),
        readonly=True,
        help='Última coordenada de latitud recibida desde Traccar.'
    )
    traccar_last_longitude = fields.Float(
        string='Última Longitud',
        digits=(10, 7),
        readonly=True,
        help='Última coordenada de longitud recibida desde Traccar.'
    )
    traccar_last_speed = fields.Float(
        string='Última Velocidad (km/h)',
        readonly=True,
        help='Velocidad reportada en la última posición recibida.'
    )
    traccar_last_update = fields.Datetime(
        string='Fecha Última Posición',
        readonly=True,
        help='Marca temporal de la última posición reportada por el dispositivo.'
    )
    traccar_device_status = fields.Selection([
        ('unknown', 'Desconocido'),
        ('online', 'En línea'),
        ('offline', 'Fuera de línea')
    ], string='Estado en Traccar', default='unknown', readonly=True)

    _sql_constraints = [
        ('traccar_device_id_unique',
         'unique(traccar_device_id)',
         'El ID de dispositivo Traccar debe ser único por vehículo.')
    ]

    @api.constrains('traccar_device_id')
    def _check_traccar_device_id(self):
        for record in self:
            if record.traccar_device_id and record.traccar_device_id < 0:
                raise ValidationError(_("El ID de dispositivo Traccar no puede ser negativo."))
            if record.traccar_device_id:
                existing = self.search([
                    ('id', '!=', record.id),
                    ('traccar_device_id', '=', record.traccar_device_id)
                ], limit=1)
                if existing:
                    raise ValidationError(_(
                        "El dispositivo Traccar ID %s ya se encuentra asociado al vehículo %s."
                    ) % (record.traccar_device_id, existing.display_name))
