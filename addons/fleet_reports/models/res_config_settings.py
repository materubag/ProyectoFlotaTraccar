# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    """Extiende los ajustes del sistema con la configuración de Grafana."""
    _inherit = 'res.config.settings'

    # ─── URL base de Grafana ────────────────────────────────────────────────
    grafana_base_url = fields.Char(
        string='URL de Grafana',
        config_parameter='fleet_reports.grafana_base_url',
        default='http://localhost:3000',
        help=(
            'URL base donde está disponible Grafana. '
            'Ejemplo: http://localhost:3000  o  http://grafana:3000'
        ),
    )

    # ─── UID del dashboard principal de flota ──────────────────────────────
    grafana_fleet_dashboard_uid = fields.Char(
        string='UID del Dashboard de Flota',
        config_parameter='fleet_reports.grafana_fleet_dashboard_uid',
        default='fleet-traccar-main',
        help=(
            'UID del dashboard en Grafana que será embebido en Odoo. '
            'Lo encuentras en la URL del dashboard: /d/{UID}/...'
        ),
    )

    # ─── Intervalo de actualización automática (segundos) ──────────────────
    grafana_refresh_interval = fields.Integer(
        string='Intervalo de Actualización (seg)',
        config_parameter='fleet_reports.grafana_refresh_interval',
        default=30,
        help='Intervalo en segundos para refrescar el iframe de Grafana automáticamente.',
    )

    # ─── Rango de tiempo por defecto ───────────────────────────────────────
    grafana_default_time_range = fields.Selection(
        selection=[
            ('now-15m', 'Últimos 15 minutos'),
            ('now-30m', 'Últimos 30 minutos'),
            ('now-1h', 'Última hora'),
            ('now-3h', 'Últimas 3 horas'),
            ('now-6h', 'Últimas 6 horas'),
            ('now-12h', 'Últimas 12 horas'),
            ('now-24h', 'Últimas 24 horas'),
            ('now-7d', 'Últimos 7 días'),
        ],
        string='Rango de Tiempo por Defecto',
        config_parameter='fleet_reports.grafana_default_time_range',
        default='now-6h',
        help='Ventana de tiempo que se mostrará en el dashboard al abrirlo.',
    )
