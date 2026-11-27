# Aplicación móvil Mi Ruta

Implementada en `fleet_rutas` para Odoo 16. No requiere otro servicio web.

## Acceso y roles

- **Usuario de la aplicación:** usuario de tipo Portal, con el permiso `Acceso a Flota / Usuario de la aplicación`. Entra en `/flota/app`. No puede abrir el panel `/web` ni los mapas, importadores y editores administrativos anteriores.
- **Administrador de Flota:** usuario interno con `Acceso a Flota / Administrador de Flota`. Entra en `/web`. Gestiona rutas, vehículos, recorridos e incidencias. No puede consultar la PWA como pasajero.
- Los administradores de Ajustes reciben automáticamente el rol Administrador de Flota al actualizar el módulo. Solo estos administradores pueden crear usuarios y configurar claves push.
- Las cuentas existentes no se convierten automáticamente a Portal. Para una cuenta de pasajero existente, quitar permisos internos y elegir Portal antes de asignar el rol de la aplicación. No asignar ambos roles a una cuenta.
- En **Flota / Configuración / Usuarios de la aplicación**, crear las cuentas de pasajeros. La acción prepara los grupos Portal y Usuario de la aplicación. Configurar las credenciales mediante los mecanismos normales de Odoo.
- En cada ruta, pestaña **Usuarios de la aplicación**, asignar quién puede consultarla. Sin asignaciones, el usuario ve un estado vacío. La aplicación no permite autoasignarse rutas.

Los pasajeros no tienen ACL sobre los modelos operativos. Las API devuelven campos explícitos, filtrando las rutas por el usuario de la sesión antes de elevar permisos. El historial y sus posiciones vuelven a comprobar la asignación. Las solicitudes POST utilizan la protección CSRF de Odoo.

## Puesta en marcha

El servicio Odoo ahora usa `config/Dockerfile.odoo` para incluir `pywebpush`.

```powershell
docker compose build odoo
docker compose up -d db traccar
docker compose stop odoo
docker compose run --rm --entrypoint /entrypoint.sh odoo odoo -d odoo_flota -u fleet_rutas --stop-after-init --no-http
docker compose up -d odoo
```

Usar el nombre real de la base si difiere de `odoo_flota`. La actualización usa directamente el entrypoint oficial de Odoo. En una base nueva, usar el arranque normal del proyecto para instalar los módulos antes de actualizar. Hacer un respaldo antes de actualizar una base con datos.

Abrir `http://localhost:8070/flota/app` en desarrollo. Para acceder desde un teléfono e instalar la PWA, publicar Odoo mediante **HTTPS** y un dominio accesible desde el teléfono. En Android usar Instalar app o el menú del navegador. En iPhone usar Compartir / Agregar a pantalla de inicio.

## Traccar y frecuencia

Se reutilizan las credenciales del servidor y la integración Traccar existente. Vincular cada vehículo a su dispositivo y comenzar un recorrido con una ruta asignada. El webhook existente recibe posiciones; su secreto debe estar configurado tanto en Traccar como en Odoo. La sincronización programada existente sirve como respaldo.

La PWA consulta Odoo cada **5 segundos** mientras está visible. No inventa posiciones cuando no existe señal. Marca posiciones de más de **120 segundos** como desactualizadas y muestra su fecha real. Sin un recorrido en curso no muestra un vehículo en vivo. La latencia real depende del GPS, Traccar y el webhook; el sondeo no acelera la recepción del GPS.

El mapa de referencia conecta las paradas con una línea discontinua: no representa una ruta vial calculada. El historial muestra posiciones GPS reales del recorrido, con hasta aproximadamente 1500 puntos muestreados, incluidos el primero y el último. Los recorridos se paginan de veinte en veinte. Este historial contiene recorridos de las rutas actualmente asignadas, no prueba que el pasajero haya abordado el transporte.

Leaflet 1.9.4 se carga desde unpkg y el mapa usa OpenStreetMap. Requieren conexión a Internet. La aplicación no conserva posiciones, sesiones ni documentos autenticados en la caché offline; solo guarda recursos públicos y una pantalla sin conexión.

## Avisos y notificaciones push

Los avisos dentro de la aplicación funcionan al recibir nuevas incidencias, sin configurar push. Se muestran las últimas cien incidencias pendientes de las rutas asignadas, excluyendo falsos positivos.

Para recibir notificaciones con la aplicación cerrada:

1. Reconstruir Odoo con la dependencia `pywebpush` y habilitar HTTPS.
2. En Ajustes / Aplicación móvil, indicar un contacto válido como `mailto:soporte@universidad.edu.ec` y guardar.
3. Pulsar **Generar claves Web Push**. La clave privada queda en parámetros restringidos al administrador y nunca se entrega al navegador. No se reemplazan claves existentes para conservar las suscripciones.
4. En la PWA, abrir Avisos / Activar notificaciones y aceptar el permiso del navegador. En iPhone se necesita una PWA instalada compatible con Web Push.

Las incidencias nuevas se encolan al crearse y el cron entrega lotes de diez cada minuto. El envío en segundo plano puede tardar aproximadamente un minuto o más por carga, reintentos, sistema operativo y servicio push; no se garantiza entrega instantánea. Los avisos dentro de la aplicación se detectan en el siguiente sondeo de cinco segundos desde que Odoo registra la incidencia.

La cola comprueba nuevamente la asignación, el rol y el estado del usuario antes de enviar, descarta incidencias resueltas o falsas y avisos con más de 24 horas, reintenta fallos hasta cinco veces y desactiva suscripciones vencidas HTTP 404/410. Solo permite endpoints HTTPS de los proveedores push admitidos, para impedir solicitudes a la red interna. La entrega tiene semántica de al menos una vez; una etiqueta por incidencia reduce duplicados en el dispositivo. Los mensajes no incluyen coordenadas GPS. Desactivar notificaciones elimina la suscripción de ese dispositivo; Salir también la retira antes de cerrar la sesión.

## Validación

```powershell
.venv/Scripts/python.exe scripts/verificar_fuentes.py
.venv/Scripts/python.exe -m pytest addons/fleet_rutas/tests -q -p no:cacheprovider
node --check addons/fleet_rutas/static/mobile/app.js
node --check addons/fleet_rutas/static/mobile/sw.js
```

Las pruebas aisladas comprueban las fronteras de rol, el filtrado de rutas, el rechazo de un historial ajeno y los destinos push permitidos. No sustituyen las pruebas de instalación y de permisos ORM en un Odoo real.

Verificar en una instancia de prueba: inicio de sesión de ambos roles; rechazo cruzado de `/web` y `/flota/app`; usuario sin rutas; dos pasajeros con rutas diferentes; acceso directo a historial ajeno; recepción de GPS vía webhook; incidencia y revocación de asignación; instalación y push en un teléfono real; logout y ausencia de datos privados offline.

Referencias: [seguridad de Odoo 16](https://www.odoo.com/documentation/16.0/developer/reference/backend/security.html), [PushManager](https://developer.mozilla.org/en-US/docs/Web/API/PushManager/subscribe), [pywebpush](https://github.com/web-push-libs/pywebpush).
