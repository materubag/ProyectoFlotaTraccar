"""Ejecutar en odoo shell: reconstruye assets conservando las versiones anteriores.

No actualiza módulos ni registros de operación. La sustitución del método de
limpieza vive solamente durante esta llamada de generación en este proceso.
"""
import json
from unittest.mock import patch
from odoo.addons.base.models.assetsbundle import AssetsBundle

attachments = env['ir.attachment'].sudo()
previous_ids = attachments.search([('url', 'like', '/web/assets/%'), ('name', 'like', 'web.assets_backend%')]).ids
models = ['fleet.vehicle', 'fleet.ruta', 'fleet.parada', 'fleet.recorrido', 'fleet.posicion.gps', 'fleet.incidencia', 'fleet.metricas.recorrido']
counts_before = {name: env[name].sudo().search_count([]) for name in models}
with patch.object(AssetsBundle, 'clean_attachments', return_value=True):
    nodes = env['ir.qweb']._get_asset_nodes('web.assets_backend', css=True, js=True)
assert len(attachments.browse(previous_ids).exists()) == len(previous_ids), 'No se conservaron los assets anteriores'
counts_after = {name: env[name].sudo().search_count([]) for name in models}
assert counts_before == counts_after, 'Cambió un conteo de registros de operación'
urls = {kind: attachments.search([('name', '=', 'web.assets_backend.min.' + kind)], order='id desc', limit=1).url
        for kind in ('css', 'js')}
env.cr.commit()
print('DASHBOARD_ASSETS=' + json.dumps({'urls': urls, 'assets_anteriores_conservados': len(previous_ids),
                                       'conteos_antes': counts_before, 'conteos_despues': counts_after}))
