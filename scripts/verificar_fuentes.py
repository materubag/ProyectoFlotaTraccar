"""Static source checks; this does not replace installation under Odoo 16."""
import ast
import csv
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

root = Path(__file__).resolve().parents[1]
counts = {'python': 0, 'xml': 0, 'json': 0, 'access_csv': 0, 'owl_templates': 0}
for path in (root / 'addons').rglob('*.py'):
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    counts['python'] += 1
for path in (root / 'addons').rglob('*.xml'):
    ET.parse(path)
    counts['xml'] += 1
for path in (root / 'config').rglob('*.json'):
    json.loads(path.read_text(encoding='utf-8'))
    counts['json'] += 1
for path in (root / 'addons').rglob('ir.model.access.csv'):
    rows = list(csv.DictReader(path.open(encoding='utf-8')))
    assert len({row['id'] for row in rows}) == len(rows), path
    for row in rows:
        assert row['group_id:id'], path
        assert all(row[key] in ('0', '1') for key in ('perm_read', 'perm_write', 'perm_create', 'perm_unlink'))
    counts['access_csv'] += 1
for path in (root / 'addons').rglob('__manifest__.py'):
    manifest = ast.literal_eval(path.read_text(encoding='utf-8'))
    for name in manifest.get('data', []) + manifest.get('demo', []):
        assert (path.parent / name).is_file(), name
for path in (root / 'addons').rglob('*.js'):
    for template in re.findall(r'xml/\* xml \*/`(.*?)`', path.read_text(encoding='utf-8'), re.S):
        ET.fromstring(template)
        counts['owl_templates'] += 1
print(json.dumps({'status': 'ok', 'checks': counts}, ensure_ascii=False, indent=2))
