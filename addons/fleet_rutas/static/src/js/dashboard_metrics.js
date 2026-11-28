/** @odoo-module **/
/** Cálculos del dashboard sobre los registros leídos. Sin dependencias, para poder probarlos. */

export const toDate = (value) => (value ? new Date(value.replace(" ", "T") + "Z") : null);

const DAY = 86400000;

/** "auto" muestra datos reales si ya hay recorridos reales medidos; nunca los mezcla. */
export function resolveOrigin(requested, trips, metrics) {
  if (requested !== "auto") return requested;
  const measured = new Set(metrics.map((m) => m.recorrido_id[0]));
  return trips.some((t) => !t.simulado && measured.has(t.id)) ? "real" : "simulado";
}

export function periodRange(days, now = Date.now()) {
  if (!days) return { current: null, previous: null };
  const span = Number(days) * DAY;
  return {
    current: [now - span, now],
    previous: [now - 2 * span, now - span],
  };
}

export function selectTrips(trips, { routeId, origin, range }) {
  return trips.filter((t) => {
    if (routeId && t.ruta_id[0] !== Number(routeId)) return false;
    if (origin === "real" && t.simulado) return false;
    if (origin === "simulado" && !t.simulado) return false;
    if (!range) return true;
    const start = toDate(t.fecha_inicio).getTime();
    return start >= range[0] && start < range[1];
  });
}

const average = (rows, field) =>
  rows.length ? rows.reduce((sum, row) => sum + Number(row[field] || 0), 0) / rows.length : null;

/** Un valor null significa "sin muestra", que no es lo mismo que cero. */
export function summarize(trips, metrics, incidents) {
  const ids = new Set(trips.map((t) => t.id));
  const measured = metrics.filter((m) => ids.has(m.recorrido_id[0]));
  const events = incidents.filter((i) => ids.has(i.recorrido_id[0]));
  const measuredIds = new Set(measured.map((m) => m.recorrido_id[0]));
  const hours = measured.reduce((sum, m) => sum + Number(m.duracion_real_min || 0), 0) / 60;
  const measuredEvents = events.filter((i) => measuredIds.has(i.recorrido_id[0])).length;
  return {
    trips: trips.length,
    measured: measured.length,
    incidents: events.length,
    pct_cumplimiento_ruta: average(measured, "pct_cumplimiento_ruta"),
    pct_puntualidad: average(measured, "pct_puntualidad"),
    retraso_promedio_min: average(measured, "retraso_promedio_min"),
    pct_paradas_cumplidas: average(measured, "pct_paradas_cumplidas"),
    pct_desviacion_ruta: average(measured, "pct_desviacion_ruta"),
    diferencia_distancia_km: average(measured, "diferencia_distancia_km"),
    distancia_real_km: average(measured, "distancia_real_km"),
    duracion_real_min: average(measured, "duracion_real_min"),
    frecuencia_incidencias: hours > 0 ? measuredEvents / hours : null,
    integridad_gps_pct: average(measured, "integridad_gps_pct"),
    exactitud_sincronizacion_pct: average(
      measured.filter((m) => m.calidad_sync_disponible), "exactitud_sincronizacion_pct"),
    tiempo_respuesta_ms: average(measured, "tiempo_respuesta_ms"),
    tasa_verdaderos_positivos_pct: average(
      measured.filter((m) => m.deteccion_validada), "tasa_verdaderos_positivos_pct"),
  };
}

export function formatValue(value, digits = 1) {
  return value === null || value === undefined ? "Sin muestra" : value.toFixed(digits);
}

/** better: 1 si subir es mejorar, -1 si bajar es mejorar, 0 si no se juzga. */
export function compare(current, previous, better) {
  if (current === null || previous === null) return { text: "Sin período anterior comparable", tone: "" };
  const change = current - previous;
  if (Math.abs(change) < 0.05) return { text: "Igual que el período anterior", tone: "" };
  const tone = !better ? "" : change * better > 0 ? "up" : "down";
  return {
    text: `${change > 0 ? "▲" : "▼"} ${Math.abs(change).toFixed(1)} frente al período anterior`,
    tone,
  };
}

export function byRoute(routes, trips, metrics, incidents) {
  return routes.map((route) => ({
    id: route.id,
    name: route.name,
    distance: route.distancia_estimada_km,
    ...summarize(trips.filter((t) => t.ruta_id[0] === route.id), metrics, incidents),
  }));
}

/** Puntualidad y cumplimiento por día local, para los últimos días con mediciones. */
export function dailyTrend(trips, metrics, incidents, limit = 14) {
  const measured = new Set(metrics.map((m) => m.recorrido_id[0]));
  const days = new Map();
  for (const trip of trips) {
    if (!measured.has(trip.id)) continue;
    const date = toDate(trip.fecha_inicio);
    const key = [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"),
      String(date.getDate()).padStart(2, "0")].join("-");
    if (!days.has(key)) days.set(key, []);
    days.get(key).push(trip);
  }
  return [...days.keys()].sort().slice(-limit).map((key) => ({
    key,
    label: `${key.slice(8, 10)}/${key.slice(5, 7)}`,
    ...summarize(days.get(key), metrics, incidents),
  }));
}

/** Barras proporcionales al tipo más frecuente, de mayor a menor. */
export function incidentsByType(types, trips, incidents) {
  const ids = new Set(trips.map((t) => t.id));
  const selected = incidents.filter((i) => ids.has(i.recorrido_id[0]));
  const rows = Object.entries(types).map(([type, name]) => ({
    type,
    name,
    count: selected.filter((i) => i.tipo === type).length,
  }));
  const max = Math.max(1, ...rows.map((r) => r.count));
  return rows
    .map((r) => ({ ...r, width: (r.count / max) * 100, share: selected.length ? (r.count / selected.length) * 100 : 0 }))
    .sort((a, b) => b.count - a.count);
}
