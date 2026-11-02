"""Authenticated map using stored GPS data and the configured reference corridor."""
import json
from html import escape

from odoo import http
from odoo.http import request, Response


class FleetMapa(http.Controller):
    @http.route('/fleet_rutas/mapa/<int:recorrido_id>', auth='user', type='http')
    def mapa(self, recorrido_id, **kwargs):
        rec = request.env['fleet.recorrido'].browse(recorrido_id).exists()
        if not rec:
            return request.not_found()
        rec.check_access_rights('read')
        rec.check_access_rule('read')
        rec.vehicle_id.check_access_rule('read')
        points = rec.posicion_ids.sorted('timestamp')
        data = {
            'reference': [[p.latitud, p.longitud] for p in rec.ruta_id.parada_ids.sorted('secuencia')],
            'track': [[p.latitud, p.longitud] for p in points],
            'stops': [{'point': [p.latitud, p.longitud], 'name': p.name} for p in rec.ruta_id.parada_ids],
        }
        payload = json.dumps(data).replace('<', '\\u003c')
        last = str(points[-1].timestamp) + ' UTC' if points else 'Sin posiciones GPS'
        html = '''<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapa del recorrido</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>body{margin:0;font:16px system-ui;display:flex;flex-direction:column;height:100vh;height:100dvh}
header{padding:12px;overflow-wrap:anywhere}h1{font-size:18px;margin:0 0 6px}#map{flex:1;min-height:250px}
.legend{font-size:14px;margin-top:6px}a{color:#1658b5}</style></head><body>
<header><h1>__TITLE__</h1><div>__LAST__ · __SOURCE__</div>
<div class="legend">Azul: corredor de referencia · Naranja: recorrido GPS · Marcador: última posición guardada</div>
<div id="error" role="status">Cargando mapa…</div></header><div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const data=__DATA__;
if(typeof L==='undefined'){document.getElementById('error').textContent='No se pudo cargar el mapa. Comprueba la conexión a Internet.';}
else {
const map=L.map('map').setView([-1.249,-78.617],13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:19}).addTo(map);
const reference=L.polyline(data.reference,{color:'#2563eb',weight:8,opacity:.4}).addTo(map);
const track=L.polyline(data.track,{color:'#ea580c',weight:4}).addTo(map);
data.stops.forEach(s=>{const label=document.createElement('span');label.textContent=s.name;L.circleMarker(s.point,{radius:7}).bindPopup(label).addTo(map);});
if(data.track.length){L.marker(data.track[data.track.length-1]).addTo(map).bindPopup('Última posición GPS guardada');}
const bounds=L.latLngBounds([...data.reference,...data.track]);if(bounds.isValid())map.fitBounds(bounds.pad(.15));
document.getElementById('error').textContent=data.track.length?'':'Todavía no hay posiciones GPS para este recorrido.';
}
</script></body></html>'''
        html = html.replace('__TITLE__', escape(rec.name or '')).replace('__LAST__', escape(last))
        html = html.replace('__SOURCE__', 'SIMULADO' if rec.simulado else 'Datos registrados').replace('__DATA__', payload)
        return Response(html, content_type='text/html; charset=utf-8', headers={'Cache-Control': 'no-store'})
