# -*- coding: utf-8 -*-
"""
Modelo fleet.incidencia — Registro de incidencias detectadas durante un recorrido.
Las incidencias pueden ser generadas automáticamente por los algoritmos de detección
o registradas manualmente por el operador.
"""
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

TIPO_INCIDENCIA = [
    ('incompleto', 'Recorrido Incompleto'),
    ('retraso', 'Retraso de Horario'),
    ('parada_omitida', 'Parada Omitida'),
    ('desviacion', 'Desviación de Ruta'),
    ('senal_perdida', 'Pérdida de Señal GPS'),
    ('velocidad', 'Exceso de Velocidad'),
]

SEVERIDAD = [
    ('baja', 'Baja'),
    ('media', 'Media'),
    ('alta', 'Alta'),
    ('critica', 'Crítica'),
]


class FleetIncidencia(models.Model):
    _name = 'fleet.incidencia'
    _description = 'Incidencia de Recorrido'
    _order = 'timestamp desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Descripción Corta',
        compute='_compute_name',
        store=True,
    )
    recorrido_id = fields.Many2one(
        comodel_name='fleet.recorrido',
        string='Recorrido',
        required=True,
        ondelete='cascade',
        index=True,
    )
    tipo = fields.Selection(
        selection=TIPO_INCIDENCIA,
        string='Tipo de Incidencia',
        required=True,
        index=True,
    )
    severidad = fields.Selection(
        selection=SEVERIDAD,
        string='Severidad',
        default='media',
        required=True,
        index=True,
    )
    timestamp = fields.Datetime(
        string='Fecha/Hora',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    latitud = fields.Float(
        string='Latitud',
        digits=(10, 7),
    )
    longitud = fields.Float(
        string='Longitud',
        digits=(10, 7),
    )
    descripcion = fields.Text(
        string='Descripción',
    )
    valor_detectado = fields.Float(
        string='Valor Detectado',
    )
    valor_esperado = fields.Float(
        string='Valor Esperado',
    )
    unidad = fields.Char(
        string='Unidad de Medida',
    )
    resuelta = fields.Boolean(
        string='Resuelta',
        default=False,
        index=True,
    )
    notas_resolucion = fields.Text(
        string='Notas de Resolución',
    )
    validacion = fields.Selection([
        ('pendiente', 'Sin validar'), ('verdadero', 'Verdadero positivo'),
        ('falso', 'Falso positivo')], default='pendiente', string='Validación del evento')
    # Relacionados para filtros rápidos
    vehicle_id = fields.Many2one(
        comodel_name='fleet.vehicle',
        related='recorrido_id.vehicle_id',
        string='Vehículo',
        store=True,
        index=True,
    )
    ruta_id = fields.Many2one(
        comodel_name='fleet.ruta',
        related='recorrido_id.ruta_id',
        string='Ruta',
        store=True,
        index=True,
    )

    @api.depends('tipo', 'recorrido_id', 'timestamp')
    def _compute_name(self):
        tipo_dict = dict(TIPO_INCIDENCIA)
        for inc in self:
            tipo_label = tipo_dict.get(inc.tipo, inc.tipo or 'Sin tipo')
            recorrido_name = inc.recorrido_id.name if inc.recorrido_id else 'N/D'
            ts_str = ''
            if inc.timestamp:
                ts_str = fields.Datetime.context_timestamp(
                    inc, inc.timestamp
                ).strftime('%d/%m %H:%M')
            inc.name = f'{tipo_label} | {recorrido_name} | {ts_str}'

    def action_resolver(self):
        """Marca la incidencia como resuelta."""
        self.ensure_one()
        self.write({'resuelta': True})

    def action_reabrir(self):
        """Reabre una incidencia ya resuelta."""
        self.ensure_one()
        self.write({'resuelta': False, 'notas_resolucion': False})

    @api.model
    def crear_incidencia_velocidad(self, recorrido_id, velocidad_kmh, velocidad_limite_kmh,
                                   latitud=0.0, longitud=0.0, timestamp=None):
        """
        Crea una incidencia de exceso de velocidad.
        
        Args:
            recorrido_id: ID del recorrido activo
            velocidad_kmh: Velocidad detectada
            velocidad_limite_kmh: Velocidad límite configurada
            latitud, longitud: Coordenadas del evento
            timestamp: Momento del evento (usa now() si None)
        """
        exceso = velocidad_kmh - velocidad_limite_kmh
        if exceso <= 0:
            return self.browse()

        severidad = 'baja'
        if exceso > 30:
            severidad = 'critica'
        elif exceso > 20:
            severidad = 'alta'
        elif exceso > 10:
            severidad = 'media'

        return self.create({
            'recorrido_id': recorrido_id,
            'tipo': 'velocidad',
            'severidad': severidad,
            'timestamp': timestamp or fields.Datetime.now(),
            'latitud': latitud,
            'longitud': longitud,
            'descripcion': (
                f'Exceso de velocidad detectado: {velocidad_kmh:.1f} km/h '
                f'(límite: {velocidad_limite_kmh:.1f} km/h, exceso: {exceso:.1f} km/h)'
            ),
            'valor_detectado': velocidad_kmh,
            'valor_esperado': velocidad_limite_kmh,
            'unidad': 'km/h',
        })

    @api.model
    def crear_incidencia_perdida_senal(self, recorrido_id, duracion_seg,
                                       timestamp_inicio=None):
        """
        Crea una incidencia de pérdida de señal GPS.
        
        Args:
            recorrido_id: ID del recorrido activo
            duracion_seg: Duración del gap de señal en segundos
            timestamp_inicio: Momento de inicio de la pérdida de señal
        """
        severidad = 'baja'
        if duracion_seg > 600:
            severidad = 'critica'
        elif duracion_seg > 300:
            severidad = 'alta'
        elif duracion_seg > 120:
            severidad = 'media'

        return self.create({
            'recorrido_id': recorrido_id,
            'tipo': 'senal_perdida',
            'severidad': severidad,
            'timestamp': timestamp_inicio or fields.Datetime.now(),
            'descripcion': (
                f'Pérdida de señal GPS durante {duracion_seg:.0f} segundos '
                f'({duracion_seg / 60:.1f} minutos).'
            ),
            'valor_detectado': duracion_seg,
            'valor_esperado': 120.0,
            'unidad': 'seg',
        })
