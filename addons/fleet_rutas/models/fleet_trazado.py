"""Trazado vial de referencia de una ruta: generado con OSRM o desde un recorrido GPS."""
import json
import logging
import math

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from .fleet_algoritmos import (elegir_secuencia_minima, limpiar_posiciones_gps,
                               longitud_polilinea_m, min_distance_to_polyline_m,
                               simplificar_polilinea)

_logger = logging.getLogger(__name__)

OSRM_URL = 'https://router.project-osrm.org'
MARGEN_PARADA_M = 150.0
TOLERANCIA_SIMPLIFICACION_M = 5.0
MAX_PUNTOS = 5000
MARGEN_CALZADA_M = 40.0   # distancia máxima para considerar otra calzada de la misma parada
MAX_TABLA_OSRM = 100      # límite de coordenadas del servicio público


def _consultar_osrm(url, parametros):
    respuesta = requests.get(url, params=parametros, headers={'User-Agent': 'fleet-rutas'}, timeout=15)
    respuesta.raise_for_status()
    datos = respuesta.json()
    if datos.get('code') != 'Ok':
        raise ValueError(datos.get('code'))
    return datos


def ajustar_paradas_a_calzada(base, puntos):
    """
    En vías de doble calzada, la calle más cercana a una parada puede ir en sentido
    contrario y OSRM da un rodeo para volver. Se buscan las calzadas próximas a cada
    parada y se elige la combinación con el recorrido total más corto.

    ``puntos`` es una lista de (lon, lat). Ante cualquier fallo se devuelven sin cambios.
    """
    por_parada = min(6, MAX_TABLA_OSRM // max(len(puntos), 1))
    if por_parada < 2:
        return puntos
    try:
        candidatos = []
        for lon, lat in puntos:
            datos = _consultar_osrm('%s/nearest/v1/driving/%.6f,%.6f' % (base, lon, lat),
                                    {'number': por_parada})
            cercanos = []
            for punto in datos['waypoints']:
                ubicacion = tuple(punto['location'])
                if punto['distance'] <= MARGEN_CALZADA_M and ubicacion not in cercanos:
                    cercanos.append(ubicacion)
            candidatos.append(cercanos or [(lon, lat)])
        if all(len(c) == 1 for c in candidatos):
            return puntos
        planos = [p for grupo in candidatos for p in grupo]
        tabla = _consultar_osrm(
            '%s/table/v1/driving/%s' % (base, ';'.join('%.6f,%.6f' % p for p in planos)),
            {'annotations': 'distance'})
        elegidos = elegir_secuencia_minima([len(c) for c in candidatos], tabla['distances'])
        return [planos[i] for i in elegidos] if elegidos else puntos
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        _logger.warning('No se pudo ajustar las paradas a la calzada: %s', type(exc).__name__)
        return puntos


class FleetRutaTrazado(models.Model):
    _inherit = 'fleet.ruta'

    trazado = fields.Text(string='Trazado (JSON)', readonly=True, copy=False)
    trazado_origen = fields.Selection(
        [('osrm', 'Automático (OSRM)'), ('gps', 'Recorrido GPS')],
        string='Origen del trazado', readonly=True, copy=False)
    trazado_recorrido_id = fields.Many2one(
        'fleet.recorrido', string='Recorrido usado como referencia', readonly=True,
        copy=False, ondelete='set null')
    trazado_fecha = fields.Datetime(string='Fecha del trazado', readonly=True, copy=False)
    trazado_firma = fields.Char(readonly=True, copy=False)
    trazado_vigente = fields.Boolean(string='Trazado vigente', compute='_compute_trazado_vigente')

    def _paradas_ordenadas(self):
        self.ensure_one()
        return self.parada_ids.sorted('secuencia')

    def _firma_paradas(self):
        return json.dumps([[round(p.latitud, 6), round(p.longitud, 6)]
                           for p in self._paradas_ordenadas()])

    @api.depends('trazado', 'trazado_firma', 'parada_ids.latitud', 'parada_ids.longitud',
                 'parada_ids.secuencia', 'parada_ids.active')
    def _compute_trazado_vigente(self):
        for ruta in self:
            ruta.trazado_vigente = bool(ruta.trazado) and ruta.trazado_firma == ruta._firma_paradas()

    def puntos_referencia(self):
        """
        Línea contra la que se evalúa la ruta. Sin un trazado vigente se usan las
        rectas entre paradas, que son solo una aproximación.
        """
        self.ensure_one()
        if self.trazado_vigente:
            return [tuple(p) for p in json.loads(self.trazado)]
        return [(p.latitud, p.longitud) for p in self._paradas_ordenadas()]

    def _propuesta(self, origen, puntos, recorrido=None):
        puntos = simplificar_polilinea(puntos, TOLERANCIA_SIMPLIFICACION_M)
        paradas = self._paradas_ordenadas()
        lejanas = []
        for parada in paradas:
            distancia = min_distance_to_polyline_m(parada.latitud, parada.longitud, puntos)
            if distancia > MARGEN_PARADA_M:
                lejanas.append({'nombre': parada.name, 'distancia_m': round(distancia)})
        return {
            'origen': origen,
            'recorrido_id': recorrido.id if recorrido else False,
            'puntos': [[round(a, 7), round(b, 7)] for a, b in puntos],
            'distancia_km': round(longitud_polilinea_m(puntos) / 1000, 3),
            'distancia_recta_km': round(longitud_polilinea_m(
                [(p.latitud, p.longitud) for p in paradas]) / 1000, 3),
            'paradas_lejanas': lejanas,
            'simulado': bool(recorrido and recorrido.simulado),
        }

    def generar_trazado_osrm(self):
        """Pide el camino por calles entre las paradas. Envía sus coordenadas al servidor OSRM."""
        self.ensure_one()
        self.check_access_rights('write')
        paradas = self._paradas_ordenadas()
        if len(paradas) < 2:
            raise UserError('La ruta necesita al menos dos paradas.')
        base = (self.env['ir.config_parameter'].sudo().get_param('fleet_rutas.osrm_url')
                or OSRM_URL).rstrip('/')
        ajustados = ajustar_paradas_a_calzada(base, [(p.longitud, p.latitud) for p in paradas])
        coordenadas = ';'.join('%.6f,%.6f' % p for p in ajustados)
        try:
            datos = _consultar_osrm('%s/route/v1/driving/%s' % (base, coordenadas),
                                    {'overview': 'full', 'geometries': 'geojson'})
            puntos = [(float(lat), float(lon))
                      for lon, lat in datos['routes'][0]['geometry']['coordinates']]
            if len(puntos) < 2:
                raise ValueError('geometría vacía')
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            _logger.warning('OSRM no devolvió un trazado: %s', type(exc).__name__)
            raise UserError('OSRM no devolvió un trazado. Intente más tarde o use un recorrido GPS.')
        return self._propuesta('osrm', puntos)

    def trazado_desde_recorrido(self, recorrido_id):
        """Construye el trazado con las posiciones de un recorrido de esta ruta."""
        self.ensure_one()
        self.check_access_rights('write')
        recorrido = self.env['fleet.recorrido'].browse(int(recorrido_id)).exists()
        if not recorrido or recorrido.ruta_id != self:
            raise UserError('El recorrido no pertenece a esta ruta.')
        puntos = limpiar_posiciones_gps([
            {'latitud': p.latitud, 'longitud': p.longitud, 'timestamp': p.timestamp,
             'precision_m': p.precision_m}
            for p in recorrido.posicion_ids.sorted('timestamp')])
        if len(puntos) < 2:
            raise UserError('El recorrido no tiene suficientes posiciones GPS válidas.')
        propuesta = self._propuesta('gps', puntos, recorrido)
        if propuesta['paradas_lejanas']:
            raise UserError('El recorrido no pasa cerca de: %s.' % ', '.join(
                p['nombre'] for p in propuesta['paradas_lejanas']))
        return propuesta

    def guardar_trazado(self, puntos, origen, recorrido_id=False):
        self.ensure_one()
        if origen not in ('osrm', 'gps'):
            raise UserError('Origen de trazado desconocido.')
        try:
            puntos = [(float(a), float(b)) for a, b in puntos]
        except (TypeError, ValueError):
            raise UserError('El trazado no es válido.')
        if not 2 <= len(puntos) <= MAX_PUNTOS or not all(
                math.isfinite(a) and math.isfinite(b) and -90 <= a <= 90 and -180 <= b <= 180
                for a, b in puntos):
            raise UserError('El trazado no es válido.')
        recorrido = self.env['fleet.recorrido'].browse(int(recorrido_id or 0)).exists()
        if recorrido and recorrido.ruta_id != self:
            raise UserError('El recorrido no pertenece a esta ruta.')
        self.write({
            'trazado': json.dumps(puntos),
            'trazado_origen': origen,
            'trazado_recorrido_id': recorrido.id if origen == 'gps' else False,
            'trazado_fecha': fields.Datetime.now(),
            'trazado_firma': self._firma_paradas(),
            'distancia_estimada_km': round(longitud_polilinea_m(puntos) / 1000, 3),
        })

    def quitar_trazado(self):
        self.ensure_one()
        self.write({'trazado': False, 'trazado_origen': False, 'trazado_recorrido_id': False,
                    'trazado_fecha': False, 'trazado_firma': False})

    def action_abrir_trazado(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': '/fleet_rutas/trazado/%d' % self.id,
                'target': 'self'}
