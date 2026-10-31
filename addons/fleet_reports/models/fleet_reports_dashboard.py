# -*- coding: utf-8 -*-
from odoo import models, api


class FleetReportsDashboard(models.TransientModel):
    """Modelo auxiliar que provee al frontend los parámetros de Grafana."""
    _name = 'fleet.reports.dashboard'
    _description = 'Fleet Reports — Configuración del Dashboard Grafana'

    @api.model
    def get_grafana_config(self):
        """
        Retorna la configuración de Grafana leída desde ir.config_parameter.
        El widget JS la consume en el arranque y construye la URL del iframe.
        """
        ICP = self.env['ir.config_parameter'].sudo()

        base_url = ICP.get_param(
            'fleet_reports.grafana_base_url', 'http://localhost:3000'
        )
        dashboard_uid = ICP.get_param(
            'fleet_reports.grafana_fleet_dashboard_uid', 'fleet-traccar-main'
        )
        refresh_interval = int(ICP.get_param(
            'fleet_reports.grafana_refresh_interval', 30
        ))
        time_from = ICP.get_param(
            'fleet_reports.grafana_default_time_range', 'now-6h'
        )

        # Construir la URL embebible de Grafana (modo kiosk para ocultar
        # la barra superior y lateral, dejando solo el contenido del panel)
        embed_url = (
            f"{base_url.rstrip('/')}/d/{dashboard_uid}/flota-vehicular-gps-traccar"
            f"?orgId=1&from={time_from}&to=now&kiosk=tv&refresh={refresh_interval}s"
            f"&theme=dark"
        )

        return {
            'base_url': base_url,
            'dashboard_uid': dashboard_uid,
            'refresh_interval': refresh_interval,
            'time_from': time_from,
            'embed_url': embed_url,
        }
