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
            'stops': [{'point': [p.latitud, p.longitud], 'name': p.name, 'seq': p.secuencia} for p in rec.ruta_id.parada_ids.sorted('secuencia')],
        }
        payload = json.dumps(data).replace('<', '\\u003c')
        last = str(points[-1].timestamp) + ' UTC' if points else 'Sin posiciones GPS'
        vehiculo = rec.vehicle_id.name or 'Vehículo'
        ruta = rec.ruta_id.name or 'Ruta'
        
        is_embed = kwargs.get('embed') == '1'
        body_class = ' class="is-embed"' if is_embed else ''

        html = '''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transporte UTA · Mapa de Monitoreo</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root {
  --bg: #f5f6f8; --card: #ffffff; --bd: #e6e8ec; --tx: #1a2230; --mu: #5f6b7c;
  --bl: #2f6df0; --bls: #e8eefc; --blt: #1d4ed8; --gn: #1e7a4c; --gns: #dff3e7;
  --rd: #b42a2a; --rds: #fbe1e1; --am: #8a5a00; --ams: #fdebc8;
}
* { box-sizing: border-box; border-radius: 0 !important; }
body {
  margin: 0; font: 14px/1.4 'Inter', -apple-system, system-ui, sans-serif;
  color: var(--tx); background: var(--bg); display: flex; flex-direction: column;
  height: 100vh; height: 100dvh; overflow: hidden;
}
body.is-embed header { display: none !important; }
header {
  background: var(--card); border-bottom: 1px solid var(--bd); padding: 14px 20px;
  display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap;
  z-index: 1000;
}
.title-block h1 { margin: 0 0 4px; font-size: 18px; font-weight: 700; color: var(--tx); }
.title-block .sub { color: var(--mu); font-size: 13px; }
.hud { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.pill {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
  font-size: 12px; font-weight: 600; border: 1px solid transparent;
}
.pill.gn { background: var(--gns); color: var(--gn); border-color: rgba(30,122,76,0.2); }
.pill.bl { background: var(--bls); color: var(--blt); border-color: rgba(47,109,240,0.2); }
.pill.am { background: var(--ams); color: var(--am); }
#map { flex: 1; width: 100%; min-height: 250px; background: #e5e7eb; }
.legend-bar {
  background: var(--card); border-top: 1px solid var(--bd); padding: 8px 20px;
  font-size: 12px; color: var(--mu); display: flex; gap: 20px; flex-wrap: wrap; align-items: center;
}
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.sw { width: 12px; height: 12px; display: inline-block; }
.leaflet-popup-content-wrapper, .leaflet-popup-tip { border-radius: 0 !important; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
.leaflet-popup-content { margin: 10px 14px; font-family: inherit; font-size: 13px; font-weight: 600; }
</style>
</head>
<body__BODY_CLASS__>
<header>
  <div class="title-block">
    <h1>__TITLE__</h1>
    <div class="sub">Vehículo: <b>__VEHICULO__</b> · Ruta: <b>__RUTA__</b></div>
  </div>
  <div class="hud">
    <span class="pill gn">GPS: __LAST__</span>
    <span class="pill bl">__SOURCE__</span>
  </div>
</header>
<div id="map"></div>
<div class="legend-bar">
  <div class="legend-item"><span class="sw" style="background:var(--bl);opacity:0.4;height:6px;"></span> Corredor de referencia</div>
  <div class="legend-item"><span class="sw" style="background:#ea580c;height:4px;"></span> Traza GPS real</div>
  <div class="legend-item"><span class="sw" style="background:var(--card);border:2px solid var(--bl);"></span> Punto de control</div>
  <div class="legend-item"><span class="sw" style="background:#1e7a4c;"></span> Posición actual</div>
  <div id="error" style="margin-left:auto;color:var(--am);font-weight:600;" role="status"></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const data = __DATA__;
if (typeof L === 'undefined') {
  document.getElementById('error').textContent = 'No se pudo cargar el mapa. Comprueba la conexión.';
} else {
  const map = L.map('map', { attributionControl: false }).setView([-1.249, -78.617], 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

  if (data.reference && data.reference.length) {
    L.polyline(data.reference, { color: '#2f6df0', weight: 8, opacity: 0.35 }).addTo(map);
  }
  if (data.track && data.track.length) {
    L.polyline(data.track, { color: '#ea580c', weight: 4 }).addTo(map);
  }

  // Puntos de control (cuadrados planos)
  if (data.stops) {
    data.stops.forEach((s, idx) => {
      const stopIcon = L.divIcon({
        className: 'custom-stop-marker',
        html: '<div style="background:#ffffff;border:2px solid #2f6df0;color:#1d4ed8;font-weight:700;font-size:11px;text-align:center;line-height:20px;width:22px;height:22px;">' + (s.seq || idx + 1) + '</div>',
        iconSize: [22, 22],
        iconAnchor: [11, 11]
      });
      L.marker(s.point, { icon: stopIcon }).bindPopup('<b>Parada ' + (s.seq || idx + 1) + ':</b> ' + s.name).addTo(map);
    });
  }

  // Última posición conocida (cuadrado verde)
  if (data.track && data.track.length) {
    const lastPos = data.track[data.track.length - 1];
    const busIcon = L.divIcon({
      className: 'custom-bus-marker',
      html: '<div style="background:#1e7a4c;border:2px solid #ffffff;width:24px;height:24px;box-shadow:0 0 6px rgba(0,0,0,0.4);"></div>',
      iconSize: [24, 24],
      iconAnchor: [12, 12]
    });
    L.marker(lastPos, { icon: busIcon }).bindPopup('<b>Última posición GPS registrada</b>').addTo(map);
  }

  const allPoints = [...(data.reference || []), ...(data.track || [])];
  if (allPoints.length) {
    const bounds = L.latLngBounds(allPoints);
    if (bounds.isValid()) map.fitBounds(bounds.pad(0.12));
  } else {
    document.getElementById('error').textContent = 'No hay coordenadas disponibles para este recorrido.';
  }
}
</script>
</body>
</html>'''
        html = html.replace('__BODY_CLASS__', body_class)
        html = html.replace('__TITLE__', escape(rec.name or 'Recorrido'))
        html = html.replace('__VEHICULO__', escape(vehiculo))
        html = html.replace('__RUTA__', escape(ruta))
        html = html.replace('__LAST__', escape(last))
        html = html.replace('__SOURCE__', 'SIMULADO' if rec.simulado else 'Datos registrados Traccar')
        html = html.replace('__DATA__', payload)
        return Response(html, content_type='text/html; charset=utf-8', headers={'Cache-Control': 'no-store'})
