#!/usr/bin/env bash
set -e

# ==============================================================================
# Script de Inicialización de Bases de Datos Independientes: Odoo y Traccar
# Compatible con PostgreSQL 15 - Idempotente y Seguro
# ==============================================================================

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-postgres}"

ODOO_DB_NAME="${ODOO_DB_NAME:-odoo_flota}"
ODOO_DB_USER="${ODOO_DB_USER:-odoo}"
ODOO_DB_PASSWORD="${ODOO_DB_PASSWORD:-odoo_pass}"

TRACCAR_DB_NAME="${TRACCAR_DB_NAME:-traccar}"
TRACCAR_DB_USER="${TRACCAR_DB_USER:-traccar}"
TRACCAR_DB_PASSWORD="${TRACCAR_DB_PASSWORD:-traccar_pass}"

echo "=========================================================="
echo ">>> [init-databases] Configurando usuarios y bases aisladas..."
echo "=========================================================="

# 1. Configurar Usuario y Base para ODOO
echo ">>> [init-databases] Verificando usuario Odoo: ${ODOO_DB_USER}..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${ODOO_DB_USER}') THEN
            CREATE ROLE ${ODOO_DB_USER} WITH LOGIN CREATEDB PASSWORD '${ODOO_DB_PASSWORD}';
            RAISE NOTICE 'Usuario ${ODOO_DB_USER} creado.';
        ELSE
            ALTER ROLE ${ODOO_DB_USER} WITH LOGIN CREATEDB PASSWORD '${ODOO_DB_PASSWORD}';
            RAISE NOTICE 'Usuario ${ODOO_DB_USER} actualizado.';
        END IF;
    END
    \$\$;
EOSQL

if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='${ODOO_DB_NAME}'" | grep -q 1; then
    echo ">>> [init-databases] Creando base de datos Odoo: ${ODOO_DB_NAME}..."
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        CREATE DATABASE ${ODOO_DB_NAME} OWNER ${ODOO_DB_USER};
EOSQL
else
    echo ">>> [init-databases] Base de datos Odoo ${ODOO_DB_NAME} ya existe."
fi

# Configurar permisos para Odoo
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    GRANT ALL PRIVILEGES ON DATABASE ${ODOO_DB_NAME} TO ${ODOO_DB_USER};
    ALTER DATABASE ${ODOO_DB_NAME} OWNER TO ${ODOO_DB_USER};
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${ODOO_DB_NAME}" <<-EOSQL
    GRANT ALL ON SCHEMA public TO ${ODOO_DB_USER};
    GRANT USAGE, CREATE ON SCHEMA public TO ${ODOO_DB_USER};
EOSQL

# 2. Configurar Usuario y Base para TRACCAR
echo ">>> [init-databases] Verificando usuario Traccar: ${TRACCAR_DB_USER}..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${TRACCAR_DB_USER}') THEN
            CREATE ROLE ${TRACCAR_DB_USER} WITH LOGIN PASSWORD '${TRACCAR_DB_PASSWORD}';
            RAISE NOTICE 'Usuario ${TRACCAR_DB_USER} creado.';
        ELSE
            ALTER ROLE ${TRACCAR_DB_USER} WITH LOGIN PASSWORD '${TRACCAR_DB_PASSWORD}';
            RAISE NOTICE 'Usuario ${TRACCAR_DB_USER} actualizado.';
        END IF;
    END
    \$\$;
EOSQL

if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='${TRACCAR_DB_NAME}'" | grep -q 1; then
    echo ">>> [init-databases] Creando base de datos Traccar: ${TRACCAR_DB_NAME}..."
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        CREATE DATABASE ${TRACCAR_DB_NAME} OWNER ${TRACCAR_DB_USER};
EOSQL
else
    echo ">>> [init-databases] Base de datos Traccar ${TRACCAR_DB_NAME} ya existe."
fi

# Configurar permisos para Traccar
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    GRANT ALL PRIVILEGES ON DATABASE ${TRACCAR_DB_NAME} TO ${TRACCAR_DB_USER};
    ALTER DATABASE ${TRACCAR_DB_NAME} OWNER TO ${TRACCAR_DB_USER};
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${TRACCAR_DB_NAME}" <<-EOSQL
    GRANT ALL ON SCHEMA public TO ${TRACCAR_DB_USER};
    REVOKE ALL ON SCHEMA public FROM PUBLIC;
    GRANT USAGE, CREATE ON SCHEMA public TO ${TRACCAR_DB_USER};
EOSQL

# 3. AISLAMIENTO ESTRICTO DE ACCESOS CRUZADOS
echo ">>> [init-databases] Aplicando aislamiento entre Odoo y Traccar..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Revocar permisos de conexión a PUBLIC (aislamiento por defecto)
    REVOKE CONNECT ON DATABASE ${ODOO_DB_NAME} FROM PUBLIC;
    REVOKE CONNECT ON DATABASE ${TRACCAR_DB_NAME} FROM PUBLIC;

    -- Conceder conexión solo a su respectivo dueño
    GRANT CONNECT ON DATABASE ${ODOO_DB_NAME} TO ${ODOO_DB_USER};
    GRANT CONNECT ON DATABASE ${TRACCAR_DB_NAME} TO ${TRACCAR_DB_USER};

    -- Revocar explícitamente cualquier permiso cruzado
    REVOKE ALL ON DATABASE ${ODOO_DB_NAME} FROM ${TRACCAR_DB_USER};
    REVOKE ALL ON DATABASE ${TRACCAR_DB_NAME} FROM ${ODOO_DB_USER};
EOSQL

echo "=========================================================="
echo ">>> [init-databases] Inicialización multi-base completada con éxito."
echo "=========================================================="
