"""Verifica salud, bloqueo anónimo y acceso autenticado sin imprimir credenciales."""
import base64
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


root = Path(__file__).resolve().parents[1]
settings = {}
for line in (root / '.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        key, value = line.split('=', 1)
        settings[key.strip()] = value.strip().strip('\"\'')
base = 'http://127.0.0.1:' + settings.get('GRAFANA_PORT', '3000')
opener = build_opener(NoRedirect)


def call(path, authenticated=False, data=None):
    headers = {}
    if authenticated:
        token = settings.get('GRAFANA_ADMIN_USER', 'admin') + ':' + settings['GRAFANA_ADMIN_PASSWORD']
        headers['Authorization'] = 'Basic ' + base64.b64encode(token.encode()).decode()
    if data is not None:
        data = json.dumps(data).encode()
        headers['Content-Type'] = 'application/json'
    try:
        response = opener.open(Request(base + path, headers=headers, data=data), timeout=20)
    except HTTPError as error:
        response = error
    return response.code, response.headers, response.read()


status, _, body = call('/api/health')
assert status == 200 and json.loads(body)['database'] == 'ok', 'Grafana no está saludable'
print('PASS salud de Grafana y su base interna')
for path in ('/api/dashboards/uid/fleet-traccar-main', '/api/datasources'):
    status, _, _ = call(path)
    assert status == 401, f'Acceso anónimo permitido: {path}: {status}'
status, _, _ = call('/api/ds/query', data={'queries': []})
assert status == 401, 'Las consultas deben requerir autenticación'
status, headers, _ = call('/d/fleet-traccar-main/flota-vehicular-gps-traccar')
assert status == 302 and '/login' in headers.get('Location', ''), 'El panel no exige login'
print('PASS paneles, fuentes y consultas bloqueados sin sesión')
status, _, body = call('/api/dashboards/uid/fleet-traccar-main', True)
assert status == 200, 'No se pudo acceder con las credenciales configuradas en .env'
assert json.loads(body)['dashboard']['uid'] == 'fleet-traccar-main'
for uid in ('traccar-pg', 'odoo-pg'):
    status, _, body = call('/api/datasources/uid/' + uid + '/health', True)
    assert status == 200 and json.loads(body)['status'] == 'OK', f'Fuente no saludable: {uid}'
print('PASS acceso autenticado al dashboard y conexión a Traccar/Odoo')
