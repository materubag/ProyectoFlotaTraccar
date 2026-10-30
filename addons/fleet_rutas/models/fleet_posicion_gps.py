# -*- coding: utf-8 -*-
"""
Modelo fleet.posicion.gps — Registro histórico de posiciones GPS de los vehículos
durante un recorrido, sincronizadas desde Traccar.
"""
import json
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class FleetPosicionGps(models.Model):
    _name = 'fleet.posicion.gps'
    _description = 'Posición GPS Registrada'
    _order = 'timestamp desc'
    _rec_name = 'timestamp'

    recorrido_id = fields.Many2one(
        comodel_name='fleet.recorrido',
        string='Recorrido',
        required=False,
        ondelete='cascade',
        index=True,
    )
    vehicle_id = fields.Many2one(
        comodel_name='fleet.vehicle',
        string='Vehículo',
        required=True,
        index=True,
    )
    timestamp = fields.Datetime(
        string='Timestamp GPS',
        required=True,
        index=True,
    )
    latitud = fields.Float(
        string='Latitud',
        required=True,
        digits=(10, 7),
    )
    longitud = fields.Float(
        string='Longitud',
        required=True,
        digits=(10, 7),
    )
    velocidad_kmh = fields.Float(
        string='Velocidad (km/h)',
        digits=(10, 2),
        default=0.0,
    )
    velocidad = fields.Float(
        string='Velocidad Alias',
        digits=(10, 2),
        related='velocidad_kmh',
        readonly=False,
        store=True,
    )
    altitud_m = fields.Float(
        string='Altitud (m)',
        digits=(10, 2),
        default=0.0,
    )
    altitud = fields.Float(
        string='Altitud Alias',
        digits=(10, 2),
        related='altitud_m',
        readonly=False,
        store=True,
    )
    precision_m = fields.Float(
        string='Precisión GPS (m)',
        digits=(10, 2),
        default=0.0,
    )
    precision = fields.Float(
        string='Precisión Alias',
        digits=(10, 2),
        related='precision_m',
        readonly=False,
        store=True,
    )
    rumbo = fields.Float(
        string='Rumbo / Curso',
        digits=(10, 2),
        default=0.0,
    )
    atributos_raw = fields.Text(
        string='Atributos Raw (JSON)',
        default='{}',
    )
    traccar_position_id = fields.Integer(
        string='ID Posición Traccar',
        index=True,
        help='ID de posición en Traccar para evitar duplicados',
    )
    es_desviacion = fields.Boolean(
        string='¿Es Desviación de Ruta?',
        default=False,
        index=True,
    )
    distancia_ruta_m = fields.Float(
        string='Distancia a Ruta Base (m)',
        digits=(10, 2),
        default=0.0,
        help='Distancia mínima en metros al corredor geográfico de la ruta.',
    )
    fuente = fields.Selection(
        selection=[
            ('traccar', 'Traccar API'),
            ('manual', 'Manual'),
            ('simulado', 'Simulado'),
        ],
        string='Fuente',
        default='traccar',
        required=True,
    )

    _sql_constraints = [
        (
            'posicion_traccar_unique',
            'UNIQUE(traccar_position_id)',
            'Ya existe una posición registrada con este ID de Traccar.',
        ),
    ]

    def detectar_desviacion(self):
        """
        Evalúa si la posición actual se aparta del corredor geográfico de la ruta
        asociada al recorrido activo, y verifica el paso por paradas.
        """
        for pos in self:
            if not pos.recorrido_id:
                continue
            recorrido = pos.recorrido_id
            paradas = recorrido.ruta_id.parada_ids.sorted('secuencia')
            if len(paradas) >= 2:
                from .fleet_algoritmos import detectar_desviacion
                polyline = [(p.latitud, p.longitud) for p in paradas]
                resultado = detectar_desviacion(pos.latitud, pos.longitud, polyline, umbral_m=100.0)
                pos.write({
                    'es_desviacion': resultado['es_desviacion'],
                    'distancia_ruta_m': resultado['distancia_m'],
                })
                if resultado['es_desviacion'] and resultado['distancia_m'] > 100.0:
                    pos._crear_incidencia_desviacion(recorrido, pos, resultado['distancia_m'])
            pos._verificar_paradas(recorrido, pos)

    @api.model
    def registrar_posicion(self, recorrido_id, vehicle_id, timestamp, latitud, longitud,
                           velocidad_kmh=0.0, altitud_m=0.0, precision_m=0.0,
                           traccar_position_id=None, fuente='traccar'):
        """
        Método de conveniencia para registrar una posición GPS evitando duplicados.
        Retorna el registro creado o el existente si ya estaba registrado.
        """
        if traccar_position_id:
            existente = self.search([
                ('traccar_position_id', '=', traccar_position_id)
            ], limit=1)
            if existente:
                return existente

        recorrido = self.env['fleet.recorrido'].browse(recorrido_id)
        if recorrido_id and not recorrido.exists():
            _logger.warning('Intento de registrar posición para recorrido inexistente ID=%s', recorrido_id)
            return self.browse()

        vals = {
            'recorrido_id': recorrido_id,
            'vehicle_id': vehicle_id,
            'timestamp': timestamp,
            'latitud': latitud,
            'longitud': longitud,
            'velocidad_kmh': velocidad_kmh,
            'altitud_m': altitud_m,
            'precision_m': precision_m,
            'fuente': fuente,
        }
        if traccar_position_id:
            vals['traccar_position_id'] = traccar_position_id

        posicion = self.create(vals)
        if recorrido_id:
            posicion.detectar_desviacion()

        return posicion

    def _crear_incidencia_desviacion(self, recorrido, posicion, distancia_m):
        """Crea una incidencia de desviación si no existe una reciente."""
        ultima_incidencia = self.env['fleet.incidencia'].search([
            ('recorrido_id', '=', recorrido.id),
            ('tipo', '=', 'desviacion'),
            ('resuelta', '=', False),
        ], limit=1, order='timestamp desc')

        if not ultima_incidencia:
            severidad = 'baja'
            if distancia_m > 400:
                severidad = 'alta'
            elif distancia_m > 200:
                severidad = 'media'

            self.env['fleet.incidencia'].create({
                'recorrido_id': recorrido.id,
                'tipo': 'desviacion',
                'severidad': severidad,
                'timestamp': posicion.timestamp,
                'latitud': posicion.latitud,
                'longitud': posicion.longitud,
                'descripcion': f'Vehículo a {distancia_m:.0f}m del corredor de ruta base.',
                'valor_detectado': distancia_m,
                'valor_esperado': 100.0,
                'unidad': 'm',
            })

    def _verificar_paradas(self, recorrido, posicion):
        """Verifica si la posición actual completa alguna parada pendiente."""
        for cumplimiento in recorrido.cumplimiento_parada_ids.filtered(lambda c: not c.cumplida):
            parada = cumplimiento.parada_id
            from .fleet_algoritmos import haversine_distance_m
            dist = haversine_distance_m(
                posicion.latitud, posicion.longitud,
                parada.latitud, parada.longitud,
            )
            if dist <= parada.radio_proximidad_m:
                retraso_min = 0
                if parada.hora_prevista and recorrido.fecha_inicio:
                    h = int(parada.hora_prevista)
                    m = int(round((parada.hora_prevista - h) * 60))
                    fecha_ref = recorrido.fecha_inicio.date()
                    programado = fields.Datetime.from_string(
                        f'{fecha_ref} {h:02d}:{m:02d}:00'
                    )
                    diff_seg = (posicion.timestamp - programado).total_seconds()
                    retraso_min = int(diff_seg / 60)

                cumplimiento.write({
                    'cumplida': True,
                    'timestamp_llegada': posicion.timestamp,
                    'distancia_minima_m': round(dist, 2),
                    'posicion_id': posicion.id,
                    'retraso_min': retraso_min,
                })
                _logger.info(
                    'Parada "%s" cumplida para recorrido %s (distancia: %.1f m, retraso: %d min)',
                    parada.name, recorrido.name, dist, retraso_min,
                )
