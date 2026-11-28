"""
Estimación de la hora de llegada a las próximas paradas.

Método: se proyecta el vehículo sobre el trazado de la ruta; hasta la próxima parada
se usa la velocidad reciente (o la prevista por el horario si el bus está detenido o
no hay datos suficientes) y, para las siguientes, los intervalos del horario.
"""
from datetime import timedelta

from odoo import fields, models

from .fleet_algoritmos import progresos_paradas, proyectar_en_polilinea

VENTANA_VELOCIDAD_S = 180
VENTANA_MINIMA_S = 30
VELOCIDAD_MIN_MS = 8 / 3.6      # por debajo se considera detenido
VELOCIDAD_MAX_MS = 90 / 3.6
VELOCIDAD_POR_DEFECTO_MS = 20 / 3.6
SENAL_VIGENTE_S = 120
FUERA_DE_RUTA_M = 150.0
MARGEN_PASADA_M = 100.0


class FleetRecorridoLlegadas(models.Model):
    _inherit = 'fleet.recorrido'

    def estimar_llegadas(self, ahora=None):
        """
        Devuelve ``{'motivo': str|None, 'paradas': [...]}``. Cada parada indica su
        estado y la hora programada; las pendientes incluyen la hora estimada cuando
        hay datos fiables. Solo usa información disponible hasta ``ahora``.
        """
        self.ensure_one()
        ahora = ahora or fields.Datetime.now()
        paradas = self.paradas_del_recorrido()
        if not paradas or not self.fecha_inicio:
            return {'motivo': 'Recorrido sin paradas', 'paradas': []}
        visitadas = {
            c.parada_id.id: c.timestamp_llegada for c in self.cumplimiento_parada_ids
            if c.cumplida and c.timestamp_llegada and c.timestamp_llegada <= ahora}
        ultima = max((i for i, p in enumerate(paradas) if p.id in visitadas), default=-1)
        filas = [{
            'id': p.id, 'nombre': p.name, 'secuencia': p.secuencia,
            'estado': 'visitada' if p.id in visitadas else ('omitida' if i < ultima else 'pendiente'),
            'programada': self.hora_programada(p), 'llegada': visitadas.get(p.id),
            'estimada': None, 'minutos': None, 'retraso_min': None, 'tolerancia_min': p.tolerancia_min,
        } for i, p in enumerate(paradas)]

        def sin_estimacion(motivo):
            return {'motivo': motivo, 'paradas': filas}

        if ultima == len(paradas) - 1:
            return sin_estimacion('El vehículo ya llegó al destino')
        Posicion = self.env['fleet.posicion.gps']
        actual = Posicion.search([('recorrido_id', '=', self.id), ('timestamp', '<=', ahora)],
                                 order='timestamp desc, id desc', limit=1)
        if not actual:
            return sin_estimacion('Sin posiciones todavía')
        if (ahora - actual.timestamp).total_seconds() > SENAL_VIGENTE_S:
            return sin_estimacion('Señal sin actualizar')
        linea = self.ruta_id.puntos_referencia()
        if len(linea) < 2:
            return sin_estimacion('Ruta sin trazado de referencia')
        avance = progresos_paradas([(p.latitud, p.longitud) for p in paradas], linea)
        desde = max(0.0, avance[ultima] - MARGEN_PASADA_M) if ultima >= 0 else 0.0
        lugar, separacion = proyectar_en_polilinea(actual.latitud, actual.longitud, linea, desde)
        if lugar is None or separacion > FUERA_DE_RUTA_M:
            return sin_estimacion('El vehículo está fuera de la ruta')

        # Una parada que ya quedó atrás sin registro no se anuncia como próxima.
        siguiente = next((i for i in range(ultima + 1, len(paradas))
                          if avance[i] >= lugar - MARGEN_PASADA_M), len(paradas) - 1)
        for i in range(ultima + 1, siguiente):
            filas[i]['estado'] = 'omitida'

        velocidad = None
        reciente = Posicion.search([
            ('recorrido_id', '=', self.id), ('timestamp', '<=', actual.timestamp),
            ('timestamp', '>=', actual.timestamp - timedelta(seconds=VENTANA_VELOCIDAD_S))],
            order='timestamp, id', limit=1)
        segundos = (actual.timestamp - reciente.timestamp).total_seconds()
        if segundos >= VENTANA_MINIMA_S:
            antes, lejos = proyectar_en_polilinea(reciente.latitud, reciente.longitud, linea, desde)
            if antes is not None and lejos <= FUERA_DE_RUTA_M:
                medida = (lugar - antes) / segundos
                if VELOCIDAD_MIN_MS <= medida <= VELOCIDAD_MAX_MS:
                    velocidad = medida
        if velocidad is None and siguiente > 0:
            tramo = avance[siguiente] - avance[siguiente - 1]
            previsto = (filas[siguiente]['programada'] - filas[siguiente - 1]['programada']).total_seconds()
            if tramo > 0 and previsto > 0:
                velocidad = min(max(tramo / previsto, VELOCIDAD_MIN_MS / 2), VELOCIDAD_MAX_MS)
        velocidad = velocidad or VELOCIDAD_POR_DEFECTO_MS

        llegada = actual.timestamp + timedelta(seconds=max(avance[siguiente] - lugar, 0) / velocidad)
        llegada = max(llegada, ahora)
        for i in range(siguiente, len(paradas)):
            estimada = llegada + (filas[i]['programada'] - filas[siguiente]['programada'])
            estimada = max(estimada, llegada).replace(microsecond=0)
            filas[i].update({
                'estimada': estimada,
                'minutos': max(0, round((estimada - ahora).total_seconds() / 60)),
                'retraso_min': round((estimada - filas[i]['programada']).total_seconds() / 60, 1),
            })
        return {'motivo': None, 'paradas': filas}

    def evaluar_estimaciones(self):
        """
        Repite la estimación en cada posición de un recorrido terminado y la compara con
        la llegada real a la próxima parada. Devuelve pares de errores en segundos:
        (error de la estimación, error de suponer la hora programada, horizonte).
        La estimación en un instante no usa datos posteriores a él.
        """
        self.ensure_one()
        reales = {c.parada_id.id: c.timestamp_llegada for c in self.cumplimiento_parada_ids
                  if c.cumplida and c.timestamp_llegada}
        errores = []
        for posicion in self.posicion_ids.sorted('timestamp'):
            resultado = self.estimar_llegadas(ahora=posicion.timestamp)
            proxima = next((f for f in resultado['paradas'] if f['estimada']), None)
            real = proxima and reales.get(proxima['id'])
            if not real or real <= posicion.timestamp:
                continue
            errores.append((abs((proxima['estimada'] - real).total_seconds()),
                            abs((proxima['programada'] - real).total_seconds()),
                            (real - posicion.timestamp).total_seconds()))
        return errores
