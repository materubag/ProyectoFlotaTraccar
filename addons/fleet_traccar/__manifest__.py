# -*- coding: utf-8 -*-
{
    'name': 'Fleet Traccar GPS Integration',
    'version': '16.0.1.0.0',
    'category': 'Fleet',
    'summary': 'Integración de seguimiento GPS vehicular con Traccar Server para Odoo 16',
    'description': """
Módulo de Integración de Flota con Servidor GPS Traccar
======================================================
* Extensión del modelo fleet.vehicle para vincular dispositivos GPS de Traccar.
* Parámetros de configuración del servidor Traccar (URL interna y credenciales).
* Visualización de última posición recibida (latitud, longitud, velocidad, marca temporal).
* Restricción de unicidad para evitar duplicidad de dispositivos GPS entre vehículos.
    """,
    'author': 'Proyecto Flota Traccar',
    'website': 'https://github.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'fleet',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/fleet_vehicle_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
