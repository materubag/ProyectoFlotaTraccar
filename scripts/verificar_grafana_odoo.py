"""Ejecutar por stdin de odoo shell; no conserva cambios de configuración."""
from types import SimpleNamespace
from unittest.mock import patch
from odoo.addons.fleet_reports.models import fleet_reports_dashboard

try:
    params = env['ir.config_parameter'].sudo()
    dashboard = env['fleet.reports.dashboard']
    for name in ('portal', 'fleet_rutas', 'fleet_reports'):
        assert env['ir.module.module'].search([('name', '=', name)]).state == 'installed', name
    for stored_url in ('', 'http://localhost:3000'):
        params.set_param('fleet_reports.grafana_base_url', stored_url)
        params.set_param('fleet_reports.grafana_refresh_interval', '30')
        with patch.object(fleet_reports_dashboard, 'request', SimpleNamespace(
                httprequest=SimpleNamespace(host_url='http://192.168.1.20:8070/'))):
            result = dashboard.get_grafana_config()
        assert result['base_url'] == 'http://192.168.1.20:3000', result['base_url']
        assert 'refresh=30s' in result['embed_url']
    for stored_interval, expected in (('0', 5), ('-3', 5), ('incorrecto', 30)):
        params.set_param('fleet_reports.grafana_refresh_interval', stored_interval)
        with patch.object(fleet_reports_dashboard, 'request', SimpleNamespace(
                httprequest=SimpleNamespace(host_url='http://localhost:8070/'))):
            assert dashboard.get_grafana_config()['refresh_interval'] == expected
    print('PASS módulos instalados, URL remota y configuración de refresco en Odoo real')
finally:
    env.cr.rollback()
