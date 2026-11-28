"""Convierte los JSON de la línea base en tablas Markdown (resumen.md)."""
import json
import math
import statistics
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / 'docs' / 'mejora_continua' / 'linea_base'


def leer(nombre):
    return json.loads((DIR / (nombre + '.json')).read_text(encoding='utf-8'))


def pct(a, b):
    return '%.1f %%' % (a / b * 100) if b else 'sin muestra'


def p95(valores):
    orden = sorted(valores)
    return orden[math.ceil(.95 * len(orden)) - 1]


def haversine(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def vincenty(a, b):
    """Distancia geodésica WGS84 (fórmula inversa de Vincenty), en metros."""
    if list(a) == list(b):
        return 0.0
    A, f = 6378137.0, 1 / 298.257223563
    B = A * (1 - f)
    u1, u2 = (math.atan((1 - f) * math.tan(math.radians(p[0]))) for p in (a, b))
    L = lam = math.radians(b[1] - a[1])
    for _ in range(200):
        ss = math.hypot(math.cos(u2) * math.sin(lam),
                        math.cos(u1) * math.sin(u2) - math.sin(u1) * math.cos(u2) * math.cos(lam))
        cs = math.sin(u1) * math.sin(u2) + math.cos(u1) * math.cos(u2) * math.cos(lam)
        s = math.atan2(ss, cs)
        sa = math.cos(u1) * math.cos(u2) * math.sin(lam) / ss
        c2a = 1 - sa ** 2
        c2m = cs - 2 * math.sin(u1) * math.sin(u2) / c2a if c2a else 0
        C = f / 16 * c2a * (4 + f * (4 - 3 * c2a))
        previo, lam = lam, L + (1 - C) * f * sa * (s + C * ss * (c2m + C * cs * (-1 + 2 * c2m ** 2)))
        if abs(lam - previo) < 1e-12:
            break
    k = c2a * (A ** 2 - B ** 2) / B ** 2
    Ka = 1 + k / 16384 * (4096 + k * (-768 + k * (320 - 175 * k)))
    Kb = k / 1024 * (256 + k * (-128 + k * (74 - 47 * k)))
    ds = Kb * ss * (c2m + Kb / 4 * (cs * (-1 + 2 * c2m ** 2) - Kb / 6 * c2m * (-3 + 4 * ss ** 2) * (-3 + 4 * c2m ** 2)))
    return B * Ka * (s - ds)


datos, esc, srv, http, cod = (leer(n) for n in (
    'datos_actuales', 'escenarios', 'rendimiento_servidor', 'rendimiento_http', 'calidad_codigo'))
md = ['# Resultados de la línea base', '', 'Generado por `scripts/linea_base/resumen.py`. '
      'Todos los escenarios y volúmenes son **simulados**.', '', '## 1. Detección de incidencias', '',
      '| ID | Escenario | Esperado | Obtenido | Antes del cierre | VP | FP | FN |', '|---|---|---|---|---|--:|--:|--:|']
texto = lambda d: ', '.join('%s×%d' % kv for kv in sorted(d.items())) or '—'
tipos, tot, temprano = {}, [0, 0, 0], 0
for e in esc['escenarios']:
    fila = [0, 0, 0]
    for t in set(e['esperado']) | set(e['obtenido']):
        x, o = e['esperado'].get(t, 0), e['obtenido'].get(t, 0)
        v = [min(x, o), max(0, o - x), max(0, x - o)]
        fila = [i + j for i, j in zip(fila, v)]
        tipos[t] = [i + j for i, j in zip(tipos.get(t, [0, 0, 0]), v)]
        temprano += min(x, e['en_curso'].get(t, 0))
    tot = [i + j for i, j in zip(tot, fila)]
    md.append('| %s | %s | %s | %s | %s | %d | %d | %d |' % (
        e['id'], e['nombre'], texto(e['esperado']), texto(e['obtenido']), texto(e['en_curso']), *fila))
vp, fp, fn = tot
exactos = sum(e['esperado'] == e['obtenido'] for e in esc['escenarios'])
md += ['', '| Tipo | VP | FP | FN | Precisión | Exhaustividad |', '|---|--:|--:|--:|--:|--:|']
for t, (a, b, c) in sorted(tipos.items()):
    md.append('| %s | %d | %d | %d | %s | %s |' % (t, a, b, c, pct(a, a + b), pct(a, a + c)))
md.append('| **Total** | %d | %d | %d | **%s** | **%s** |' % (vp, fp, fn, pct(vp, vp + fp), pct(vp, vp + fn)))
md += ['', '- Escenarios con resultado exacto: %d de %d (%s).' % (exactos, len(esc['escenarios']), pct(exactos, len(esc['escenarios']))),
       '- Eventos esperados ya registrados con el recorrido en curso: %d de %d (%s).' % (temprano, vp + fn, pct(temprano, vp + fn)),
       '', '### Métricas calculadas por el sistema en cada escenario cerrado', '',
       '| ID | Cumplimiento | Puntualidad | Paradas | Desviación | Integridad GPS |', '|---|--:|--:|--:|--:|--:|']
for e in esc['escenarios']:
    m = e['metricas']
    if m:
        md.append('| %s | %.0f | %.0f | %.0f | %.1f | %.1f |' % (e['id'], m['pct_cumplimiento_ruta'], m['pct_puntualidad'],
                  m['pct_paradas_cumplidas'], m['pct_desviacion_ruta'], m['integridad_gps_pct']))
md += ['', '## 2. Defectos reproducidos', '', '| Comprobación | Resultado |', '|---|---|']
md += ['| %s | `%s` |' % kv for kv in esc['defectos'].items()]
md.append('| Webhook sin token (copia con módulos actualizados) | HTTP %d |' % http['webhook_sin_token_http'])

md += ['', '## 3. Rendimiento (ms)', '', 'Odoo temporal en el mismo equipo; no incluye red externa ni dibujo en el navegador.', '',
       '| Operación | Posiciones | n | p50 | p95 |', '|---|--:|--:|--:|--:|']
def fila(nombre, n, v):
    md.append('| %s | %s | %d | %.0f | %.0f |' % (nombre, n, len(v), statistics.median(v), p95(v)))
fila('Consultas del dashboard', 'todas', http['dashboard']['ms'])
for n in ('100', '1000', '10000'):
    fila('Calcular métricas (servidor)', n, srv[n]['metricas_ms'])
    fila('Ingerir 1 posición (servidor)', n, srv[n]['ingesta_ms'])
    for clave, nombre in (('mapa', 'Página de mapa'), ('repeticion', 'Datos de repetición'), ('historial_completo', 'Historial completo (RPC)')):
        fila(nombre, n, http['%s_%s' % (clave, n)]['ms'])

cruce = leer('traccar_vs_odoo')
md += ['', '## Completitud Traccar → Odoo', '', '%d de %d posiciones almacenadas en Traccar están en Odoo (%s).'
       % (cruce['en_odoo'], cruce['traccar'], pct(cruce['en_odoo'], cruce['traccar']))]
md += ['', '## 4. Datos en la base del proyecto (solo lectura)', '', '```json',
       json.dumps({k: v for k, v in datos.items() if k != 'paradas_rutas'}, indent=1, ensure_ascii=False), '```',
       '', '## 5. Distancia entre paradas', '',
       '| Ruta | Estimada guardada (km) | Haversine (km) | Geodésica WGS84 (km) | Haversine − geodésica |', '|---|--:|--:|--:|--:|']
for r in datos['paradas_rutas']:
    h, v = (sum(f(a, b) for a, b in zip(r['puntos'], r['puntos'][1:])) / 1000 for f in (haversine, vincenty))
    md.append('| %s | %.3f | %.3f | %.3f | %+.2f %% |' % (r['ruta'], r['estimada_km'], h, v, (h - v) / v * 100))
md += ['', 'Falta la referencia vial (distancia real por calles): medirla en campo o con un trazado.', '',
       '## 6. Código', '', '| Indicador | Valor |', '|---|---|',
       '| Pruebas aprobadas / fallidas / omitidas | %(passed)d / %(failed)d / %(skipped)d |' % cod['pruebas'],
       '| Archivos de prueba que no cargaron | %s |' % (', '.join(cod['archivos_de_prueba_no_cargados']) or 'ninguno'),
       '| Líneas Python (SLOC, sin pruebas) | %d |' % cod['python_sloc'],
       '| Líneas no vacías JS / CSS / XML | %(js)d / %(css)d / %(xml)d |' % cod['lineas_no_vacias'],
       '| Cobertura de líneas Python (aproximada, trazador propio) | %.1f %% (%d de %d) |' % (cod['cobertura_aprox_pct'], cod['lineas_cubiertas'], cod['lineas_ejecutables']),
       '| Funciones / complejidad ciclomática media | %d / %.2f |' % (cod['funciones'], cod['cc_media']),
       '| Funciones con complejidad > 15 | %d |' % len(cod['funciones_cc_mayor_15']), '',
       '| Función compleja | Archivo | CC |', '|---|---|--:|']
md += ['| %s | `%s:%d` | %d |' % (b['funcion'], b['archivo'], b['linea'], b['cc']) for b in cod['funciones_cc_mayor_15']]
(DIR / 'resumen.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
print('\n'.join(md))
