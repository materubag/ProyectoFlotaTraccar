# Capturas de la interfaz sobre una copia temporal de la base. No modifica la base del proyecto.
# Uso desde la raíz:  pwsh scripts/usabilidad/capturar.ps1 -Salida docs/mejora_continua/usabilidad/antes
param([string]$Salida = 'docs/mejora_continua/usabilidad/antes')
$ErrorActionPreference = 'Stop'
$db = 'ui_capturas'
$existe = docker exec flota-db psql -U postgres -At -c "select 1 from pg_database where datname='$db'"
if ($existe) { throw "Ya existe la base '$db'. Revísela y elimínela antes de repetir." }
$env:UI_PASSWORD = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 30 | ForEach-Object { [char]$_ })
try {
    docker exec flota-db sh -c "createdb -U postgres -O odoo $db && pg_dump -U postgres odoo_flota | psql -U postgres -q -v ON_ERROR_STOP=1 -d $db >/dev/null && psql -U postgres -q -d $db -c 'update ir_cron set active=false'"
    if ($LASTEXITCODE) { throw 'Falló la copia' }
    docker exec flota-odoo cp -a /var/lib/odoo/filestore/odoo_flota "/var/lib/odoo/filestore/$db"
    Get-Content -Raw -Encoding utf8 "$PSScriptRoot/usuarios_captura.py" |
        docker exec -i -e UI_PASSWORD -e UI_EN_VIVO="$env:UI_EN_VIVO" flota-odoo /entrypoint.sh odoo shell -d $db --no-http --max-cron-threads=0 --log-level=error
    if ($LASTEXITCODE) { throw 'Falló la creación de usuarios' }
    docker compose run -d --name flota-ui -p 127.0.0.1:8099:8069 --entrypoint /entrypoint.sh odoo odoo -d $db "--db-filter=^$db`$" --max-cron-threads=0 | Out-Null
    $listo = $false
    foreach ($i in 1..60) {
        try { Invoke-WebRequest http://localhost:8099/web/login -TimeoutSec 5 | Out-Null; $listo = $true; break } catch { Start-Sleep 2 }
    }
    if (-not $listo) { throw 'El Odoo temporal no respondió' }
    node "$PSScriptRoot/capturar.mjs" $Salida
}
finally {
    Remove-Item Env:UI_PASSWORD
    docker rm -f flota-ui 2>$null | Out-Null
    docker exec flota-db dropdb -U postgres --if-exists --force $db
    docker exec flota-odoo rm -rf "/var/lib/odoo/filestore/$db"
}
