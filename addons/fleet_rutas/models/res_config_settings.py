# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    """Configuración de personalización visual y colores de Transporte UTA."""
    _inherit = 'res.config.settings'

    fleet_color_primary = fields.Char(
        string='Color de Acento / Primario',
        config_parameter='fleet_rutas.color_primary',
        default='#714b67',
        help='Color de los botones primarios, enlaces activos y acento institucional (ej. #714b67 o #0f62fe).',
    )
    fleet_color_primary_hover = fields.Char(
        string='Color Primario Hover',
        config_parameter='fleet_rutas.color_primary_hover',
        default='#5d3d54',
        help='Color cuando el cursor pasa sobre botones primarios.',
    )
    fleet_color_primary_soft = fields.Char(
        string='Color de Selección Suave',
        config_parameter='fleet_rutas.color_primary_soft',
        default='#f3ebf1',
        help='Fondo para elementos seleccionados o rutas activas.',
    )
    fleet_color_background = fields.Char(
        string='Color de Fondo de Página',
        config_parameter='fleet_rutas.color_background',
        default='#f4f4f4',
        help='Color de fondo general del área de trabajo.',
    )
    fleet_color_card = fields.Char(
        string='Color de Paneles y Tarjetas',
        config_parameter='fleet_rutas.color_card',
        default='#ffffff',
        help='Color de fondo para tarjetas de métricas y tablas.',
    )
    fleet_color_text = fields.Char(
        string='Color de Texto Principal',
        config_parameter='fleet_rutas.color_text',
        default='#161616',
        help='Color principal de títulos, cifras y texto legible.',
    )

    @api.model
    def set_theme_colors(self, colors):
        """Permite guardar los colores de diseño desde el dashboard en ir.config_parameter."""
        ICP = self.env['ir.config_parameter'].sudo()
        if 'primary' in colors and colors['primary']:
            ICP.set_param('fleet_rutas.color_primary', colors['primary'])
        if 'primary_hover' in colors and colors['primary_hover']:
            ICP.set_param('fleet_rutas.color_primary_hover', colors['primary_hover'])
        if 'primary_soft' in colors and colors['primary_soft']:
            ICP.set_param('fleet_rutas.color_primary_soft', colors['primary_soft'])
        if 'background' in colors and colors['background']:
            ICP.set_param('fleet_rutas.color_background', colors['background'])
        if 'card' in colors and colors['card']:
            ICP.set_param('fleet_rutas.color_card', colors['card'])
        if 'text' in colors and colors['text']:
            ICP.set_param('fleet_rutas.color_text', colors['text'])
        return True

    @api.model
    def get_theme_colors(self):
        """Retorna los colores configurados del sistema."""
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'primary': ICP.get_param('fleet_rutas.color_primary', '#714b67'),
            'primary_hover': ICP.get_param('fleet_rutas.color_primary_hover', '#5d3d54'),
            'primary_soft': ICP.get_param('fleet_rutas.color_primary_soft', '#f3ebf1'),
            'background': ICP.get_param('fleet_rutas.color_background', '#f4f4f4'),
            'card': ICP.get_param('fleet_rutas.color_card', '#ffffff'),
            'text': ICP.get_param('fleet_rutas.color_text', '#161616'),
        }
