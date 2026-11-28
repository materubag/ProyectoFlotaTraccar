# Resultados de la línea base

Generado por `scripts/linea_base/resumen.py`. Todos los escenarios y volúmenes son **simulados**.

## 1. Detección de incidencias

| ID | Escenario | Esperado | Obtenido | Antes del cierre | VP | FP | FN |
|---|---|---|---|---|--:|--:|--:|
| E01 | Puntual sobre vía recta | — | — | — | 0 | 0 | 0 |
| E02 | Puntual sobre vía real curva (250 m de la recta) | — | desviacion×1 | desviacion×1 | 0 | 1 | 0 |
| E03 | Llegada 8 min tarde a la parada 3 | retraso×1 | retraso×1 | retraso×1 | 1 | 0 | 0 |
| E04 | Llegada 4 min tarde (dentro de tolerancia) | — | — | — | 0 | 0 | 0 |
| E05 | Parada 3 omitida (pasa a 80 m) | parada_omitida×1 | incompleto×1, parada_omitida×1 | — | 1 | 1 | 0 |
| E06 | Un desvío real de 300 m | desviacion×1 | desviacion×1 | desviacion×1 | 1 | 0 | 0 |
| E07 | Dos desvíos reales separados | desviacion×2 | desviacion×1 | desviacion×1 | 1 | 0 | 1 |
| E08 | Un único punto GPS erróneo a 150 m | — | desviacion×1 | desviacion×1 | 0 | 1 | 0 |
| E09 | Pérdida de señal de 240 s | senal_perdida×1 | senal_perdida×1 | senal_perdida×1 | 1 | 0 | 0 |
| E10 | Recorrido termina en la parada 2 | incompleto×1, parada_omitida×2 | incompleto×1, parada_omitida×2 | — | 3 | 0 | 0 |
| E11 | Detenido en curso, 9 min sin llegar a la parada 2 | retraso×1 | — | — | 0 | 0 | 1 |

| Tipo | VP | FP | FN | Precisión | Exhaustividad |
|---|--:|--:|--:|--:|--:|
| desviacion | 2 | 2 | 1 | 50.0 % | 66.7 % |
| incompleto | 1 | 1 | 0 | 50.0 % | 100.0 % |
| parada_omitida | 3 | 0 | 0 | 100.0 % | 100.0 % |
| retraso | 1 | 0 | 1 | 100.0 % | 50.0 % |
| senal_perdida | 1 | 0 | 0 | 100.0 % | 100.0 % |
| **Total** | 8 | 3 | 2 | **72.7 %** | **80.0 %** |

- Escenarios con resultado exacto: 6 de 11 (54.5 %).
- Eventos esperados ya registrados con el recorrido en curso: 4 de 10 (40.0 %).

### Métricas calculadas por el sistema en cada escenario cerrado

| ID | Cumplimiento | Puntualidad | Paradas | Desviación | Integridad GPS |
|---|--:|--:|--:|--:|--:|
| E01 | 100 | 100 | 100 | 0.0 | 100.0 |
| E02 | 0 | 100 | 100 | 24.6 | 100.0 |
| E03 | 100 | 75 | 100 | 0.0 | 100.0 |
| E04 | 100 | 100 | 100 | 0.0 | 100.0 |
| E05 | 0 | 75 | 75 | 0.0 | 100.0 |
| E06 | 0 | 100 | 100 | 18.0 | 100.0 |
| E07 | 0 | 100 | 100 | 36.1 | 100.0 |
| E08 | 0 | 100 | 100 | 1.6 | 100.0 |
| E09 | 100 | 100 | 100 | 0.0 | 73.3 |
| E10 | 0 | 50 | 50 | 0.0 | 100.0 |

## 2. Defectos reproducidos

| Comprobación | Resultado |
|---|---|
| H07_ruta_de_recorrido_en_curso_modificable | `True` |
| H08_editar_ruta_con_historial_falla | `ForeignKeyViolation` |
| H09_bus_sendone_existe | `False` |
| H06_secreto_webhook_configurado | `False` |
| Webhook sin token (copia con módulos actualizados) | HTTP 401 |

## 3. Rendimiento (ms)

Odoo temporal en el mismo equipo; no incluye red externa ni dibujo en el navegador.

| Operación | Posiciones | n | p50 | p95 |
|---|--:|--:|--:|--:|
| Consultas del dashboard | todas | 20 | 55 | 59 |
| Calcular métricas (servidor) | 100 | 10 | 12 | 17 |
| Ingerir 1 posición (servidor) | 100 | 20 | 8 | 10 |
| Página de mapa | 100 | 20 | 15 | 17 |
| Datos de repetición | 100 | 20 | 15 | 16 |
| Historial completo (RPC) | 100 | 20 | 11 | 11 |
| Calcular métricas (servidor) | 1000 | 10 | 49 | 83 |
| Ingerir 1 posición (servidor) | 1000 | 20 | 21 | 23 |
| Página de mapa | 1000 | 20 | 32 | 42 |
| Datos de repetición | 1000 | 20 | 40 | 57 |
| Historial completo (RPC) | 1000 | 20 | 30 | 31 |
| Calcular métricas (servidor) | 10000 | 10 | 464 | 556 |
| Ingerir 1 posición (servidor) | 10000 | 20 | 179 | 186 |
| Página de mapa | 10000 | 20 | 253 | 281 |
| Datos de repetición | 10000 | 20 | 267 | 275 |
| Historial completo (RPC) | 10000 | 20 | 269 | 320 |

## Completitud Traccar → Odoo

4 de 24 posiciones almacenadas en Traccar están en Odoo (16.7 %).

## 4. Datos en la base del proyecto (solo lectura)

```json
{
 "modulos": {
  "fleet_reports": "installed 16.0.1.0.0",
  "fleet_rutas": "installed 16.0.1.0.0",
  "fleet_traccar": "installed 16.0.1.0.0",
  "portal": "uninstalled "
 },
 "vehiculos": 8,
 "rutas": 3,
 "paradas": 12,
 "recorridos": [
  {
   "estado": "completado",
   "simulado": true,
   "n": 3
  },
  {
   "estado": "con_incidencias",
   "simulado": true,
   "n": 9
  },
  {
   "estado": "en_curso",
   "simulado": true,
   "n": 1
  },
  {
   "estado": "programado",
   "simulado": true,
   "n": 2
  }
 ],
 "posiciones": [
  {
   "fuente": "simulado",
   "n": 736,
   "con_snapshot": 0,
   "con_recorrido": 736
  },
  {
   "fuente": "traccar",
   "n": 4,
   "con_snapshot": 4,
   "con_recorrido": 0
  }
 ],
 "ids_traccar_duplicados": 0,
 "incidencias": {
  "incompleto": 3,
  "parada_omitida": 3,
  "desviacion": 6,
  "senal_perdida": 4,
  "retraso": 18
 },
 "incidencias_validadas": 0,
 "metricas": {
  "n": 12,
  "n_reales": 0,
  "cumplimiento": 50.0,
  "puntualidad": 68.75,
  "retraso_min": 1.91,
  "paradas": 93.75,
  "desviacion": 7.53,
  "dif_distancia_km": 0.35,
  "duracion_min": 30.0,
  "incidencias_h": 5.5,
  "integridad": 95.83,
  "con_exactitud": 0,
  "con_deteccion": 0
 },
 "sync": {
  "completado": 427,
  "error": 11
 }
}
```

## 5. Distancia entre paradas

| Ruta | Estimada guardada (km) | Haversine (km) | Geodésica WGS84 (km) | Haversine − geodésica |
|---|--:|--:|--:|--:|
| [DEMO] Ficoa - UTA | 2.753 | 2.753 | 2.743 | +0.37 % |
| [DEMO] Centro - UTA | 2.582 | 2.582 | 2.570 | +0.49 % |
| [DEMO] Huachi - UTA | 2.388 | 2.388 | 2.378 | +0.41 % |

Falta la referencia vial (distancia real por calles): medirla en campo o con un trazado.

## 6. Código

| Indicador | Valor |
|---|---|
| Pruebas aprobadas / fallidas / omitidas | 64 / 0 / 0 |
| Archivos de prueba que no cargaron | addons.fleet_rutas.tests.test_revision_pdf |
| Líneas Python (SLOC, sin pruebas) | 4618 |
| Líneas no vacías JS / CSS / XML | 2074 / 1711 / 1670 |
| Cobertura de líneas Python (aproximada, trazador propio) | 8.2 % (304 de 3713) |
| Funciones / complejidad ciclomática media | 132 / 6.92 |
| Funciones con complejidad > 15 | 12 |

| Función compleja | Archivo | CC |
|---|---|--:|
| FleetMetricasRecorrido.get_dashboard_kpis | `addons/fleet_rutas/models/fleet_metricas.py:287` | 105 |
| FleetMapa.importar_ruta | `addons/fleet_rutas/controllers/mapa.py:81` | 61 |
| FleetMetricasRecorrido.calcular_para_recorrido | `addons/fleet_rutas/models/fleet_metricas.py:157` | 33 |
| FleetMapa.crear_ruta | `addons/fleet_rutas/controllers/mapa.py:353` | 26 |
| FleetTraccarSync.sincronizar_historial | `addons/fleet_rutas/models/fleet_traccar_sync.py:428` | 22 |
| FleetTraccarSync.sincronizar_dispositivos | `addons/fleet_rutas/models/fleet_traccar_sync.py:676` | 21 |
| calcular_metricas_recorrido | `addons/fleet_rutas/models/fleet_algoritmos.py:467` | 19 |
| FleetMobileDelivery._send_pending | `addons/fleet_rutas/models/fleet_mobile.py:110` | 19 |
| FleetMapa.exportar_ruta | `addons/fleet_rutas/controllers/mapa.py:17` | 18 |
| TraccarWebhookController._process_single_position | `addons/fleet_rutas/controllers/traccar_webhook.py:215` | 18 |
| FleetTraccarSync._procesar_posicion_ultima | `addons/fleet_rutas/models/fleet_traccar_sync.py:344` | 18 |
| FleetTraccarSync.sincronizar_ultima_posicion | `addons/fleet_rutas/models/fleet_traccar_sync.py:202` | 17 |
