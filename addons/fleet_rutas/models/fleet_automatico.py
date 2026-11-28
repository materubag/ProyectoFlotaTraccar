"""
Seguimiento en tiempo real: inicio y cierre automáticos de recorridos y alertas de
retraso y parada omitida mientras el bus sigue en ruta.

Solo actúa sobre recorridos reales: los marcados como simulados nunca se tocan
desde la tarea programada.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

from .fleet_algoritmos import haversine_distance_m

_logger = logging.getLogger(__name__)

ANTICIPO_INICIO_MIN = 5       # un inicio dentro de la tolerancia no cuenta como adelanto
ESPERA_INICIO_MIN = 60        # pasado este tiempo ya no se inicia automáticamente
VENTANA_SIN_INICIAR_H = 12    # no se generan alertas de recorridos programados antiguos
CIERRE_VENCIDO_MIN = 60       # tras el fin previsto...
CIERRE_SILENCIO_MIN = 15      # ...y sin posiciones recientes, se cierra


class FleetIncidenciaParada(models.Model):
    _inherit = 'fleet.incidencia'

    parada_id = fields.Many2one('fleet.parada', string='Parada', ondelete='set null', index=True)

    @api.model
    def registrar_en_parada(self, recorrido, parada, tipo, valores, actualizar=True):
        """Mantiene una sola incidencia por recorrido, parada y tipo."""
        existente = self.search([('recorrido_id', '=', recorrido.id), ('parada_id', '=', parada.id),
                                 ('tipo', '=', tipo)], limit=1)
        if not existente:
            return self.create(dict(valores, recorrido_id=recorrido.id, parada_id=parada.id, tipo=tipo))
        if actualizar:
            existente.write({k: v for k, v in valores.items() if k != 'timestamp'})
        return existente


class FleetRecorridoAutomatico(models.Model):
    _inherit = 'fleet.recorrido'

    def hora_programada(self, parada):
        """La primera parada coincide con el inicio programado; las demás conservan el intervalo."""
        self.ensure_one()
        primera = self.paradas_del_recorrido()[:1]
        desfase = (round(parada.hora_prevista * 60) - round(primera.hora_prevista * 60)) % 1440
        return self.fecha_inicio + timedelta(minutes=desfase)

    def revisar_paradas_pendientes(self, ahora=None):
        """Alerta paradas omitidas o con retraso sin esperar al cierre del recorrido."""
        self.ensure_one()
        ahora = ahora or fields.Datetime.now()
        incidencias = self.env['fleet.incidencia']
        visitadas = self.cumplimiento_parada_ids.filtered('cumplida').mapped('parada_id')
        ultima = max(visitadas.mapped('secuencia'), default=None)
        for cumplimiento in self.cumplimiento_parada_ids.filtered(lambda c: not c.cumplida):
            parada = cumplimiento.parada_id
            if ultima is not None and parada.secuencia < ultima:
                incidencias.registrar_en_parada(self, parada, 'parada_omitida', {
                    'timestamp': ahora,
                    'descripcion': f'Parada no visitada: {parada.name}'}, actualizar=False)
                continue
            retraso = (ahora - self.hora_programada(parada)).total_seconds() / 60
            if retraso > parada.tolerancia_min:
                incidencias.registrar_en_parada(self, parada, 'retraso', {
                    'timestamp': ahora,
                    'descripcion': f'Sin llegada registrada a {parada.name}: {retraso:.0f} minutos de retraso.',
                    'valor_detectado': round(retraso, 2), 'valor_esperado': parada.tolerancia_min,
                    'unidad': 'min'}, actualizar=False)

    def _iniciar_si_salio(self, ahora):
        """Inicia un recorrido programado cuando el vehículo está en el origen a su hora."""
        self.ensure_one()
        origen = self.ruta_id.parada_ids.sorted('secuencia')[:1]
        if not origen or self.ruta_id.estado != 'activa':
            return False
        if self.search_count([('vehicle_id', '=', self.vehicle_id.id), ('estado', '=', 'en_curso')]):
            return False
        desde = self.fecha_inicio - timedelta(minutes=ANTICIPO_INICIO_MIN)
        hasta = min(ahora, self.fecha_inicio + timedelta(minutes=ESPERA_INICIO_MIN))
        libres = self.env['fleet.posicion.gps'].search([
            ('vehicle_id', '=', self.vehicle_id.id), ('recorrido_id', '=', False),
            ('timestamp', '>=', desde)], order='timestamp, id')
        salida = next((p for p in libres if p.timestamp <= hasta and haversine_distance_m(
            p.latitud, p.longitud, origen.latitud, origen.longitud) <= origen.radio_proximidad_m), None)
        if not salida:
            return False
        self.action_iniciar(momento=salida.timestamp)
        recientes = libres.filtered(lambda p: p.timestamp >= salida.timestamp)
        recientes.write({'recorrido_id': self.id})
        recientes.sorted('timestamp').detectar_desviacion()
        self.message_post(body='Recorrido iniciado automáticamente al detectar el vehículo en el origen.')
        return True

    def _avisar_sin_iniciar(self, ahora):
        self.ensure_one()
        origen = self.ruta_id.parada_ids.sorted('secuencia')[:1]
        retraso = (ahora - self.fecha_inicio).total_seconds() / 60
        if origen and retraso > origen.tolerancia_min:
            self.env['fleet.incidencia'].registrar_en_parada(self, origen, 'retraso', {
                'timestamp': ahora,
                'descripcion': f'El recorrido no ha iniciado: {retraso:.0f} minutos después de lo programado.',
                'valor_detectado': round(retraso, 2), 'valor_esperado': origen.tolerancia_min,
                'unidad': 'min'}, actualizar=False)

    def _cerrar_si_corresponde(self, ahora):
        """
        Cierra al llegar al destino habiendo pasado por al menos la mitad de las paradas
        intermedias, o cuando el recorrido venció hace tiempo y no envía posiciones.
        """
        self.ensure_one()
        paradas = self.paradas_del_recorrido()
        if not paradas:
            return False
        destino, intermedias = paradas[-1], paradas[1:-1]
        cumplidas = self.cumplimiento_parada_ids.filtered('cumplida')
        llegada = cumplidas.filtered(lambda c: c.parada_id == destino)
        pasadas = len(cumplidas.filtered(lambda c: c.parada_id in intermedias))
        if llegada and llegada.timestamp_llegada and pasadas * 2 >= len(intermedias):
            momento = max(llegada.timestamp_llegada, self.fecha_inicio_real)
            motivo = 'llegada al destino'
        else:
            fin_previsto = self.fecha_fin_estimada or self.hora_programada(destino)
            ultima = self.env['fleet.posicion.gps'].search(
                [('recorrido_id', '=', self.id)], order='timestamp desc, id desc', limit=1)
            referencia = ultima.timestamp if ultima else self.fecha_inicio_real
            if (ahora - fin_previsto < timedelta(minutes=CIERRE_VENCIDO_MIN)
                    or ahora - referencia < timedelta(minutes=CIERRE_SILENCIO_MIN)):
                return False
            momento = ahora
            motivo = 'tiempo vencido sin posiciones'
        self.posicion_ids.filtered(lambda p: p.timestamp > momento).write({'recorrido_id': False})
        self.invalidate_recordset(['posicion_ids'])
        self.action_completar(momento=momento)
        self.message_post(body=f'Recorrido cerrado automáticamente: {motivo}.')
        return True

    @api.model
    def revisar_recorridos(self, ahora=None):
        """Tarea programada. Un fallo en un recorrido no detiene la revisión de los demás."""
        ahora = ahora or fields.Datetime.now()
        automatico = self.env['ir.config_parameter'].sudo().get_param(
            'fleet_rutas.recorridos_automaticos', '1') != '0'
        programados = self.search([
            ('estado', '=', 'programado'), ('simulado', '=', False),
            ('fecha_inicio', '<=', ahora + timedelta(minutes=ANTICIPO_INICIO_MIN)),
            ('fecha_inicio', '>=', ahora - timedelta(hours=VENTANA_SIN_INICIAR_H))],
            order='fecha_inicio')
        for recorrido in programados:
            try:
                with self.env.cr.savepoint():
                    if not (automatico and recorrido._iniciar_si_salio(ahora)):
                        recorrido._avisar_sin_iniciar(ahora)
            except Exception:
                _logger.exception('No se pudo revisar el recorrido programado %s', recorrido.id)
        for recorrido in self.search([('estado', '=', 'en_curso'), ('simulado', '=', False)]):
            try:
                with self.env.cr.savepoint():
                    recorrido.revisar_paradas_pendientes(ahora)
                    # Aquí cada minuto: la tarea propia de señal conserva su intervalo
                    # en las instalaciones existentes.
                    self.env['fleet.traccar.sync'].verificar_perdida_senal(recorrido.id, ahora=ahora)
                    if automatico:
                        recorrido._cerrar_si_corresponde(ahora)
            except Exception:
                _logger.exception('No se pudo revisar el recorrido en curso %s', recorrido.id)
        return True
