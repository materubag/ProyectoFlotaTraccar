# -*- coding: utf-8 -*-
"""
Modelo fleet.cumplimiento.parada — Registro del cumplimiento de cada parada
durante la ejecución de un recorrido.
"""
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class FleetCumplimientoParada(models.Model):
    _name = 'fleet.cumplimiento.parada'
    _description = 'Cumplimiento de Parada en Recorrido'
    _order = 'parada_id'
    _rec_name = 'display_name'

    recorrido_id = fields.Many2one(
        comodel_name='fleet.recorrido',
        string='Recorrido',
        required=True,
        ondelete='cascade',
        index=True,
    )
    parada_id = fields.Many2one(
        comodel_name='fleet.parada',
        string='Parada',
        required=True,
        ondelete='restrict',
        index=True,
    )
    cumplida = fields.Boolean(
        string='Cumplida',
        default=False,
        index=True,
    )
    timestamp_llegada = fields.Datetime(
        string='Hora Real de Llegada',
    )
    retraso_min = fields.Float(
        string='Retraso (min)',
        readonly=True,
        help='Positivo = tarde, negativo = adelantado respecto a hora programada.',
        default=0,
    )
    distancia_minima_m = fields.Float(
        string='Distancia Mínima Alcanzada (m)',
        digits=(10, 2),
        default=0.0,
    )
    posicion_id = fields.Many2one(
        comodel_name='fleet.posicion.gps',
        string='Posición GPS de Llegada',
        ondelete='set null',
    )
    # Campos relacionados para acceso rápido en vistas
    secuencia_parada = fields.Integer(
        related='parada_id.secuencia',
        string='Secuencia',
        store=True,
    )
    tipo_parada = fields.Selection(
        related='parada_id.tipo',
        string='Tipo de Parada',
        store=True,
    )
    hora_prevista_str = fields.Char(
        related='parada_id.hora_prevista_str',
        string='Hora Programada',
    )
    radio_proximidad_m = fields.Float(
        related='parada_id.radio_proximidad_m',
        string='Radio (m)',
    )

    @api.depends('recorrido_id', 'parada_id')
    def _compute_display_name(self):
        for rec in self:
            parada_name = rec.parada_id.name if rec.parada_id else '?'
            recorrido_name = rec.recorrido_id.name if rec.recorrido_id else '?'
            rec.display_name = f'{parada_name} ({recorrido_name})'

    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
    )

    def estado_cumplimiento(self):
        """Devuelve una cadena descriptiva del estado de cumplimiento."""
        self.ensure_one()
        if not self.cumplida:
            return 'omitida'
        if self.retraso_min > self.parada_id.tolerancia_min:
            return 'tardía'
        if self.retraso_min < -self.parada_id.tolerancia_min:
            return 'adelantada'
        return 'puntual'
