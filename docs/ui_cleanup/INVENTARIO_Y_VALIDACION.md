# Depuración de interfaz Flota UTA — 17/11/2026

## Inventario previo y destino

Se consultaron `ir_model_data`, `ir_ui_menu`, `ir_actions`, `ir_act_window` e `ir_act_client` antes de editar. Había 34 menús de los módulos afectados y 23 acciones. Se presentó la tabla antes/después al usuario antes de modificar archivos.

| Antes | Después |
|---|---|
| Transporte > Panel de control | Panel, primer menú superior |
| Flota > Flota | Vehículos, acceso directo a Fleet estándar |
| Transporte > Operaciones > Recorridos/Incidencias/Telemetría GPS | Registros > Recorridos/Incidencias/Posiciones GPS |
| Reportes y calidad > Métricas ISO/IEC 25010 | Registros > Métricas por recorrido; análisis en Métricas |
| Transporte > Rutas y sincronización > Rutas y Paradas | Configuración > Rutas y paradas |
| Sincronización Traccar | Pestaña Sincronización; historial desde Ver registros |
| Ajustes Fleet y Ajustes y Colores | Configuración > Ajustes, formulario único |
| Configuración > Modelos > Modelos/Fabricantes | Configuración > Catálogo de vehículos > Modelos/Fabricantes |
| Contratos, Servicios, Odómetros, Informe/Costes y Categorías | Menús archivados, acciones y datos conservados |
| Tipos de servicio, Estado, Etiquetas y Tipos de actividad | Menús auxiliares archivados |
| Reportes y calidad > Grafana > Monitoreo GPS | Menús archivados, módulo y contenedor conservados |
| Nueve pestañas independientes | Seis: Panel, Monitoreo en vivo, Recorridos, Rutas y programación, Métricas, Sincronización |
| Asignaciones | Rutas y programación > Programación |
| Línea de tiempo | Recorridos > detalle > Línea de tiempo |
| Vehículos y GPS | Monitoreo en vivo; dispositivos en Sincronización |

Los XML IDs se verificaron contra la base. Los principales son `fleet.menu_root`, `fleet.fleet_vehicle_menu`, `fleet.fleet_configuration`, `fleet.fleet_models_configuration`, `fleet.fleet_vehicle_model_menu` y `fleet.fleet_vehicle_model_brand_menu`. Los IDs propios existentes se conservan y se reasignan, sin recrear acciones.

## Acciones que quedan sin menú activo

Todas se conservan. «Sin menú» no implica que desaparezcan sus enlaces, favoritos o uso desde formularios.

| XML ID | ID en esta instalación | Acceso tras el cambio |
|---|---:|---|
| fleet.fleet_config_settings_action | 140 | Sustituida en navegación por ajustes unificados |
| fleet.fleet_costs_reporting_action | 138 | Menú archivado |
| fleet.fleet_vehicle_log_contract_action | 136 | Menú archivado |
| fleet.fleet_vehicle_log_services_action | 137 | Menú archivado |
| fleet.fleet_vehicle_model_category_action | 130 | Menú archivado |
| fleet.fleet_vehicle_odometer_action | 132 | Menú archivado |
| fleet.fleet_vehicle_service_types_action | 133 | Menú archivado |
| fleet.fleet_vehicle_state_action | 134 | Menú archivado |
| fleet.fleet_vehicle_tag_action | 135 | Menú archivado |
| fleet.mail_activity_type_action_config_fleet | 139 | Menú archivado |
| fleet_reports.action_fleet_reports_grafana | 177 | Menú archivado |
| fleet_rutas.action_fleet_incidencia_activas | 175 | Ya carecía de menú propio |
| fleet_rutas.action_fleet_traccar_sync | 171 | Ver registros en Sincronización |

## Conservación de datos

| Entidad | Antes | Después de actualizar |
|---|---:|---:|
| Vehículos | 5 | 5 |
| Rutas | 3 | 3 |
| Paradas | 12 | 12 |
| Recorridos | 65 | 65 |
| Posiciones GPS | 1497 | 1497 |
| Incidencias | 52 | 52 |
| Métricas | 60 | 60 |

No se editaron modelos Python, ACL, algoritmos ni fórmulas de cálculo. Se crearon únicamente vistas/widgets de presentación y se modificaron menús, assets y traducciones. Las 65 asignaciones existentes son simuladas; el dashboard y las listas lo identifican.

## Verificación

- Sintaxis JavaScript y verificación estática: aprobadas (30 Python, 14 XML, 1 JSON, 3 CSV de acceso, 5 plantillas OWL).
- Suite existente: **51 aprobadas**, utilizando dependencias aisladas en `tmp`.
- Actualización de módulos: correcta, con respaldo previo y Odoo detenido durante la actualización.
- Traducciones españolas de los menús estándar: actualizadas con `--i18n-overwrite`.
- Consulta SQL de menús activos sin acción ni hijos activos: cero resultados.
- Chrome temporal contra la instalación real; sin modificar recorridos, vehículos ni GPS. Resultados y capturas en esta carpeta. No se pulsó Sincronizar ahora durante la prueba para evitar escrituras operativas.

## Pendientes expresamente acordados

El usuario eligió mantener el alcance de interfaz. No existen campos de duración de parada ni de corredor configurable en el modelo actual. Por tanto, no se añadieron duración 0–60 min, salida calculada, ni corredor editable; tampoco se añadió validación de solapamientos. Las tolerancias y radios existentes siguen editándose por parada. La restricción ya existente impide asociar un mismo dispositivo a dos vehículos.

El estado del túnel no está disponible desde los modelos actuales. La pestaña Sincronización lo indica expresamente; no muestra un estado inventado.

Grafana sigue instalado. Su menú ya no forma parte de Flota; si no hay consumidores externos, se pueden retirar posteriormente su contenedor y su acceso anónimo. Esta tarea no los desactiva.

Vehículos abre primero la lista estándar de Fleet (kanban disponible como vista alternativa). Evita una entrada aparentemente vacía cuando el grupo «Ninguno» del kanban está plegado. No se modifica el estado de los vehículos.

## Resultado final del navegador

| Comprobación | Resultado |
|---|---|
| Seis pestañas | Correctas, sin excepciones JavaScript |
| Regreso por migas de pan de Odoo | Conserva Programación y detalle/Línea de tiempo |
| Mapa autenticado de recorrido | HTTP 200 |
| Vista previa de ruta | Cuatro puntos de control cargados |
| Vehículo | Dispositivo y telemetría visibles, validación de unicidad preexistente conservada |
| Ajustes | Controlador nativo `base_settings`, Guardar/Descartar y bloque Flota UTA |
| Ruta/período | Cambian las mediciones seleccionadas; sin mediciones muestra Sin muestra |
| Anchos 1280, 1440 y 390 px | Sin desbordamiento horizontal de página ni del contenedor principal |
| Tabla de métricas | Encabezados 40 px, filas 48 px en los tres anchos |
| Listas y catálogos | Vehículos, Recorridos, Incidencias, Posiciones GPS, Métricas, Modelos y Fabricantes cargan registros, sin diálogos de error |

`browser_result.json` contiene los resultados completos. Los conteos visuales de las listas corresponden a registros/grupos de la página, no sustituyen los conteos SQL. No se simuló una sesión de un usuario Fleet distinto al administrador: la asignación de grupos se verificó en SQL y no se cambiaron ACL.

El script `verificar_navegacion.py` reproduce la inspección contra esta instalación (IDs de acción registrados en el inventario). Requiere Playwright para Python, Chrome y `--session-file` apuntando a un archivo local con una sesión de pruebas autorizada. No contiene ni conserva credenciales. No pulsa Guardar ni Sincronizar ahora. La validación completa de conectividad móvil, túnel y GPS externo queda fuera de esta tarea de interfaz.

## Cambio posterior solicitado: Dashboard Grafana

El usuario solicitó recuperar Grafana en la barra lateral y revisar su presentación oscura. La navegación pasa expresamente de seis a siete entradas laterales, manteniendo los cuatro menús superiores. Dashboard Grafana reutiliza el widget existente, con tema claro, modo kiosk, controles de acento dinámico y tarjetas de cifras coloreadas. Los menús superiores de Grafana siguen archivados y su servicio se conserva en uso.

Resultados específicos: `grafana_browser_result.json`. Captura: [Dashboard Grafana claro](grafana_light.png). Esta petición sustituye la indicación previa de retirar Grafana si no se utilizaba.
