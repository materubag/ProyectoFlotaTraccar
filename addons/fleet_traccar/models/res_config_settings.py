# -*- coding: utf-8 -*-
from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    traccar_server_url = fields.Char(
        string='URL del Servidor Traccar',
        config_parameter='fleet_traccar.server_url',
        default='http://traccar:8082',
        help='URL base interna o externa para la API REST de Traccar (ej. http://traccar:8082).'
    )
    traccar_user = fields.Char(
        string='Usuario de la API Traccar',
        config_parameter='fleet_traccar.user',
        help='Correo o usuario con permisos en Traccar para consultar la API.'
    )
    traccar_password = fields.Char(
        string='Contraseña / Token de Traccar',
        config_parameter='fleet_traccar.password',
        help='Contraseña de acceso o token de autenticación para la API de Traccar.'
    )
