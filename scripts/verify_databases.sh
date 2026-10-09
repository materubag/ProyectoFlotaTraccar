#!/usr/bin/env bash
# ==============================================================================
# Script de Verificación de Integridad y Aislamiento de Bases de Datos
# ==============================================================================

set -e

POSTGRES_USER="${POSTGRES_USER:-postgres}"
ODOO_DB_NAME="${ODOO_DB_NAME:-odoo_flota}"
ODOO_DB_USER="${ODOO_DB_USER:-odoo}"
TRACCAR_DB_NAME="${TRACCAR_DB_NAME:-traccar}"
TRACCAR_DB_USER="${TRACCAR_DB_USER:-traccar}"

echo "=========================================================="
echo ">>> [VERIFICACIÓN] Comprobando bases de datos y roles..."
echo "=========================================================="

echo "--- 1. Bases de datos existentes ---"
psql -U "$POSTGRES_USER" -d postgres -c "\l"

echo "--- 2. Roles y permisos de conexión ---"
psql -U "$POSTGRES_USER" -d postgres -c "\du"

echo "--- 3. Prueba de conexión de usuario Odoo a su BD ($ODOO_DB_NAME) ---"
PGPASSWORD="$ODOO_DB_PASSWORD" psql -U "$ODOO_DB_USER" -d "$ODOO_DB_NAME" -c "SELECT current_user, current_database();"

echo "--- 4. Prueba de conexión de usuario Traccar a su BD ($TRACCAR_DB_NAME) ---"
PGPASSWORD="$TRACCAR_DB_PASSWORD" psql -U "$TRACCAR_DB_USER" -d "$TRACCAR_DB_NAME" -c "SELECT current_user, current_database();"

echo "--- 5. Prueba de AISLAMIENTO: Traccar intentando conectar a $ODOO_DB_NAME (debe ser RECHAZADO) ---"
if PGPASSWORD="$TRACCAR_DB_PASSWORD" psql -U "$TRACCAR_DB_USER" -d "$ODOO_DB_NAME" -c "SELECT 1;" 2>&1 | grep -E "FATAL|denied|rechazada"; then
    echo ">>> CONFIRMADO: Traccar NO tiene acceso a la base de Odoo (Aislamiento exitoso)."
else
    echo ">>> ALERTA: Traccar pudo conectar a la base de Odoo."
fi

echo "--- 6. Prueba de AISLAMIENTO: Odoo intentando conectar a $TRACCAR_DB_NAME (debe ser RECHAZADO) ---"
if PGPASSWORD="$ODOO_DB_PASSWORD" psql -U "$ODOO_DB_USER" -d "$TRACCAR_DB_NAME" -c "SELECT 1;" 2>&1 | grep -E "FATAL|denied|rechazada"; then
    echo ">>> CONFIRMADO: Odoo NO tiene acceso a la base de Traccar (Aislamiento exitoso)."
else
    echo ">>> ALERTA: Odoo pudo conectar a la base de Traccar."
fi

echo "=========================================================="
echo ">>> [VERIFICACIÓN] Comprobación finalizada."
echo "=========================================================="
