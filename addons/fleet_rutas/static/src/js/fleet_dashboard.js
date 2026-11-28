/** @odoo-module **/
/** Vistas de lectura: solo consulta registros y métricas existentes mediante el ORM. */
import { Component, useState, onMounted, onWillUnmount, useRef, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
const TABS = [
  { id: "panel", label: "Panel", icon: "fa-dashboard" },
  { id: "monitoreo", label: "Monitoreo en vivo", icon: "fa-map-marker" },
  { id: "recorridos", label: "Recorridos", icon: "fa-road" },
  { id: "rutas", label: "Rutas y programación", icon: "fa-calendar" },
  { id: "metricas", label: "Métricas", icon: "fa-bar-chart" },
  { id: "sync", label: "Sincronización", icon: "fa-refresh" },
  { id: "grafana", label: "Dashboard Grafana", icon: "fa-line-chart" },
  { id: "traccar", label: "Traccar", icon: "fa-globe" },
];
const STATES = {
  programado: "Programado",
  en_curso: "En curso",
  completado: "Completado",
  con_incidencias: "Con incidencias",
  cancelado: "Cancelado",
};
const TYPES = {
  retraso: "Retraso",
  parada_omitida: "Parada omitida",
  desviacion: "Desvío",
  incompleto: "Recorrido incompleto",
  senal_perdida: "Pérdida de señal",
  velocidad: "Exceso de velocidad",
};
const METRICS = [
  [
    "Cumplimiento de rutas",
    "Media de recorridos que cumplen × 100",
    "pct_cumplimiento_ruta",
    "%",
    "Cumplimiento del trazado y puntos de control",
  ],
  [
    "Puntualidad",
    "Paradas dentro de tolerancia / programadas × 100",
    "pct_puntualidad",
    "%",
    "Incluye las omisiones en el total programado",
  ],
  [
    "Retraso promedio",
    "Σ retrasos positivos / paradas visitadas",
    "retraso_promedio_min",
    "min",
    "Los adelantos no compensan los retrasos",
  ],
  [
    "Paradas cumplidas",
    "Visitadas / programadas × 100",
    "pct_paradas_cumplidas",
    "%",
    "Puntos alcanzados dentro de su radio",
  ],
  [
    "Desviación de ruta",
    "Posiciones fuera del corredor / posiciones × 100",
    "pct_desviacion_ruta",
    "%",
    "Depende del trazado de referencia",
  ],
  [
    "Diferencia de distancia",
    "Distancia GPS − distancia estimada",
    "diferencia_distancia_km",
    "km",
    "Positivo: mayor distancia recorrida",
  ],
  [
    "Tiempo de recorrido",
    "Fin real − inicio real",
    "duracion_real_min",
    "min",
    "Duración de los recorridos evaluados",
  ],
  [
    "Frecuencia de incidencias",
    "Eventos / horas de operación",
    "frecuencia_incidencias",
    "inc/h",
    "Frecuencia de eventos detectados",
  ],
  [
    "Integridad GPS",
    "(1 − segundos sin señal / duración) × 100",
    "integridad_gps_pct",
    "%",
    "Continuidad de la telemetría en la ventana evaluada",
  ],
  [
    "Exactitud Traccar–Odoo",
    "Posiciones coincidentes / comparadas × 100",
    "exactitud_sincronizacion_pct",
    "%",
    "Comparación con el JSON recibido; requiere muestra",
  ],
  [
    "Tiempo del cálculo",
    "Fin de evaluación − comienzo",
    "tiempo_respuesta_ms",
    "ms",
    "Tiempo parcial: excluye red e interfaz",
  ],
  [
    "Precisión de incidencias",
    "Verdaderos positivos / eventos validados × 100",
    "tasa_verdaderos_positivos_pct",
    "%",
    "Requiere validación humana; no mide falsos negativos",
  ],
];
class FleetRutasDashboard extends Component {
  setup() {
    this.rpc = useService("rpc");
    this.actionService = useService("action");
    this.routeImportInput = useRef("routeImportInput");
    this.tabs = TABS;
    let saved = {};
    try {
      saved = JSON.parse(
        sessionStorage.getItem("fleet_dashboard_navigation") || "{}",
      );
    } catch (e) {}
    const old = sessionStorage.getItem("fleet_dashboard_tab");
    this.state = useState({
      tab: TABS.some((t) => t.id === (saved.tab || old))
        ? saved.tab || old
        : "panel",
      routeTab: saved.routeTab === "programacion" ? "programacion" : "lista",
      tripTab: ["mapa", "repeticion", "cronologia", "incidencias"].includes(saved.tripTab)
        ? saved.tripTab
        : "mapa",
      tripId: saved.tripId || null,
      activeId: null,
      routeId: null,
      routeFilter: "",
      period: "",
      search: "",
      trips: [],
      routes: [],
      stops: [],
      vehicles: [],
      metrics: [],
      incidents: [],
      syncs: [],
      detailStops: [],
      activeChecks: [],
      detailIncidents: [],
      loading: true,
      detailLoading: false,
      error: "",
      detailError: "",
      syncBusy: false,
      syncMessage: "",
      traccarUrl: "",
      traccarError: "",
      updated: "",
    });
    this.disposed = false;
    this.inFlight = false;
    this.detailRequest = 0;
    onMounted(() => {
      if (this.state.tab === "traccar") this.loadTraccarUrl();
      this.loadData();
      this.timer = setInterval(() => this.loadData(), 5000);
    });
    onWillUnmount(() => {
      this.disposed = true;
      this.save();
      clearInterval(this.timer);
    });
  }
  save() {
    try {
      sessionStorage.setItem("fleet_dashboard_tab", this.state.tab);
      sessionStorage.setItem(
        "fleet_dashboard_navigation",
        JSON.stringify({
          tab: this.state.tab,
          routeTab: this.state.routeTab,
          tripTab: this.state.tripTab,
          tripId: this.state.tripId,
        }),
      );
    } catch (e) {}
  }
  setTab(id) {
    this.state.tab = id;
    this.save();
    if (id === "traccar") this.loadTraccarUrl();
  }
  async loadTraccarUrl() {
    this.state.traccarError = "";
    try {
      this.state.traccarUrl = await this.call("fleet.traccar.sync", "get_traccar_web_url");
    } catch (e) {
      this.state.traccarError =
        e?.data?.message || "No se pudo obtener la dirección de Traccar.";
    }
  }
  get traccarBlocked() {
    return window.location.protocol === "https:" && this.state.traccarUrl.startsWith("http:");
  }
  setRouteTab(id) {
    this.state.routeTab = id;
    this.save();
  }
  openNewRoute() {
    window.open("/fleet_rutas/rutas/nueva", "_blank");
  }
  openEditRoute() {
    if (!this.selectedRoute) return;
    window.open("/fleet_rutas/rutas/nueva?route_id=" + this.selectedRoute.id, "_blank");
  }
  openRoutePath() {
    if (!this.selectedRoute) return;
    window.open("/fleet_rutas/trazado/" + this.selectedRoute.id, "_blank");
  }
  async exportRoute() {
    if (!this.selectedRoute) return;
    const response = await fetch(
      "/fleet_rutas/rutas/" + this.selectedRoute.id + "/exportar",
    );
    if (!response.ok) {
      alert("No se pudo exportar la ruta.");
      return;
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    const filename = match?.[1] || "ruta.json";
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }
  async importRouteFile(event) {
    const input = event.target;
    const file = input.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const response = await fetch("/fleet_rutas/rutas/importar", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: text,
      });
      let result = {};
      try {
        result = await response.json();
      } catch (e) {
        alert("Odoo no pudo procesar la importación. Actualiza la página e intenta nuevamente.");
        return;
      }
      if (!response.ok) {
        alert(result.message || "No se pudo importar la ruta.");
        return;
      }
      const skipped = result.schedules_skipped?.length
        ? "\nVehículos no encontrados: " + result.schedules_skipped.join(", ")
        : "";
      alert(
        "Ruta importada como " + result.route_code +
        ". Programaciones creadas: " + result.schedules_created + "." +
        skipped,
      );
      await this.loadData();
    } catch (e) {
      alert("No se pudo leer el archivo de ruta.");
    } finally {
      input.value = "";
    }
  }
  openRouteImport() {
    this.routeImportInput.el?.click();
  }
  setTripTab(id) {
    this.state.tripTab = id;
    this.save();
  }
  async call(model, method, args = [], kwargs = {}) {
    return this.rpc("/web/dataset/call_kw", { model, method, args, kwargs });
  }
  async rows(model, fields, domain = [], order = "id desc") {
    const result = [];
    let batch;
    do {
      batch = await this.call(model, "search_read", [], {
        domain,
        fields,
        order,
        offset: result.length,
        limit: 200,
      });
      result.push(...batch);
    } while (batch.length === 200);
    return result;
  }
  async loadData() {
    if (this.inFlight || this.disposed) return;
    this.inFlight = true;
    try {
      const [trips, routes, stops, vehicles, metrics, incidents, syncs] =
        await Promise.all([
          this.rows(
            "fleet.recorrido",
            [
              "name",
              "ruta_id",
              "vehicle_id",
              "fecha_inicio",
              "fecha_fin_estimada",
              "fecha_inicio_real",
              "fecha_fin_real",
              "estado",
              "simulado",
              "distancia_real_km",
              "porcentaje_paradas_cumplidas",
              "tiene_desviacion",
            ],
            [],
            "fecha_inicio desc, id desc",
          ),
          this.rows("fleet.ruta", [
            "name",
            "code",
            "estado",
            "origen",
            "destino",
            "distancia_estimada_km",
            "duracion_estimada_min",
          ]),
          this.rows(
            "fleet.parada",
            [
              "name",
              "ruta_id",
              "secuencia",
              "hora_prevista",
              "tolerancia_min",
              "radio_proximidad_m",
              "latitud",
              "longitud",
            ],
            [],
            "secuencia,id",
          ),
          this.rows("fleet.vehicle", [
            "display_name",
            "license_plate",
            "traccar_device_id",
            "traccar_unique_id",
            "traccar_device_status",
            "traccar_last_update",
            "traccar_last_latitude",
            "traccar_last_longitude",
            "traccar_last_speed",
          ]),
          this.rows("fleet.metricas.recorrido", [
            "recorrido_id",
            "ruta_id",
            "fecha_recorrido",
            "calidad_sync_disponible",
            "deteccion_validada",
            ...METRICS.map((m) => m[2]),
          ]),
          this.rows(
            "fleet.incidencia",
            ["recorrido_id", "tipo", "timestamp", "descripcion", "resuelta"],
            [],
            "timestamp desc,id desc",
          ),
          this.call("fleet.traccar.sync", "search_read", [], {
            domain: [],
            fields: [
              "fecha_inicio",
              "estado",
              "registros_procesados",
              "registros_nuevos",
              "registros_duplicados",
              "registros_error",
              "error_mensaje",
            ],
            limit: 1,
            order: "id desc",
          }),
        ]);
      if (this.disposed) return;
      Object.assign(this.state, {
        trips,
        routes,
        stops,
        vehicles,
        metrics,
        incidents,
        syncs,
        loading: false,
        error: "",
        updated: new Date().toLocaleTimeString("es-EC"),
      });
      if (this.state.tripId && !trips.some((t) => t.id === this.state.tripId))
        this.state.tripId = null;
      const activeIds = trips
        .filter((t) => t.estado === "en_curso")
        .map((t) => t.id);
      this.state.activeChecks = activeIds.length
        ? await this.rows(
            "fleet.cumplimiento.parada",
            ["recorrido_id", "parada_id", "cumplida", "timestamp_llegada"],
            [["recorrido_id", "in", activeIds]],
            "secuencia_parada,id",
          )
        : [];
      if (this.selectedTrip) await this.loadDetail(this.selectedTrip.id);
    } catch (e) {
      if (!this.disposed) {
        this.state.loading = false;
        this.state.error =
          "No se pudieron actualizar los registros. Se conserva la última lectura.";
      }
    } finally {
      this.inFlight = false;
    }
  }
  label(pair) {
    return pair ? (pair[1] || "—") : "—";
  }
  vehicleLabel(pair) {
    const vehicle = this.state.vehicles.find(v => v.id === pair?.[0]);
    return vehicle?.display_name || vehicle?.license_plate || this.label(pair);
  }
  stamp(value) {
    return value
      ? new Date(value.replace(" ", "T") + "Z").toLocaleString("es-EC")
      : "—";
  }
  clock(value) {
    const minutes = ((Math.round(value * 60) % 1440) + 1440) % 1440;
    return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
  }
  status(value) {
    return STATES[value] || value;
  }
  type(value) {
    return TYPES[value] || value;
  }
  origin(trip) {
    return trip.simulado ? "Simulado" : "Real";
  }
  badge(value) {
    return ["completado", "online"].includes(value)
      ? "pill gn"
      : ["con_incidencias", "offline", "cancelado", "error"].includes(value)
        ? "pill rd"
        : "pill am";
  }
  stale(v) {
    return (
      !v.traccar_last_update ||
      Date.now() -
        new Date(v.traccar_last_update.replace(" ", "T") + "Z").getTime() >
        120000
    );
  }
  get filteredTrips() {
    const s = this.state;
    const cutoff = s.period ? Date.now() - Number(s.period) * 86400000 : null;
    return s.trips.filter(
      (t) =>
        (!s.routeFilter || t.ruta_id[0] === Number(s.routeFilter)) &&
        (!cutoff ||
          new Date(t.fecha_inicio.replace(" ", "T") + "Z").getTime() >= cutoff),
    );
  }
  get history() {
    const q = this.state.search.toLocaleLowerCase("es");
    return this.filteredTrips.filter((t) =>
      (
        this.label(t.ruta_id) +
        this.label(t.vehicle_id) +
        t.name +
        this.origin(t)
      )
        .toLocaleLowerCase("es")
        .includes(q),
    );
  }
  get measured() {
    const ids = new Set(this.filteredTrips.map((t) => t.id));
    return this.state.metrics.filter((m) => ids.has(m.recorrido_id[0]));
  }
  mean(field, items = this.measured) {
    if (field === "exactitud_sincronizacion_pct")
      items = items.filter((m) => m.calidad_sync_disponible);
    if (field === "tasa_verdaderos_positivos_pct")
      items = items.filter((m) => m.deteccion_validada);
    return items.length
      ? (
          items.reduce((s, m) => s + Number(m[field] || 0), 0) / items.length
        ).toFixed(1)
      : "Sin muestra";
  }
  get metricRows() {
    return METRICS.map(([name, formula, field, unit, interpretation]) => ({
      name,
      formula,
      field,
      unit,
      interpretation,
      result: this.mean(field),
      source: `fleet.metricas.recorrido.${field}`,
    }));
  }
  get routeBars() {
    return this.state.routes
      .filter(
        (r) =>
          !this.state.routeFilter || r.id === Number(this.state.routeFilter),
      )
      .map((r) => {
        const items = this.measured.filter((m) => m.ruta_id[0] === r.id);
        return {
          id: r.id,
          name: r.name,
          result: this.mean("pct_puntualidad", items),
          pct: items.length ? Number(this.mean("pct_puntualidad", items)) : 0,
        };
      });
  }
  get incidentBars() {
    const ids = new Set(this.filteredTrips.map((t) => t.id));
    return Object.entries(TYPES).map(([type, name]) => ({
      type,
      name,
      count: this.state.incidents.filter(
        (i) => ids.has(i.recorrido_id[0]) && i.tipo === type,
      ).length,
    }));
  }
  get selectedRoute() {
    return (
      this.state.routes.find((r) => r.id === this.state.routeId) ||
      this.state.routes[0]
    );
  }
  get routeStops() {
    return this.selectedRoute
      ? this.state.stops.filter((p) => p.ruta_id[0] === this.selectedRoute.id)
      : [];
  }
  get activeTrips() {
    return this.state.trips.filter((t) => t.estado === "en_curso");
  }
  get activeTrip() {
    return (
      this.activeTrips.find((t) => t.id === this.state.activeId) ||
      this.activeTrips[0]
    );
  }
  get activeControls() {
    const trip = this.activeTrip;
    return trip
      ? this.state.activeChecks.filter((c) => c.recorrido_id[0] === trip.id)
      : [];
  }
  get selectedTrip() {
    return this.state.trips.find((t) => t.id === this.state.tripId);
  }
  get latestSync() {
    return this.state.syncs[0];
  }
  get outdated() {
    return this.state.vehicles.filter(
      (v) => v.traccar_device_id && this.stale(v),
    ).length;
  }
  get programming() {
    return this.state.trips.filter((t) =>
      ["programado", "en_curso"].includes(t.estado),
    );
  }
  programmingForRoute(routeId) {
    return this.programming.filter((trip) => trip.ruta_id?.[0] === routeId);
  }
  routeTimeRange(route) {
    const stops = this.routeStops;
    if (!stops.length) return "Por configurar";
    const first = stops.reduce(
      (min, stop) => stop.secuencia < min.secuencia ? stop : min,
      stops[0],
    );
    const last = stops.reduce(
      (max, stop) => stop.secuencia > max.secuencia ? stop : max,
      stops[0],
    );
    return this.clock(first.hora_prevista) + " – " + this.clock(last.hora_prevista);
  }
  get detailRows() {
    const trip = this.selectedTrip;
    if (!trip) return [];
    const stops = this.state.stops.filter(
      (p) => p.ruta_id[0] === trip.ruta_id[0],
    );
    const base = stops.length ? Math.round(stops[0].hora_prevista * 60) : 0;
    return stops.map((p) => {
      const cp = this.state.detailStops.find((c) => c.parada_id[0] === p.id);
      const minutes = (Math.round(p.hora_prevista * 60) - base + 1440) % 1440;
      const date = trip.fecha_inicio
        ? new Date(
            new Date(trip.fecha_inicio.replace(" ", "T") + "Z").getTime() +
              minutes * 60000,
          )
        : null;
      return {
        id: p.id,
        name: p.name,
        planned: date ? date.toLocaleString("es-EC") : "—",
        actual: cp ? this.stamp(cp.timestamp_llegada) : "—",
        delay: cp && cp.cumplida ? cp.retraso_min : "—",
        visited: !!cp?.cumplida,
        tolerance: p.tolerancia_min,
      };
    });
  }
  async selectTrip(id, subTab = "mapa") {
    this.state.tripTab = subTab;
    this.state.tripId = id;
    this.state.tab = "recorridos";
    this.save();
    await this.loadDetail(id);
  }
  async loadDetail(id) {
    this.state.detailIncidents = this.state.incidents.filter(
      (i) => i.recorrido_id[0] === id,
    );
    const request = ++this.detailRequest;
    this.state.detailLoading = true;
    this.state.detailError = "";
    try {
      const rows = await this.rows(
        "fleet.cumplimiento.parada",
        ["parada_id", "cumplida", "timestamp_llegada", "retraso_min"],
        [["recorrido_id", "=", id]],
        "secuencia_parada,id",
      );
      if (this.disposed || request !== this.detailRequest) return;
      this.state.detailStops = rows;
      this.state.detailIncidents = this.state.incidents.filter(
        (i) => i.recorrido_id[0] === id,
      );
    } catch (e) {
      if (request === this.detailRequest) {
        this.state.detailStops = [];
        this.state.detailError = "No se pudo cargar el detalle del recorrido.";
      }
    } finally {
      if (request === this.detailRequest) this.state.detailLoading = false;
    }
  }
  backToHistory() {
    this.state.tripId = null;
    this.detailRequest++;
    this.state.detailLoading = false;
    this.save();
  }
  get GrafanaDashboard() {
    const actions = registry.category("actions");
    return actions.contains("fleet_reports.grafana_dashboard")
      ? actions.get("fleet_reports.grafana_dashboard") : null;
  }
  openRecords() {
    this.save();
    const actions = {
      panel: "fleet_rutas.action_fleet_metricas",
      monitoreo: "fleet_rutas.action_fleet_posicion_gps",
      recorridos: "fleet_rutas.action_fleet_recorrido",
      rutas:
        this.state.routeTab === "programacion"
          ? "fleet_rutas.action_fleet_recorrido"
          : "fleet_rutas.action_fleet_ruta",
      metricas: "fleet_rutas.action_fleet_metricas",
      sync: "fleet_rutas.action_fleet_traccar_sync",
    };
    this.actionService.doAction(actions[this.state.tab]);
  }
  async triggerSync() {
    if (this.state.syncBusy) return;
    this.state.syncBusy = true;
    this.state.syncMessage = "";
    try {
      const devices = await this.call(
        "fleet.traccar.sync",
        "sincronizar_dispositivos",
      );
      const result = await this.call(
        "fleet.traccar.sync",
        "sincronizar_ultima_posicion",
      );
      this.state.syncMessage =
        result.errores || devices.errores
          ? "Sincronización con errores. Consulta el registro."
          : "Sincronización terminada.";
      await this.loadData();
    } catch (e) {
      this.state.syncMessage =
        "No se pudo sincronizar. Revisa la conexión y los permisos.";
    } finally {
      this.state.syncBusy = false;
    }
  }
}
FleetRutasDashboard.template = xml/* xml */`
<div class="o_fleet_rutas_dashboard o_uta">
  <nav class="fleet_sidebar" aria-label="Análisis de flota">
    <div class="fleet_brand">
      <i class="fa fa-bus" />
      <span>Transporte UTA</span>
    </div>
    <button t-foreach="tabs" t-as="tab" t-key="tab.id" t-att-class="'fleet_nav_item'+(state.tab===tab.id?' on':'')" t-att-aria-current="state.tab===tab.id?'page':undefined" t-on-click="()=&gt;this.setTab(tab.id)">
      <i t-att-class="'fa '+tab.icon" aria-hidden="true" />
      <span t-esc="tab.label" />
    </button>
  </nav>
  <main t-att-class="'fleet_main' + (state.tab === 'grafana' ? ' fleet_main_grafana' : '')">
    <div class="hd" t-if="state.tab !== 'grafana' &amp;&amp; state.tab !== 'traccar'">
      <h2 t-esc="tabs.find(t=&gt;t.id===state.tab).label" />
      <div class="fleet_toolbar">
        <span class="lb" t-if="state.updated">Lectura: <t t-esc="state.updated" />
        </span>
        <button class="btn s" t-on-click="loadData" t-att-disabled="inFlight">Actualizar</button>
        <button class="btn p uta-btn-primary" t-on-click="openRecords">Ver registros</button>
      </div>
    </div>
    <p t-if="state.loading &amp;&amp; state.tab !== 'grafana'" role="status">Cargando registros…</p>
    <div t-if="state.error &amp;&amp; state.tab !== 'grafana'" class="fleet_notice is_error" role="alert">
      <span t-esc="state.error" />
      <button class="btn s" t-on-click="loadData">Reintentar</button>
    </div>
    <t t-if="state.tab==='panel' || state.tab==='metricas'">
      <div class="fleet_filters">
        <label>Ruta <select t-model="state.routeFilter">
            <option value="">Todas las rutas</option>
            <option t-foreach="state.routes" t-as="r" t-key="r.id" t-att-value="r.id" t-esc="r.name" />
          </select>
        </label>
        <label>Período <select t-model="state.period">
            <option value="">Todo el historial</option>
            <option value="7">Últimos 7 días</option>
            <option value="30">Últimos 30 días</option>
            <option value="90">Últimos 90 días</option>
          </select>
        </label>
        <span class="lb">
          <t t-esc="measured.length" /> mediciones · <t t-esc="filteredTrips.filter(t=&gt;t.simulado).length" /> recorridos simulados</span>
      </div>
    </t>
    <t t-if="state.tab==='panel'">
      <div class="g g4">
        <div class="card" t-foreach="metricRows.slice(0,4)" t-as="m" t-key="m.field">
          <div class="lb" t-esc="m.name" />
          <div class="big">
            <t t-esc="m.result" />
            <small t-esc="m.unit" />
          </div>
        </div>
      </div>
      <div class="g g2">
        <section class="card">
          <h3>Puntualidad por ruta</h3>
          <div t-foreach="routeBars" t-as="r" t-key="r.id" class="hb">
            <p>
              <span t-esc="r.name" />
              <b>
                <t t-esc="r.result" /> %</b>
            </p>
            <u>
              <i t-att-style="'width:'+r.pct+'%;'" />
            </u>
          </div>
        </section>
        <section class="card">
          <h3>Incidencias por tipo</h3>
          <div class="hb" t-foreach="incidentBars" t-as="i" t-key="i.type">
            <p>
              <span t-esc="i.name" />
              <b t-esc="i.count" />
            </p>
            <u>
              <i t-att-style="'width:'+Math.min(100,i.count*5)+'%;'" />
            </u>
          </div>
        </section>
      </div>
      <section class="card">
        <h3>Calidad del sistema</h3>
        <div class="g g4">
          <div t-foreach="metricRows.slice(8)" t-as="m" t-key="m.field">
            <div class="lb" t-esc="m.name" />
            <strong>
              <t t-esc="m.result" />
              <t t-esc="m.unit" />
            </strong>
          </div>
        </div>
      </section>
    </t>
    <t t-if="state.tab==='monitoreo'">
      <div class="card">
        <iframe class="fleet_map_frame" title="Mapa general de monitoreo en vivo"
                src="/fleet_rutas/mapa/vivo" />
      </div>
      <section class="card">
        <h3>Vehículos y última posición</h3>
        <div class="tw">
          <table class="uta-table">
            <thead>
              <tr>
                <th>Vehículo</th>
                <th>Estado GPS</th>
                <th>Última posición</th>
                <th>Fecha</th>
                <th>Velocidad</th>
              </tr>
            </thead>
            <tbody>
              <tr t-foreach="state.vehicles" t-as="v" t-key="v.id">
                <td t-esc="v.display_name || v.license_plate" />
                <td>
                  <span t-att-class="stale(v)?'pill am':'pill gn'" t-esc="stale(v)?'Desactualizado':'Reciente'" />
                </td>
                <td>
                  <t t-if="v.traccar_last_update">
                    <t t-esc="v.traccar_last_latitude" />, <t t-esc="v.traccar_last_longitude" />
                  </t>
                  <t t-else="">Sin posición</t>
                </td>
                <td t-esc="stamp(v.traccar_last_update)" />
                <td>
                  <t t-esc="v.traccar_last_speed" /> km/h</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </t>
    <t t-if="state.tab==='recorridos'">
      <t t-if="!selectedTrip">
        <div class="fleet_filters">
          <label>Buscar <input type="search" t-model="state.search" placeholder="Ruta, vehículo u origen" />
          </label>
          <span>
            <t t-esc="history.length" /> recorridos</span>
        </div>
        <div class="card">
          <div class="tw">
            <table class="uta-table">
              <thead>
                <tr>
                  <th>Salida programada</th>
                  <th>Vehículo / ruta</th>
                  <th>Origen</th>
                  <th>Estado</th>
                  <th>Paradas</th>
                  <th>Detalle</th>
                </tr>
              </thead>
              <tbody>
                <tr t-foreach="history" t-as="t" t-key="t.id">
                  <td t-esc="stamp(t.fecha_inicio)" />
                  <td>
                    <b t-esc="vehicleLabel(t.vehicle_id)" />
                    <br />
                    <span class="lb" t-esc="label(t.ruta_id)" />
                  </td>
                  <td>
                    <span class="pill" t-esc="origin(t)" />
                  </td>
                  <td>
                    <span t-att-class="badge(t.estado)" t-esc="status(t.estado)" />
                  </td>
                  <td>
                    <t t-esc="t.porcentaje_paradas_cumplidas" /> %</td>
                  <td>
                    <div class="fleet_detail_links">
                      <button class="btn s" title="Mapa" aria-label="Mapa" t-on-click="()=&gt;this.selectTrip(t.id,'mapa')"><i class="fa fa-map-marker" aria-hidden="true" /></button>
                      <button class="btn s" title="Horarios" aria-label="Horarios" t-on-click="()=&gt;this.selectTrip(t.id,'cronologia')"><i class="fa fa-clock-o" aria-hidden="true" /></button>
                      <button class="btn s" title="Incidencias" aria-label="Incidencias" t-on-click="()=&gt;this.selectTrip(t.id,'incidencias')"><i class="fa fa-exclamation-triangle" aria-hidden="true" /></button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p t-if="!history.length">No hay recorridos que coincidan.</p>
        </div>
      </t>
      <t t-else="">
        <div class="hd">
          <button class="btn s" t-on-click="backToHistory">Volver al historial</button>
          <h3 t-esc="selectedTrip.name" />
          <span class="pill" t-esc="origin(selectedTrip)" />
        </div>
        <nav class="fleet_subtabs" aria-label="Detalle del recorrido">
          <button t-foreach="[{id:'mapa',name:'Mapa'},{id:'repeticion',name:'Repetición de ruta'},{id:'cronologia',name:'Línea de tiempo'},{id:'incidencias',name:'Incidencias'}]" t-as="s" t-key="s.id" t-att-class="state.tripTab===s.id?'btn p':'btn s'" t-on-click="()=&gt;this.setTripTab(s.id)" t-esc="s.name" />
        </nav>
        <div t-if="state.tripTab==='mapa'" class="card">
          <iframe class="fleet_map_frame" title="Traza GPS y referencia del recorrido" t-att-src="'/fleet_rutas/mapa/'+selectedTrip.id+'?embed=1'" />
        </div>
        <div t-if="state.tripTab==='repeticion'" class="card">
          <iframe class="fleet_map_frame fleet_replay_frame" title="Repetición histórica del recorrido" t-att-src="'/fleet_rutas/repeticion/'+selectedTrip.id" />
        </div>
        <p t-if="state.detailLoading" role="status">Cargando detalle…</p>
        <p t-if="state.detailError" role="alert" t-esc="state.detailError" />
        <div t-if="state.tripTab==='cronologia' &amp;&amp; !state.detailLoading &amp;&amp; !state.detailError" class="card">
          <h3>Horario previsto frente a real</h3>
          <div class="tw">
            <table class="uta-table">
              <thead>
                <tr>
                  <th>Punto de control</th>
                  <th>Llegada prevista</th>
                  <th>Llegada real</th>
                  <th>Retraso (min)</th>
                  <th>Tolerancia</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                <tr t-foreach="detailRows" t-as="p" t-key="p.id">
                  <td t-esc="p.name" />
                  <td t-esc="p.planned" />
                  <td t-esc="p.actual" />
                  <td t-esc="p.delay" />
                  <td>
                    <t t-esc="p.tolerance" /> min</td>
                  <td>
                    <span t-att-class="p.visited?'pill gn':'pill am'" t-esc="p.visited?'Visitada':'Sin visita registrada'" />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div t-if="state.tripTab==='incidencias'" class="card">
          <div class="tw">
            <table class="uta-table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Tipo</th>
                  <th>Descripción</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                <tr t-foreach="state.detailIncidents" t-as="i" t-key="i.id">
                  <td t-esc="stamp(i.timestamp)" />
                  <td t-esc="type(i.tipo)" />
                  <td t-esc="i.descripcion" />
                  <td t-esc="i.resuelta?'Resuelta':'Pendiente'" />
                </tr>
              </tbody>
            </table>
          </div>
          <p t-if="!state.detailIncidents.length">Sin incidencias registradas.</p>
        </div>
      </t>
    </t>
    <t t-if="state.tab==='rutas'">
      <nav class="fleet_subtabs" aria-label="Rutas y programación">
        <button t-att-class="state.routeTab==='lista'?'btn p':'btn s'" t-on-click="()=&gt;this.setRouteTab('lista')">Rutas</button>
        <button t-att-class="state.routeTab==='programacion'?'btn p':'btn s'" t-on-click="()=&gt;this.setRouteTab('programacion')">Programación</button>
      </nav>
      <t t-if="state.routeTab==='lista'">
        <div class="fleet_route_toolbar">
          <div class="fleet_route_actions">
            <input t-ref="routeImportInput" class="fleet_route_import_input" type="file" accept=".json,application/json"
                   t-on-change="importRouteFile" />
            <button class="btn s" t-on-click="openRouteImport">
              <i class="fa fa-upload" /> Importar ruta
            </button>
            <button class="btn s" t-att-disabled="!selectedRoute" t-on-click="exportRoute">
              <i class="fa fa-download" /> Exportar ruta
            </button>
            <button class="btn p uta-btn-primary" t-on-click="openNewRoute">
              <i class="fa fa-plus" /> Nueva ruta
            </button>
          </div>
        </div>
        <div class="fleet_routes_layout">
          <aside class="card fleet_routes_list">
            <h3>Rutas registradas</h3>
            <button t-foreach="state.routes" t-as="r" t-key="r.id"
                    t-att-class="'fleet_route_item'+(selectedRoute&amp;&amp;selectedRoute.id===r.id?' selected':'')"
                    t-on-click="()=&gt;state.routeId=r.id">
              <b t-esc="r.name" />
              <span t-esc="(r.origen || '')+' - '+(r.destino || '')" />
              <span t-esc="(r.distancia_estimada_km || 0).toFixed(1)+' km'" />
            </button>
            <p t-if="!state.routes.length">Aún no hay rutas registradas.</p>
          </aside>
          <section t-if="selectedRoute" class="fleet_routes_detail">
            <div class="card fleet_route_summary">
              <div class="fleet_route_summary_header">
                <h3 t-esc="selectedRoute.name" />
                <div class="fleet_route_summary_actions">
                  <button class="btn s" t-on-click="openRoutePath">
                    <i class="fa fa-road" /> Trazado
                  </button>
                  <button class="btn s" t-on-click="openEditRoute">
                    <i class="fa fa-pencil" /> Editar ruta
                  </button>
                </div>
              </div>
              <div class="g g4">
                <div><span class="lb">Origen</span><b t-esc="selectedRoute.origen" /></div>
                <div><span class="lb">Destino</span><b t-esc="selectedRoute.destino" /></div>
                <div><span class="lb">Distancia estimada</span><b t-esc="(selectedRoute.distancia_estimada_km || 0).toFixed(1)+' km'" /></div>
                <div><span class="lb">Horario</span><b t-esc="selectedRoute.duracion_estimada_min ? routeTimeRange(selectedRoute) : 'Por configurar'" /></div>
              </div>
            </div>
            <div class="card">
              <h3>Puntos de control</h3>
              <div class="tw">
                <table class="uta-table">
                  <thead><tr><th>N.º</th><th>Nombre</th><th>Coordenadas</th><th>Llegada</th><th>Salida</th><th>Tolerancia</th><th>Radio</th></tr></thead>
                  <tbody>
                    <tr t-foreach="routeStops" t-as="p" t-key="p.id">
                      <td t-esc="p.secuencia" />
                      <td t-esc="p.name" />
                      <td t-esc="p.latitud.toFixed(6)+', '+p.longitud.toFixed(6)" />
                      <td t-esc="clock(p.hora_prevista)" />
                      <td t-esc="p.tolerancia_min ? clock(p.hora_prevista + p.tolerancia_min/60) : '—'" />
                      <td t-esc="p.tolerancia_min+' min'" />
                      <td t-esc="p.radio_proximidad_m+' m'" />
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div class="card fleet_route_assignment">
              <h3>Asignación</h3>
              <p t-if="!programmingForRoute(selectedRoute.id).length">Esta ruta aún no tiene asignaciones programadas.</p>
              <div t-foreach="programmingForRoute(selectedRoute.id)" t-as="t" t-key="t.id" class="g g3">
                <div><span class="lb">Vehículo</span><b t-esc="vehicleLabel(t.vehicle_id)" /></div>
                <div><span class="lb">Fecha</span><b t-esc="stamp(t.fecha_inicio)" /></div>
                <div><span class="lb">Estado</span><b t-esc="status(t.estado)" /></div>
              </div>
            </div>
          </section>
        </div>
      </t>
      <div t-else="" class="card">
        <h3>Programación de salidas</h3>
        <div class="tw">
          <table class="uta-table">
            <thead>
              <tr>
                <th>Salida</th>
                <th>Fin estimado</th>
                <th>Vehículo</th>
                <th>Ruta</th>
                <th>Origen</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              <tr t-foreach="programming" t-as="t" t-key="t.id">
                <td t-esc="stamp(t.fecha_inicio)" />
                <td t-esc="stamp(t.fecha_fin_estimada)" />
                <td t-esc="vehicleLabel(t.vehicle_id)" />
                <td t-esc="label(t.ruta_id)" />
                <td t-esc="origin(t)" />
                <td t-esc="status(t.estado)" />
              </tr>
            </tbody>
          </table>
        </div>
        <p t-if="!programming.length">Sin salidas programadas ni en curso.</p>
      </div>
    </t>
    <section t-if="state.tab==='metricas'" class="card">
      <h3>Indicadores almacenados · media de las mediciones seleccionadas</h3>
      <div class="tw">
        <table class="uta-table fleet_metrics_table">
          <thead>
            <tr>
              <th>Indicador</th>
              <th>Fórmula</th>
              <th>Fuente</th>
              <th>Unidad</th>
              <th>Resultado</th>
              <th>Interpretación</th>
            </tr>
          </thead>
          <tbody>
            <tr t-foreach="metricRows" t-as="m" t-key="m.field">
              <td><span class="fleet_cell_text" t-att-title="m.name" t-esc="m.name" /></td>
              <td><span class="fleet_cell_text" t-att-title="m.formula" t-esc="m.formula" /></td>
              <td><span class="fleet_cell_text" t-att-title="m.source" t-esc="m.source" /></td>
              <td><span class="fleet_cell_text" t-att-title="m.unit" t-esc="m.unit" /></td>
              <td><span class="fleet_cell_text" t-att-title="m.result" t-esc="m.result" /></td>
              <td><span class="fleet_cell_text" t-att-title="m.interpretation" t-esc="m.interpretation" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <t t-if="state.tab==='sync'">
      <div class="hd">
        <h3>Traccar y recepción de posiciones</h3>
        <button class="btn p" t-att-disabled="state.syncBusy" t-on-click="triggerSync" t-esc="state.syncBusy?'Sincronizando…':'Sincronizar ahora'" />
      </div>
      <p t-if="state.syncMessage" role="status" t-esc="state.syncMessage" />
      <div class="g g4">
        <div class="card">
          <div class="lb">Última sincronización</div>
          <b t-esc="latestSync?stamp(latestSync.fecha_inicio):'Sin registros'" />
          <p t-if="latestSync" t-esc="latestSync.estado==='completado'?'Completada':latestSync.estado==='error'?'Error':'Pendiente'" />
        </div>
        <div class="card">
          <div class="lb">Posiciones procesadas / nuevas</div>
          <b>
            <t t-esc="latestSync?latestSync.registros_procesados:0" /> / <t t-esc="latestSync?latestSync.registros_nuevos:0" />
          </b>
        </div>
        <div class="card">
          <div class="lb">Duplicados evitados</div>
          <b t-esc="latestSync?latestSync.registros_duplicados:0" />
        </div>
        <div class="card">
          <div class="lb">Dispositivos con datos desactualizados</div>
          <b t-esc="outdated" />
        </div>
      </div>
      <p t-if="latestSync &amp;&amp; latestSync.error_mensaje" role="alert" t-esc="latestSync.error_mensaje" />
      <div class="card">
        <h3>Dispositivos asociados</h3>
        <div class="tw">
          <table class="uta-table">
            <thead>
              <tr>
                <th>Dispositivo</th>
                <th>Identificador</th>
                <th>Vehículo</th>
                <th>Estado</th>
                <th>Última posición</th>
              </tr>
            </thead>
            <tbody>
              <tr t-foreach="state.vehicles.filter(v=&gt;v.traccar_device_id)" t-as="v" t-key="v.id">
                <td t-esc="v.traccar_device_id" />
                <td t-esc="v.traccar_unique_id||'—'" />
                <td t-esc="v.display_name || v.license_plate" />
                <td t-esc="v.traccar_device_status==='online'?'En línea':v.traccar_device_status==='offline'?'Fuera de línea':v.traccar_device_status==='removed'?'No disponible en Traccar':'Desconocido'" />
                <td t-esc="stamp(v.traccar_last_update)" />
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <p class="lb">Conectividad externa: el estado del túnel no está disponible en Odoo.</p>
    </t>
    <t t-if="state.tab === 'traccar'">
      <div class="hd">
        <h2>Traccar</h2>
        <div class="fleet_toolbar">
          <button class="btn s" t-att-disabled="state.syncBusy" t-on-click="triggerSync" t-esc="state.syncBusy?'Sincronizando…':'Sincronizar dispositivos'" />
          <a t-if="state.traccarUrl" class="btn s" t-att-href="state.traccarUrl" target="_blank" rel="noopener noreferrer">Abrir en otra pestaña</a>
        </div>
      </div>
      <p t-if="state.syncMessage" role="status" t-esc="state.syncMessage" />
      <p class="lb">Inicie sesión con su cuenta de Traccar. Los dispositivos nuevos aparecen en Odoo al sincronizar, al llegar su primera posición o en un máximo de 5 minutos.</p>
      <p t-if="state.traccarError" class="fleet_notice is_error" role="alert" t-esc="state.traccarError" />
      <p t-elif="traccarBlocked" class="fleet_notice is_error" role="alert">El navegador bloquea Traccar por HTTP dentro de Odoo por HTTPS. Configure una URL HTTPS de Traccar en Ajustes.</p>
      <div t-elif="state.traccarUrl" class="card">
        <iframe class="fleet_map_frame fleet_traccar_frame" title="Traccar" t-att-src="state.traccarUrl" />
      </div>
    </t>
    <t t-if="state.tab === 'grafana'">
      <t t-if="GrafanaDashboard"><t t-component="GrafanaDashboard" /></t>
      <p t-else="" role="alert">El módulo de reportes de Grafana no está disponible.</p>
    </t>
  </main>
</div>
`;
registry.category("actions").add("fleet_rutas.dashboard", FleetRutasDashboard);
