# -*- coding: utf-8 -*-
"""
Fixtures y configuración para la suite de pruebas Pytest.
Sistema de Monitoreo de Rutas de Transporte Universitario.
"""
import pytest
from datetime import datetime, timezone, timedelta


@pytest.fixture
def fecha_base():
    """Fecha de referencia para pruebas temporales."""
    return datetime(2026, 10, 30, 8, 0, 0)


@pytest.fixture
def polyline_campus_quito():
    """
    Polilínea representativa de una ruta universitaria en Quito, Ecuador.
    Conecta Campus Central con Residencias Universitarias Norte.
    """
    return [
        (-0.210452, -78.491230),  # Parada 1: Puerta Principal
        (-0.205000, -78.490000),  # Tramo Av. Universitaria
        (-0.198320, -78.489110),  # Parada 2: Fac. Medicina
        (-0.192000, -78.485000),  # Tramo Av. América
        (-0.187640, -78.480250),  # Parada 3: Biblioteca General
        (-0.181000, -78.476000),  # Tramo Av. 10 de Agosto
        (-0.174510, -78.472180),  # Parada 4: Residencias Norte
    ]


@pytest.fixture
def historial_gps_continuo(fecha_base):
    """
    Historial de 15 posiciones GPS regulares espaciadas cada 30 segundos
    sin pérdidas de señal.
    """
    posiciones = []
    lat_base = -0.210452
    lon_base = -78.491230
    for i in range(15):
        posiciones.append({
            'latitud': lat_base + (i * 0.002),
            'longitud': lon_base + (i * 0.001),
            'timestamp': fecha_base + timedelta(seconds=i * 30),
            'velocidad_kmh': 35.0,
        })
    return posiciones


@pytest.fixture
def historial_gps_con_gap(fecha_base):
    """
    Historial GPS que incluye una pérdida de señal prolongada (gap de 240 segundos / 4 minutos).
    """
    posiciones = []
    # 5 posiciones normales
    for i in range(5):
        posiciones.append({
            'latitud': -0.210 + (i * 0.001),
            'longitud': -78.491 + (i * 0.001),
            'timestamp': fecha_base + timedelta(seconds=i * 30),
        })
    # Salto de 240 segundos (pérdida de señal de 4 min)
    ts_despues_gap = fecha_base + timedelta(seconds=(4 * 30) + 240)
    for i in range(5):
        posiciones.append({
            'latitud': -0.205 + (i * 0.001),
            'longitud': -78.486 + (i * 0.001),
            'timestamp': ts_despues_gap + timedelta(seconds=i * 30),
        })
    return posiciones


@pytest.fixture
def mock_traccar_positions_payload():
    """Payload JSON típico devuelto por el endpoint GET /api/positions de Traccar."""
    return [
        {
            "id": 1001,
            "deviceId": 1,
            "serverTime": "2026-10-30T08:00:15.000Z",
            "deviceTime": "2026-10-30T08:00:12.000Z",
            "fixTime": "2026-10-30T08:00:10.000Z",
            "latitude": -0.210452,
            "longitude": -78.491230,
            "altitude": 2815.4,
            "speed": 18.5,  # nudos
            "course": 45.0,
            "accuracy": 4.2,
            "attributes": {"batteryLevel": 98.0, "ignition": True}
        },
        {
            "id": 1002,
            "deviceId": 1,
            "serverTime": "2026-10-30T08:00:45.000Z",
            "deviceTime": "2026-10-30T08:00:42.000Z",
            "fixTime": "2026-10-30T08:00:40.000Z",
            "latitude": -0.208400,
            "longitude": -78.490100,
            "altitude": 2818.0,
            "speed": 21.0,  # nudos
            "course": 42.0,
            "accuracy": 3.8,
            "attributes": {"batteryLevel": 98.0, "ignition": True}
        }
    ]

