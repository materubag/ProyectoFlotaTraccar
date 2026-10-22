# -*- coding: utf-8 -*-
{
    'name': 'Fleet Reports — Grafana Embedded',
    'version': '16.0.1.0.0',
    'category': 'Fleet',
    'summary': 'Módulo de reportes de flota vehicular con dashboards Grafana embebidos y actualización en tiempo real',
    'description': """
Módulo de Reportes de Flota Vehicular con Grafana
==================================================
* Panel de reportes embebido directamente en el menú de Odoo.
* Dashboard Grafana con datos GPS en tiempo real desde Traccar.
* Actualización automática cada 30 segundos sin recargar la página.
* KPIs: dispositivos activos, vehículos en línea, velocidad promedio, alertas.
* Tabla de posición actual de todos los vehículos.
* Serie de tiempo de velocidad por vehículo.
* Historial de eventos y alertas.
* Configuración de URL de Grafana desde los ajustes del sistema.
    """,
    'author': 'Proyecto Flota Traccar',
    'website': 'https://github.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'fleet',
        'fleet_traccar',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/fleet_reports_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'fleet_reports/static/src/css/fleet_reports.css',
            'fleet_reports/static/src/js/fleet_reports_widget.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
