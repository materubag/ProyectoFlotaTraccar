# Ejecuta prueba_posiciones.py en una copia temporal de la base y la elimina al terminar.
# Uso desde la raíz:  pwsh scripts/pruebas/prueba_posiciones.ps1 -Salida resultado.json
param([string]$Salida = '')
$ErrorActionPreference = 'Stop'
$db = 'prueba_posiciones'
$existe = docker exec flota-db psql -U postgres -At -c "select 1 from pg_database where datname='$db'"
if ($existe) { throw "Ya existe la base '$db'. Revísela y elimínela antes de repetir." }
try {
    docker exec flota-db sh -c "createdb -U postgres -O odoo $db && pg_dump -U postgres odoo_flota | psql -U postgres -q -v ON_ERROR_STOP=1 -d $db >/dev/null && psql -U postgres -q -d $db -c 'update ir_cron set active=false'"
    if ($LASTEXITCODE) { throw 'Falló la copia' }
    $salidaShell = Get-Content -Raw -Encoding utf8 "$PSScriptRoot/prueba_posiciones.py" |
        docker exec -i flota-odoo /entrypoint.sh odoo shell -d $db --no-http --max-cron-threads=0 --log-level=critical 2>&1
    $r = $salidaShell | Where-Object { "$_" -like 'RESULT:*' } | Select-Object -Last 1
    if (-not $r) { $salidaShell | Select-Object -Last 30; throw 'Sin resultado' }
    $json = "$r".Substring(7)
    if ($Salida) { $json | Set-Content -Encoding utf8NoBOM $Salida }
    $json | ConvertFrom-Json | Format-Table id, ok, esperado, obtenido, caso -AutoSize -Wrap | Out-String -Width 200
}
finally {
    docker exec flota-db dropdb -U postgres --if-exists --force $db
}
