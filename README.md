# ProyectoFlotaTraccar: Integración Odoo 16 + Traccar 6.16 + PostgreSQL 15

Entorno contenerizado con Docker Compose para la gestión y monitoreo GPS de flotas vehiculares, integrando **Odoo 16**, **Traccar 6.16.0** y **PostgreSQL 15**.

---

## 1. Arquitectura del Sistema

```text
  Teléfonos / Dispositivos GPS (OsmAnd Protocol)
                        │
                        ▼ Puerto 5055 (TCP/UDP)
                 ┌──────────────┐
                 │   TRACCAR    │ (Puerto Web 8082)
                 │   (v6.16.0)  │
                 └──────┬───────┘
                        │ API REST (http://traccar:8082)
                        ▼
                 ┌──────────────┐
                 │   ODOO 16    │ (Puerto Web 8070)
                 │ fleet_traccar│
                 └──────┬───────┘
                        │
       Red Interna Docker (flota-net)
                        │
                        ▼
                 ┌──────────────┐
                 │  POSTGRESQL  │ (v15 - Sin publicar en Host)
                 │   flota-db   │
                 └──────┬───────┘
            ┌───────────┴───────────┐
            ▼                       ▼
    Base: odoo_flota        Base: traccar
    Usuario: odoo           Usuario: traccar
    (Esquema Odoo)          (Esquema Traccar)
```

### Principios de Diseño
* **Bases de datos independientes**: Odoo y Traccar residen en el mismo motor PostgreSQL pero en bases de datos separadas (`odoo_flota` y `traccar`), con usuarios dedicados (`odoo` y `traccar`) y permisos restringidos.
* **Aislamiento de seguridad**: Se revoca el privilegio `CONNECT` de `PUBLIC` para que el usuario de Traccar no pueda acceder a la base de Odoo, ni Odoo a la de Traccar.
* **Integración desacoplada**: Odoo se comunica exclusivamente mediante la **API REST** de Traccar vía la red interna `flota-net`, sin consultas directas a las tablas internas de Traccar.
* **No interferencia**: Contenedores, volúmenes y redes utilizan prefijos exclusivos (`flota-*`), garantizando que instalaciones previas u otros proyectos (como `proyectoGC`) permanezcan intactos.

---

## 2. Puertos y Direcciones de Acceso

| Servicio | URL / Host Local | Puerto Host | Puerto Contenedor | Protocolo |
| :--- | :--- | :---: | :---: | :--- |
| **Odoo 16** | [http://localhost:8070](http://localhost:8070) | `8070` | `8069` | HTTP |
| **Traccar Web/API** | [http://localhost:8082](http://localhost:8082) | `8082` | `8082` | HTTP / REST |
| **Traccar GPS OsmAnd** | `localhost:5055` | `5055` | `5055` | TCP / UDP |
| **PostgreSQL 15** | `db:5432` (solo interno) | *No publicado* | `5432` | TCP |

---

## 3. Requisitos Previos

* **Sistema Operativo**: Windows 10/11 con PowerShell.
* **Docker Desktop**: Con soporte para contenedores Linux y Compose v2.
* **Git**: Para control de versiones.

---

## 4. Estructura del Directorio

```text
ProyectoFlotaTraccar/
├── addons/
│   └── fleet_traccar/           # Módulo Odoo de integración GPS
│       ├── models/
│       ├── views/
│       ├── security/
│       ├── __init__.py
│       └── __manifest__.py
├── backups/                     # Respaldos de bases de datos
├── config/
│   ├── odoo.conf                # Configuración estándar de Odoo
│   └── init-databases.sh        # Inicialización multi-base y aislamiento PostgreSQL
├── scripts/
│   ├── manage.ps1               # Script PowerShell de gestión
│   └── verify_databases.sh      # Verificación de integridad y aislamiento
├── traccar/
│   ├── traccar.xml.template     # Plantilla segura de configuración JDBC Traccar
│   └── logs/                    # Volumen local de logs
├── docker-compose.yml           # Configuración principal de servicios
├── docker-compose.init.yml      # Configuración reducida para inicio base
├── .env.example                 # Plantilla de variables de entorno
├── .env                         # Variables de entorno locales (ignorado por Git)
├── .gitignore                   # Exclusiones de control de versiones
└── README.md                    # Documentación técnica
```

---

## 5. Puesta en Marcha y Operación (PowerShell)

### A. Preparación Inicial
1. Copiar la plantilla de variables de entorno:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Modificar `.env` con contraseñas seguras para su entorno local si lo desea.

### B. Iniciar los Servicios
Para levantar todos los contenedores en segundo plano:
```powershell
docker compose up -d
```
O utilizando el script asistente:
```powershell
.\scripts\manage.ps1 -Action start
```

### C. Verificar Estado de Contenedores
```powershell
docker compose ps
```
Debe observar `flota-db` (healthy), `flota-odoo` (Up) y `flota-traccar` (Up).

### D. Detener los Servicios sin Perder Datos
```powershell
docker compose stop
```
Para volver a iniciarlos sin reconstruir:
```powershell
docker compose start
```
> [!IMPORTANT]
> **Nunca** ejecute `docker compose down -v` ya que eliminará los volúmenes de datos persistentes.

---

## 6. Monitoreo y Verificación

### Ver Registros (Logs)
```powershell
# Ver todos los logs en tiempo real
docker compose logs -f --tail=100

# Ver logs de un servicio específico
docker compose logs -f traccar
docker compose logs -f odoo
docker compose logs -f db
```

### Verificar Bases de Datos y Aislamiento Estricto
Ejecute la prueba automatizada que comprueba que ni Traccar ni Odoo pueden acceder a la base del otro:
```powershell
docker compose exec db bash /scripts/verify_databases.sh
```

---

## 7. Configuración de Traccar y GPS

### A. Registro del Usuario Administrador
Al tratarse de una instalación nueva:
1. Abra [http://localhost:8082](http://localhost:8082).
2. Registre su usuario administrador (ej. `admin@flota.local` y su contraseña).

### B. Registro de un Dispositivo GPS
1. En la barra lateral izquierda de Traccar, haga clic en el botón `+` (Añadir dispositivo).
2. Ingrese el **Nombre** (ej. `Bus 101`) y el **Identificador único** (ej. `BUS-101-GPS` o el IMEI del equipo).

### C. Configurar Traccar Client en un Teléfono Móvil
1. Descargue **Traccar Client** (Android en Google Play / iOS en App Store).
2. Abra la aplicación y configure:
   * **Identificador de dispositivo**: El mismo identificador configurado en Traccar (ej. `BUS-101-GPS`).
   * **URL del servidor**: `http://IP_DE_SU_PC:5055` (reemplace `IP_DE_SU_PC` por la IP local de la computadora en la red Wi-Fi, ej. `http://192.168.1.50:5055`).
   * **Frecuencia de reporte**: 10 segundos.
   * **Activar servicio**: Activar el interruptor de encendido.
3. Otorgue permisos de ubicación precisa "Permitir siempre".

### D. Probar Telemetría Simulada por Consola
Puede enviar una coordenada de prueba directamente con PowerShell:
```powershell
$epoch = [int64](([DateTime]::UtcNow)-(Get-Date "1970-01-01")).TotalSeconds
Invoke-RestMethod -Uri "http://localhost:5055/?id=BUS-101-GPS&lat=-0.180653&lon=-78.467838&speed=40.0&bearing=90&timestamp=$epoch"
```
Compruebe inmediatamente en [http://localhost:8082](http://localhost:8082) la aparición del vehículo en el mapa con su telemetría.

---

## 8. Procedimientos de Respaldo y Restauración

Los procesos de backup y restauración están aislados bajo perfiles de Compose para evitar ejecuciones accidentales durante el arranque.

### Respaldar Odoo bajo demanda
```powershell
docker compose --profile tools run --rm backup
```
Genera `backups/db_demo.dump` y copia el filestore.

### Restaurar Respaldo de Odoo bajo demanda
```powershell
docker compose --profile restore run --rm restore
```
> [!CAUTION]
> Esta operación cerrará las sesiones activas en `odoo_flota`, recreará la base y restaurará el dump junto con su filestore. Úselo únicamente bajo demanda.

---

## 9. Matriz de Pruebas Ejecutadas y Verificadas

| Prueba | Descripción | Resultado | Evidencia |
| :--- | :--- | :---: | :--- |
| **Infraestructura** | Sintaxis Compose válida | Aprobada | `docker compose config` código 0 |
| **PostgreSQL Multi-BD** | Creación de bases `odoo_flota` y `traccar` | Aprobada | Ambas BDs creadas por `init-databases.sh` |
| **Aislamiento de BD** | Traccar denegado en Odoo / Odoo denegado en Traccar | Aprobada | `permission denied for database` confirmado en `verify_databases.sh` |
| **Traccar 6.16 JDBC** | Conexión nativa con PostgreSQL vía driver JDBC | Aprobada | Liquibase ejecutó 35 change sets en PostgreSQL |
| **Traccar Web/API** | Respuesta HTTP 200 y JSON `/api/server` | Aprobada | Versión 6.16.0 confirmada vía API REST |
| **Recepción GPS (5055)** | Telemetría recibida vía protocolo OsmAnd | Aprobada | Dispositivo `BUS-101-GPS` registrado y posición almacenada |
| **Persistencia** | Los datos persisten tras reiniciar Traccar | Aprobada | Datos intactos tras `docker compose restart traccar` |
| **DNS Interno Docker** | Comunicación Odoo -> Traccar por nombre | Aprobada | Odoo consultó `http://traccar:8082` exitosamente |
| **Odoo 16 Web** | Acceso web en puerto `8070` | Aprobada | HTTP 200 en `http://localhost:8070/web/login` |
| **Aislamiento Proyecto** | Proyecto original `proyectoGC` intacto en `8888` | Aprobada | HTTP 200 en `8888`, contenedores intactos |
