# -*- coding: utf-8 -*-
{
    'name': 'Fleet Rutas — Sistema de Monitoreo de Rutas Universitarias',
    'version': '16.0.1.0.0',
    'category': 'Fleet',
    'summary': 'Monitoreo y evaluación de rutas de transporte universitario con métricas ISO/IEC 25010',
    'description': """
Sistema de Monitoreo y Evaluación de Rutas de Transporte Universitario
======================================================================
Ecosistema que integra Odoo 16, Traccar Server y PostgreSQL para el control
y auditoría de flota vehicular universitaria bajo estándares de calidad ISO/IEC 25010.

Características implementadas:
------------------------------
* Arquitectura de Integración: API REST Traccar bidireccional, webhook en tiempo real y tolerancia a fallos.
* Modelado Relacional: Rutas, paradas/puntos de control geográficos, recorridos y telemetría GPS histórica.
* Motor de Detección: Haversine, cálculo de retrasos con ventana de tolerancia, validación de paradas y desvíos espaciales.
* Motor de Métricas Dinámicas: Indicadores de operación de transporte y métricas SQA (integridad, exactitud, tiempos).
* Dashboards y Analítica: Cuadro de mando OWL nativo en Odoo y vistas SQL materializadas para Power BI.
    """,
    'author': 'Proyecto Flota Traccar',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'fleet',
        'fleet_traccar',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/scheduled_actions.xml',
        'views/fleet_dashboard_views.xml',
        'views/fleet_metricas_views.xml',
        'views/fleet_recorrido_views.xml',
        'views/fleet_ruta_views.xml',
        'views/menu_views.xml',
    ],
    'demo': ['data/fleet_rutas_demo.xml'],
    'assets': {
        'web.assets_backend': [
            'fleet_rutas/static/src/css/fleet_dashboard.css',
            'fleet_rutas/static/src/js/fleet_dashboard.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'sequence': 10,
}
