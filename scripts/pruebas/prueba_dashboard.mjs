// Pruebas de los cálculos del dashboard.  Uso desde la raíz:  node scripts/pruebas/prueba_dashboard.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const fuente = readFileSync(new URL('../../addons/fleet_rutas/static/src/js/dashboard_metrics.js', import.meta.url), 'utf8');
const m = await import('data:text/javascript;base64,' + Buffer.from(fuente).toString('base64'));

const viaje = (id, ruta, simulado, fecha) => ({ id, ruta_id: [ruta, 'R' + ruta], simulado, fecha_inicio: fecha });
const medida = (id, extra) => ({ recorrido_id: [id, ''], duracion_real_min: 30, pct_puntualidad: 100, ...extra });
const trips = [viaje(1, 1, false, '2026-11-27 12:00:00'), viaje(2, 1, true, '2026-11-27 13:00:00'),
  viaje(3, 2, false, '2026-11-10 12:00:00')];
const metrics = [medida(1, { pct_puntualidad: 80, calidad_sync_disponible: true, exactitud_sincronizacion_pct: 90 }),
  medida(2, { pct_puntualidad: 20 }), medida(3, { pct_puntualidad: 60 })];
const incidents = [{ recorrido_id: [1, ''], tipo: 'retraso' }, { recorrido_id: [1, ''], tipo: 'retraso' },
  { recorrido_id: [1, ''], tipo: 'desviacion' }, { recorrido_id: [2, ''], tipo: 'desviacion' }];
const ahora = Date.parse('2026-11-28T00:00:00Z');
const casos = [];
const caso = (nombre, fn) => casos.push([nombre, fn]);

caso('auto elige datos reales si existen', () => assert.equal(m.resolveOrigin('auto', trips, metrics), 'real'));
caso('auto usa simulados si no hay reales medidos', () =>
  assert.equal(m.resolveOrigin('auto', trips, [metrics[1]]), 'simulado'));
caso('no mezcla reales y simulados', () =>
  assert.deepEqual(m.selectTrips(trips, { origin: 'real' }).map((t) => t.id), [1, 3]));
caso('período actual y anterior', () => {
  const r = m.periodRange(7, ahora);
  assert.deepEqual(m.selectTrips(trips, { origin: 'todos', range: r.current }).map((t) => t.id), [1, 2]);
  assert.equal(m.selectTrips(trips, { origin: 'todos', range: r.previous }).length, 0);
  assert.equal(m.periodRange('', ahora).current, null);
});
caso('filtra por ruta', () => assert.deepEqual(m.selectTrips(trips, { routeId: '2', origin: 'todos' }).map((t) => t.id), [3]));
caso('promedios e incidencias por hora', () => {
  const s = m.summarize([trips[0]], metrics, incidents);
  assert.equal(s.pct_puntualidad, 80);
  assert.equal(s.incidents, 3);
  assert.equal(s.frecuencia_incidencias, 6);
  assert.equal(s.exactitud_sincronizacion_pct, 90);
});
caso('sin muestra no es cero', () => {
  const s = m.summarize([], metrics, incidents);
  assert.equal(s.pct_puntualidad, null);
  assert.equal(s.frecuencia_incidencias, null);
  assert.equal(m.formatValue(s.pct_puntualidad), 'Sin muestra');
  assert.equal(m.formatValue(0), '0.0');
  assert.equal(m.summarize([trips[1]], metrics, incidents).exactitud_sincronizacion_pct, null);
});
caso('comparación según qué dirección es mejor', () => {
  assert.equal(m.compare(90, 80, 1).tone, 'up');
  assert.equal(m.compare(5, 3, -1).tone, 'down');
  assert.equal(m.compare(5, null, 1).tone, '');
  assert.equal(m.compare(5, 5, 1).tone, '');
});
caso('comparación por ruta', () => {
  const r = m.byRoute([{ id: 1, name: 'A' }, { id: 2, name: 'B' }], trips, metrics, incidents);
  assert.deepEqual(r.map((x) => x.pct_puntualidad), [50, 60]);
});
caso('evolución diaria ordenada', () => {
  const d = m.dailyTrend(trips, metrics, incidents);
  assert.equal(d.length, 2);
  assert.ok(d[0].key < d[1].key);
});
caso('barras proporcionales y ordenadas', () => {
  const b = m.incidentsByType({ desviacion: 'D', retraso: 'R', velocidad: 'V' }, trips.slice(0, 1), incidents);
  assert.deepEqual(b.map((x) => [x.type, x.count, x.width]), [['retraso', 2, 100], ['desviacion', 1, 50], ['velocidad', 0, 0]]);
});

let fallos = 0;
for (const [nombre, fn] of casos) {
  try { fn(); console.log('ok  ', nombre); } catch (e) { fallos++; console.log('FALLA', nombre, e.message); }
}
console.log(`${casos.length - fallos} de ${casos.length} correctas`);
process.exit(fallos ? 1 : 0);
