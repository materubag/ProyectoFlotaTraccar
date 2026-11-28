"""Mide HTTP contra el Odoo temporal (127.0.0.1:8099 dentro del contenedor)."""
import json
import time
import requests

URL = 'http://127.0.0.1:8099'
cred = json.load(open('/tmp/lb_cred.json'))
s = requests.Session()


def rpc(path, params):
    r = s.post(URL + path, json={'jsonrpc': '2.0', 'method': 'call', 'params': params}, timeout=120)
    r.raise_for_status()
    body = r.json()
    if 'error' in body:
        raise RuntimeError(body['error']['data'].get('message'))
    return body['result']


for _ in range(60):
    try:
        s.get(URL + '/web/login', timeout=5)
        break
    except requests.ConnectionError:
        time.sleep(1)
assert rpc('/web/session/authenticate',
           {'db': 'linea_base', 'login': 'lb_medicion', 'password': cred['password']})['uid']


def buscar(model, fields, domain=(), paginar=True, limite=200):
    total = 0
    while True:
        filas = rpc('/web/dataset/call_kw', {'model': model, 'method': 'search_read', 'args': [],
                    'kwargs': {'domain': list(domain), 'fields': fields, 'offset': total, 'limit': limite}})
        total += len(filas)
        if not paginar or len(filas) < limite:
            return total


def dashboard():
    # Mismas consultas que fleet_dashboard.js (aquí secuenciales; el navegador las lanza en paralelo).
    buscar('fleet.recorrido', ['name', 'ruta_id', 'vehicle_id', 'fecha_inicio', 'estado', 'simulado',
                               'distancia_real_km', 'porcentaje_paradas_cumplidas', 'tiene_desviacion'])
    buscar('fleet.ruta', ['name', 'code', 'estado', 'origen', 'destino'])
    buscar('fleet.parada', ['name', 'ruta_id', 'secuencia', 'hora_prevista', 'latitud', 'longitud'])
    buscar('fleet.vehicle', ['display_name', 'license_plate', 'traccar_last_update'])
    buscar('fleet.metricas.recorrido', ['recorrido_id', 'ruta_id', 'pct_puntualidad'])
    buscar('fleet.incidencia', ['recorrido_id', 'tipo', 'timestamp', 'descripcion', 'resuelta'])
    buscar('fleet.traccar.sync', ['fecha_inicio', 'estado'], paginar=False, limite=1)


def get(path):
    r = s.get(URL + path, timeout=120)
    r.raise_for_status()
    assert '/web/login' not in r.url
    return len(r.content)


def medir(fn, repeticiones=20):
    for _ in range(2):
        fn()
    tiempos, extra = [], None
    for _ in range(repeticiones):
        t = time.perf_counter()
        extra = fn()
        tiempos.append((time.perf_counter() - t) * 1000)
    return {'ms': tiempos, 'bytes': extra}


out = {'dashboard': medir(dashboard)}
for n, rid in cred['volumenes'].items():
    out['mapa_%s' % n] = medir(lambda: get('/fleet_rutas/mapa/%d?embed=1' % rid))
    out['repeticion_%s' % n] = medir(lambda: get('/fleet_rutas/repeticion/%d/datos' % rid))
    out['historial_completo_%s' % n] = medir(lambda: buscar(
        'fleet.posicion.gps', ['timestamp', 'latitud', 'longitud', 'velocidad_kmh'],
        [('recorrido_id', '=', rid)], paginar=False, limite=n and int(n) + 100) and None)
r = requests.post(URL + '/fleet_rutas/webhook/traccar', json={}, timeout=30)
out['webhook_sin_token_http'] = r.status_code
print('RESULT:' + json.dumps(out))
