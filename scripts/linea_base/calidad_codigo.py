"""Tamaño, complejidad, mantenibilidad, pruebas y cobertura aproximada del código propio.

Cobertura: trazador propio de líneas (no coverage.py). Genera coverage.xml (Cobertura)
para que SonarQube pueda leerlo. Requiere radon y pytest.
"""
import json
import subprocess
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import quoteattr

import pytest
from radon.complexity import cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze

RAIZ = Path(__file__).resolve().parents[2]
ADDONS = RAIZ / 'addons'
SALIDA = RAIZ / 'docs' / 'mejora_continua' / 'linea_base'
fuentes = [p for p in ADDONS.rglob('*.py') if 'tests' not in p.parts and p.name != '__manifest__.py']

ejecutadas = {}
objetivo = {str(p): p for p in fuentes}


def trazar(frame, evento, arg):
    archivo = frame.f_code.co_filename
    if archivo not in objetivo:
        return None
    lineas = ejecutadas.setdefault(archivo, set())
    lineas.add(frame.f_lineno)
    return trazar


ARGS = [str(ADDONS / 'fleet_rutas' / 'tests'), '-q', '--import-mode=importlib', '-p', 'no:cacheprovider',
        '--continue-on-collection-errors']

# 1) Resultado de las pruebas SIN trazador (el trazado distorsiona las pruebas de tiempo).
with tempfile.TemporaryDirectory() as tmp:
    informe = Path(tmp) / 'junit.xml'
    subprocess.run([sys.executable, '-m', 'pytest', *ARGS, '--junitxml=%s' % informe], capture_output=True)
    casos = ET.parse(informe).getroot().findall('.//testcase')
pruebas = {'passed': 0, 'failed': 0, 'skipped': 0}
no_cargados = []
for caso in casos:
    error = caso.find('error')
    if error is not None and 'collection' in error.get('message', ''):
        no_cargados.append(caso.get('name'))
    elif caso.find('failure') is not None or error is not None:
        pruebas['failed'] += 1
    elif caso.find('skipped') is not None:
        pruebas['skipped'] += 1
    else:
        pruebas['passed'] += 1

# 2) Segunda ejecución solo para registrar líneas cubiertas.
sys.settrace(trazar)
threading.settrace(trazar)
pytest.main(ARGS)
sys.settrace(None)


def lineas_ejecutables(codigo):
    lineas = {l for _, _, l in codigo.co_lines() if l}
    for c in codigo.co_consts:
        if hasattr(c, 'co_lines'):
            lineas |= lineas_ejecutables(c)
    return lineas


archivos, bloques = [], []
for p in sorted(fuentes):
    texto = p.read_text(encoding='utf-8-sig')
    crudo = analyze(texto)
    ejecutables = lineas_ejecutables(compile(texto, str(p), 'exec'))
    cubiertas = ejecutables & ejecutadas.get(str(p), set())
    rel = p.relative_to(RAIZ).as_posix()
    archivos.append({'archivo': rel, 'sloc': crudo.sloc, 'mi': round(mi_visit(texto, True), 1),
                     'ejecutables': len(ejecutables), 'cubiertas': len(cubiertas),
                     '_lineas': sorted(ejecutables), '_hit': cubiertas})
    for b in cc_visit(texto):
        if not hasattr(b, 'methods'):
            bloques.append({'archivo': rel, 'funcion': getattr(b, 'fullname', b.name),
                            'linea': b.lineno, 'cc': b.complexity})

clases = []
for a in archivos:
    lineas = ''.join('<line number="%d" hits="%d"/>' % (l, l in a['_hit']) for l in a['_lineas'])
    clases.append('<class name=%s filename=%s><lines>%s</lines></class>' % (
        quoteattr(a['archivo']), quoteattr(a['archivo']), lineas))
(RAIZ / 'coverage.xml').write_text(
    '<?xml version="1.0"?><coverage version="1"><sources><source>.</source></sources><packages>'
    '<package name="addons"><classes>%s</classes></package></packages></coverage>' % ''.join(clases),
    encoding='utf-8')

web = {}
for ext in ('js', 'css', 'xml'):
    web[ext] = sum(len([l for l in p.read_text(encoding='utf-8-sig').splitlines() if l.strip()])
                   for p in ADDONS.rglob('*.' + ext))
total_e = sum(a['ejecutables'] for a in archivos)
total_c = sum(a['cubiertas'] for a in archivos)
for a in archivos:
    del a['_lineas'], a['_hit']
out = {'pruebas': pruebas, 'archivos_de_prueba_no_cargados': no_cargados,
       'python_sloc': sum(a['sloc'] for a in archivos), 'lineas_no_vacias': web,
       'cobertura_aprox_pct': round(total_c / total_e * 100, 1), 'lineas_ejecutables': total_e,
       'lineas_cubiertas': total_c, 'funciones': len(bloques),
       'cc_media': round(sum(b['cc'] for b in bloques) / len(bloques), 2),
       'funciones_cc_mayor_15': sorted([b for b in bloques if b['cc'] > 15], key=lambda b: -b['cc']),
       'archivos': archivos}
SALIDA.mkdir(parents=True, exist_ok=True)
(SALIDA / 'calidad_codigo.json').write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding='utf-8')
print(json.dumps({k: v for k, v in out.items() if k != 'archivos'}, indent=1, ensure_ascii=False))
