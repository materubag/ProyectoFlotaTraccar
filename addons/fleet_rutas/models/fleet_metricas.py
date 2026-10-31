# -*- coding: utf-8 -*-
"""
Modelo fleet.metricas.recorrido — Cálculo dinámico y almacenamiento de métricas
operativas y de calidad SQA (ISO/IEC 25010) para rutas de transporte universitario.
"""
import logging
import json
from time import perf_counter
from odoo import api, fields, models
from .fleet_algoritmos import (
    calcular_metricas_recorrido,
    calcular_retraso_min,
    detectar_desviacion,
    detectar_perdida_senal,
    calcular_distancia_total_km,
    posicion_coincide_con_origen,
)

_logger = logging.getLogger(__name__)


class FleetMetricasRecorrido(models.Model):
    _name = 'fleet.metricas.recorrido'
    _description = 'Métricas Calculadas de Recorrido (ISO/IEC 25010)'
    _order = 'fecha_calculo desc'
    _rec_name = 'recorrido_id'
    _sql_constraints = [('recorrido_unique', 'unique(recorrido_id)', 'Ya existen métricas para este recorrido.')]

    calidad_sync_disponible = fields.Boolean(string='Sincronización medida', readonly=True)
    deteccion_validada = fields.Boolean(string='Eventos validados disponibles', readonly=True)
    fecha_recorrido = fields.Datetime(related='recorrido_id.fecha_inicio', store=True, string='Fecha del recorrido', index=True)
    diferencia_duracion_min = fields.Float(string='Diferencia de duración (min)', readonly=True, group_operator='avg')

    recorrido_id = fields.Many2one(
        comodel_name='fleet.recorrido',
        string='Recorrido',
        required=True,
        ondelete='cascade',
        index=True,
    )
    fecha_calculo = fields.Datetime(
        string='Fecha de Cálculo',
        default=fields.Datetime.now,
        readonly=True,
        required=True,
    )
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

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Métricas de Operación de Transporte
    # ──────────────────────────────────────────────────────────────────────────
    pct_cumplimiento_ruta = fields.Float(
        string='% Cumplimiento de Ruta',
        digits=(5, 2),
        readonly=True, group_operator='avg',
        help='Porcentaje global de cumplimiento del recorrido según paradas y ruta.',
    )
    pct_puntualidad = fields.Float(
        string='% Puntualidad',
        digits=(5, 2),
        readonly=True, group_operator='avg',
        help='Porcentaje de paradas a las que se llegó dentro del margen de tolerancia.',
    )
    retraso_promedio_min = fields.Float(
        string='Retraso Promedio (min)',
        digits=(6, 2),
        readonly=True, group_operator='avg',
        help='Promedio de minutos de retraso en puntos de control evaluados.',
    )
    pct_paradas_cumplidas = fields.Float(
        string='% Paradas Cumplidas',
        digits=(5, 2),
        readonly=True, group_operator='avg',
        help='Porcentaje de puntos de control efectivamente visitados.',
    )
    pct_desviacion_ruta = fields.Float(
        string='% Desviación de Ruta',
        digits=(5, 2),
        readonly=True, group_operator='avg',
        help='Porcentaje de registros GPS situados fuera del corredor autorizado.',
    )
    distancia_real_km = fields.Float(
        string='Distancia Real (km)',
        digits=(10, 3),
        readonly=True, group_operator='avg',
    )
    diferencia_distancia_km = fields.Float(
        string='Diferencia de Distancia (km)',
        digits=(10, 3),
        readonly=True, group_operator='avg',
        help='Diferencia entre distancia recorrida real y distancia estimada programada.',
    )
    duracion_real_min = fields.Integer(
        string='Duración Real (min)',
        readonly=True, group_operator='avg',
        help='Tiempo total de viaje entre salida y llegada.',
    )
    frecuencia_incidencias = fields.Float(
        string='Frecuencia de Incidencias (inc/h)',
        digits=(5, 2),
        readonly=True, group_operator='avg',
        help='Tasa de incidencias registradas por hora de operación.',
    )

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Métricas de Calidad de Software (ISO/IEC 25010)
    # ──────────────────────────────────────────────────────────────────────────
    integridad_gps_pct = fields.Float(
        string='Integridad de Registros GPS (%)',
        digits=(5, 2),
        readonly=True, group_operator='avg',
        help='ISO 25010 (Fiabilidad/Tolerancia a fallos): Porcentaje de tiempo con telemetría continua sin pérdidas de señal prolongadas.',
    )
    exactitud_sincronizacion_pct = fields.Float(
        string='Exactitud de Sincronización (%)',
        digits=(5, 2),
        readonly=True, group_operator='avg',
        help='Posiciones almacenadas que coinciden con su JSON original recibido de Traccar, según la precisión de los campos.',
    )
    tiempo_respuesta_ms = fields.Float(
        string='Tiempo de Respuesta (ms)',
        digits=(8, 2),
        readonly=True, group_operator='avg',
        help='Tiempo medido del cálculo de métricas antes de persistir el resultado; no incluye latencia de red ni renderizado.',
    )
    tasa_verdaderos_positivos_pct = fields.Float(
        string='Tasa Verdaderos Positivos (%)',
        digits=(5, 2),
        readonly=True, group_operator='avg',
        help='Precisión: verdaderos positivos / eventos validados. No mide falsos negativos; sin validaciones no hay resultado disponible.',
    )
    n_gaps_senal = fields.Integer(
        string='Gaps de Señal GPS',
        readonly=True,
        help='Número de eventos detectados con pérdida de señal > 120 segundos.',
    )
    duracion_gaps_seg = fields.Float(
        string='Duración Total Gaps (seg)',
        digits=(10, 2),
        readonly=True, group_operator='avg',
    )

    @api.model
    def calcular_para_recorrido(self, recorrido_id):
        """
        Calcula y persiste las métricas completas para el recorrido indicado.
        """
        self.check_access_rights('write')
        started = perf_counter()
        recorrido = self.env['fleet.recorrido'].browse(recorrido_id)
        if not recorrido.exists():
            _logger.error('Recorrido %s no existe para cálculo de métricas.', recorrido_id)
            return self.browse()

        posiciones = recorrido.posicion_ids.sorted('timestamp')
        paradas = recorrido.ruta_id.parada_ids.sorted('secuencia')
        cumplimientos = recorrido.cumplimiento_parada_ids

        # Preparar datos para los algoritmos
        historial_gps = [
            {
                'latitud': p.latitud,
                'longitud': p.longitud,
                'timestamp': p.timestamp,
                'velocidad_kmh': getattr(p, 'velocidad_kmh', getattr(p, 'velocidad', 0.0)),
            }
            for p in posiciones
        ]

        paradas_info = []
        for c in cumplimientos:
            paradas_info.append({
                'parada_id': c.parada_id.id,
                'cumplida': c.cumplida,
                'retraso_min': c.retraso_min,
                'es_puntual': c.cumplida and abs(c.retraso_min) <= c.parada_id.tolerancia_min,
            })

        polyline_ruta = [(p.latitud, p.longitud) for p in paradas]

        # Invocación al motor algorítmico
        res_alg = calcular_metricas_recorrido(
            historial_gps=historial_gps,
            paradas_info=paradas_info,
            polyline_ruta=polyline_ruta,
            max_gap_seg=120,
            umbral_desviacion_m=100.0,
        )

        total_paradas = len(cumplimientos)
        paradas_cumplidas_count = len(cumplimientos.filtered('cumplida'))
        pct_paradas = round((paradas_cumplidas_count / total_paradas * 100.0), 2) if total_paradas else 0.0

        retrasos_list = [max(0.0, c.retraso_min) for c in cumplimientos if c.cumplida]
        retraso_prom = round(sum(retrasos_list) / len(retrasos_list), 2) if retrasos_list else 0.0

        # Cálculo de desviaciones
        total_pos = len(posiciones)
        pos_desviadas = sum(1 for p in posiciones if detectar_desviacion(p.latitud, p.longitud, polyline_ruta, 100.0)['es_desviacion']) if len(polyline_ruta) >= 2 else 0
        pct_desv = round((pos_desviadas / total_pos * 100.0), 2) if total_pos else 0.0

        # Duración real
        duracion_min = recorrido.duracion_real_min
        if not duracion_min and recorrido.fecha_inicio_real and recorrido.fecha_fin_real:
            duracion_min = int((recorrido.fecha_fin_real - recorrido.fecha_inicio_real).total_seconds() / 60)

        # Diferencia de distancia
        dist_real = res_alg.get('distancia_total_km', recorrido.distancia_real_km or 0.0)
        dist_est = recorrido.ruta_id.distancia_estimada_km or 0.0
        dif_dist = round(dist_real - dist_est, 3)

        # Frecuencia de incidencias
        n_inc = len(recorrido.incidencia_ids)
        horas_op = duracion_min / 60.0
        frec_inc = round(n_inc / horas_op, 2) if horas_op > 0 else 0.0

        # Binary route compliance permits an aggregate percentage of completed routes.
        pct_punt = res_alg.get('pct_puntualidad', 0.0)
        pct_cumplimiento_global = 100.0 if (total_pos >= 2 and total_paradas > 0 and pct_paradas == 100 and pct_desv == 0 and recorrido.fecha_fin_real) else 0.0

        # SQA Metricas
        integridad_gps = res_alg.get('integridad_gps_pct', 100.0)
        n_gaps = res_alg.get('num_gaps', 0)
        duracion_gaps = res_alg.get('duracion_gaps_seg', 0.0)

        snapshots = posiciones.filtered('payload_origen')
        received = len(snapshots)
        matches = 0
        for pos in snapshots:
            try:
                raw = json.loads(pos.payload_origen)
            except (ValueError, TypeError):
                raw = {}
            matches += posicion_coincide_con_origen(pos.latitud, pos.longitud, pos.velocidad_kmh, pos.timestamp, raw)
        exactitud_sync = matches / received * 100.0 if received else 0.0
        validated = recorrido.incidencia_ids.filtered(lambda i: i.validacion != 'pendiente')
        precision = len(validated.filtered(lambda i: i.validacion == 'verdadero')) / len(validated) * 100 if validated else 0.0

        # Buscar si ya existe métrica para este recorrido y actualizar o crear
        metrica = self.search([('recorrido_id', '=', recorrido.id)], limit=1)
        vals = {
            'recorrido_id': recorrido.id,
            'fecha_calculo': fields.Datetime.now(),
            'pct_cumplimiento_ruta': pct_cumplimiento_global,
            'pct_puntualidad': pct_punt,
            'retraso_promedio_min': retraso_prom,
            'pct_paradas_cumplidas': pct_paradas,
            'pct_desviacion_ruta': pct_desv,
            'distancia_real_km': dist_real,
            'diferencia_distancia_km': dif_dist,
            'duracion_real_min': duracion_min,
            'diferencia_duracion_min': duracion_min - recorrido.ruta_id.duracion_estimada_min,
            'frecuencia_incidencias': frec_inc,
            'integridad_gps_pct': integridad_gps,
            'exactitud_sincronizacion_pct': exactitud_sync,
            'tiempo_respuesta_ms': round((perf_counter() - started) * 1000, 2),
            'tasa_verdaderos_positivos_pct': precision,
            'calidad_sync_disponible': bool(received),
            'deteccion_validada': bool(validated),
            'n_gaps_senal': n_gaps,
            'duracion_gaps_seg': duracion_gaps,
        }

        if metrica:
            metrica.write(vals)
        else:
            metrica = self.create(vals)

        return metrica

    @api.model
    def get_dashboard_kpis(self):
        """
        Retorna KPIs agregados para el dashboard OWL en tiempo real.
        """
        Recorrido = self.env['fleet.recorrido']
        Incidencia = self.env['fleet.incidencia']
        Metricas = self.env['fleet.metricas.recorrido']

        from datetime import timedelta
        import pytz
        tz = pytz.timezone(self.env.user.tz or 'America/Guayaquil')
        local_day = pytz.utc.localize(fields.Datetime.now()).astimezone(tz).date()
        from datetime import datetime, time
        start = tz.localize(datetime.combine(local_day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        end = tz.localize(datetime.combine(local_day + timedelta(days=1), time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        recorridos_hoy = Recorrido.search([('fecha_inicio', '>=', start), ('fecha_inicio', '<', end)])
        en_curso = Recorrido.search_count([('estado', '=', 'en_curso')])
        completados = Recorrido.search_count([('fecha_fin_real', '!=', False)])
        incidencias_activas = Incidencia.search_count([('resuelta', '=', False)])

        all_metricas = Metricas.search([('recorrido_id.fecha_fin_real', '!=', False), ('recorrido_id.simulado', '=', False)], order='fecha_calculo desc')

        avg_puntualidad = 0.0
        avg_cumplimiento = 0.0
        avg_integridad_gps = 0.0

        if all_metricas:
            avg_puntualidad = round(sum(m.pct_puntualidad for m in all_metricas) / len(all_metricas), 1)
            avg_cumplimiento = round(sum(m.pct_cumplimiento_ruta for m in all_metricas) / len(all_metricas), 1)
            avg_integridad_gps = round(sum(m.integridad_gps_pct for m in all_metricas) / len(all_metricas), 1)

        # Recorridos activos detallados
        activos_data = []
        for r in Recorrido.search([('estado', '=', 'en_curso')], limit=10):
            activos_data.append({
                'id': r.id,
                'name': r.name,
                'ruta': r.ruta_id.name,
                'vehiculo': r.vehicle_id.name,
                'paradas_cumplidas': f"{r.porcentaje_paradas_cumplidas:.0f}%",
                'desviacion': r.tiene_desviacion,
            })

        return {
            'recorridos_hoy': len(recorridos_hoy),
            'en_curso': en_curso,
            'completados': completados,
            'incidencias_activas': incidencias_activas,
            'avg_puntualidad': avg_puntualidad,
            'avg_cumplimiento': avg_cumplimiento,
            'avg_integridad_gps': avg_integridad_gps,
            'recorridos_activos': activos_data,
        }

