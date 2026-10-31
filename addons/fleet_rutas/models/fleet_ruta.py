# -*- coding: utf-8 -*-
"""
Modelos principales del Sistema de Monitoreo de Rutas Universitarias.
Incluye: fleet.ruta, fleet.parada, fleet.recorrido
"""
import logging
from datetime import datetime
from odoo import api, fields, models
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class FleetRuta(models.Model):
    _name = 'fleet.ruta'
    _description = 'Ruta de Transporte Universitario'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(
        string='Nombre de Ruta',
        required=True,
        index=True,
    )
    code = fields.Char(
        string='Código',
        copy=False,
        index=True,
    )
    estado = fields.Selection(
        selection=[
            ('activa', 'Activa'),
            ('suspendida', 'Suspendida'),
            ('mantenimiento', 'En Mantenimiento'),
        ],
        string='Estado',
        default='activa',
        required=True,
        index=True,
    )
    origen = fields.Char(
        string='Punto de Origen',
        required=True,
    )
    destino = fields.Char(
        string='Punto de Destino',
        required=True,
    )
    distancia_estimada_km = fields.Float(
        string='Distancia Estimada (km)',
        digits=(10, 3),
        default=0.0,
    )
    duracion_estimada_min = fields.Integer(
        string='Duración Estimada (min)',
        default=0,
    )
    parada_ids = fields.One2many(
        comodel_name='fleet.parada',
        inverse_name='ruta_id',
        string='Puntos de Control',
    )
    recorrido_ids = fields.One2many(
        comodel_name='fleet.recorrido',
        inverse_name='ruta_id',
        string='Recorridos',
    )
    total_paradas = fields.Integer(
        string='Total de Paradas',
        compute='_compute_total_paradas',
        store=True,
    )
    velocidad_promedio_kmh = fields.Float(
        string='Velocidad Promedio Estimada (km/h)',
        compute='_compute_velocidad_promedio',
        store=True,
        digits=(10, 2),
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )
    notas = fields.Text(
        string='Notas',
    )
    zona_horaria = fields.Char(string='Zona horaria de horarios', default='America/Guayaquil', required=True)

    _sql_constraints = [
        (
            'ruta_code_unique',
            'UNIQUE(code)',
            'El código de ruta debe ser único.',
        ),
    ]

    @api.constrains('zona_horaria', 'distancia_estimada_km', 'duracion_estimada_min')
    def _check_ruta(self):
        import pytz
        for ruta in self:
            if ruta.zona_horaria not in pytz.all_timezones_set:
                raise ValidationError('Zona horaria desconocida.')
            if ruta.distancia_estimada_km < 0 or ruta.duracion_estimada_min < 0:
                raise ValidationError('La distancia y la duración no pueden ser negativas.')

    @api.depends('parada_ids')
    def _compute_total_paradas(self):
        for ruta in self:
            ruta.total_paradas = len(ruta.parada_ids)

    @api.depends('distancia_estimada_km', 'duracion_estimada_min')
    def _compute_velocidad_promedio(self):
        for ruta in self:
            if ruta.duracion_estimada_min and ruta.duracion_estimada_min > 0:
                ruta.velocidad_promedio_kmh = (
                    ruta.distancia_estimada_km / (ruta.duracion_estimada_min / 60.0)
                )
            else:
                ruta.velocidad_promedio_kmh = 0.0

    def action_activar(self):
        """Activa la ruta."""
        self.ensure_one()
        self.estado = 'activa'

    def action_suspender(self):
        """Suspende la ruta."""
        self.ensure_one()
        self.estado = 'suspendida'

    def action_mantenimiento(self):
        """Pone la ruta en mantenimiento."""
        self.ensure_one()
        self.estado = 'mantenimiento'

    def name_get(self):
        result = []
        for ruta in self:
            if ruta.code:
                result.append((ruta.id, f'[{ruta.code}] {ruta.name}'))
            else:
                result.append((ruta.id, ruta.name))
        return result


class FleetParada(models.Model):
    _name = 'fleet.parada'
    _description = 'Punto de Control / Parada'
    _order = 'secuencia'
    _rec_name = 'name'

    name = fields.Char(
        string='Nombre de Parada',
        required=True,
    )
    ruta_id = fields.Many2one(
        comodel_name='fleet.ruta',
        string='Ruta',
        required=True,
        ondelete='cascade',
        index=True,
    )
    secuencia = fields.Integer(
        string='Secuencia',
        default=10,
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
    radio_proximidad_m = fields.Float(
        string='Radio de Proximidad (m)',
        default=50.0,
        digits=(10, 2),
    )
    hora_prevista = fields.Float(
        string='Hora Prevista (HH.MM)',
        help='Expresada como decimal, e.g. 8.5 = 08:30',
    )
    tolerancia_min = fields.Integer(
        string='Tolerancia (min)',
        default=5,
    )
    tipo = fields.Selection(
        selection=[
            ('origen', 'Origen'),
            ('intermedia', 'Intermedia'),
            ('destino', 'Destino'),
        ],
        string='Tipo',
        default='intermedia',
        required=True,
    )
    descripcion = fields.Text(
        string='Descripción',
    )
    hora_prevista_str = fields.Char(
        string='Hora Prevista',
        compute='_compute_hora_prevista_str',
        store=True,
    )

    @api.depends('hora_prevista')
    def _compute_hora_prevista_str(self):
        for parada in self:
            horas, minutos = divmod(round(parada.hora_prevista * 60) % 1440, 60)
            parada.hora_prevista_str = f'{horas:02d}:{minutos:02d}'

    @api.constrains('latitud', 'longitud')
    def _check_coordenadas(self):
        for parada in self:
            if not (-90.0 <= parada.latitud <= 90.0):
                raise ValidationError(
                    f'La latitud de la parada "{parada.name}" debe estar entre -90 y 90. '
                    f'Valor actual: {parada.latitud}'
                )
            if not (-180.0 <= parada.longitud <= 180.0):
                raise ValidationError(
                    f'La longitud de la parada "{parada.name}" debe estar entre -180 y 180. '
                    f'Valor actual: {parada.longitud}'
                )

    @api.constrains('hora_prevista', 'radio_proximidad_m', 'tolerancia_min')
    def _check_parametros(self):
        for parada in self:
            if not 0 <= parada.hora_prevista < 24 or parada.radio_proximidad_m <= 0 or parada.tolerancia_min < 0:
                raise ValidationError('La hora debe estar entre 0 y 24; el radio debe ser positivo y la tolerancia no negativa.')


class FleetRecorrido(models.Model):
    _name = 'fleet.recorrido'
    _description = 'Recorrido / Asignación de Ruta'
    _order = 'fecha_inicio desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Nombre de Recorrido',
        compute='_compute_name',
        store=True,
    )
    ruta_id = fields.Many2one(
        comodel_name='fleet.ruta',
        string='Ruta',
        required=True,
        ondelete='restrict',
        index=True,
    )
    vehicle_id = fields.Many2one(
        comodel_name='fleet.vehicle',
        string='Vehículo',
        required=True,
        domain=[('traccar_tracking_enabled', '=', True)],
        index=True,
    )
    conductor_id = fields.Many2one(
        comodel_name='res.users',
        string='Conductor',
    )
    estado = fields.Selection(
        selection=[
            ('programado', 'Programado'),
            ('en_curso', 'En Curso'),
            ('completado', 'Completado'),
            ('cancelado', 'Cancelado'),
            ('con_incidencias', 'Con Incidencias'),
        ],
        string='Estado',
        default='programado',
        required=True,
        index=True,
    )
    fecha_inicio = fields.Datetime(
        string='Fecha/Hora Inicio Programada',
        required=True,
    )
    fecha_fin_estimada = fields.Datetime(
        string='Fecha/Hora Fin Estimada',
    )
    fecha_inicio_real = fields.Datetime(
        string='Inicio Real',
        readonly=True,
    )
    fecha_fin_real = fields.Datetime(
        string='Fin Real',
        readonly=True,
    )
    distancia_real_km = fields.Float(
        string='Distancia Real (km)',
        digits=(10, 3),
        readonly=True,
    )
    velocidad_promedio_real = fields.Float(
        string='Velocidad Promedio Real (km/h)',
        digits=(10, 2),
        readonly=True,
    )
    posicion_ids = fields.One2many(
        comodel_name='fleet.posicion.gps',
        inverse_name='recorrido_id',
        string='Historial GPS',
    )
    incidencia_ids = fields.One2many(
        comodel_name='fleet.incidencia',
        inverse_name='recorrido_id',
        string='Incidencias',
    )
    cumplimiento_parada_ids = fields.One2many(
        comodel_name='fleet.cumplimiento.parada',
        inverse_name='recorrido_id',
        string='Cumplimiento de Paradas',
    )
    notas = fields.Text(
        string='Notas',
    )

    # ── Campos computados ──────────────────────────────────────────────────
    duracion_real_min = fields.Integer(
        string='Duración Real (min)',
        compute='_compute_duracion_real',
        store=True,
    )
    retraso_inicio_min = fields.Integer(
        string='Retraso en Inicio (min)',
        compute='_compute_retraso_inicio',
        store=True,
        help='Positivo = tarde, negativo = adelantado',
    )
    porcentaje_paradas_cumplidas = fields.Float(
        string='% Paradas Cumplidas',
        compute='_compute_porcentaje_paradas',
        store=True,
        digits=(5, 2),
    )
    tiene_desviacion = fields.Boolean(
        string='Tiene Desviación',
        compute='_compute_tiene_desviacion',
        store=True,
    )
    total_incidencias = fields.Integer(
        string='Total Incidencias',
        compute='_compute_total_incidencias',
        store=True,
    )

    # ── Compute methods ────────────────────────────────────────────────────

    simulado = fields.Boolean(string='Datos simulados', default=False)

    @api.constrains('fecha_inicio', 'fecha_fin_estimada', 'fecha_inicio_real', 'fecha_fin_real')
    def _check_fechas(self):
        for rec in self:
            if rec.fecha_fin_estimada and rec.fecha_fin_estimada <= rec.fecha_inicio:
                raise ValidationError('El fin estimado debe ser posterior al inicio programado.')
            if rec.fecha_fin_real and (not rec.fecha_inicio_real or rec.fecha_fin_real < rec.fecha_inicio_real):
                raise ValidationError('El fin real debe ser posterior al inicio real.')

    def action_ver_mapa(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': f'/fleet_rutas/mapa/{self.id}', 'target': 'new'}

    def action_sincronizar_historial(self):
        self.ensure_one()
        result = self.env['fleet.traccar.sync'].sincronizar_historial(self.id)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': 'Historial GPS', 'message': str(result), 'type': 'info', 'sticky': True}}

    @api.depends('ruta_id', 'vehicle_id', 'fecha_inicio')
    def _compute_name(self):
        for rec in self:
            parts = []
            if rec.ruta_id:
                parts.append(rec.ruta_id.name)
            if rec.vehicle_id:
                parts.append(rec.vehicle_id.name)
            if rec.fecha_inicio:
                parts.append(fields.Datetime.context_timestamp(
                    rec, rec.fecha_inicio
                ).strftime('%d/%m/%Y %H:%M'))
            rec.name = ' | '.join(parts) if parts else 'Nuevo Recorrido'

    @api.depends('fecha_inicio_real', 'fecha_fin_real')
    def _compute_duracion_real(self):
        for rec in self:
            if rec.fecha_inicio_real and rec.fecha_fin_real:
                diff = rec.fecha_fin_real - rec.fecha_inicio_real
                rec.duracion_real_min = int(diff.total_seconds() / 60)
            else:
                rec.duracion_real_min = 0

    @api.depends('fecha_inicio', 'fecha_inicio_real')
    def _compute_retraso_inicio(self):
        for rec in self:
            if rec.fecha_inicio and rec.fecha_inicio_real:
                diff = rec.fecha_inicio_real - rec.fecha_inicio
                rec.retraso_inicio_min = int(diff.total_seconds() / 60)
            else:
                rec.retraso_inicio_min = 0

    @api.depends('cumplimiento_parada_ids', 'cumplimiento_parada_ids.cumplida')
    def _compute_porcentaje_paradas(self):
        for rec in self:
            total = len(rec.cumplimiento_parada_ids)
            if total:
                cumplidas = len(rec.cumplimiento_parada_ids.filtered('cumplida'))
                rec.porcentaje_paradas_cumplidas = round(cumplidas / total * 100.0, 2)
            else:
                rec.porcentaje_paradas_cumplidas = 0.0

    @api.depends('posicion_ids', 'posicion_ids.es_desviacion')
    def _compute_tiene_desviacion(self):
        for rec in self:
            rec.tiene_desviacion = any(
                p.es_desviacion for p in rec.posicion_ids
            )

    @api.depends('incidencia_ids')
    def _compute_total_incidencias(self):
        for rec in self:
            rec.total_incidencias = len(rec.incidencia_ids)

    # ── Action methods ─────────────────────────────────────────────────────

    def action_iniciar(self):
        """Inicia el recorrido: cambia estado y registra hora de inicio real."""
        self.ensure_one()
        if self.estado not in ('programado',):
            raise UserError(
                f'No se puede iniciar un recorrido en estado "{dict(self._fields["estado"].selection).get(self.estado)}".'
            )
        # Serialize starts for the same vehicle, including concurrent requests.
        self.env.cr.execute('SELECT id FROM fleet_vehicle WHERE id = %s FOR UPDATE', [self.vehicle_id.id])
        if self.search_count([('vehicle_id', '=', self.vehicle_id.id), ('estado', '=', 'en_curso'), ('id', '!=', self.id)]):
            raise UserError('Este vehículo ya tiene un recorrido en curso.')
        if self.ruta_id.estado != 'activa' or not self.ruta_id.parada_ids:
            raise UserError('La ruta debe estar activa y tener paradas.')
        now = fields.Datetime.now()
        self.write({
            'estado': 'en_curso',
            'fecha_inicio_real': now,
        })
        # Inicializar registros de cumplimiento de paradas
        self._inicializar_cumplimiento_paradas()
        _logger.info(
            'Recorrido %s iniciado a las %s por usuario %s',
            self.name, now, self.env.user.name,
        )

    def action_completar(self):
        """Completa el recorrido: registra fin real y calcula métricas."""
        self.ensure_one()
        if self.estado != 'en_curso' or self.fecha_fin_real:
            raise UserError(
                f'Solo se puede completar un recorrido "En Curso" o "Con Incidencias".'
            )
        now = fields.Datetime.now()
        # Calcular distancia real y velocidad promedio desde historial GPS
        distancia_km = 0.0
        velocidad_prom = 0.0
        posiciones = self.posicion_ids.sorted('timestamp')
        if len(posiciones) >= 2:
            from .fleet_algoritmos import calcular_distancia_total_km
            historial = [
                {'latitud': p.latitud, 'longitud': p.longitud, 'timestamp': p.timestamp}
                for p in posiciones
            ]
            distancia_km = calcular_distancia_total_km(historial)
            if self.fecha_inicio_real:
                dur_h = (now - self.fecha_inicio_real).total_seconds() / 3600.0
                if dur_h > 0:
                    velocidad_prom = round(distancia_km / dur_h, 2)

        for pos in posiciones:
            pos.detectar_desviacion()
        self._registrar_incidencias_cierre(now)
        self.env['fleet.traccar.sync'].verificar_perdida_senal(self.id)
        # Determinar estado final
        estado_final = 'completado'
        if self.incidencia_ids:
            estado_final = 'con_incidencias'

        self.write({
            'estado': estado_final,
            'fecha_fin_real': now,
            'distancia_real_km': distancia_km,
            'velocidad_promedio_real': velocidad_prom,
        })

        # Calcular métricas completas
        self.env['fleet.metricas.recorrido'].sudo().calcular_para_recorrido(self.id)

        _logger.info('Recorrido %s completado. Distancia: %.3f km, Velocidad: %.2f km/h',
                     self.name, distancia_km, velocidad_prom)

    def action_cancelar(self):
        """Cancela el recorrido."""
        self.ensure_one()
        if self.estado in ('completado', 'cancelado') or self.fecha_fin_real:
            raise UserError(
                'No se puede cancelar un recorrido ya completado o cancelado.'
            )
        self.write({'estado': 'cancelado'})
        _logger.info('Recorrido %s cancelado por usuario %s', self.name, self.env.user.name)

    def _registrar_incidencias_cierre(self, now):
        self.ensure_one()
        incidence = self.env['fleet.incidencia']
        for cumplimiento in self.cumplimiento_parada_ids:
            if not cumplimiento.cumplida:
                incidence.create({'recorrido_id': self.id, 'tipo': 'parada_omitida', 'timestamp': now,
                                  'descripcion': f'Parada no visitada: {cumplimiento.parada_id.name}'})
        if not self.posicion_ids or self.cumplimiento_parada_ids.filtered(lambda c: not c.cumplida):
            incidence.create({'recorrido_id': self.id, 'tipo': 'incompleto', 'timestamp': now,
                              'descripcion': 'Recorrido sin GPS o con puntos de control pendientes.'})
        if self.retraso_inicio_min > 5:
            incidence.create({'recorrido_id': self.id, 'tipo': 'retraso', 'timestamp': self.fecha_inicio_real,
                              'descripcion': 'Inicio fuera de la tolerancia de 5 minutos.',
                              'valor_detectado': self.retraso_inicio_min, 'valor_esperado': 5, 'unidad': 'min'})
        if self.fecha_fin_estimada and (now - self.fecha_fin_estimada).total_seconds() > 300:
            incidence.create({'recorrido_id': self.id, 'tipo': 'retraso', 'timestamp': now,
                              'descripcion': 'Llegada final fuera de la tolerancia de 5 minutos.',
                              'valor_detectado': (now - self.fecha_fin_estimada).total_seconds() / 60,
                              'valor_esperado': 5, 'unidad': 'min'})

    def _inicializar_cumplimiento_paradas(self):
        """Crea registros de cumplimiento para cada parada de la ruta."""
        self.ensure_one()
        existing = self.cumplimiento_parada_ids.mapped('parada_id')
        vals_list = []
        for parada in self.ruta_id.parada_ids:
            if parada in existing:
                continue
            vals_list.append({
                'recorrido_id': self.id,
                'parada_id': parada.id,
                'cumplida': False,
            })
        if vals_list:
            self.env['fleet.cumplimiento.parada'].create(vals_list)

    def action_view_posiciones(self):
        """Abre las posiciones GPS del recorrido."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Posiciones GPS — {self.name}',
            'res_model': 'fleet.posicion.gps',
            'view_mode': 'tree,form',
            'domain': [('recorrido_id', '=', self.id)],
            'context': {'default_recorrido_id': self.id},
        }

    def action_view_incidencias(self):
        """Abre las incidencias del recorrido."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Incidencias — {self.name}',
            'res_model': 'fleet.incidencia',
            'view_mode': 'tree,form',
            'domain': [('recorrido_id', '=', self.id)],
            'context': {'default_recorrido_id': self.id},
        }
