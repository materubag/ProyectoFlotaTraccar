# ==============================================================================
# scripts/manage.ps1 - Utilidad de gestión para ProyectoFlotaTraccar en Windows
# ==============================================================================

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet('start', 'stop', 'restart', 'status', 'logs', 'verify-db', 'restore-odoo', 'backup-odoo')]
    [string]$Action,
    [string]$Service = ""
)

switch ($Action) {
    'start' {
        Write-Host ">>> Iniciando servicios de ProyectoFlotaTraccar..." -ForegroundColor Cyan
        docker compose up -d
        docker compose ps
    }
    'stop' {
        Write-Host ">>> Deteniendo servicios de ProyectoFlotaTraccar..." -ForegroundColor Yellow
        docker compose stop
    }
    'restart' {
        Write-Host ">>> Reiniciando servicios..." -ForegroundColor Cyan
        if ($Service) {
            docker compose restart $Service
        } else {
            docker compose restart
        }
    }
    'status' {
        Write-Host ">>> Estado de contenedores:" -ForegroundColor Cyan
        docker compose ps
    }
    'logs' {
        if ($Service) {
            docker compose logs -f --tail=100 $Service
        } else {
            docker compose logs -f --tail=100
        }
    }
    'verify-db' {
        Write-Host ">>> Ejecutando verificación de PostgreSQL y aislamiento..." -ForegroundColor Cyan
        docker compose exec db bash /scripts/verify_databases.sh
    }
    'restore-odoo' {
        Write-Host ">>> ADVERTENCIA: Se restaurará el backup de Odoo bajo demanda." -ForegroundColor Yellow
        $confirm = Read-Host "¿Desea continuar? (s/N)"
        if ($confirm -eq 's' -or $confirm -eq 'S') {
            docker compose --profile restore run --rm restore
        } else {
            Write-Host "Operación cancelada." -ForegroundColor Gray
        }
    }
    'backup-odoo' {
        Write-Host ">>> Generando respaldo bajo demanda..." -ForegroundColor Cyan
        docker compose --profile tools run --rm backup
    }
}
