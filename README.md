# Proyecto Flota Traccar (Odoo 16 + Traccar + PostgreSQL)

Revisión de requisitos, correcciones, resultados y tabla de pendientes: [docs/REVISION_PROYECTO.md](docs/REVISION_PROYECTO.md). Matriz automatizada: [docs/MATRIZ_PRUEBAS.md](docs/MATRIZ_PRUEBAS.md).

Plataforma de gestión de flota vehicular y monitoreo GPS que integra **Odoo 16**, **Traccar 6.16** y **PostgreSQL 15** bajo contenedores Docker aislados.

---

## 1. Stack Tecnológico y Módulos

| Componente | Versión | Rol / Descripción |
| :--- | :---: | :--- |
| **Odoo** | `16.0` | ERP para gestión de flota, vehículos (`fleet.vehicle`) y telemetría. |
| **Traccar** | `6.16.0` | Servidor de rastreo GPS (protocolos OsmAnd, Teltonika, etc.) y API REST. |
| **PostgreSQL** | `15` | Motor de BD compartido con bases aisladas: `odoo_flota` y `traccar`. |
| **fleet_traccar** | `16.0.1.0` | Módulo personalizado Odoo que vincula vehículos con dispositivos Traccar. |
| **Docker Compose** | v2 | Orquestador de la infraestructura y red interna `flota-net`. |

### Estructura del Módulo `fleet_traccar` (`addons/fleet_traccar/`)
* **Extensión `fleet.vehicle`**: Agrega ID de dispositivo Traccar (con validación de unicidad), switch de seguimiento y telemetría (última latitud, longitud, velocidad y fecha).
* **Ajustes (`res.config.settings`)**: Configuración segura de la URL interna (`http://traccar:8082`) y credenciales de la API Traccar.

---

## 2. Puertos y Direcciones de Acceso

| Servicio | URL Local | Puerto Host | Puerto Contenedor |
| :--- | :--- | :---: | :---: |
| **Odoo 16** | [http://localhost:8070](http://localhost:8070) | `8070` | `8069` |
| **Traccar Web / API** | [http://localhost:8082](http://localhost:8082) | `8082` | `8082` |
| **Traccar GPS (OsmAnd)** | `localhost:5055` | `5055` | `5055` (TCP/UDP) |
| **PostgreSQL 15** | Red interna `flota-net` | *No publicado* | `5432` |

---

## 3. Cómo Ejecutar el Proyecto (PowerShell / Windows)

### Paso 1: Configurar Variables de Entorno
Si no existe el archivo `.env`, crearlo a partir de la plantilla:
```powershell
Copy-Item .env.example .env
```

### Paso 2: Iniciar Servicios
Levantar los contenedores en segundo plano:
```powershell
docker compose up -d
```
Verificar que los 3 contenedores estén activos:
```powershell
docker compose ps
```

### Paso 3: Acceso Inicial
* **Odoo**: Ingrese a [http://localhost:8070](http://localhost:8070).
* **Traccar**: Ingrese a [http://localhost:8082](http://localhost:8082). Registre su usuario administrador inicial.

---

## 4. Comandos de Gestión Frecuentes

```powershell
# Detener los servicios sin borrar datos
docker compose stop

# Volver a iniciar los servicios
docker compose start

# Ver logs en tiempo real (ejemplo Traccar)
docker compose logs -f traccar

# Probar recepción de posición GPS simulada en puerto 5055
$epoch = [int64](([DateTime]::UtcNow)-(Get-Date "1970-01-01")).TotalSeconds
Invoke-RestMethod "http://localhost:5055/?id=BUS-101-GPS&lat=-0.180653&lon=-78.467838&speed=35&timestamp=$epoch"

# Verificar aislamiento de las dos bases de datos en PostgreSQL
docker compose exec db bash /scripts/verify_databases.sh

# Restaurar backup de Odoo (bajo demanda)
docker compose --profile restore run --rm restore

# Generar backup de Odoo (bajo demanda)
docker compose --profile tools run --rm backup
```
