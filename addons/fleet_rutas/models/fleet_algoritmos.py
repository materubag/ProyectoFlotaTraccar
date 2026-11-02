# -*- coding: utf-8 -*-
"""
fleet_algoritmos.py
===================
Algoritmos geoespaciales y de análisis para el Sistema de Monitoreo de Rutas
de Transporte Universitario.

Todos los algoritmos son funciones puras (sin dependencias de Odoo) para
facilitar las pruebas unitarias con pytest fuera del entorno Odoo.

Referencia de calidad: ISO/IEC 25010 — Funcionalidad (precisión) y
Fiabilidad (tolerancia a fallos).
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

_logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────────────────

RADIO_TIERRA_M = 6_371_000.0   # Radio medio de la Tierra en metros
KM_POR_M = 0.001


def posicion_coincide_con_origen(latitud, longitud, velocidad_kmh, timestamp, payload):
    """Compare a persisted fix against its received Traccar snapshot, at field precision."""
    from datetime import timezone
    try:
        raw_time = payload.get('fixTime') or payload.get('deviceTime') or payload.get('serverTime')
        source_time = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
        if source_time.tzinfo:
            source_time = source_time.astimezone(timezone.utc).replace(tzinfo=None)
        return (
            math.isclose(latitud, float(payload['latitude']), rel_tol=0, abs_tol=1e-7)
            and math.isclose(longitud, float(payload['longitude']), rel_tol=0, abs_tol=1e-7)
            and math.isclose(velocidad_kmh, float(payload.get('speed', 0)) * 1.852, rel_tol=0, abs_tol=.011)
            and abs((timestamp - source_time).total_seconds()) < 1
        )
    except (TypeError, ValueError, KeyError, AttributeError):
        return False


# ──────────────────────────────────────────────────────────────────────────────
# 1. Distancia Haversine
# ──────────────────────────────────────────────────────────────────────────────

def haversine_distance_m(lat1: float, lon1: float,
                         lat2: float, lon2: float) -> float:
    """
    Calcula la distancia en metros entre dos puntos geográficos usando la
    fórmula de Haversine (distancia de círculo máximo sobre la esfera terrestre).

    Parámetros
    ----------
    lat1, lon1 : float
        Coordenadas del primer punto en grados decimales.
    lat2, lon2 : float
        Coordenadas del segundo punto en grados decimales.

    Retorna
    -------
    float
        Distancia en metros.

    Característica ISO 25010: Precisión funcional.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    a = max(0.0, min(1.0, a))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return RADIO_TIERRA_M * c


# ──────────────────────────────────────────────────────────────────────────────
# 2. Distancia punto a segmento
# ──────────────────────────────────────────────────────────────────────────────

def point_to_segment_distance_m(lat_p: float, lon_p: float,
                                lat_a: float, lon_a: float,
                                lat_b: float, lon_b: float) -> float:
    """
    Calcula la distancia mínima en metros desde el punto P al segmento AB.

    Usa proyección lineal en coordenadas locales (aproximación plana válida
    para segmentos cortos < 50 km).

    Característica ISO 25010: Precisión funcional.
    """
    # Convertir a coordenadas cartesianas locales (metros)
    scale_lat = RADIO_TIERRA_M * math.pi / 180.0
    scale_lon = scale_lat * math.cos(math.radians((lat_a + lat_b) / 2.0))

    px = (lon_p - lon_a) * scale_lon
    py = (lat_p - lat_a) * scale_lat
    bx = (lon_b - lon_a) * scale_lon
    by = (lat_b - lat_a) * scale_lat

    seg_len_sq = bx * bx + by * by
    if seg_len_sq == 0.0:
        # El segmento degenera en un punto
        return haversine_distance_m(lat_p, lon_p, lat_a, lon_a)

    t = max(0.0, min(1.0, (px * bx + py * by) / seg_len_sq))
    closest_x = t * bx
    closest_y = t * by
    dx = px - closest_x
    dy = py - closest_y
    return math.sqrt(dx * dx + dy * dy)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Distancia mínima a polilínea
# ──────────────────────────────────────────────────────────────────────────────

def min_distance_to_polyline_m(lat_p: float, lon_p: float,
                               polyline: List[Tuple[float, float]]) -> float:
    """
    Calcula la distancia mínima en metros desde el punto P a cualquier
    segmento de la polilínea indicada.

    Parámetros
    ----------
    lat_p, lon_p : float
        Coordenadas del punto a evaluar.
    polyline : list of (lat, lon) tuples
        Secuencia de vértices que definen la ruta.

    Retorna
    -------
    float
        Distancia mínima en metros. Retorna float('inf') si la polilínea
        tiene menos de 2 vértices.

    Característica ISO 25010: Precisión funcional.
    """
    if len(polyline) < 2:
        if len(polyline) == 1:
            return haversine_distance_m(lat_p, lon_p, polyline[0][0], polyline[0][1])
        return float('inf')

    min_dist = float('inf')
    for i in range(len(polyline) - 1):
        lat_a, lon_a = polyline[i]
        lat_b, lon_b = polyline[i + 1]
        dist = point_to_segment_distance_m(lat_p, lon_p, lat_a, lon_a, lat_b, lon_b)
        if dist < min_dist:
            min_dist = dist
    return min_dist


# ──────────────────────────────────────────────────────────────────────────────
# 4. Cálculo de retraso
# ──────────────────────────────────────────────────────────────────────────────

def calcular_retraso_min(hora_prevista_decimal: float,
                         fecha_referencia,
                         hora_llegada: datetime,
                         tolerancia_min: int = 5) -> Dict:
    """
    Calcula si el bus llegó tarde, puntual o adelantado a una parada.

    Parámetros
    ----------
    hora_prevista_decimal : float
        Hora programada en formato decimal (8.5 = 08:30).
    fecha_referencia : date
        Fecha de referencia para construir el datetime programado.
    hora_llegada : datetime
        Timestamp real de llegada del vehículo.
    tolerancia_min : int
        Ventana de tolerancia en minutos (±).

    Retorna
    -------
    dict con claves:
        - retraso_min (float): minutos de diferencia (positivo = tarde).
        - es_retraso (bool): True si llegó más de tolerancia_min tarde.
        - es_puntual (bool): True si llegó dentro de la tolerancia.
        - es_adelanto (bool): True si llegó más de tolerancia_min temprano.
        - hora_prevista_str (str): hora programada formateada.
        - hora_llegada_str (str): hora de llegada formateada.

    Característica ISO 25010: Corrección funcional, Fiabilidad.
    """
    if not 0 <= hora_prevista_decimal < 24 or tolerancia_min < 0:
        raise ValueError('Hora o tolerancia fuera de rango')
    total_min = round(hora_prevista_decimal * 60)
    horas, minutos = divmod(total_min % 1440, 60)
    hora_programada = datetime.combine(fecha_referencia, datetime.min.time()) + timedelta(minutes=total_min)

    diff_seg = (hora_llegada - hora_programada).total_seconds()
    retraso_min = diff_seg / 60.0

    es_retraso = retraso_min > tolerancia_min
    es_adelanto = retraso_min < -tolerancia_min
    es_puntual = not es_retraso and not es_adelanto

    return {
        'retraso_min': round(retraso_min, 2),
        'es_retraso': es_retraso,
        'es_puntual': es_puntual,
        'es_adelanto': es_adelanto,
        'hora_prevista_str': f'{horas:02d}:{minutos:02d}',
        'hora_llegada_str': hora_llegada.strftime('%H:%M:%S'),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 5. Validación de parada
# ──────────────────────────────────────────────────────────────────────────────

def validar_parada(lat_parada: float, lon_parada: float,
                   radio_m: float,
                   historial_gps: List[Dict]) -> Dict:
    """
    Determina si el vehículo estuvo dentro del radio de una parada en algún
    momento del historial GPS proporcionado.

    Parámetros
    ----------
    lat_parada, lon_parada : float
        Coordenadas de la parada.
    radio_m : float
        Radio de proximidad en metros.
    historial_gps : list of dict
        Cada elemento debe tener 'latitud', 'longitud' y 'timestamp'.

    Retorna
    -------
    dict con claves:
        - cumplida (bool): True si el vehículo estuvo dentro del radio.
        - distancia_minima_m (float): distancia mínima alcanzada en metros.
        - posicion_cumplimiento (dict | None): posición donde se cumplió.

    Característica ISO 25010: Corrección funcional.
    """
    min_dist = float('inf')
    posicion_cumplimiento = None

    for pos in historial_gps:
        lat = pos.get('latitud', pos.get('lat', 0.0))
        lon = pos.get('longitud', pos.get('lon', 0.0))
        dist = haversine_distance_m(lat, lon, lat_parada, lon_parada)
        if dist < min_dist:
            min_dist = dist
        if dist <= radio_m and (posicion_cumplimiento is None or pos['timestamp'] < posicion_cumplimiento['timestamp']):
            posicion_cumplimiento = pos

    cumplida = min_dist <= radio_m
    return {
        'cumplida': cumplida,
        'distancia_minima_m': round(min_dist, 2) if min_dist != float('inf') else None,
        'posicion_cumplimiento': posicion_cumplimiento,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 6. Detección de desviación
# ──────────────────────────────────────────────────────────────────────────────

def detectar_desviacion(lat_p: float, lon_p: float,
                        polyline_ruta: List[Tuple[float, float]],
                        umbral_m: float = 100.0) -> Dict:
    """
    Determina si un punto está desviado del corredor geográfico de la ruta.

    Parámetros
    ----------
    lat_p, lon_p : float
        Coordenadas del punto a evaluar (posición GPS del vehículo).
    polyline_ruta : list of (lat, lon) tuples
        Polilínea que define el corredor de la ruta.
    umbral_m : float
        Distancia máxima permitida en metros (ancho del corredor).

    Retorna
    -------
    dict con claves:
        - es_desviacion (bool): True si supera el umbral.
        - distancia_m (float): distancia al corredor en metros.
        - umbral_m (float): umbral configurado.
        - margen_m (float): diferencia entre distancia y umbral (negativo = dentro).

    Característica ISO 25010: Corrección funcional, Fiabilidad.
    """
    distancia_m = min_distance_to_polyline_m(lat_p, lon_p, polyline_ruta)
    es_desviacion = distancia_m > umbral_m
    return {
        'es_desviacion': es_desviacion,
        'distancia_m': round(distancia_m, 2),
        'umbral_m': umbral_m,
        'margen_m': round(distancia_m - umbral_m, 2),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 7. Detección de pérdida de señal
# ──────────────────────────────────────────────────────────────────────────────

def detectar_perdida_senal(historial_gps: List[Dict],
                           max_gap_segundos: int = 120) -> List[Dict]:
    """
    Detecta períodos de pérdida de señal GPS analizando brechas temporales
    entre posiciones consecutivas.

    Parámetros
    ----------
    historial_gps : list of dict
        Cada elemento debe tener 'timestamp' (datetime o str ISO 8601).
    max_gap_segundos : int
        Umbral en segundos para considerar una brecha como pérdida de señal.

    Retorna
    -------
    list of dict, cada uno con:
        - inicio (datetime): timestamp del último punto antes del gap.
        - fin (datetime): timestamp del primer punto después del gap.
        - duracion_seg (int): duración del gap en segundos.
        - indice_inicio (int): índice en historial_gps.
        - indice_fin (int): índice en historial_gps.

    Característica ISO 25010: Fiabilidad (tolerancia a fallos).
    """
    gaps = []
    if len(historial_gps) < 2:
        return gaps

    def _parse_ts(val):
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            return datetime.fromisoformat(val.replace('Z', '+00:00'))
        raise TypeError(f'Tipo de timestamp no soportado: {type(val)}')

    timestamps = [_parse_ts(p['timestamp']) for p in historial_gps]

    for i in range(len(timestamps) - 1):
        diff = (timestamps[i + 1] - timestamps[i]).total_seconds()
        if diff > max_gap_segundos:
            gaps.append({
                'inicio': timestamps[i],
                'fin': timestamps[i + 1],
                'duracion_seg': int(diff),
                'indice_inicio': i,
                'indice_fin': i + 1,
            })
    return gaps


# ──────────────────────────────────────────────────────────────────────────────
# 8. Filtrado de posiciones duplicadas
# ──────────────────────────────────────────────────────────────────────────────

def filtrar_posiciones_duplicadas(posiciones: List[Dict],
                                  min_distancia_m: float = 5.0,
                                  min_tiempo_seg: int = 10) -> List[Dict]:
    """
    Elimina posiciones GPS duplicadas o casi estacionarias.

    Un punto se descarta si cumple AMBAS condiciones respecto al último
    punto conservado:
      - La distancia es menor que min_distancia_m, Y
      - El tiempo transcurrido es menor que min_tiempo_seg.

    Parámetros
    ----------
    posiciones : list of dict
        Cada elemento debe tener 'latitud' (o 'lat'), 'longitud' (o 'lon')
        y 'timestamp'.
    min_distancia_m : float
        Distancia mínima en metros para considerar un punto como nuevo.
    min_tiempo_seg : int
        Tiempo mínimo en segundos para considerar un punto como nuevo.

    Retorna
    -------
    list of dict
        Subconjunto filtrado de posiciones.

    Característica ISO 25010: Eficiencia de rendimiento, Fiabilidad.
    """
    if not posiciones:
        return []

    def _get_lat(p):
        return p.get('latitud', p.get('lat', 0.0))

    def _get_lon(p):
        return p.get('longitud', p.get('lon', 0.0))

    def _parse_ts(val):
        if isinstance(val, datetime):
            return val
        return datetime.fromisoformat(str(val).replace('Z', '+00:00'))

    resultado = [posiciones[0]]
    ultimo = posiciones[0]

    for pos in posiciones[1:]:
        dist = haversine_distance_m(
            _get_lat(ultimo), _get_lon(ultimo),
            _get_lat(pos), _get_lon(pos)
        )
        t_ultimo = _parse_ts(ultimo['timestamp'])
        t_actual = _parse_ts(pos['timestamp'])
        diff_t = abs((t_actual - t_ultimo).total_seconds())

        # Conservar si la distancia O el tiempo superan los umbrales
        if dist >= min_distancia_m or diff_t >= min_tiempo_seg:
            resultado.append(pos)
            ultimo = pos

    return resultado


# ──────────────────────────────────────────────────────────────────────────────
# 9. Distancia total recorrida
# ──────────────────────────────────────────────────────────────────────────────

def calcular_distancia_total_km(historial_gps: List[Dict]) -> float:
    """
    Calcula la distancia total recorrida en kilómetros sumando la distancia
    Haversine entre posiciones GPS consecutivas.

    Parámetros
    ----------
    historial_gps : list of dict
        Cada elemento debe tener 'latitud' y 'longitud'.

    Retorna
    -------
    float
        Distancia total en kilómetros.

    Característica ISO 25010: Precisión funcional.
    """
    if len(historial_gps) < 2:
        return 0.0

    total_m = 0.0
    for i in range(len(historial_gps) - 1):
        a = historial_gps[i]
        b = historial_gps[i + 1]
        lat_a = a.get('latitud', a.get('lat', 0.0))
        lon_a = a.get('longitud', a.get('lon', 0.0))
        lat_b = b.get('latitud', b.get('lat', 0.0))
        lon_b = b.get('longitud', b.get('lon', 0.0))
        total_m += haversine_distance_m(lat_a, lon_a, lat_b, lon_b)

    return round(total_m * KM_POR_M, 4)


# ──────────────────────────────────────────────────────────────────────────────
# 10. Métricas completas del recorrido
# ──────────────────────────────────────────────────────────────────────────────

def calcular_metricas_recorrido(historial_gps: List[Dict],
                                paradas_info: List[Dict],
                                polyline_ruta: List[Tuple[float, float]],
                                max_gap_seg: int = 120,
                                umbral_desviacion_m: float = 100.0) -> Dict:
    """
    Calcula el conjunto completo de métricas de calidad para un recorrido.

    Parámetros
    ----------
    historial_gps : list of dict
        Historial GPS del recorrido.  Cada elemento: latitud, longitud, timestamp.
    paradas_info : list of dict
        Lista de paradas con: lat_parada, lon_parada, radio_m, es_puntual (bool).
    polyline_ruta : list of (lat, lon)
        Polilínea de la ruta base.
    max_gap_seg : int
        Umbral para detección de pérdida de señal.
    umbral_desviacion_m : float
        Umbral para detección de desviación.

    Retorna
    -------
    dict con claves:
        - distancia_total_km (float)
        - pct_puntualidad (float): porcentaje de paradas puntuales.
        - total_paradas (int)
        - paradas_puntuales (int)
        - gaps_senal (list): períodos de pérdida de señal.
        - num_gaps (int)
        - duracion_total_seg (float): duración total del recorrido.
        - duracion_gaps_seg (float): segundos totales sin señal.
        - integridad_gps_pct (float): % tiempo con señal activa.
        - posiciones_duplicadas_eliminadas (int)
        - velocidad_promedio_kmh (float)

    Característica ISO 25010: Precisión funcional, Fiabilidad.
    """
    result = {
        'distancia_total_km': 0.0,
        'pct_puntualidad': 0.0,
        'total_paradas': len(paradas_info),
        'paradas_puntuales': 0,
        'gaps_senal': [],
        'num_gaps': 0,
        'duracion_total_seg': 0.0,
        'duracion_gaps_seg': 0.0,
        'integridad_gps_pct': 0.0,
        'posiciones_duplicadas_eliminadas': 0,
        'velocidad_promedio_kmh': 0.0,
    }

    # ── Puntualidad ──────────────────────────────────────────────────────────
    if paradas_info:
        puntuales = sum(1 for p in paradas_info if p.get('es_puntual', False))
        result['paradas_puntuales'] = puntuales
        result['pct_puntualidad'] = round(puntuales / len(paradas_info) * 100.0, 2)

    if not historial_gps:
        return result

    # ── Distancia total ──────────────────────────────────────────────────────
    result['distancia_total_km'] = calcular_distancia_total_km(historial_gps)

    # ── Pérdida de señal / integridad GPS ───────────────────────────────────
    gaps = detectar_perdida_senal(historial_gps, max_gap_seg)
    result['gaps_senal'] = gaps
    result['num_gaps'] = len(gaps)

    def _parse_ts(val):
        if isinstance(val, datetime):
            return val
        return datetime.fromisoformat(str(val).replace('Z', '+00:00'))

    if len(historial_gps) >= 2:
        t_inicio = _parse_ts(historial_gps[0]['timestamp'])
        t_fin = _parse_ts(historial_gps[-1]['timestamp'])
        duracion_total = (t_fin - t_inicio).total_seconds()
        result['duracion_total_seg'] = duracion_total

        duracion_gaps = sum(g['duracion_seg'] for g in gaps)
        result['duracion_gaps_seg'] = duracion_gaps

        if duracion_total > 0:
            result['integridad_gps_pct'] = round(
                (1.0 - duracion_gaps / duracion_total) * 100.0, 2
            )

    # ── Filtrado de duplicados ───────────────────────────────────────────────
    filtrado = filtrar_posiciones_duplicadas(historial_gps)
    result['posiciones_duplicadas_eliminadas'] = len(historial_gps) - len(filtrado)

    # ── Velocidad promedio ───────────────────────────────────────────────────
    if result['duracion_total_seg'] > 0:
        dur_h = result['duracion_total_seg'] / 3600.0
        result['velocidad_promedio_kmh'] = round(
            result['distancia_total_km'] / dur_h, 2
        )

    return result
