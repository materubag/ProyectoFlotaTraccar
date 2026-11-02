# -*- coding: utf-8 -*-
"""
Suite de Pruebas Automatizadas (Pytest) — Sistema de Monitoreo de Rutas Universitarias
Norma de Calidad: ISO/IEC 25010 (SQuaRE)

Cobertura:
  1. Pruebas de Caja Negra (Funcionalidad, precisión geométrica, tolerancias).
  2. Pruebas de Caja Blanca (Ramas de decisión en filtros y umbrales internos).
  3. Pruebas de Integración (Cliente REST Traccar y manejo de errores de protocolo).
  4. Pruebas de Rendimiento / Carga (Límites de tiempo de respuesta para algoritmos espaciales).
  5. Pruebas de Métricas Agregadas (Cálculo de indicadores de calidad del servicio).
"""
import math
import os
import sys
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Asegurar importación del módulo de algoritmos independiente de la instalación de Odoo
MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models'))
SERVICES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'services'))
if MODELS_DIR not in sys.path:
    sys.path.insert(0, MODELS_DIR)
if SERVICES_DIR not in sys.path:
    sys.path.insert(0, SERVICES_DIR)

from fleet_algoritmos import (
    haversine_distance_m,
    point_to_segment_distance_m,
    min_distance_to_polyline_m,
    calcular_retraso_min,
    validar_parada,
    detectar_desviacion,
    detectar_perdida_senal,
    filtrar_posiciones_duplicadas,
    calcular_distancia_total_km,
    calcular_metricas_recorrido,
)
from traccar_service import TraccarService, TraccarAPIError, TraccarAuthError


# ═════════════════════════════════════════════════════════════════════════════
# 1. PRUEBAS DE CAJA NEGRA (Funcionalidad y Precisión Geométrica)
# ═════════════════════════════════════════════════════════════════════════════

class TestCajaNegraGeometria:
    """Verificación funcional de cálculos espaciales basados en la fórmula de Haversine."""

    def test_haversine_distancia_conocida(self):
        """
        ISO 25010: Precisión funcional.
        Compara distancia entre Aeropuerto de Quito (-0.1292, -78.3583) y
        Plaza Grande Quito (-0.2201, -78.5124).
        Distancia geodésica real conocida ≈ 20.1 - 20.8 km.
        """
        dist_m = haversine_distance_m(-0.1292, -78.3583, -0.2201, -78.5124)
        dist_km = dist_m / 1000.0
        assert 19.5 <= dist_km <= 20.5, f"Distancia fuera de rango esperado: {dist_km:.2f} km"

    def test_haversine_mismo_punto(self):
        """La distancia entre coordenadas idénticas debe ser estrictamente 0 metros."""
        dist_m = haversine_distance_m(-0.210452, -78.491230, -0.210452, -78.491230)
        assert dist_m == 0.0

    def test_haversine_antipodas_ecuatoriales(self):
        """Distancia entre puntos ecuatoriales opuestos (0,0) y (0,180) debe ser medio perímetro terrestre ≈ 20,015 km."""
        dist_m = haversine_distance_m(0.0, 0.0, 0.0, 180.0)
        dist_km = dist_m / 1000.0
        assert 19900 <= dist_km <= 20150


class TestCajaNegraHorariosYTolerancia:
    """Verificación funcional del motor de detección de puntualidad y retrasos."""

    def test_retraso_deteccion_tardanza(self, fecha_base):
        """Llegada 12 minutos después de lo previsto con tolerancia de 5 min -> Clasificado como retraso."""
        hora_programada_decimal = 8.0  # 08:00
        llegada_real = fecha_base.replace(hour=8, minute=12, second=0)
        res = calcular_retraso_min(hora_programada_decimal, fecha_base, llegada_real, tolerancia_min=5)

        assert res['es_retraso'] is True
        assert res['es_puntual'] is False
        assert res['es_adelanto'] is False
        assert pytest.approx(res['retraso_min'], 0.1) == 12.0

    def test_retraso_dentro_tolerancia_gracia(self, fecha_base):
        """Llegada 4 minutos después de la hora programada (dentro de la tolerancia de 5 min) -> Puntual."""
        hora_programada_decimal = 8.5  # 08:30
        fecha_ref = fecha_base.replace(hour=8, minute=30)
        llegada_real = fecha_ref + timedelta(minutes=4)
        res = calcular_retraso_min(hora_programada_decimal, fecha_base, llegada_real, tolerancia_min=5)

        assert res['es_puntual'] is True
        assert res['es_retraso'] is False
        assert res['es_adelanto'] is False

    def test_retraso_adelanto_excesivo(self, fecha_base):
        """Llegada 10 minutos antes de la hora programada -> Clasificado como adelanto."""
        hora_programada_decimal = 9.0  # 09:00
        fecha_ref = fecha_base.replace(hour=9, minute=0)
        llegada_real = fecha_ref - timedelta(minutes=10)
        res = calcular_retraso_min(hora_programada_decimal, fecha_base, llegada_real, tolerancia_min=5)

        assert res['es_adelanto'] is True
        assert res['es_puntual'] is False
        assert res['es_retraso'] is False


class TestCajaNegraValidacionParadasYDesvios:
    """Verificación funcional de proximidad geográfica a paradas y corredores viales."""

    def test_validar_parada_ingreso_exitoso(self, fecha_base):
        """El vehículo pasa a 25 metros de la parada cuyo radio de proximidad es 50 metros."""
        lat_parada, lon_parada = -0.210452, -78.491230
        historial = [
            {'latitud': -0.215000, 'longitud': -78.495000, 'timestamp': fecha_base},
            {'latitud': -0.210460, 'longitud': -78.491000, 'timestamp': fecha_base + timedelta(seconds=30)},
        ]
        res = validar_parada(lat_parada, lon_parada, radio_m=50.0, historial_gps=historial)
        assert res['cumplida'] is True
        assert res['distancia_minima_m'] <= 50.0

    def test_validar_parada_no_visitada(self, fecha_base):
        """El vehículo pasa a más de 150 metros de la parada -> Parada no cumplida (omitida)."""
        lat_parada, lon_parada = -0.210452, -78.491230
        historial = [
            {'latitud': -0.215000, 'longitud': -78.495000, 'timestamp': fecha_base},
            {'latitud': -0.213000, 'longitud': -78.494000, 'timestamp': fecha_base + timedelta(seconds=30)},
        ]
        res = validar_parada(lat_parada, lon_parada, radio_m=50.0, historial_gps=historial)
        assert res['cumplida'] is False
        assert res['distancia_minima_m'] > 50.0

    def test_desviacion_dentro_del_corredor(self, polyline_campus_quito):
        """Punto ubicado sobre el trazado base -> No es desviación (distancia < umbral)."""
        lat_p, lon_p = -0.198320, -78.489110  # Coincide con nodo de la ruta
        res = detectar_desviacion(lat_p, lon_p, polyline_campus_quito, umbral_m=100.0)
        assert res['es_desviacion'] is False
        assert res['distancia_m'] <= 10.0

    def test_desviacion_fuera_del_corredor(self, polyline_campus_quito):
        """Punto situado a más de 300 metros del corredor -> Detecta desviación de ruta."""
        lat_p, lon_p = -0.198320, -78.482000  # Desviado hacia el este
        res = detectar_desviacion(lat_p, lon_p, polyline_campus_quito, umbral_m=100.0)
        assert res['es_desviacion'] is True
        assert res['distancia_m'] > 100.0


# ═════════════════════════════════════════════════════════════════════════════
# 2. PRUEBAS DE CAJA BLANCA (Estructura Interna y Flujos de Control)
# ═════════════════════════════════════════════════════════════════════════════

class TestCajaBlancaAlgoritmos:
    """Evaluación de ramas de ejecución, umbrales y filtrado de datos espaciales."""

    def test_filtro_duplicados_elimina_estacionarios(self, fecha_base):
        """
        Puntos generados con variación menor a 5 metros y menor a 10 segundos
        deben filtrarse para evitar sobrecarga en la base de datos.
        """
        posiciones = [
            {'latitud': -0.210452, 'longitud': -78.491230, 'timestamp': fecha_base},
            # Idéntico punto 3 segundos después
            {'latitud': -0.210452, 'longitud': -78.491230, 'timestamp': fecha_base + timedelta(seconds=3)},
            # Punto a solo 1 metro de distancia 5 segundos después
            {'latitud': -0.210453, 'longitud': -78.491230, 'timestamp': fecha_base + timedelta(seconds=5)},
            # Punto a 80 metros de distancia 20 segundos después (debe conservarse)
            {'latitud': -0.211200, 'longitud': -78.491230, 'timestamp': fecha_base + timedelta(seconds=20)},
        ]
        filtradas = filtrar_posiciones_duplicadas(posiciones, min_distancia_m=5.0, min_tiempo_seg=10)
        assert len(filtradas) == 2
        assert filtradas[0]['timestamp'] == fecha_base
        assert filtradas[1]['timestamp'] == fecha_base + timedelta(seconds=20)

    def test_perdida_senal_detecta_brecha_exacta(self, historial_gps_con_gap):
        """Identifica de forma unívoca el intervalo de pérdida de señal superior a 120 segundos."""
        gaps = detectar_perdida_senal(historial_gps_con_gap, max_gap_segundos=120)
        assert len(gaps) == 1
        assert gaps[0]['duracion_seg'] == 240

    def test_perdida_senal_sin_falsos_positivos(self, historial_gps_continuo):
        """En un historial continuo con paquetes cada 30 segundos no deben existir pérdidas de señal."""
        gaps = detectar_perdida_senal(historial_gps_continuo, max_gap_segundos=120)
        assert len(gaps) == 0


# ═════════════════════════════════════════════════════════════════════════════
# 3. PRUEBAS DE INTEGRACIÓN (Cliente API Traccar -> Odoo)
# ═════════════════════════════════════════════════════════════════════════════

class TestIntegracionTraccarAPI:
    """Verificación de conectividad, mapeo de respuestas y tolerancia a fallos."""

    def test_traccar_test_connection_mock_exito(self):
        """Simula respuesta 200 OK del endpoint /api/server de Traccar."""
        service = TraccarService('http://traccar:8082', 'admin', 'pass123')
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'version': '6.16.0'}

        with patch.object(service.session, 'get', return_value=mock_response):
            ok, msg = service.test_connection()
            assert ok is True
            assert '6.16.0' in msg

    def test_traccar_test_connection_falla_autenticacion(self):
        """Simula respuesta 401 Unauthorized ante credenciales erróneas."""
        service = TraccarService('http://traccar:8082', 'admin', 'bad_pass')
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.url = 'http://traccar:8082/api/server'

        with patch.object(service.session, 'get', return_value=mock_response):
            ok, msg = service.test_connection()
            assert ok is False
            assert 'Autenticación fallida' in msg

    def test_traccar_get_positions_parsea_payload(self, mock_traccar_positions_payload):
        """Valida que el servicio consume y parsea adecuadamente las posiciones del servidor GPS."""
        service = TraccarService('http://traccar:8082', 'admin', 'pass123')
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_traccar_positions_payload

        with patch.object(service.session, 'get', return_value=mock_response):
            positions = service.get_last_positions(device_ids=[1])
            assert len(positions) == 2
            assert positions[0]['latitude'] == -0.210452
            assert positions[1]['speed'] == 21.0


# ═════════════════════════════════════════════════════════════════════════════
# 4. PRUEBAS DE CARGA Y RENDIMIENTO (Eficiencia ISO/IEC 25010)
# ═════════════════════════════════════════════════════════════════════════════

class TestRendimientoYCarga:
    """Verificación de tiempos de respuesta bajo alta volumetría de telemetría."""

    def test_rendimiento_haversine_1000_calculos(self):
        """1000 ejecuciones del cálculo de Haversine deben completarse en menos de 0.15 segundos."""
        inicio = time.perf_counter()
        for i in range(1000):
            haversine_distance_m(-0.210452 + (i * 0.0001), -78.491230, -0.174510, -78.472180)
        duracion = time.perf_counter() - inicio
        assert duracion < 0.15, f"Haversine excedió el umbral temporal: {duracion:.4f}s"

    def test_rendimiento_evaluacion_desviacion_polilinea_extensa(self):
        """Evaluación de 200 puntos GPS contra una ruta extensa de 500 segmentos en menos de 0.50 segundos."""
        # Generar polilínea sintética de 500 nodos
        polyline = [(-0.2 + (i * 0.001), -78.5 + (i * 0.0005)) for i in range(500)]
        inicio = time.perf_counter()
        for i in range(200):
            detectar_desviacion(-0.21 + (i * 0.0008), -78.49, polyline, umbral_m=100.0)
        duracion = time.perf_counter() - inicio
        assert duracion < 0.50, f"Evaluación de polilínea extensa tardó {duracion:.4f}s (máximo permitido 0.50s)"


# ═════════════════════════════════════════════════════════════════════════════
# 5. PRUEBAS DE MÉTRICAS AGREGADAS (Evaluación de Calidad ISO 25010)
# ═════════════════════════════════════════════════════════════════════════════

class TestMetricasAgregadas:
    """Evaluación de métricas compuestas de operación y calidad del servicio."""

    def test_porcentaje_puntualidad_calculado(self):
        """De 4 paradas, 3 puntuales y 1 con retraso -> 75% puntualidad."""
        paradas_info = [
            {'cumplida': True, 'es_puntual': True},
            {'cumplida': True, 'es_puntual': True},
            {'cumplida': True, 'es_puntual': True},
            {'cumplida': True, 'es_puntual': False},
        ]
        res = calcular_metricas_recorrido(
            historial_gps=[],
            paradas_info=paradas_info,
            polyline_ruta=[],
        )
        assert res['pct_puntualidad'] == 75.0
        assert res['paradas_puntuales'] == 3
        assert res['total_paradas'] == 4

    def test_calculo_distancia_total_cuadrilatero(self):
        """
        Calcula la distancia de un trayecto cuadrado cerrado de aproximadamente
        1 km por lado (perímetro ≈ 4 km).
        """
        # Cuadrilátero de aprox 0.009 grados lat (~1 km)
        trayecto = [
            {'latitud': 0.000, 'longitud': 0.000},
            {'latitud': 0.009, 'longitud': 0.000},
            {'latitud': 0.009, 'longitud': 0.009},
            {'latitud': 0.000, 'longitud': 0.009},
            {'latitud': 0.000, 'longitud': 0.000},
        ]
        dist_km = calcular_distancia_total_km(trayecto)
        assert 3.8 <= dist_km <= 4.2

    def test_integridad_gps_con_perdida_senal(self, historial_gps_con_gap):
        """La integridad de telemetría debe reflejar la proporción de tiempo sin brechas."""
        res = calcular_metricas_recorrido(
            historial_gps=historial_gps_con_gap,
            paradas_info=[],
            polyline_ruta=[],
            max_gap_seg=120,
        )
        assert res['num_gaps'] == 1
        assert res['duracion_gaps_seg'] == 240
        assert res['integridad_gps_pct'] < 100.0
