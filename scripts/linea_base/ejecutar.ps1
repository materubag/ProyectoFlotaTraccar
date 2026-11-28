# Reproduce la línea base. No modifica la base del proyecto: trabaja sobre una copia temporal.
# Uso desde la raíz del repositorio:  pwsh scripts/linea_base/ejecutar.ps1
$ErrorActionPreference = 'Stop'
$raiz = Resolve-Path "$PSScriptRoot/../.."
$salida = Join-Path $raiz 'docs/mejora_continua/linea_base'
New-Item -ItemType Directory -Force $salida | Out-Null
$db = 'linea_base'

function Save-Result($lineas, $nombre) {
    $r = $lineas | Where-Object { "$_" -like 'RESULT:*' } | Select-Object -Last 1
    if (-not $r) { $lineas | Select-Object -Last 30; throw "Sin resultado: $nombre" }
    "$r".Substring(7) | Set-Content -Encoding utf8NoBOM (Join-Path $salida "$nombre.json")
}
function Invoke-Shell($script) {
    Get-Content -Raw -Encoding utf8 "$PSScriptRoot/$script" |
        docker exec -i flota-odoo /entrypoint.sh odoo shell -d $db --no-http --max-cron-threads=0 --log-level=error 2>&1
}

$existe = docker exec flota-db psql -U postgres -At -c "select 1 from pg_database where datname='$db'"
if ($existe) { throw "Ya existe la base '$db'. Revísela y elimínela antes de repetir." }

$sql = Get-Content -Raw -Encoding utf8 "$PSScriptRoot/datos_actuales.sql" |
    docker exec -i flota-db psql -U postgres -d odoo_flota -At -q -v ON_ERROR_STOP=1
if ($LASTEXITCODE) { throw 'Falló la consulta de datos' }
($sql -join "`n") | Set-Content -Encoding utf8NoBOM (Join-Path $salida 'datos_actuales.json')

$cruce = [ordered]@{
    traccar = [int](docker exec flota-db psql -U postgres -d traccar -At -c 'select count(*) from tc_positions')
}
$ids = (docker exec flota-db psql -U postgres -d traccar -At -c 'select id from tc_positions') -join ','
$cruce.en_odoo = if ($ids) { [int](docker exec flota-db psql -U postgres -d odoo_flota -At -c "select count(*) from fleet_posicion_gps where fuente='traccar' and traccar_position_id in ($ids)") } else { 0 }
$cruce | ConvertTo-Json | Set-Content -Encoding utf8NoBOM (Join-Path $salida 'traccar_vs_odoo.json')

try {
    docker exec flota-db sh -c "createdb -U postgres -O odoo $db && pg_dump -U postgres odoo_flota | psql -U postgres -q -v ON_ERROR_STOP=1 -d $db >/dev/null && psql -U postgres -q -d $db -c 'update ir_cron set active=false'"
    if ($LASTEXITCODE) { throw 'Falló la copia' }
    docker exec flota-odoo /entrypoint.sh odoo -d $db -i portal -u fleet_traccar,fleet_rutas,fleet_reports --stop-after-init --no-http --max-cron-threads=0 --log-level=error
    if ($LASTEXITCODE) { throw 'Falló la actualización de módulos' }
    docker exec flota-db psql -U postgres -q -d $db -c 'update ir_cron set active=false'

    Save-Result (Invoke-Shell 'escenarios.py') 'escenarios'
    Save-Result (Invoke-Shell 'preparar_rendimiento.py') 'rendimiento_servidor'

    docker exec -d flota-odoo /entrypoint.sh odoo -d $db "--db-filter=^$db`$" --http-port=8099 --max-cron-threads=0 --pidfile=/tmp/lb.pid --logfile=/tmp/lb.log
    Save-Result (docker exec flota-odoo python3 /scripts/linea_base/rendimiento_http.py 2>&1) 'rendimiento_http'
}
finally {
    docker exec flota-odoo sh -c 'test -f /tmp/lb.pid && kill $(cat /tmp/lb.pid)'
    Start-Sleep -Seconds 3
    docker exec flota-odoo rm -f /tmp/lb_cred.json /tmp/lb.pid /tmp/lb.log
    docker exec flota-db dropdb -U postgres --if-exists --force $db
    docker exec flota-odoo rm -rf "/var/lib/odoo/filestore/$db"
}

python "$PSScriptRoot/calidad_codigo.py" | Out-Null
python "$PSScriptRoot/resumen.py"
