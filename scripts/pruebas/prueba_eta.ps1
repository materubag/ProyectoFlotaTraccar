# Actualiza los módulos en una copia temporal, ejecuta prueba_eta.py y los 11 escenarios.
# Uso desde la raíz:  pwsh scripts/pruebas/prueba_eta.ps1 
param([switch]$OsrmReal)
$ErrorActionPreference = 'Stop'
$db = 'prueba_flota'
$existe = docker exec flota-db psql -U postgres -At -c "select 1 from pg_database where datname='$db'"
if ($existe) { throw "Ya existe la base '$db'. Revísela y elimínela antes de repetir." }
try {
    docker exec flota-db sh -c "createdb -U postgres -O odoo $db && pg_dump -U postgres odoo_flota | psql -U postgres -q -v ON_ERROR_STOP=1 -d $db >/dev/null && psql -U postgres -q -d $db -c 'update ir_cron set active=false'"
    if ($LASTEXITCODE) { throw 'Falló la copia' }
    docker exec flota-odoo /entrypoint.sh odoo -d $db -u fleet_traccar,fleet_rutas --stop-after-init --no-http --max-cron-threads=0 --log-level=error
    if ($LASTEXITCODE) { throw 'Falló la actualización de módulos' }
    docker exec flota-db psql -U postgres -q -d $db -c 'update ir_cron set active=false'
    $destino = 'docs/mejora_continua/ciclo_eta'
    New-Item -ItemType Directory -Force $destino | Out-Null
    $real = if ($OsrmReal) { '1' } else { '0' }
    function Invoke-Prueba($script, $base) {
        $s = Get-Content -Raw -Encoding utf8 $script |
            docker exec -i -e OSRM_REAL=$real flota-odoo /entrypoint.sh odoo shell -d $base --no-http --max-cron-threads=0 --log-level=critical 2>&1
        $r = $s | Where-Object { "$_" -like 'RESULT:*' } | Select-Object -Last 1
        if (-not $r) { $s | Select-Object -Last 30; throw "Sin resultado: $script" }
        "$r".Substring(7)
    }
    $json = Invoke-Prueba "$PSScriptRoot/prueba_eta.py" $db
    $json | Set-Content -Encoding utf8NoBOM "$destino/pruebas.json"
    $o = $json | ConvertFrom-Json
    $o.casos | Format-Table id, ok, esperado, obtenido, caso -AutoSize -Wrap | Out-String -Width 200
    $o.informativo | ConvertTo-Json -Depth 5

}
finally {
    docker exec flota-db dropdb -U postgres --if-exists --force $db
    docker exec flota-odoo rm -rf "/var/lib/odoo/filestore/$db"
}
