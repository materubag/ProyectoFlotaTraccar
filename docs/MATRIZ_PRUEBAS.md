# Matriz de pruebas — 30/10/2026

Resultado ejecutado: **39 aprobadas** en Python 3.13.2. Evidencia por caso y duración: [pytest-report.xml](pytest-report.xml). Comando reproducible en [REVISION_PROYECTO.md](REVISION_PROYECTO.md). Esta suite no levanta Odoo ni un servidor Traccar: las pruebas REST usan mocks y las de controlador extraen métodos reales mediante AST.

| ID / prueba | Tipo | Entrada | Esperado | Obtenido |
|---|---|---|---|---|
| T01 `test_haversine_distancia_conocida` | Caja negra | Coordenadas de dos puntos conocidos | Distancia dentro de tolerancia de la prueba | Aprobado |
| T02 `test_haversine_mismo_punto` | Límite | Mismo origen y destino | 0 metros | Aprobado |
| T03 `test_haversine_antipodas_ecuatoriales` | Límite | Antípodas ecuatoriales | Distancia cercana a media circunferencia terrestre | Aprobado |
| T04 `test_retraso_deteccion_tardanza` | Caja negra | Llegada posterior a horario y tolerancia | Retraso identificado | Aprobado |
| T05 `test_retraso_dentro_tolerancia_gracia` | Caja blanca | Diferencia dentro de ventana de gracia | Puntual | Aprobado |
| T06 `test_retraso_adelanto_excesivo` | Caja blanca | Llegada anterior al límite | Adelanto identificado | Aprobado |
| T07 `test_validar_parada_ingreso_exitoso` | Funcional | Coordenada dentro del radio | Parada cumplida | Aprobado |
| T08 `test_validar_parada_no_visitada` | Funcional | Coordenadas fuera del radio | Parada no cumplida | Aprobado |
| T09 `test_desviacion_dentro_del_corredor` | Funcional | Punto cercano a polilínea | Sin desviación | Aprobado |
| T10 `test_desviacion_fuera_del_corredor` | Funcional | Punto exterior al corredor | Desviación | Aprobado |
| T11 `test_filtro_duplicados_elimina_estacionarios` | Caja blanca | Puntos próximos en espacio y tiempo | Eliminar duplicados según umbrales | Aprobado |
| T12 `test_perdida_senal_detecta_brecha_exacta` | Caja blanca | Historial con brecha de 240 s | Brecha detectada y duración correcta | Aprobado |
| T13 `test_perdida_senal_sin_falsos_positivos` | Caja blanca | Historial continuo | Ninguna brecha | Aprobado |
| T14 `test_traccar_test_connection_mock_exito` | Contrato REST simulado | Respuesta HTTP simulada válida | Conexión aceptada | Aprobado |
| T15 `test_traccar_test_connection_falla_autenticacion` | Contrato REST simulado | Respuesta HTTP 401 simulada | Error de autenticación | Aprobado |
| T16 `test_traccar_get_positions_parsea_payload` | Contrato REST simulado | JSON de dos posiciones | Lista recuperada sin alterar campos | Aprobado |
| T17 `test_rendimiento_haversine_1000_calculos` | Rendimiento algoritmo | 1.000 distancias | Cumplir umbral de la prueba | Aprobado |
| T18 `test_rendimiento_evaluacion_desviacion_polilinea_extensa` | Rendimiento algoritmo | Polilínea extensa y varios puntos | Cumplir umbral de la prueba | Aprobado |
| T19 `test_porcentaje_puntualidad_calculado` | Métricas | Paradas con puntualidad mixta | Porcentaje calculado desde entradas | Aprobado |
| T20 `test_calculo_distancia_total_cuadrilatero` | Métricas | Cuatro lados de trazado | Distancia acumulada esperada | Aprobado |
| T21 `test_integridad_gps_con_perdida_senal` | Métricas | Historial con pérdida | Integridad inferior a 100% | Aprobado |
| T22–26 `test_webhook_requires_configured_secret` | Seguridad / regresión | Secreto ausente, token ausente, token erróneo, coincidente y configuración vacía | Solo token coincidente con configuración no vacía es aceptado | 5 aprobadas |
| T27–30 `test_gps_timestamp_normalizes_utc` | Integridad temporal | ISO con −05:00, Z, cadena inválida y vacía | Conversión a UTC / rechazo | 4 aprobadas |
| T31 `test_decimal_time_rounding_does_not_create_minute_60` | Regresión | Hora 8.9999 y llegada 09:00 | 0 minutos, sin excepción | Aprobado |
| T32 `test_zero_tolerance_boundary` | Límite | Un segundo tarde con tolerancia 0 | Retraso | Aprobado |
| T33 `test_first_arrival_is_not_replaced_by_closer_later_fix` | Regresión | Primera visita y punto posterior más próximo, orden invertido | Conservar primera visita cronológica | Aprobado |
| T34 `test_no_gps_is_not_perfect_integrity` | Regresión | Historial vacío | Integridad 0, no 100 | Aprobado |
| T35–36 `test_sync_accuracy_compares_received_data` | Integridad / regresión | Posición coincidente y latitud alterada respecto al JSON original | Coincidencia verdadera y falsa respectivamente | 2 aprobadas |
| T37–39 `test_invalid_schedule_rejected` | Validación | Hora −1, hora 24 y tolerancia negativa | ValueError | 3 aprobadas |

Comprobaciones adicionales aprobadas: sintaxis de 28 archivos Python, 12 XML, 1 JSON, 3 CSV de acceso y 2 plantillas OWL; sintaxis JavaScript de ambos paneles; configuración Compose con el túnel opcional.

Pendientes de ejecución: instalación/actualización Odoo, permisos por rol/compañía, escritura y rollback PostgreSQL, peticiones HTTP reales al webhook, carreras de inserción, transmisión móvil externa, 10 recorridos documentados, rendimiento con BD de 100/1.000/10.000 posiciones y verificación visual móvil. Los tiempos del JUnit corresponden al equipo de esta auditoría y no son tiempos de respuesta de producción.
