// Capturas de la interfaz con Chrome/Edge en modo headless (protocolo DevTools). Sin dependencias.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [salida] = process.argv.slice(2);
const BASE = 'http://localhost:8099';
const clave = process.env.UI_PASSWORD;
mkdirSync(salida, { recursive: true });
const navegador = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync);
const proceso = spawn(navegador, ['--headless=new', '--remote-debugging-port=9333', '--no-first-run',
  '--hide-scrollbars', `--user-data-dir=${mkdtempSync(join(tmpdir(), 'ui-'))}`, 'about:blank'], { stdio: 'ignore' });
const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

let destino;
for (let i = 0; i < 50 && !destino; i++) {
  await dormir(300);
  try {
    destino = (await (await fetch('http://127.0.0.1:9333/json/list')).json()).find((t) => t.type === 'page');
  } catch { /* el navegador aún arranca */ }
}
const ws = new WebSocket(destino.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let n = 0;
const pendientes = new Map();
const errores = [];
let actual = '';
ws.addEventListener('message', ({ data }) => {
  const m = JSON.parse(data);
  if (m.method === 'Runtime.exceptionThrown') {
    errores.push({ pantalla: actual, error: m.params.exceptionDetails.exception?.description?.slice(0, 200) });
  }
  if (m.id) { pendientes.get(m.id)(m); pendientes.delete(m.id); }
});
const cdp = (method, params = {}) => new Promise((resolve, reject) => {
  pendientes.set(++n, (m) => (m.error ? reject(new Error(m.error.message)) : resolve(m.result)));
  ws.send(JSON.stringify({ id: n, method, params }));
});
const js = async (expression) => (await cdp('Runtime.evaluate',
  { expression, awaitPromise: true, returnByValue: true })).result.value;
const tamano = (width, height, mobile = false) => cdp('Emulation.setDeviceMetricsOverride',
  { width, height, deviceScaleFactor: 1, mobile });
const ir = async (ruta, espera = 5000) => { await cdp('Page.navigate', { url: BASE + ruta }); await dormir(espera); };
const clic = async (selector, texto = '', espera = 4000) => {
  const ok = await js(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(selector)})]
    .find((x) => x.textContent.trim().includes(${JSON.stringify(texto)})); if (e) e.click(); return !!e; })()`);
  if (!ok) errores.push({ pantalla: actual, error: `No se encontró ${selector} ${texto}` });
  await dormir(espera);
};
const hechas = [];
const foto = async (nombre) => {
  actual = nombre;
  const { data } = await cdp('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(salida, nombre + '.png'), Buffer.from(data, 'base64'));
  hechas.push(nombre);
};
const entrar = async (login) => {
  await cdp('Network.clearBrowserCookies');
  await ir('/web/login', 3000);
  const uid = await js(`fetch('/web/session/authenticate', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({jsonrpc: '2.0', params: {db: 'ui_capturas', login: ${JSON.stringify(login)},
    password: ${JSON.stringify(clave)}}})}).then((r) => r.json()).then((r) => r.result && r.result.uid)`);
  if (!uid) throw new Error('No se pudo iniciar sesión con ' + login);
};

try {
  await cdp('Page.enable'); await cdp('Runtime.enable'); await cdp('Network.enable');
  await tamano(1440, 900);
  await entrar('ui_admin');
  await ir('/web#action=fleet_rutas.action_fleet_rutas_dashboard', 12000);
  await clic('.fleet_nav_item', 'Panel'); await foto('01_panel');
  for (const [nombre, pestana] of [['02_monitoreo', 'Monitoreo en vivo'], ['03_recorridos', 'Recorridos']]) {
    await clic('.fleet_nav_item', pestana, 7000); await foto(nombre);
  }
  // Se abre el primer recorrido con incidencias, que es el que tiene contenido.
  if (!await js(`(() => { const fila = [...document.querySelectorAll('.uta-table tbody tr')]
    .find((f) => f.textContent.includes('Con incidencias'));
    fila?.querySelector('button[title="Horarios"]').click(); return !!fila; })()`)) {
    errores.push({ pantalla: actual, error: 'No hay un recorrido con incidencias' });
  }
  await dormir(4000); await foto('04_recorrido_horarios');
  await clic('.fleet_subtabs button', 'Mapa', 7000); await foto('05_recorrido_mapa');
  await clic('.fleet_subtabs button', 'Incidencias'); await foto('05b_recorrido_incidencias');
  await clic('.fleet_nav_item', 'Rutas y programación'); await foto('06_rutas');
  await clic('.fleet_subtabs button', 'Programación'); await foto('07_programacion');
  await clic('.fleet_nav_item', 'Métricas'); await foto('08_metricas');
  await clic('.fleet_nav_item', 'Sincronización'); await foto('09_sincronizacion');
  await clic('.fleet_nav_item', 'Dashboard Grafana', 8000); await foto('10_grafana');
  await ir('/web#action=fleet_rutas.action_fleet_recorrido&view_type=list'); await foto('11_lista_recorridos');
  await ir('/web#action=fleet_rutas.action_fleet_incidencia&view_type=list'); await foto('12_lista_incidencias');
  await ir('/web#action=fleet_rutas.action_fleet_metricas&view_type=list'); await foto('13_lista_metricas');
  await tamano(390, 844, true);
  await ir('/web#action=fleet_rutas.action_fleet_rutas_dashboard', 10000);
  await clic('.fleet_nav_item', 'Panel'); await foto('14_panel_movil');
  await entrar('ui_pasajero');
  await ir('/flota/app', 9000); await foto('15_pasajero_en_vivo');
  await clic('[data-tab="history"]', '', 4000); await foto('16_pasajero_recorridos');
  await clic('[data-tab="alerts"]', '', 3000); await foto('17_pasajero_avisos');
} finally {
  console.log(JSON.stringify({ capturas: hechas, errores }, null, 1));
  ws.close();
  proceso.kill();
}
