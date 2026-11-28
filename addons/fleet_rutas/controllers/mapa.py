"""Authenticated map using stored GPS data and the configured reference corridor."""
import json
from html import escape

from werkzeug.exceptions import Forbidden

from odoo import http, fields
from odoo.exceptions import UserError, ValidationError
from odoo.http import request, Response

from ..models.fleet_algoritmos import longitud_polilinea_m


class FleetMapa(http.Controller):
    def _require_admin(self):
        if not request.env.user.has_group('fleet_rutas.group_fleet_admin'):
            raise Forbidden('Solo el administrador de Flota puede acceder a esta página.')

    @http.route('/fleet_rutas/rutas/<int:route_id>/exportar', auth='user',
                type='http', methods=['GET'], csrf=False)
    def exportar_ruta(self, route_id, **kwargs):
        self._require_admin()
        ruta = request.env['fleet.ruta'].sudo().browse(route_id).exists()
        if not ruta:
            return request.not_found()

        schedules = []
        for trip in ruta.recorrido_ids.sorted('fecha_inicio'):
            schedules.append({
                'vehicle': {
                    'name': trip.vehicle_id.display_name or trip.vehicle_id.license_plate or '',
                    'license_plate': trip.vehicle_id.license_plate or '',
                    'traccar_device_id': trip.vehicle_id.traccar_device_id or 0,
                    'traccar_unique_id': trip.vehicle_id.traccar_unique_id or '',
                },
                'driver': trip.conductor_id.login or trip.conductor_id.name or '',
                'fecha_inicio': str(trip.fecha_inicio or ''),
                'fecha_fin_estimada': str(trip.fecha_fin_estimada or ''),
                'estado': trip.estado,
                'simulado': bool(trip.simulado),
                'notas': trip.notas or '',
            })

        payload = {
            'format': 'fleet-ruta-programacion',
            'version': 1,
            'exported_at': fields.Datetime.now().isoformat(),
            'route': {
                'name': ruta.name,
                'code': ruta.code or '',
                'estado': ruta.estado,
                'origen': ruta.origen,
                'destino': ruta.destino,
                'distancia_estimada_km': ruta.distancia_estimada_km,
                'duracion_estimada_min': ruta.duracion_estimada_min,
                'zona_horaria': ruta.zona_horaria,
                'notas': ruta.notas or '',
                'points': [{
                    'name': stop.name,
                    'secuencia': stop.secuencia,
                    'latitud': stop.latitud,
                    'longitud': stop.longitud,
                    'radio_proximidad_m': stop.radio_proximidad_m,
                    'hora_prevista': stop.hora_prevista,
                    'tolerancia_min': stop.tolerancia_min,
                    'tipo': stop.tipo,
                    'descripcion': stop.descripcion or '',
                } for stop in ruta.parada_ids.sorted('secuencia')],
            },
            'schedules': schedules,
        }
        filename = ('ruta-' + (ruta.code or str(ruta.id)) + '.json').replace(' ', '-')
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        return Response(
            body,
            status=200,
            headers=[
                ('Content-Type', 'application/json; charset=utf-8'),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ],
        )

    @http.route('/fleet_rutas/rutas/importar', auth='user',
                type='http', methods=['POST'], csrf=False)
    def importar_ruta(self, **kwargs):
        self._require_admin()
        try:
            payload = json.loads(request.httprequest.data.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return self._json_response({'status': 'error', 'message': 'Archivo JSON inválido.'}, 400)

        if not isinstance(payload, dict):
            return self._json_response({
                'status': 'error',
                'message': 'El archivo JSON debe contener un objeto de ruta.',
            }, 400)
        if payload.get('format') != 'fleet-ruta-programacion':
            return self._json_response({'status': 'error', 'message': 'Formato de archivo no reconocido.'}, 400)
        route = payload.get('route')
        points = route.get('points') if isinstance(route, dict) else None
        if not isinstance(route, dict) or not isinstance(points, list) or len(points) < 2:
            return self._json_response({
                'status': 'error',
                'message': 'La ruta debe incluir al menos dos puntos de control.',
            }, 400)

        Ruta = request.env['fleet.ruta'].sudo()
        Parada = request.env['fleet.parada'].sudo()
        Recorrido = request.env['fleet.recorrido'].sudo()

        code = str(route.get('code') or '').strip()[:32]
        if not code:
            code = ''.join(ch for ch in str(route.get('name') or 'RUTA').upper() if ch.isalnum())[:12] or 'RUTA'
        candidate = code
        suffix = 2
        while Ruta.search_count([('code', '=', candidate)]):
            candidate = '%s-%d' % (code[:28], suffix)
            suffix += 1

        ruta = Ruta.create({
            'name': str(route.get('name') or 'Ruta importada').strip(),
            'code': candidate,
            'estado': route.get('estado') if route.get('estado') in ('activa', 'suspendida', 'mantenimiento') else 'activa',
            'origen': str(route.get('origen') or points[0].get('name') or 'Origen'),
            'destino': str(route.get('destino') or points[-1].get('name') or 'Destino'),
            'distancia_estimada_km': float(route.get('distancia_estimada_km') or 0),
            'duracion_estimada_min': int(route.get('duracion_estimada_min') or 0),
            'zona_horaria': str(route.get('zona_horaria') or 'America/Guayaquil'),
            'notas': str(route.get('notas') or ''),
        })

        for index, point in enumerate(points, start=1):
            if not isinstance(point, dict):
                ruta.unlink()
                return self._json_response({
                    'status': 'error',
                    'message': 'El archivo contiene un punto de control inválido.',
                }, 400)
            try:
                latitud = float(point['latitud'])
                longitud = float(point['longitud'])
                if not (-90 <= latitud <= 90 and -180 <= longitud <= 180):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                ruta.unlink()
                return self._json_response({
                    'status': 'error',
                    'message': 'El archivo contiene coordenadas inválidas.',
                }, 400)
            Parada.create({
                'name': str(point.get('name') or 'Punto %d' % index),
                'ruta_id': ruta.id,
                'secuencia': int(point.get('secuencia') or index),
                'latitud': latitud,
                'longitud': longitud,
                'radio_proximidad_m': float(point.get('radio_proximidad_m') or 50),
                'hora_prevista': float(point.get('hora_prevista') or 8),
                'tolerancia_min': int(point.get('tolerancia_min') or 5),
                'tipo': point.get('tipo') if point.get('tipo') in ('origen', 'intermedia', 'destino') else (
                    'origen' if index == 1 else ('destino' if index == len(points) else 'intermedia')
                ),
                'descripcion': str(point.get('descripcion') or ''),
            })

        schedules_created = 0
        schedules_skipped = []
        Vehicle = request.env['fleet.vehicle'].sudo()
        User = request.env['res.users'].sudo()
        for schedule in payload.get('schedules') or []:
            if not isinstance(schedule, dict):
                schedules_skipped.append('Programación inválida')
                continue
            vehicle_data = schedule.get('vehicle') or {}
            if not isinstance(vehicle_data, dict):
                schedules_skipped.append('Vehículo desconocido')
                continue
            vehicle = False
            if vehicle_data.get('traccar_device_id'):
                try:
                    traccar_device_id = int(vehicle_data['traccar_device_id'])
                    vehicle = Vehicle.search([
                        ('traccar_device_id', '=', traccar_device_id),
                    ], limit=1)
                except (TypeError, ValueError):
                    vehicle = False
            if not vehicle and vehicle_data.get('traccar_unique_id'):
                vehicle = Vehicle.search([
                    ('traccar_unique_id', '=', str(vehicle_data['traccar_unique_id'])),
                ], limit=1)
            if not vehicle and vehicle_data.get('license_plate'):
                vehicle = Vehicle.search([
                    ('license_plate', '=', str(vehicle_data['license_plate'])),
                ], limit=1)
            if not vehicle:
                schedules_skipped.append(vehicle_data.get('name') or 'Vehículo desconocido')
                continue

            fecha_inicio = schedule.get('fecha_inicio')
            if not fecha_inicio:
                schedules_skipped.append(vehicle_data.get('name') or 'Vehículo desconocido')
                continue
            try:
                fecha_inicio_dt = fields.Datetime.from_string(str(fecha_inicio).replace('T', ' ')[:19])
                fecha_fin_dt = False
                if schedule.get('fecha_fin_estimada'):
                    fecha_fin_dt = fields.Datetime.from_string(
                        str(schedule['fecha_fin_estimada']).replace('T', ' ')[:19]
                    )
            except Exception:
                schedules_skipped.append(vehicle_data.get('name') or 'Vehículo desconocido')
                continue

            driver = False
            if schedule.get('driver'):
                driver = User.search([
                    ('login', '=', str(schedule['driver'])),
                ], limit=1)
            estado = schedule.get('estado') if schedule.get('estado') in (
                'programado', 'en_curso', 'completado', 'cancelado', 'con_incidencias'
            ) else 'programado'
            Recorrido.create({
                'ruta_id': ruta.id,
                'vehicle_id': vehicle.id,
                'conductor_id': driver.id if driver else False,
                'fecha_inicio': fecha_inicio_dt,
                'fecha_fin_estimada': fecha_fin_dt,
                'estado': estado,
                'simulado': bool(schedule.get('simulado')),
                'notas': str(schedule.get('notas') or ''),
            })
            schedules_created += 1

        return self._json_response({
            'status': 'ok',
            'route_id': ruta.id,
            'route_code': candidate,
            'schedules_created': schedules_created,
            'schedules_skipped': schedules_skipped,
        })

    @http.route('/fleet_rutas/rutas/nueva', auth='user', type='http', methods=['GET'])
    def nueva_ruta(self, **kwargs):
        self._require_admin()
        route_id = int(kwargs.get('route_id') or 0)
        route_data = {'name': '', 'distance': 0, 'departure': '08:00', 'corridor': 100, 'points': []}
        if route_id:
            ruta = request.env['fleet.ruta'].sudo().browse(route_id).exists()
            if not ruta:
                return request.not_found()
            stops = ruta.parada_ids.sorted('secuencia')
            corridor = stops[0].radio_proximidad_m if stops else 100
            if stops:
                first_minutes = round(stops[0].hora_prevista * 60)
                route_data['departure'] = '%02d:%02d' % (first_minutes // 60 % 24, first_minutes % 60)
            route_data.update({
                'name': ruta.name,
                'distance': ruta.distancia_estimada_km,
                'corridor': corridor,
                'points': [{
                    'lat': stop.latitud,
                    'lng': stop.longitud,
                    'name': stop.name,
                    'time': '%02d:%02d' % (round(stop.hora_prevista * 60) // 60 % 24, round(stop.hora_prevista * 60) % 60),
                    'tolerance': stop.tolerancia_min,
                    'radio': stop.radio_proximidad_m,
                } for stop in stops],
            })
        html = r'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__ROUTE_TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
*{box-sizing:border-box} body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#1f2937}
.header{height:72px;display:flex;align-items:center;justify-content:space-between;padding:0 24px;background:#fff;border-bottom:1px solid #e5e7eb}
.header h1{font-size:24px;margin:0}

.layout{display:grid;grid-template-columns:minmax(0,1fr) 440px;height:calc(100vh - 72px)}
.map-wrap{position:relative;padding:16px}.map-wrap input{position:absolute;z-index:500;top:28px;left:28px;width:280px;height:38px;border:1px solid #d1d5db;border-radius:8px;padding:0 12px}
#map{height:100%;border-radius:12px;border:1px solid #dfe3e8}
.panel{background:#fff;border-left:1px solid #e5e7eb;padding:20px;overflow:auto}.field{margin-bottom:14px}.field label{display:block;font-size:13px;color:#6b7280;margin-bottom:6px}
.field input{width:100%;height:42px;border:1px solid #d1d5db;border-radius:8px;padding:0 10px}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.metric{font-size:13px;color:#6b7280}.metric strong{display:block;color:#111827;font-size:16px;margin-top:3px}
.point{display:grid;grid-template-columns:28px minmax(0,1fr) 96px 30px;align-items:center;gap:6px 8px;padding:10px 0;border-bottom:1px solid #edf0f3}.seq{width:24px;height:24px;border-radius:50%;background:#2563eb;color:#fff;text-align:center;line-height:24px;font-weight:bold}
.point input{width:100%;min-width:0;height:32px;border:1px solid #d1d5db;border-radius:6px;padding:0 6px}.point .latlng{grid-column:2/-1;display:grid;grid-template-columns:1fr 1fr;gap:8px}.latlng label{display:flex;align-items:center;gap:4px;font-size:12px;color:#6b7280}
.point .remove{height:30px;border:0;border-radius:6px;background:#e5e7eb;cursor:pointer}.add{width:100%;height:36px;margin-top:10px;border:1px dashed #9ca3af;border-radius:8px;background:#fff;cursor:pointer}
.footer{position:sticky;bottom:-20px;background:#fff;border-top:1px solid #e5e7eb;padding:14px 0 0;display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}.footer button:disabled{opacity:.5;cursor:not-allowed}.footer small{flex-basis:100%;text-align:right;color:#6b7280}.footer small[hidden]{display:none}
.footer button{height:40px;border:0;border-radius:8px;padding:0 10px;font-size:13px;white-space:nowrap;cursor:pointer}.cancel{background:#e5e7eb}.save{background:#2563eb;color:#fff}.hint{background:#dbeafe;color:#2563eb;padding:12px;border-radius:8px;font-size:13px;margin-top:10px;text-align:center}
@media(max-width:900px){.layout{grid-template-columns:1fr}.panel{border-left:0}.map-wrap{height:420px}}
</style>
</head>
<body>
<div class="header"><h1>__ROUTE_TITLE__</h1></div>
<div class="layout">
<div class="map-wrap" id="mapWrap"><input id="search" placeholder="Buscar dirección o lugar"><div id="map"></div></div>
<aside class="panel">
<div class="row"><div class="field"><label>Nombre de la ruta</label><input id="name" value="__ROUTE_NAME__" placeholder="Ej.: Ficoa - UTA"></div><div class="field"><label>Hora de salida</label><input id="departure" type="time" value="__ROUTE_DEPARTURE__"></div></div>
<div class="row"><div class="metric">Distancia estimada<strong id="distance">__ROUTE_DISTANCE__ km (calculada)</strong></div><div class="field"><label>Corredor de desvío (m)</label><input id="corridor" type="number" value="__ROUTE_CORRIDOR__"></div></div>
<h3>Puntos de control: <span id="pointCount">0</span></h3>
<div id="points"></div>
<button type="button" id="addCoord" class="add">Agregar por coordenadas</button>
<div class="hint" id="hint">Haz clic en el mapa para agregar un punto o edita sus coordenadas en la lista. Arrastra los marcadores para moverlos. Clic derecho sobre un punto para eliminarlo.</div>
<div class="footer"><button class="cancel" onclick="location.href='/web#menu_id=0&action=fleet_rutas.action_fleet_rutas_dashboard'">Cancelar</button><button class="cancel" id="save" disabled>Guardar sin trazado</button><button class="save" id="savePath" disabled>Continuar con trazado</button><small id="minimo" role="status">Agrega al menos dos puntos de control para guardar.</small></div>
</aside>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const map=L.map('map').setView([-1.249,-78.617],13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);
const editingRouteId=__EDIT_ROUTE_ID__;
let points=__ROUTE_POINTS__;
let routeLine=null;
function haversine(a,b){const R=6371,p1=a.lat*Math.PI/180,p2=b.lat*Math.PI/180,d=Math.PI*(b.lat-a.lat)/180,x=Math.PI*(b.lng-a.lng)/180,s=Math.sin(d/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(x/2)**2;return 2*R*Math.asin(Math.sqrt(s))}
function distance(){let d=0;for(let i=1;i<points.length;i++)d+=haversine(points[i-1],points[i]);document.getElementById('distance').textContent=d.toFixed(2)+' km (calculada)';return d}
function escapeHtml(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function removePoint(i){points.splice(i,1);redraw()}
function redraw(fitAll=false){
map.eachLayer(layer=>{if(layer.options&&layer.options.routeMarker)map.removeLayer(layer)});
if(routeLine){map.removeLayer(routeLine);routeLine=null}
points.forEach((p,i)=>{const icon=L.divIcon({className:'',html:'<div style="width:28px;height:28px;border-radius:50%;background:#2563eb;color:white;border:3px solid white;line-height:22px;text-align:center;font-weight:bold;box-shadow:0 2px 6px #777">'+(i+1)+'</div>',iconSize:[28,28],iconAnchor:[14,14]});const marker=L.marker([p.lat,p.lng],{icon,draggable:true,routeMarker:true}).addTo(map);marker.on('contextmenu',()=>removePoint(i));marker.on('dragend',e=>{p.lat=e.target.getLatLng().lat;p.lng=e.target.getLatLng().lng;renderPoints();redraw()})});
if(points.length>1){routeLine=L.polyline(points.map(p=>[p.lat,p.lng]),{color:'#2563eb',weight:5}).addTo(map)}
renderPoints();distance();
if(fitAll && points.length){const bounds=L.latLngBounds(points.map(p=>[p.lat,p.lng]));if(bounds.isValid()){map.fitBounds(bounds,{padding:[40,40],maxZoom:16})}}
}
function hhmmToDecimal(value){const [h,m]=(value||'08:00').split(':').map(Number);return h+(m||0)/60}
let saving=false;
function updateSaveButtons(){const missing=points.length<2;document.getElementById('save').disabled=document.getElementById('savePath').disabled=missing||saving;document.getElementById('minimo').hidden=!missing}
function renderPoints(){
updateSaveButtons();
document.getElementById('pointCount').textContent=points.length;
const container=document.getElementById('points');container.innerHTML='';
points.forEach((p,i)=>{const el=document.createElement('div');el.className='point';
el.innerHTML='<div class="seq">'+(i+1)+'</div><input class="pname" aria-label="Nombre del punto" placeholder="Nombre" value="'+escapeHtml(p.name||'')+'"><input class="ptime" type="time" aria-label="Hora prevista" value="'+escapeHtml(p.time||'08:'+String(i*15).padStart(2,'0'))+'"><button type="button" class="remove" title="Eliminar punto" aria-label="Eliminar punto">×</button><div class="latlng"><label>Lat<input class="plat" type="number" step="0.000001" value="'+Number(p.lat).toFixed(6)+'"></label><label>Lon<input class="plng" type="number" step="0.000001" value="'+Number(p.lng).toFixed(6)+'"></label></div>';
el.querySelector('.pname').oninput=e=>p.name=e.target.value;
el.querySelector('.ptime').onchange=e=>p.time=e.target.value;
el.querySelector('.remove').onclick=()=>removePoint(i);
// Un valor vacío o fuera de rango no mueve el punto: se recupera el anterior.
[['.plat','lat',90],['.plng','lng',180]].forEach(([selector,key,limit])=>{const input=el.querySelector(selector);input.onchange=()=>{const value=input.value.trim()===''?NaN:Number(input.value);if(Number.isFinite(value)&&Math.abs(value)<=limit){p[key]=value;redraw(true)}else{input.value=Number(p[key]).toFixed(6)}}});
el.oncontextmenu=e=>{if(e.target.tagName!=='INPUT'){e.preventDefault();removePoint(i)}};
container.appendChild(el)});
}
function addPoint(lat,lng){points.push({lat,lng,name:'Punto '+(points.length+1),time:'08:'+String(points.length*15).padStart(2,'0')});redraw(true)}
map.on('click',e=>addPoint(e.latlng.lat,e.latlng.lng));
document.getElementById('search').onkeydown=async e=>{if(e.key==='Enter'){e.preventDefault();const q=e.target.value;if(!q)return;const r=await fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1&q='+encodeURIComponent(q));const j=await r.json();if(j[0])map.setView([Number(j[0].lat),Number(j[0].lon)],16)}};
document.getElementById('addCoord').onclick=()=>{const c=map.getCenter();addPoint(Number(c.lat.toFixed(6)),Number(c.lng.toFixed(6)));const rows=document.querySelectorAll('.plat');rows[rows.length-1].focus()};
async function saveRoute(withPath){if(points.length<2||saving)return;const base=hhmmToDecimal(document.getElementById('departure').value);const payload={route_id:editingRouteId,name:document.getElementById('name').value.trim()||document.getElementById('name').defaultValue||'Nueva ruta',distance:distance(),departure:document.getElementById('departure').value,corridor:Number(document.getElementById('corridor').value||100),points:points.map((p,i)=>({...p,name:p.name||('Punto '+(i+1)),time:hhmmToDecimal(p.time||document.getElementById('departure').value),type:i===0?'origen':i===points.length-1?'destino':'intermedia',tolerance:p.tolerance??5,radio:p.radio||50}))};saving=true;updateSaveButtons();try{const response=await fetch('/fleet_rutas/rutas/crear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await response.json();if(!response.ok){alert(data.message||'No se pudo guardar la ruta');saving=false;updateSaveButtons();return}location.href=withPath?'/fleet_rutas/trazado/'+data.route_id+'?paso=2':'/web#menu_id=0&action=fleet_rutas.action_fleet_rutas_dashboard'}catch(e){alert('No se pudo guardar la ruta');saving=false;updateSaveButtons()}}
document.getElementById('save').onclick=()=>saveRoute(false);
document.getElementById('savePath').onclick=()=>saveRoute(true);
renderPoints();
if(editingRouteId && points.length){setTimeout(()=>redraw(true),100)}
</script>
</body>
</html>'''
        title = 'Editar ruta' if route_id else 'Nueva ruta'
        html = (html
                .replace('__ROUTE_TITLE__', escape(title))
                .replace('__ROUTE_NAME__', escape(route_data['name']))
                .replace('__ROUTE_DEPARTURE__', escape(route_data['departure']))
                .replace('__ROUTE_DISTANCE__', escape(str(round(float(route_data['distance'] or 0), 2))))
                .replace('__ROUTE_CORRIDOR__', escape(str(round(float(route_data['corridor'] or 100), 2))))
                .replace('__EDIT_ROUTE_ID__', str(route_id))
                .replace('__ROUTE_POINTS__', json.dumps(route_data['points']).replace('</', '<\\/')))
        return Response(html, content_type='text/html; charset=utf-8',
                        headers={'Cache-Control': 'no-store'})

    @http.route('/fleet_rutas/rutas/crear', auth='user', type='http', methods=['POST'], csrf=False)
    def crear_ruta(self, **kwargs):
        self._require_admin()
        try:
            payload = json.loads(request.httprequest.data.decode('utf-8'))
            name = payload['name']
            distance = payload['distance']
            departure = payload.get('departure')
            corridor = payload.get('corridor')
            points = payload['points']
            route_id = int(payload.get('route_id') or 0)
        except (AttributeError, KeyError, TypeError, json.JSONDecodeError):
            return self._json_response({'status': 'error', 'message': 'Datos inválidos'}, 400)
        if not isinstance(points, list) or len(points) < 2:
            return self._json_response({'status': 'error', 'message': 'Agrega al menos dos puntos.'}, 400)
        Ruta = request.env['fleet.ruta'].sudo()
        clean_name = str(name or '').strip()
        if not clean_name:
            clean_name = 'Nueva ruta'
        code_base = ''.join(ch for ch in clean_name.upper() if ch.isalnum())
        code = code_base[:12] or 'RUTA'
        suffix = 1
        candidate = code
        while Ruta.search_count([('code', '=', candidate)]):
            suffix += 1
            candidate = f'{code}-{suffix}'
        first = points[0]
        last = points[-1]
        duration = int(round((float(last.get('time') or 8) - float(first.get('time') or 8)) * 60))
        if duration < 0:
            duration += 24 * 60
        route_values = {
            'name': clean_name,
            'origen': str(first.get('name') or 'Origen'),
            'destino': str(last.get('name') or 'Destino'),
            'distancia_estimada_km': float(distance or 0),
            'duracion_estimada_min': duration,
            'zona_horaria': 'America/Guayaquil',
        }
        ruta = Ruta
        if route_id:
            ruta = Ruta.search([('id', '=', route_id)], limit=1)
            if not ruta:
                return self._json_response({'status': 'error', 'message': 'La ruta no existe.'}, 404)
        try:
            paradas = [{
                'name': str(point.get('name') or f'Punto {index}'),
                'secuencia': index,
                'latitud': float(point['lat']),
                'longitud': float(point['lng']),
                'radio_proximidad_m': float(
                    corridor if index in (1, len(points)) else point.get('radio') or 50),
                'hora_prevista': float(point.get('time') if point.get('time') is not None else 8),
                'tolerancia_min': int(point['tolerance'] if point.get('tolerance') is not None else 5),
                'tipo': 'origen' if index == 1 else ('destino' if index == len(points) else 'intermedia'),
            } for index, point in enumerate(points, start=1)]
            # Todo o nada: si las paradas no se aceptan, la ruta tampoco cambia.
            with request.env.cr.savepoint():
                if ruta:
                    ruta.write(route_values)
                else:
                    route_values.update({'code': candidate, 'estado': 'activa'})
                    ruta = Ruta.create(route_values)
                ruta.reemplazar_paradas(paradas)
        except (UserError, ValidationError) as exc:
            return self._json_response({'status': 'error', 'message': exc.args[0]}, 400)
        except (AttributeError, KeyError, TypeError, ValueError):
            return self._json_response({'status': 'error', 'message': 'Datos de paradas inválidos'}, 400)
        ruta.invalidate_recordset(['parada_ids', 'trazado_vigente'])
        if ruta.trazado_vigente:
            ruta.distancia_estimada_km = round(
                longitud_polilinea_m(ruta.puntos_referencia()) / 1000, 3)
        return self._json_response({'status': 'ok', 'route_id': ruta.id})

    @http.route('/fleet_rutas/vehiculos_vivos', auth='user', type='http',
                methods=['GET'], csrf=False)
    def vehiculos_vivos(self, **kwargs):
        self._require_admin()
        vehicles = request.env['fleet.vehicle'].sudo().search([
            ('traccar_tracking_enabled', '=', True),
        ], order='traccar_last_update desc')
        active_trips = request.env['fleet.recorrido'].sudo().search([
            ('estado', '=', 'en_curso'),
        ])
        trip_by_vehicle = {trip.vehicle_id.id: self._recorrido_en_vivo(trip) for trip in active_trips}
        items = []
        for vehicle in vehicles:
            items.append({
                'id': vehicle.id,
                'name': vehicle.display_name or vehicle.license_plate or f'Vehículo {vehicle.id}',
                'plate': vehicle.license_plate or '',
                'device_id': vehicle.traccar_device_id,
                'unique_id': vehicle.traccar_unique_id or '',
                'status': vehicle.traccar_device_status or 'unknown',
                'marker_color': vehicle.traccar_marker_color or '#714b67',
                'latitude': vehicle.traccar_last_latitude or 0.0,
                'longitude': vehicle.traccar_last_longitude or 0.0,
                'speed': vehicle.traccar_last_speed or 0.0,
                'last_update': str(vehicle.traccar_last_update) if vehicle.traccar_last_update else '',
                'active_trip': trip_by_vehicle.get(vehicle.id),
            })
        return self._json_response({
            'vehicles': items,
            'server_time': fields.Datetime.now().isoformat(),
        })

    @staticmethod
    def _recorrido_en_vivo(trip):
        """Ruta, rastro reciente e incidencias de un recorrido en curso, para el mapa."""
        recientes = request.env['fleet.posicion.gps'].sudo().search(
            [('recorrido_id', '=', trip.id)], order='timestamp desc, id desc', limit=200)
        tipos = dict(request.env['fleet.incidencia']._fields['tipo'].selection)
        incidencias = []
        for i in trip.incidencia_ids.filtered(lambda i: not i.resuelta):
            # Las alertas de retraso u omisión se ubican en su parada.
            lat = i.latitud or i.parada_id.latitud
            lng = i.longitud or i.parada_id.longitud
            if lat and lng:
                incidencias.append({'lat': lat, 'lng': lng, 'type': tipos.get(i.tipo, i.tipo),
                                    'text': i.descripcion or ''})
        return {
            'id': trip.id,
            'name': trip.name,
            'ruta_id': trip.ruta_id.id,
            'ruta_name': trip.ruta_id.name,
            'simulated': trip.simulado,
            'path': trip.ruta_id.puntos_referencia(),
            'approximate': not trip.ruta_id.trazado_vigente,
            'stops': [{'lat': p.latitud, 'lng': p.longitud, 'name': p.name}
                      for p in trip.paradas_del_recorrido()],
            'trail': [[p.latitud, p.longitud] for p in reversed(recientes)],
            'incidents': incidencias,
            'pending_incidents': len(trip.incidencia_ids.filtered(lambda i: not i.resuelta)),
        }

    @http.route('/fleet_rutas/asignar_ruta', auth='user', type='http',
                methods=['POST'], csrf=False)
    def asignar_ruta(self, **kwargs):
        self._require_admin()
        try:
            payload = json.loads(request.httprequest.data.decode('utf-8') or '{}')
            vehicle_id = int(payload['vehicle_id'])
            route_id = int(payload['route_id'])
            start = bool(payload.get('start', False))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return self._json_response({'status': 'error', 'message': 'Datos inválidos'}, 400)

        Vehicle = request.env['fleet.vehicle'].sudo()
        Ruta = request.env['fleet.ruta'].sudo()
        Recorrido = request.env['fleet.recorrido'].sudo()
        vehicle = Vehicle.browse(vehicle_id).exists()
        route = Ruta.browse(route_id).exists()
        if not vehicle or not route:
            return self._json_response({'status': 'error', 'message': 'Vehículo o ruta no encontrado'}, 404)
        if not vehicle.traccar_tracking_enabled:
            return self._json_response({'status': 'error', 'message': 'El vehículo no tiene seguimiento GPS'}, 400)

        trip = Recorrido.search([
            ('vehicle_id', '=', vehicle.id),
            ('estado', '=', 'en_curso'),
        ], limit=1)
        if not trip:
            trip = Recorrido.search([
                ('vehicle_id', '=', vehicle.id),
                ('estado', '=', 'programado'),
            ], limit=1, order='fecha_inicio desc')

        if trip:
            trip.write({
                'ruta_id': route.id,
                'vehicle_id': vehicle.id,
            })
        else:
            trip = Recorrido.create({
                'ruta_id': route.id,
                'vehicle_id': vehicle.id,
                'estado': 'programado',
                'fecha_inicio': fields.Datetime.now(),
                'fecha_fin_estimada': False,
            })

        if start and trip.estado == 'programado':
            trip.action_iniciar()

        return self._json_response({
            'status': 'ok',
            'trip_id': trip.id,
            'started': trip.estado == 'en_curso',
        })

    @http.route('/fleet_rutas/mapa/vivo', auth='user', type='http', methods=['GET'])
    def mapa_vivo(self, **kwargs):
        self._require_admin()
        routes = request.env['fleet.ruta'].sudo().search([('estado', '=', 'activa')], order='name')
        routes_json = json.dumps([{'id': route.id, 'name': route.name} for route in routes])
        route_options = ''.join(
            '<option value="%d">%s</option>' % (route.id, escape(route.name))
            for route in routes
        )
        html = '''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitoreo GPS en vivo</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
* { box-sizing: border-box; }
body { margin: 0; height: 100vh; font-family: Arial,sans-serif; }
#layout { display:grid; grid-template-columns:270px 1fr; height:100vh; }
#sidebar { overflow:auto; border-right:1px solid #ddd; background:#fff; padding:12px; }
#map { height:100vh; }
body.panel #layout { grid-template-columns:1fr; } body.panel #sidebar { display:none; }
#legend { position:fixed; right:10px; bottom:22px; z-index:1000; background:#fff; padding:8px 10px; font-size:12px; box-shadow:0 1px 5px #0004; max-width:260px; }
#legend i { display:inline-block; width:18px; height:4px; margin-right:6px; vertical-align:middle; }
.vehicle { border:1px solid #ddd; padding:8px; margin-bottom:8px; cursor:pointer; }
.vehicle:hover { background:#f7f7f7; }
.vehicle.selected { border-left:4px solid #714b67; }
.muted { color:#777; font-size:12px; }
.ok { color:#1e7a4c; } .stale { color:#9a6700; }
select,button { width:100%; margin-top:6px; padding:7px; }
button { border:0; background:#714b67; color:#fff; cursor:pointer; }
.leaflet-popup-content { min-width:220px; }
</style>
</head>
<body>
<div id="layout">
  <aside id="sidebar">
    <h3>Flota en vivo</h3>
    <div id="vehicles"></div>
  </aside>
  <div id="map"></div>
</div>
<div id="legend"><i style="background:#2f6df0"></i>Ruta <i style="background:#ea580c"></i>Rastro <i style="background:#b42a2a;height:10px;width:10px;border-radius:50%"></i>Incidencia<div id="live-summary" role="status"></div></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
if (new URLSearchParams(location.search).has('panel')) document.body.classList.add('panel');
const map = L.map('map').setView([-1.249, -78.617], 13);
const tripLayers = L.layerGroup().addTo(map);
const localTime = value => value ? new Date(value.replace(' ', 'T') + 'Z').toLocaleString('es-EC') : 'Sin posición';
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19}).addTo(map);
const markers = {};
const markerStates = {};
let selectedVehicleId = null;
const routeOptions = __ROUTES__;
let initialFitPending = true;
let userChangedMap = false;
let applyingInitialFit = false;
map.on('dragstart', () => { userChangedMap = true; initialFitPending = false; });
map.on('zoomstart', () => {
  if (!applyingInitialFit) {
    userChangedMap = true;
    initialFitPending = false;
  }
});

function stale(update) {
  if (!update) return true;
  return Date.now() - new Date(update.replace(' ', 'T') + 'Z').getTime() > 120000;
}
function escapeHtml(value) {
  const el = document.createElement('div');
  el.textContent = value == null ? '' : String(value);
  return el.innerHTML;
}
async function assignRoute(vehicleId, routeId, start) {
  const response = await fetch('/fleet_rutas/asignar_ruta', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({vehicle_id:vehicleId, route_id:Number(routeId), start:start})
  });
  const data = await response.json();
  if (!response.ok) alert(data.message || 'No se pudo asignar la ruta');
  else { alert(start ? 'Ruta iniciada.' : 'Ruta asignada.'); refresh(); }
}
async function refresh() {
  const response = await fetch('/fleet_rutas/vehiculos_vivos');
  const data = await response.json();
  const container = document.getElementById('vehicles');
  const points = [];
  const summary = [];
  const tripPoints = [];
  tripLayers.clearLayers();
  for (const vehicle of data.vehicles) {
    const trip = vehicle.active_trip;
    if (!trip) continue;
    if (trip.path.length > 1) L.polyline(trip.path, {color:'#2f6df0', weight:6, opacity:.5, dashArray: trip.approximate ? '8 8' : null}).addTo(tripLayers);
    trip.stops.forEach((s, i) => L.circleMarker([s.lat, s.lng], {radius:6, color:'#1d4ed8', fillColor:'#fff', fillOpacity:1})
      .bindPopup(escapeHtml((i + 1) + '. ' + s.name)).addTo(tripLayers));
    if (trip.trail.length > 1) L.polyline(trip.trail, {color:'#ea580c', weight:3}).addTo(tripLayers);
    trip.incidents.forEach(inc => L.circleMarker([inc.lat, inc.lng], {radius:8, color:'#fff', weight:2, fillColor:'#b42a2a', fillOpacity:.95})
      .bindPopup('<b>' + escapeHtml(inc.type) + '</b><br>' + escapeHtml(inc.text)).addTo(tripLayers));
    tripPoints.push(...trip.path, ...trip.trail);
    summary.push(escapeHtml(trip.ruta_name) + (trip.simulated ? ' (simulado)' : '') + ': ' + trip.pending_incidents + ' pendientes');
  }
  document.getElementById('live-summary').innerHTML = summary.length ? summary.join('<br>') : 'Sin recorridos en curso';
  for (const vehicle of data.vehicles) {
    const lat = Number(vehicle.latitude), lng = Number(vehicle.longitude);
    if (lat && lng) points.push([lat,lng]);
    const vehicleLabel = escapeHtml(vehicle.name);
    const plate = vehicle.plate ? escapeHtml(vehicle.plate) : '';
    const deviceLabel = 'Traccar ID ' + escapeHtml(String(vehicle.device_id || '-')) +
      (vehicle.unique_id ? ' · IMEI/ID ' + escapeHtml(vehicle.unique_id) : '');
    const isStale = stale(vehicle.last_update);
    const markerColor = /^#[0-9A-Fa-f]{6}$/.test(vehicle.marker_color || '') ? vehicle.marker_color : '#714b67';
    const iconKey = markerColor + ':' + isStale;
    let marker = markers[vehicle.id];
    if (lat && lng) {
      if (!marker) {
        const icon = L.divIcon({
          className:'fleet-live-marker',
          html:'<div style="width:18px;height:18px;border:3px solid '+(isStale?'#9a6700':'white')+';border-radius:50%;background:'+markerColor+';box-shadow:0 2px 8px #333"></div>',
          iconSize:[18,18], iconAnchor:[9,9]
        });
        marker = L.marker([lat,lng], {icon}).addTo(map);
        markers[vehicle.id] = marker;
        markerStates[vehicle.id] = iconKey;
      } else {
        marker.setLatLng([lat,lng]);
        if (markerStates[vehicle.id] !== iconKey) {
          const icon = L.divIcon({
            className:'fleet-live-marker',
            html:'<div style="width:18px;height:18px;border:3px solid '+(isStale?'#9a6700':'white')+';border-radius:50%;background:'+markerColor+';box-shadow:0 2px 8px #333"></div>',
            iconSize:[18,18], iconAnchor:[9,9]
          });
          marker.setIcon(icon);
          markerStates[vehicle.id] = iconKey;
        }
      }
      marker.bindPopup('<b>'+escapeHtml(vehicle.name)+'</b><br>'+
        (plate ? plate+'<br>' : '')+
        escapeHtml(deviceLabel)+'<br>'+
        escapeHtml(vehicle.speed.toFixed ? vehicle.speed.toFixed(1) : vehicle.speed)+' km/h');
    }
    const activeName = vehicle.active_trip ? vehicle.active_trip.ruta_name : 'Sin recorrido activo';
    let div = container.querySelector('[data-vehicle-id="'+vehicle.id+'"]');
    if (!div) {
      const options = routeOptions.map(r=>'<option value="'+r.id+'">'+escapeHtml(r.name)+'</option>').join('');
      div = document.createElement('div');
      div.dataset.vehicleId = vehicle.id;
      div.className = 'vehicle';
      div.innerHTML =
        '<div class="vehicle-head" style="border-left:5px solid '+markerColor+';padding-left:7px">'+
        '<b>'+vehicleLabel+'</b>'+ (plate ? '<div class="muted">Matrícula: '+plate+'</div>' : '') +
        '<div class="muted">'+deviceLabel+'</div></div>'+
        '<div class="vehicle-status muted"></div>'+
        '<div class="vehicle-trip muted"></div>'+
        '<select id="route-'+vehicle.id+'">'+options+'</select>'+
        '<button data-assign="'+vehicle.id+'" data-start="false">Asignar ruta</button>'+
        '<button data-assign="'+vehicle.id+'" data-start="true">Asignar e iniciar</button>';
      div.addEventListener('click',()=>{
        selectedVehicleId=vehicle.id;
        container.querySelectorAll('.vehicle').forEach(card=>card.classList.remove('selected'));
        div.classList.add('selected');
        if (lat && lng) map.setView([lat,lng],16);
      });
      div.querySelectorAll('button').forEach(button=>{
        button.addEventListener('click',(event)=>{
          event.stopPropagation();
          const routeId=document.getElementById('route-'+vehicle.id).value;
          assignRoute(vehicle.id,routeId,button.dataset.start==='true');
        });
      });
      container.appendChild(div);
    }
    div.querySelector('.vehicle-head').style.borderLeftColor = markerColor;
    div.querySelector('.vehicle-status').innerHTML =
      (isStale?'<span class="stale">Desactualizado</span>':'<span class="ok">Reciente</span>')+
      ' · '+escapeHtml(vehicle.speed.toFixed ? vehicle.speed.toFixed(1) : vehicle.speed)+' km/h';
    div.querySelector('.vehicle-trip').textContent =
      activeName + ' · ' + localTime(vehicle.last_update);
  }
  const fitTarget = tripPoints.length ? tripPoints : points;
  if (initialFitPending && !userChangedMap && fitTarget.length) {
    applyingInitialFit = true;
    map.fitBounds(L.latLngBounds(fitTarget).pad(0.15));
    applyingInitialFit = false;
    initialFitPending = false;
  }
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>'''.replace('__ROUTES__', routes_json)
        return Response(html, content_type='text/html; charset=utf-8',
                        headers={'Cache-Control': 'no-store'})

    @staticmethod
    def _json_response(data, status=200):
        return Response(json.dumps(data), status=status,
                        content_type='application/json',
                        headers={'Cache-Control': 'no-store'})

    @http.route('/fleet_rutas/repeticion/<int:recorrido_id>/datos', auth='user',
                type='http', methods=['GET'], csrf=False)
    def repeticion_datos(self, recorrido_id, **kwargs):
        self._require_admin()
        rec = request.env['fleet.recorrido'].sudo().browse(recorrido_id).exists()
        if not rec:
            return self._json_response({'status': 'error', 'message': 'Recorrido no encontrado'}, 404)

        domain = [('recorrido_id', '=', recorrido_id)]
        date_from = kwargs.get('date_from')
        date_to = kwargs.get('date_to')
        if date_from:
            domain.append(('timestamp', '>=', date_from.replace('T', ' ')))
        if date_to:
            domain.append(('timestamp', '<=', date_to.replace('T', ' ')))

        positions = request.env['fleet.posicion.gps'].sudo().search(
            domain,
            order='timestamp asc',
        )
        stops = rec.paradas_del_recorrido()
        data = {
            'status': 'ok',
            'name': rec.name,
            'vehicle': rec.vehicle_id.display_name or rec.vehicle_id.license_plate or '',
            'reference': [[p.latitud, p.longitud] for p in stops],
            'stops': [{
                'name': p.name,
                'seq': p.secuencia,
                'point': [p.latitud, p.longitud],
            } for p in stops],
            'track': [{
                'lat': p.latitud,
                'lng': p.longitud,
                'timestamp': str(p.timestamp),
                'speed': p.velocidad_kmh,
                'course': p.rumbo,
                'distance': p.distancia_ruta_m,
                'deviation': p.es_desviacion,
            } for p in positions],
        }
        return self._json_response(data)

    @http.route('/fleet_rutas/repeticion/<int:recorrido_id>', auth='user',
                type='http', methods=['GET'])
    def repeticion(self, recorrido_id, **kwargs):
        self._require_admin()
        rec = request.env['fleet.recorrido'].sudo().browse(recorrido_id).exists()
        if not rec:
            return request.not_found()

        start = str(rec.fecha_inicio_real or rec.fecha_inicio or fields.Datetime.now())
        end = str(rec.fecha_fin_real or rec.fecha_fin_estimada or fields.Datetime.now())
        start_value = start[:16].replace(' ', 'T')
        end_value = end[:16].replace(' ', 'T')
        html = r'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Repetición de ruta</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#fff;color:#161616}
.toolbar{display:flex;align-items:center;gap:8px;padding:10px;border-bottom:1px solid #e0e0e0;flex-wrap:wrap}
.toolbar label{font-size:12px;color:#525252}.toolbar input,.toolbar select{height:36px;border:1px solid #d0d0d0;padding:5px 8px}
.toolbar button{height:36px;border:0;background:#714b67;color:#fff;padding:0 14px;cursor:pointer}
.controls{display:flex;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid #e0e0e0}
.controls button{height:34px;border:1px solid #d0d0d0;background:#fff;cursor:pointer;padding:0 10px}
.controls button.primary{background:#2563eb;border-color:#2563eb;color:#fff}
.controls input[type=range]{flex:1}
#map{height:520px}
.status{font-size:12px;color:#525252;min-width:220px}
@media(max-width:700px){#map{height:380px}.status{width:100%}}
</style>
</head>
<body>
<div class="toolbar">
  <label>Desde<br><input id="dateFrom" type="datetime-local" value="__START__"></label>
  <label>Hasta<br><input id="dateTo" type="datetime-local" value="__END__"></label>
  <button id="show">Mostrar repetición</button>
</div>
<div class="controls">
  <button id="play" class="primary">Iniciar</button>
  <input id="progress" type="range" min="0" max="0" value="0">
  <select id="speed" aria-label="Velocidad de reproducción">
    <option value="1">1x</option><option value="5">5x</option><option value="10">10x</option>
  </select>
  <div class="status" id="status">Sin datos registrados</div>
</div>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const routeId=__RECORRIDO_ID__;
const map=L.map('map').setView([-1.249,-78.617],13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);
let track=[],timer=null,index=0,speed=1,marker=null,played=L.polyline([],{color:'#ea580c',weight:4}).addTo(map);
let referenceLine=null;
function escapeHtml(v){const el=document.createElement('div');el.textContent=v==null?'':String(v);return el.innerHTML}
async function loadTrack(){
stop();
const from=document.getElementById('dateFrom').value;
const to=document.getElementById('dateTo').value;
const params=new URLSearchParams({date_from:from,date_to:to});
const response=await fetch('/fleet_rutas/repeticion/'+routeId+'/datos?'+params.toString());
const data=await response.json();
if(!response.ok){document.getElementById('status').textContent=data.message||'No se pudo cargar';return}
track=data.track||[];
if(referenceLine){map.removeLayer(referenceLine)}
if(data.reference&&data.reference.length){referenceLine=L.polyline(data.reference,{color:'#2563eb',weight:7,opacity:.35}).addTo(map)}
track.forEach(p=>{});
if(marker){map.removeLayer(marker);marker=null}
played.setLatLngs([]);
index=0;
document.getElementById('progress').max=Math.max(track.length-1,0);
document.getElementById('progress').value=0;
if(!track.length){document.getElementById('status').textContent='Sin posiciones GPS en el intervalo seleccionado';return}
data.stops.forEach((stopItem,idx)=>{
const icon=L.divIcon({className:'',html:'<div style="width:22px;height:22px;background:#fff;border:2px solid #2563eb;text-align:center;line-height:18px;font-weight:bold">'+(stopItem.seq||idx+1)+'</div>',iconSize:[22,22],iconAnchor:[11,11]});
L.marker(stopItem.point,{icon}).bindPopup(escapeHtml(stopItem.name)).addTo(map)
});
showPosition(0,true);
const all=[...data.reference,...track.map(p=>[p.lat,p.lng])];
if(all.length){map.fitBounds(L.latLngBounds(all).pad(.12))}
}
function stop(){if(timer){clearInterval(timer);timer=null}document.getElementById('play').textContent='Iniciar';document.getElementById('play').classList.add('primary')}
function showPosition(i,fit=false){
if(!track.length)return;
index=Math.max(0,Math.min(i,track.length-1));
const p=track[index];
const icon=L.divIcon({className:'',html:'<div style="width:24px;height:24px;border:3px solid #fff;border-radius:50%;background:#1e7a4c;box-shadow:0 2px 8px #333"></div>',iconSize:[24,24],iconAnchor:[12,12]});
if(!marker){marker=L.marker([p.lat,p.lng],{icon}).addTo(map)}else{marker.setLatLng([p.lat,p.lng]).setIcon(icon)}
played.setLatLngs(track.slice(0,index+1).map(x=>[x.lat,x.lng]));
document.getElementById('progress').value=index;
document.getElementById('status').textContent=(p.timestamp||'')+' UTC · '+(Number(p.speed)||0).toFixed(1)+' km/h'+(p.deviation?' · Desvío':'');
if(fit)map.setView([p.lat,p.lng],16);
}
document.getElementById('show').onclick=loadTrack;
document.getElementById('progress').oninput=e=>showPosition(Number(e.target.value));
document.getElementById('speed').onchange=e=>{speed=Number(e.target.value)};
document.getElementById('play').onclick=()=>{
if(!track.length)return;
if(timer){stop();return}
document.getElementById('play').textContent='Pausar';
document.getElementById('play').classList.remove('primary');
if(index>=track.length-1)index=0;
timer=setInterval(()=>{showPosition(index+1);if(index>=track.length-1)stop()},1000/speed);
};
loadTrack();
</script>
</body>
</html>'''
        html = (html.replace('__START__', escape(start_value))
                    .replace('__END__', escape(end_value))
                    .replace('__RECORRIDO_ID__', str(recorrido_id)))
        return Response(html, content_type='text/html; charset=utf-8',
                        headers={'Cache-Control': 'no-store'})

    @http.route('/fleet_rutas/mapa/<int:recorrido_id>', auth='user', type='http')
    def mapa(self, recorrido_id, **kwargs):
        self._require_admin()
        rec = request.env['fleet.recorrido'].browse(recorrido_id).exists()
        if not rec:
            return request.not_found()
        rec.check_access_rights('read')
        rec.check_access_rule('read')
        rec.vehicle_id.check_access_rule('read')
        points = rec.posicion_ids.sorted('timestamp')
        data = {
            'reference': [list(p) for p in rec.ruta_id.puntos_referencia()],
            'track': [[p.latitud, p.longitud] for p in points],
            'stops': [{'point': [p.latitud, p.longitud], 'name': p.name, 'seq': p.secuencia} for p in rec.paradas_del_recorrido()],
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
