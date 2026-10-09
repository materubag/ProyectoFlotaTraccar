# Módulo Odoo 16: fleet_traccar

## Estado del Módulo
* **Versión**: 16.0.1.0.0
* **Estado actual**: Estructura base preparada, modelos de datos (`fleet.vehicle`, `res.config.settings`) y vistas XML implementadas.
* **Dependencias**: `base`, `fleet`.

## Funcionalidades Preparadas
1. **Extensión de `fleet.vehicle`**:
   - `traccar_device_id`: ID numérico del dispositivo en Traccar.
   - `traccar_unique_id`: Identificador único (ej. IMEI).
   - `traccar_tracking_enabled`: Switch de habilitación de rastreo.
   - Restricción de unicidad: Validación de que un ID de dispositivo no se asocie a dos vehículos distintos.
   - Campos de telemetría: última latitud, longitud, velocidad y fecha de actualización.
2. **Configuración de Conexión**:
   - Ajustes en Odoo para definir la URL del servidor Traccar (`http://traccar:8082`) y credenciales de API sin exponerlas en frontend público.

## Próximos Pasos (Fase de Integración API)
- Servicio Python de cliente REST para comunicación con los endpoints de Traccar 6.16 (`/api/session`, `/api/devices`, `/api/positions`).
- Tarea programada (cron) para sincronización periódica de telemetría.
- Vista de mapa basada en Leaflet para visualización en tiempo real.
