"""Exercise real controller functions without requiring a running Odoo server."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]


class Denied(Exception):
    pass


def function(path, name, namespace=None):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    candidates = list(tree.body) + [n for cls in tree.body if isinstance(cls, ast.ClassDef) for n in cls.body]
    fn = next(n for n in candidates if isinstance(n, ast.FunctionDef) and n.name == name)
    fn.decorator_list = []
    scope = {'urlsplit': urlsplit, 'Forbidden': Denied, 'BadRequest': Denied, 'json': json}
    scope.update(namespace or {})
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), '<mobile>', 'exec'), scope)
    return scope[name]


@pytest.mark.parametrize('endpoint', [
    'http://127.0.0.1/secret', 'https://traccar:8082/api',
    'https://fcm.googleapis.com.attacker.example/send',
    'https://fcm.googleapis.com@127.0.0.1/',
    'https://fcm.googleapis.com:8082/send',
    'https://user:pass@fcm.googleapis.com/send',
    'https://fcm.googleapis.com/send#fragment',
    'file:///etc/passwd', 'https://[broken', '', None,
])
def test_push_rejects_internal_or_untrusted_destinations(endpoint):
    assert not function('models/fleet_mobile.py', 'valid_push_endpoint')(endpoint)


@pytest.mark.parametrize('endpoint', [
    'https://fcm.googleapis.com/fcm/send/token',
    'https://updates.push.services.mozilla.com/wpush/v2/token',
    'https://web.push.apple.com/token',
    'https://wns2-db5p.notify.windows.com/token',
])
def test_push_accepts_known_providers(endpoint):
    assert function('models/fleet_mobile.py', 'valid_push_endpoint')(endpoint)


@pytest.mark.parametrize('groups,allowed', [
    (set(), False), ({'base.group_user'}, False),
    ({'fleet_rutas.group_fleet_admin'}, False),
    ({'fleet_rutas.group_mobile_user', 'base.group_user'}, False),
    ({'fleet_rutas.group_mobile_user', 'base.group_portal'}, True),
])
def test_pwa_is_exclusive_to_passengers(groups, allowed):
    user = SimpleNamespace(has_group=lambda group: group in groups)
    guard = function('controllers/mobile.py', 'mobile_user', {'request': SimpleNamespace(env=SimpleNamespace(user=user))})
    if allowed:
        assert guard() is user
    else:
        with pytest.raises(Denied):
            guard()


def test_route_scope_uses_authenticated_user():
    assert function('controllers/mobile.py', 'route_domain')(SimpleNamespace(id=42)) == [('mobile_user_ids', 'in', [42])]


def test_track_refuses_trip_from_another_users_route_before_reading_gps():
    routes = SimpleNamespace(ids=[10])
    route_model, trip_model = MagicMock(), MagicMock()
    route_model.sudo.return_value.search.return_value = routes
    trip_model.sudo.return_value.search.return_value = False
    env = {'fleet.ruta': route_model, 'fleet.recorrido': trip_model}
    req = SimpleNamespace(env=env, not_found=lambda: '404')
    track = function('controllers/mobile.py', 'track', {'request': req,
        'mobile_user': lambda: SimpleNamespace(id=42),
        'route_domain': lambda user: [('mobile_user_ids', 'in', [user.id])]})
    assert track(None, 9999) == '404'
    trip_model.sudo.return_value.search.assert_called_once_with([
        ('id', '=', 9999), ('ruta_id', 'in', [10])], limit=1)


def test_old_admin_endpoints_reject_passenger():
    user = SimpleNamespace(has_group=lambda group: False)
    guard = function('controllers/mapa.py', '_require_admin', {'request': SimpleNamespace(env=SimpleNamespace(user=user))})
    with pytest.raises(Denied):
        guard(None)


def test_admin_cannot_query_passenger_api_by_forging_query_parameters():
    req = SimpleNamespace(env=SimpleNamespace(user=SimpleNamespace(has_group=lambda g: g == 'fleet_rutas.group_fleet_admin')))
    mobile_user = function('controllers/mobile.py', 'mobile_user', {'request': req})
    state = function('controllers/mobile.py', 'state', {'mobile_user': mobile_user})
    with pytest.raises(Denied):
        state(None, user_id=123, route_id=1)


def test_mobile_posts_keep_odoo_csrf_enabled():
    tree = ast.parse((ROOT / 'controllers/mobile.py').read_text(encoding='utf-8'))
    post_routes = [d for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                   for d in n.decorator_list if isinstance(d, ast.Call)
                   and any(k.arg == 'methods' and 'POST' in ast.literal_eval(k.value) for k in d.keywords)]
    assert post_routes
    assert all(not any(k.arg == 'csrf' and ast.literal_eval(k.value) is False for k in route.keywords) for route in post_routes)
