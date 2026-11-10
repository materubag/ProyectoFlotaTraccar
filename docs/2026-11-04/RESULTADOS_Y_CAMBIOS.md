# Resultado de la revisión del PDF - 4 de noviembre de 2026

Se revisaron las 15 páginas de `proyectoFinal_GC (1).pdf`, los esquemas de las páginas 12-13 y la rúbrica de las páginas 14-15, el código actual y la base `odoo_flota` del proyecto. El documento se usó como requisito académico, sin ejecutar sus instrucciones como órdenes independientes.

La situación previa está registrada en [COMPARATIVA_INICIAL.md](COMPARATIVA_INICIAL.md). Esta revisión conserva los informes anteriores; sus datos corresponden a otras fechas.

## Conclusión

Hay una plataforma instalada, pero todavía no hay una demostración GPS completa: Traccar tiene 0 dispositivos y 0 posiciones; Odoo tiene 0 posiciones y 0 métricas guardadas. Los dos recorridos existentes están identificados como simulados y no están cerrados. La API de Traccar no tiene sus credenciales configuradas en Odoo. Esos bloqueos requieren configuración y recorridos reales; no se sustituyeron por datos inventados.

Se corrigieron únicamente fallos de sincronización, cálculo y diagnóstico comprobables. No se cambió el diseño, los menús, Grafana, `.env`, los permisos de usuarios ni la estructura de la base. No se eliminaron archivos ni registros.

## Cambios realizados

| ID | Fallo inicial | Corrección | Verificación |
|---|---|---|---|
| F01 | Dos posiciones con distinta ID pero igual hora se convertían en una; se descartaba (0,0); la misma ID podía pasar dos veces con horas distintas | Deduplicación por ID Traccar, conservando puntos válidos aunque coincidan en hora o coordenadas | 3 regresiones aprobadas |
| F02 | Un `speed='bad'` fallaba durante la preparación del lote y bloqueaba los puntos siguientes | Conversión y validación dentro del tratamiento individual; savepoint ORM por inserción; se cuenta el punto inválido y continúa el resto | Regresión y prueba ORM con un punto malo y otro válido; velocidad 10 nudos =18.52 km/h |
| F03 | Una alerta por silencio final se creaba pero el método devolvía 0 | Incluirla en el total retornado, manteniendo la comprobación de duplicados | Regresión; ORM devuelve 1 la primera vez y 0 al repetir |
| F04 | En un viaje de 10 minutos con GPS solo en los minutos 4 y 5 se informaba 100% de integridad | La función recibe el inicio/fin reales y contempla los silencios de los bordes; el modelo de métricas pasa esas fechas | Ahora informa 10%; recorrido sin GPS: integridad 0 y 600 s sin señal |
| F05 | Ruta con primera parada 08:00 y segunda 08:15, asignada a las 14:00: llegada 14:23 se consideraba 368 minutos tarde | Usar el inicio programado de cada asignación como ancla y conservar el intervalo entre paradas, incluido cambio de día | Ahora registra 8 minutos, en prueba controlada y con ORM real |
| F06 | El cliente recortaba el historial recibido al superar `max_records` | Conservar toda la respuesta y usar el umbral como aviso de volumen | 11 posiciones recibidas con umbral 10: se devuelven 11 |
| F07 | Una API sin configuración terminaba como error de autenticación genérico; fallos globales podían tener errores=0 y lotes parcialmente fallidos podían marcarse completados | Mensaje explícito de configuración incompleta; contador de error no nulo y estado error cuando hay fallos | 3 casos controlados y prueba ORM del fallo global |

La corrección de F06 evita el recorte del cliente; no demuestra completitud ante límites que imponga el propio servidor. La detección de desvíos sigue utilizando segmentos entre paradas y debe contrastarse con las calles reales. La detección de llegada fuera de orden y las carreras entre importaciones simultáneas requieren pruebas específicas adicionales.

## Archivos de implementación modificados

- `addons/fleet_rutas/models/fleet_traccar_sync.py`: filtro, importación individual, conteo de señal y diagnóstico.
- `addons/fleet_rutas/models/fleet_algoritmos.py`: integridad GPS sobre la ventana real de operación, conservando compatibilidad con llamadas anteriores sin fechas.
- `addons/fleet_rutas/models/fleet_metricas.py`: pasar inicio y fin del recorrido al cálculo de integridad.
- `addons/fleet_rutas/models/fleet_posicion_gps.py`: horario de parada relativo al turno asignado.
- `addons/fleet_rutas/services/traccar_service.py`: conservar el historial completo recibido.

Soporte de pruebas: se añadió `test_revision_pdf.py`, se incorporó la ruta de servicios al `conftest.py` existente y se añadió `scripts/verificar_regresiones_odoo.py`. No se reemplazaron ni borraron las pruebas anteriores.

## Evidencia y límites

| Comprobación | Resultado |
|---|---|
| Suite anterior sin correcciones | 39 aprobadas |
| Ocho regresiones antes de corregir | 8 fallos reproducidos: [regresiones_antes.xml](regresiones_antes.xml) |
| Suite final | 51 aprobadas: [pruebas_despues.xml](pruebas_despues.xml) |
| ORM de Odoo 16 / Python del contenedor | 6 comprobaciones aprobadas; rollback de cada caso |
| Análisis estático | 29 Python, 12 XML, 1 JSON, 3 CSV de acceso y 2 plantillas OWL correctos |
| Servicios después de reiniciar solo Odoo | HTTP 200 para acceso Odoo, salud Grafana e inicio Traccar |
| Conservación de datos | Mismos conteos antes/después en vehículos, rutas, paradas, recorridos, GPS, incidencias y métricas |
| Respaldo | `backups/odoo_before_pdf_review_20261104.dump`, formato PostgreSQL custom |

Las pruebas Pytest combinan algoritmos puros, contratos REST simulados y métodos extraídos mediante AST. Las seis comprobaciones ORM se ejecutaron con la base real pero revirtieron sus escrituras; no envían ubicaciones a Traccar. Las respuestas HTTP verifican disponibilidad, no la experiencia visual, los permisos de todos los roles ni el flujo GPS de extremo a extremo. Los errores provocados deliberadamente en las pruebas aparecen en los logs de ese proceso de prueba.

Conteos preservados:

| Entidad | Antes | Después |
|---|---:|---:|
| Vehículos | 7 | 7 |
| Rutas | 3 | 3 |
| Paradas | 12 | 12 |
| Recorridos | 2 | 2 |
| Posiciones GPS | 0 | 0 |
| Incidencias | 2 | 2 |
| Métricas | 0 | 0 |

## Pendientes finales para cumplir el PDF

| Prioridad | Pendiente | Qué debe aportarse / hacerse |
|---|---|---|
| Alta | Configuración de API Traccar | En Ajustes de Flota, guardar URL interna, usuario y contraseña válidos. No usar la contraseña PostgreSQL como contraseña de la API |
| Alta | Dispositivos GPS | Registrar los dispositivos en Traccar y comprobar sus IDs reales frente a los dos vehículos con seguimiento. Los IDs de Odoo no crean automáticamente dispositivos en Traccar |
| Alta | Datos desde red externa | Configurar Traccar Client y el túnel/alternativa HTTPS, apagar Wi-Fi del teléfono y documentar recepción desde datos móviles |
| Alta | Diez recorridos | Ejecutar y documentar al menos 10, repartidos entre las 3 rutas, con cumplimiento e incumplimientos; marcar toda simulación como tal |
| Alta | Resultados de métricas | Cerrar recorridos, verificar horarios/paradas/distancias y exportar resultados junto a sus fuentes y fórmulas |
| Media | Calidad del detector | Validar eventos y registrar verdad de referencia, incluidos falsos negativos; la precisión actual de eventos validados no equivale a exactitud global |
| Media | Rendimiento completo | Medir consultas de historial, mapas y métricas con diferentes volúmenes; el cronometraje del cálculo no mide toda la respuesta de red e interfaz |
| Media | SonarQube | Ejecutar el análisis del código propio y adjuntar reporte y Quality Gate. La presencia del servicio no sustituye el reporte |
| Media | Mejora continua | Usar las regresiones antes/después como evidencia PDCA; elaborar Ishikawa; construir Pareto solo con frecuencias observadas suficientes |
| Media | Validación de interfaz y defensa | Revisar móvil y roles en la instalación activa; preparar capturas y demostración con GPS de teléfono, cumplimiento e incumplimiento |

El requisito de dashboard puede satisfacerse mediante el panel nativo de Odoo (alternativa A del PDF). Power BI no es obligatorio al elegir esa alternativa. Grafana se conserva como complemento GPS.

## Reproducir las comprobaciones

Desde la raíz `ProyectoFlotaTraccar`:

```powershell
.\.venv\Scripts\python.exe -m pytest addons/fleet_rutas/tests --import-mode=importlib -p no:cacheprovider -q
python scripts/verificar_fuentes.py
Get-Content scripts/verificar_regresiones_odoo.py -Raw -Encoding utf8 | docker exec -i flota-odoo /entrypoint.sh odoo shell -d odoo_flota --no-http --max-cron-threads=0
```

El script ORM usa registros temporales dentro de savepoints que siempre revierte. El proceso principal de Odoo se reinició para cargar las correcciones Python; no fue necesaria una actualización de módulos ni migración de tablas.
