"""Vista previa y guardado del trazado vial. Todas las escrituras exigen token CSRF."""
import json
from pathlib import Path

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import UserError
from odoo.http import Response, request

PAGINA = Path(__file__).resolve().parents[1] / 'static' / 'trazado' / 'index.html'


class FleetTrazado(http.Controller):

    def _ruta(self, route_id):
        if not request.env.user.has_group('fleet_rutas.group_fleet_admin'):
            raise Forbidden('Solo el administrador de Flota puede editar trazados.')
        return request.env['fleet.ruta'].browse(route_id).exists()

    @staticmethod
    def _json(data, status=200):
        return Response(json.dumps(data), status=status, content_type='application/json',
                        headers={'Cache-Control': 'no-store'})

    @http.route('/fleet_rutas/trazado/<int:route_id>', auth='user', type='http', methods=['GET'])
    def pagina(self, route_id, **kwargs):
        ruta = self._ruta(route_id)
        if not ruta:
            return request.not_found()
        recorridos = request.env['fleet.recorrido'].search(
            [('ruta_id', '=', ruta.id), ('posicion_ids', '!=', False)],
            order='fecha_inicio desc', limit=50)
        datos = {
            'id': ruta.id,
            'nombre': ruta.name,
            'csrf': request.csrf_token(),
            'paradas': [{'nombre': p.name, 'punto': [p.latitud, p.longitud]}
                        for p in ruta.parada_ids.sorted('secuencia')],
            'trazado': json.loads(ruta.trazado) if ruta.trazado else None,
            'origen': dict(ruta._fields['trazado_origen'].selection).get(ruta.trazado_origen),
            'vigente': ruta.trazado_vigente,
            'distancia_km': ruta.distancia_estimada_km,
            'referencia': ruta.trazado_recorrido_id.display_name or None,
            'recorridos': [{'id': r.id, 'nombre': r.name + (' (simulado)' if r.simulado else '')}
                           for r in recorridos],
        }
        cuerpo = PAGINA.read_text(encoding='utf-8').replace(
            '__DATOS__', json.dumps(datos).replace('<', '\\u003c'))
        return Response(cuerpo, content_type='text/html; charset=utf-8',
                        headers={'Cache-Control': 'no-store', 'X-Frame-Options': 'SAMEORIGIN'})

    @http.route('/fleet_rutas/trazado/<int:route_id>/<string:accion>', auth='user',
                type='http', methods=['POST'])
    def accion(self, route_id, accion, **kwargs):
        ruta = self._ruta(route_id)
        if not ruta or accion not in ('propuesta', 'guardar', 'quitar'):
            return request.not_found()
        try:
            if accion == 'quitar':
                ruta.quitar_trazado()
                return self._json({'status': 'ok'})
            if accion == 'guardar':
                ruta.guardar_trazado(json.loads(kwargs.get('puntos') or '[]'),
                                     kwargs.get('origen'), kwargs.get('recorrido_id'))
                return self._json({'status': 'ok'})
            if kwargs.get('origen') == 'osrm':
                return self._json(ruta.generar_trazado_osrm())
            return self._json(ruta.trazado_desde_recorrido(kwargs.get('recorrido_id') or 0))
        except UserError as exc:
            return self._json({'status': 'error', 'message': exc.args[0]}, 400)
        except (ValueError, TypeError):
            return self._json({'status': 'error', 'message': 'Datos inválidos.'}, 400)
