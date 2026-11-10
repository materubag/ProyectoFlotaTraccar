# Comparativa inicial contra el PDF - 4 de noviembre de 2026

Estado registrado **antes de modificar el código en esta revisión**. Fuente: `proyectoFinal_GC (1).pdf`, 15 páginas, incluidas lámina gráfica (p. 12) y rúbrica (pp. 14-15). El documento es la especificación académica; no acredita que se hayan realizado sus actividades ni autoriza publicaciones o cambios de credenciales.

Git estaba limpio. Comprobaciones iniciales: 39 pruebas Pytest aprobadas; análisis estático correcto en 28 Python, 12 XML, 1 JSON, 3 CSV de permisos y 2 plantillas OWL.

## Requisitos y evidencias

| Requisito del PDF | Evidencia inicial comprobada | Evaluación inicial / qué falta |
|---|---|---|
| Actividad 1, requisitos y aceptación (pp. 2-3) | Existen `docs/REVISION_PROYECTO.md` y matriz de pruebas | Parcial: actualizar las conclusiones con el estado real y los resultados de esta revisión |
| Actividad 2, infraestructura (p. 3) | Contenedores Odoo, PostgreSQL, Traccar y Grafana activos; los 4 módulos Fleet están instalados en `odoo_flota` | Base funcional; la instalación ya no está pendiente como se indicó en la revisión anterior |
| Actividad 2, GPS mediante red externa (p. 3) | Hay Compose opcional para túnel; no se observó contenedor del túnel entre los servicios activos | Pendiente de evidencia: teléfono con Traccar Client, datos móviles y recepción HTTPS |
| Actividad 3, integración (p. 4) | 0 dispositivos y 0 posiciones en Traccar; 0 posiciones en Odoo; 44 logs de sincronización con estado error en la consulta inicial; últimos errores de autenticación | Bloqueo de configuración/datos: no están guardados los parámetros `fleet_traccar.server_url`, `.user` ni `.password`. Odoo usa URL predeterminada y credenciales vacías |
| Actividad 4, mínimos (pp. 4-5) | 7 vehículos, 3 rutas, 12 paradas (4 en cada ruta); 2 vehículos con seguimiento e ID GPS | Cumple cantidades de administración; falta registrar dispositivos reales en Traccar y verificar que sus IDs coincidan |
| Actividad 4, diferentes horarios por vehículo (p. 4) | Asignación por fecha y hora disponible | Riesgo de código: el cálculo de parada usa la hora absoluta de la ruta y no desplaza los horarios cuando la misma ruta se asigna a otro turno |
| Actividad 5, historial y 10 recorridos (p. 5) | 2 recorridos, ambos simulados: 1 programado y 1 en curso; 0 cerrados | No cumple la evidencia mínima. No se crearán recorridos ficticios para aparentar cumplimiento |
| Actividad 6, detección (p. 6) | Algoritmos de proximidad, retraso, desvío y señal presentes; 2 incidencias; no hay GPS con que contrastarlas | Parcial: comprobar falsos retrasos por turno, integridad en bordes del recorrido y conteo de alertas de silencio final |
| Actividad 7, transporte (pp. 6-7) | Fórmulas y vistas disponibles; 0 métricas persistidas | No hay resultados operativos verificables. Hace falta registrar/cerrar recorridos y contrastar métricas con GPS |
| Actividad 7, calidad del software (p. 7) | Snapshots de origen, tiempo del cálculo y validación manual de eventos implementados | Tiempo del cálculo no equivale a respuesta completa del sistema; la precisión de eventos validados no incluye falsos negativos; integridad solo observa primera a última posición |
| Actividad 8, dashboard (pp. 7-8) | Panel nativo y Grafana integrados en Fleet; mapa de recorridos existente | No puede demostrarse actualización con GPS real sin dispositivos/datos. No se modificará el diseño ni Grafana en esta revisión |
| Actividad 9, pruebas (pp. 8-9) | 39 pruebas aprobadas; matriz documentada | Agregar regresiones de los fallos encontrados y verificación ORM sin conservar datos de prueba; pendiente red móvil y rendimiento de consultas con diferentes volúmenes |
| Actividad 9, SonarQube e ISO/IEC 25010 (p. 8) | Configuración de análisis y servicio SonarQube disponible | Un servidor activo no demuestra análisis: no hay reporte verificable adjunto al repositorio. Falta evidencia del Quality Gate y su interpretación |
| Actividad 10, mejora continua (p. 9) | Informe anterior distingue cifras ilustrativas de evidencia | Agregar fallos reproducibles y resultados antes/después; Pareto requiere frecuencias observadas |
| Entregables y defensa (pp. 10-11) | Código, documentación y pruebas disponibles | Faltan recepción real, 10 recorridos documentados, casos de cumplimiento/incumplimiento, métricas con resultados y defensa |

## Fallos de código que se van a contrastar con regresiones

| ID | Comportamiento inicial | Consecuencia |
|---|---|---|
| F01 | El filtro histórico fusiona puntos con distinta ID si tienen el mismo timestamp y descarta coordenadas (0,0) | Pérdida de posiciones válidas e imposibilidad de verificar la sincronización completa |
| F02 | Conversiones numéricas de todo el lote se ejecutan antes de los savepoints de inserción | Un valor malformado puede impedir importar el resto de posiciones válidas |
| F03 | `verificar_perdida_senal` crea una incidencia por silencio final pero devuelve 0 cuando hay menos de dos puntos | El monitoreo informa que no detectó eventos aunque sí los creó |
| F04 | La integridad GPS se calcula únicamente entre el primer y último punto | Puede informar 100% aunque falte GPS al inicio o al final del recorrido |
| F05 | La hora de parada se reconstruye usando el horario absoluto de la ruta | Una ruta reasignada a otro turno puede registrar horas de retraso falsas |
| F06 | El cliente recorta silenciosamente a 10.000 posiciones tras recibir el historial | Recorridos largos pierden información y se calculan métricas sobre un subconjunto |
| F07 | Los errores globales de API pueden producir registros_error=0; la configuración vacía termina como autenticación fallida | Diagnóstico y notificación de éxito poco fiables |

Estas conclusiones no son una certificación de ausencia de otros defectos. Se preservan los informes anteriores como historial; los cambios y los resultados finales de esta revisión se documentarán por separado.
