# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.http import request
import os
from urllib.parse import urlsplit, urlunsplit


def grafana_browser_url(configured_url, browser_url, port=3000):
    """Resolver el servidor desde el navegador; conservar URLs externas explícitas."""
    configured = (configured_url or '').strip().rstrip('/')
    parsed = urlsplit(configured)
    if configured and parsed.hostname not in ('localhost', '127.0.0.1', '::1', 'grafana'):
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('La URL de Grafana debe ser HTTP/HTTPS y no contener credenciales.')
        return configured
    browser = urlsplit(browser_url)
    hostname = browser.hostname
    if not hostname:
        raise ValueError('No se pudo determinar el servidor de Odoo.')
    host = f'[{hostname}]' if ':' in hostname else hostname
    # Una URL antigua de localhost conserva su puerto publicado personalizado.
    published_port = parsed.port or int(port)
    if not 1 <= published_port <= 65535:
        raise ValueError('Puerto de Grafana inválido.')
    return urlunsplit((browser.scheme, f'{host}:{published_port}', '', '', ''))


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

        base_url = grafana_browser_url(
            ICP.get_param('fleet_reports.grafana_base_url', ''),
            request.httprequest.host_url,
            os.environ.get('GRAFANA_PORT', '3000'),
        )
        dashboard_uid = ICP.get_param(
            'fleet_reports.grafana_fleet_dashboard_uid', 'fleet-traccar-main'
        )
        try:
            refresh_interval = max(5, int(ICP.get_param(
                'fleet_reports.grafana_refresh_interval', 30
            )))
        except (TypeError, ValueError):
            refresh_interval = 30
        time_from = ICP.get_param(
            'fleet_reports.grafana_default_time_range', 'now-6h'
        )

        # Construir la URL embebible de Grafana (modo kiosk para ocultar
        # la barra superior y lateral, dejando solo el contenido del panel)
        embed_url = (
            f"{base_url.rstrip('/')}/d/{dashboard_uid}/flota-vehicular-gps-traccar"
            f"?orgId=1&from={time_from}&to=now&kiosk&refresh={refresh_interval}s"
            f"&theme=light"
        )

        return {
            'base_url': base_url,
            'dashboard_uid': dashboard_uid,
            'refresh_interval': refresh_interval,
            'time_from': time_from,
            'embed_url': embed_url,
        }
