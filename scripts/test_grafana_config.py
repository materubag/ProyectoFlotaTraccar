"""Pruebas sin servidor Odoo para resolución de URLs de navegador."""
import ast
import unittest
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


source = (Path(__file__).resolve().parents[1] /
          'addons/fleet_reports/models/fleet_reports_dashboard.py').read_text(encoding='utf-8')
function = next(node for node in ast.parse(source).body
                if isinstance(node, ast.FunctionDef) and node.name == 'grafana_browser_url')
namespace = {'urlsplit': urlsplit, 'urlunsplit': urlunsplit}
exec(compile(ast.Module(body=[function], type_ignores=[]), '<grafana_browser_url>', 'exec'), namespace)
resolve = namespace['grafana_browser_url']


class BrowserUrlTests(unittest.TestCase):
    def test_remote_browser_uses_server_not_its_own_localhost(self):
        for legacy in ('', 'http://localhost:3000', 'http://127.0.0.1:3000', 'http://grafana:3000'):
            with self.subTest(legacy=legacy):
                self.assertEqual(resolve(legacy, 'http://192.168.1.20:8070/'), 'http://192.168.1.20:3000')

    def test_local_browser(self):
        self.assertEqual(resolve('', 'http://localhost:8070/'), 'http://localhost:3000')

    def test_custom_published_port(self):
        self.assertEqual(resolve('', 'http://flota.local:8070/', '3300'), 'http://flota.local:3300')
        self.assertEqual(resolve('http://localhost:3300', 'http://flota.local/'), 'http://flota.local:3300')

    def test_ipv6(self):
        self.assertEqual(resolve('', 'http://[2001:db8::1]:8070/'), 'http://[2001:db8::1]:3000')

    def test_explicit_https_proxy_preserved(self):
        self.assertEqual(resolve('https://metrics.example.com/grafana/', 'https://flota.example.com/'),
                         'https://metrics.example.com/grafana')

    def test_no_embedded_credentials_or_non_http_urls(self):
        for url in ('javascript:alert(1)', 'ftp://metrics.example.com', 'https://user:pass@metrics.example.com'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                resolve(url, 'http://flota.local/')

    def test_invalid_port(self):
        for port in (0, 65536):
            with self.subTest(port=port), self.assertRaises(ValueError):
                resolve('', 'http://flota.local/', port)


if __name__ == '__main__':
    unittest.main()
