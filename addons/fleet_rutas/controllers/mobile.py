"""Authenticated PWA. Portal clients receive explicit DTOs, never raw ORM data."""
import importlib.util
import json
from pathlib import Path

from odoo import http, fields
from odoo.http import request, Response
from odoo.addons.web.controllers.home import Home
from werkzeug.exceptions import Forbidden, BadRequest

from ..models.fleet_mobile import valid_push_endpoint

STATIC = Path(__file__).resolve().parents[1] / 'static' / 'mobile'


def mobile_user():
    user = request.env.user
    if (not user.has_group('fleet_rutas.group_mobile_user') or
            user.has_group('base.group_user')):
        raise Forbidden('Esta aplicación es exclusiva para usuarios de Flota.')
    return user


def private_response(body, content_type='application/json; charset=utf-8'):
    return Response(body, headers={'Content-Type': content_type,
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY', 'Vary': 'Cookie'})


def json_response(data):
    return private_response(json.dumps(data, ensure_ascii=False))


def route_domain(user):
    return [('mobile_user_ids', 'in', [user.id])]


class FleetHome(Home):
    def _login_redirect(self, uid, redirect=None):
        user = request.env['res.users'].sudo().browse(uid)
        if user.has_group('fleet_rutas.group_mobile_user'):
            return '/flota/app'
        if user.has_group('fleet_rutas.group_fleet_admin'):
            return '/web'
        return super()._login_redirect(uid, redirect=redirect)

    @http.route()
    def web_client(self, s_action=None, **kw):
        if request.session.uid:
            user = request.env['res.users'].sudo().browse(request.session.uid)
            if user.has_group('fleet_rutas.group_mobile_user'):
                return request.redirect('/flota/app', 303)
            if not user.has_group('fleet_rutas.group_fleet_admin'):
                raise Forbidden('El panel web está reservado al administrador de Flota.')
        return super().web_client(s_action=s_action, **kw)

    @http.route()
    def index(self, **kw):
        if request.db and request.session.uid:
            user = request.env['res.users'].sudo().browse(request.session.uid)
            if user.has_group('fleet_rutas.group_mobile_user'):
                return request.redirect('/flota/app')
        return super().index(**kw)


class FleetMobile(http.Controller):
    @http.route('/flota/app', auth='user', type='http', methods=['GET'])
    def app(self, **kw):
        user = mobile_user()
        # A token is generated per session; no authenticated document is cached by the SW.
        body = (STATIC / 'index.html').read_text(encoding='utf-8')
        body = body.replace('__CSRF__', request.csrf_token())
        return private_response(body, 'text/html; charset=utf-8')

    @http.route('/flota/manifest.webmanifest', auth='public', type='http', methods=['GET'])
    def manifest(self, **kw):
        return private_response((STATIC / 'manifest.webmanifest').read_text(encoding='utf-8'),
                                'application/manifest+json')

    @http.route('/flota/sw.js', auth='public', type='http', methods=['GET'])
    def worker(self, **kw):
        response = private_response((STATIC / 'sw.js').read_text(encoding='utf-8'),
                                    'application/javascript')
        response.headers['Service-Worker-Allowed'] = '/flota/'
        return response

    @http.route('/flota/api/state', auth='user', type='http', methods=['GET'])
    def state(self, **kw):
        user = mobile_user()
        routes = request.env['fleet.ruta'].sudo().search(route_domain(user), order='name')
        route_ids = routes.ids
        trips = request.env['fleet.recorrido'].sudo().search([
            ('ruta_id', 'in', route_ids), ('estado', '=', 'en_curso')], order='fecha_inicio desc', limit=100)
        now = fields.Datetime.now()
        vehicles = []
        for trip in trips:
            pos = request.env['fleet.posicion.gps'].sudo().search([
                ('recorrido_id', '=', trip.id)], order='timestamp desc, id desc', limit=1)
            vehicles.append({'id': trip.id, 'route_id': trip.ruta_id.id,
                'name': trip.vehicle_id.license_plate or 'Vehículo',
                'position': {'lat': pos.latitud, 'lng': pos.longitud,
                    'speed': pos.velocidad_kmh, 'at': pos.timestamp.isoformat() + 'Z',
                    'stale': (now - pos.timestamp).total_seconds() > 120} if pos else None})
        incidents = request.env['fleet.incidencia'].sudo().search([
            ('ruta_id', 'in', route_ids), ('resuelta', '=', False),
            ('validacion', '!=', 'falso')], order='id desc', limit=100)
        params = request.env['ir.config_parameter'].sudo()
        subject = params.get_param('fleet_rutas.vapid_subject', '')
        push_ready = bool(importlib.util.find_spec('pywebpush') and
                          params.get_param('fleet_rutas.vapid_private') and subject.startswith('mailto:'))
        return json_response({'user': user.name, 'user_id': user.id,
            'server_time': now.isoformat() + 'Z', 'poll_seconds': 5,
            'push_key': params.get_param('fleet_rutas.vapid_public') if push_ready else None,
            'routes': [{'id': r.id, 'name': r.name, 'origin': r.origen, 'destination': r.destino,
                'status': r.estado, 'duration': r.duracion_estimada_min,
                'stops': [{'name': p.name, 'lat': p.latitud, 'lng': p.longitud,
                    'time': p.hora_prevista_str} for p in r.parada_ids.sorted('secuencia')]}
                for r in routes], 'vehicles': vehicles,
            'incidents': [{'id': i.id, 'route_id': i.ruta_id.id, 'route': i.ruta_id.name,
                'type': dict(i._fields['tipo'].selection).get(i.tipo, i.tipo),
                'severity': i.severidad, 'at': i.timestamp.isoformat() + 'Z'} for i in incidents]})

    @http.route('/flota/api/history', auth='user', type='http', methods=['GET'])
    def history(self, **kw):
        user = mobile_user()
        routes = request.env['fleet.ruta'].sudo().search(route_domain(user))
        try:
            offset = max(0, min(int(kw.get('offset', 0)), 100000))
        except (ValueError, TypeError):
            raise BadRequest('Página inválida')
        trips = request.env['fleet.recorrido'].sudo().search([
            ('ruta_id', 'in', routes.ids)], order='fecha_inicio desc, id desc', limit=21, offset=offset)
        return json_response({'more': len(trips) > 20, 'items': [{
            'id': t.id, 'route_id': t.ruta_id.id, 'route': t.ruta_id.name,
            'vehicle': t.vehicle_id.license_plate or 'Vehículo', 'status': t.estado,
            'date': t.fecha_inicio.isoformat() + 'Z', 'distance': t.distancia_real_km,
            'incidents': t.total_incidencias} for t in trips[:20]]})

    @http.route('/flota/api/history/<int:trip_id>', auth='user', type='http', methods=['GET'])
    def track(self, trip_id, **kw):
        user = mobile_user()
        routes = request.env['fleet.ruta'].sudo().search(route_domain(user))
        trip = request.env['fleet.recorrido'].sudo().search([
            ('id', '=', trip_id), ('ruta_id', 'in', routes.ids)], limit=1)
        if not trip:
            return request.not_found()
        # SQL sampling bounds the response while retaining the first and last fix.
        request.env.cr.execute('''SELECT latitud, longitud, timestamp FROM (
            SELECT latitud, longitud, timestamp, id,
                row_number() OVER (ORDER BY timestamp, id) AS n,
                count(*) OVER () AS total FROM fleet_posicion_gps WHERE recorrido_id = %s
            ) p WHERE n = 1 OR n = total OR mod(n, greatest(1, ceil(total / 1500.0)::int)) = 0
            ORDER BY timestamp, id''', (trip.id,))
        return json_response({'route': trip.ruta_id.name, 'sampled': True,
            'points': [{'lat': lat, 'lng': lng, 'at': at.isoformat() + 'Z'}
                       for lat, lng, at in request.env.cr.fetchall()]})

    @http.route('/flota/api/push', auth='user', type='http', methods=['POST'])
    def push(self, subscription=None, remove=None, **kw):
        user = mobile_user()
        try:
            data = json.loads(subscription or '')
            endpoint = data['endpoint']
            keys = data['keys']
            if (not valid_push_endpoint(endpoint) or len(endpoint) > 2048 or
                not isinstance(keys, dict) or
                not all(isinstance(keys.get(k), str) and 8 <= len(keys[k]) <= 256 for k in ('auth', 'p256dh'))):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise BadRequest('Suscripción inválida')
        Push = request.env['fleet.mobile.push'].sudo().with_context(active_test=False)
        existing = Push.search([('endpoint', '=', endpoint)], limit=1)
        if remove:
            if existing and existing.user_id.id == user.id:
                existing.unlink()
            return json_response({'ok': True})
        values = {'user_id': user.id, 'endpoint': endpoint,
                  'subscription': json.dumps({'endpoint': endpoint, 'keys': keys}), 'active': True}
        if existing:
            if existing.user_id.id != user.id:
                # Remove queued data from a previous account on a shared device.
                existing.unlink()
                Push.create(values)
            else:
                existing.write(values)
        else:
            if Push.search_count([('user_id', '=', user.id)]) >= 10:
                raise BadRequest('Máximo de diez dispositivos por usuario.')
            Push.create(values)
        return json_response({'ok': True})
