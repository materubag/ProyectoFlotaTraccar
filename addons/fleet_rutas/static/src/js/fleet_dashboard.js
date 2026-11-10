/** @odoo-module **/
/**
 * Centro de Control de Transporte Universitario - OWL Dashboard Widget
 * Compatible con Odoo 16 (OWL 2)
 */

import { Component, useState, useRef, onMounted, onWillUnmount, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const VIEW_PREFERENCES = "fleet_rutas.dashboard.view.v1";
const DEFAULT_VIEW = { textScale: 100, compact: false, autoRefresh: true };

class FleetRutasDashboard extends Component {
    static template = "fleet_rutas.FleetDashboardTemplate";

    setup() {
        this.rpc = useService("rpc");
        this.actionService = useService("action");
        this.tripHeading = useRef("tripHeading");
        let preferences = {};
        try {
            preferences = JSON.parse(window.localStorage.getItem(VIEW_PREFERENCES)) || {};
        } catch (_) { /* El panel funciona también sin almacenamiento local. */ }

        this.state = useState({
            loading: true,
            error: false,
            kpis: {
                recorridos_hoy: 0,
                en_curso: 0,
                completados: 0,
                incidencias_activas: 0,
                avg_puntualidad: 0.0,
                avg_cumplimiento: 0.0,
                avg_integridad_gps: 0.0,
                recorridos_activos: [],
            },
            lastUpdated: null,
            hasData: false,
            query: "",
            textScale: Math.min(140, Math.max(100, Number(preferences.textScale) || 100)),
            compact: preferences.compact === true,
            autoRefresh: preferences.autoRefresh !== false,
        });

        this.refreshInterval = null;
        this.inFlight = false;
        this.disposed = false;

        onMounted(() => {
            this.loadKpis();
            this.configureRefresh();
        });

        onWillUnmount(() => {
            this.disposed = true;
            clearInterval(this.refreshInterval);
        });
    }

    async loadKpis() {
        if (this.inFlight || this.disposed) return;
        this.inFlight = true;
        this.state.loading = true;
        try {
            const data = await this.rpc("/web/dataset/call_kw", {
                model: "fleet.metricas.recorrido",
                method: "get_dashboard_kpis",
                args: [],
                kwargs: {},
            });
            if (this.disposed) return;
            this.state.kpis = data;
            this.state.hasData = true;
            this.state.error = false;
            this.state.lastUpdated = new Date().toLocaleTimeString();
        } catch (err) {
            if (this.disposed) return;
            console.error("Error al cargar KPIs del dashboard de rutas:", err);
            this.state.error = true;
        } finally {
            this.inFlight = false;
            if (!this.disposed) this.state.loading = false;
        }
    }

    onRefresh() {
        this.loadKpis();
    }

    configureRefresh() {
        clearInterval(this.refreshInterval);
        this.refreshInterval = this.state.autoRefresh
            ? setInterval(() => this.loadKpis(), 30000) : null;
    }

    saveView() {
        const { textScale, compact, autoRefresh } = this.state;
        try {
            window.localStorage.setItem(VIEW_PREFERENCES, JSON.stringify({ textScale, compact, autoRefresh }));
        } catch (_) { /* Preferencias opcionales; no bloquean la navegación. */ }
    }

    onTextScale(ev) {
        this.state.textScale = Math.min(140, Math.max(100, Number(ev.target.value) || 100));
        this.saveView();
    }

    onCompact(ev) {
        this.state.compact = ev.target.checked;
        this.saveView();
    }

    onAutoRefresh(ev) {
        this.state.autoRefresh = ev.target.checked;
        this.configureRefresh();
        this.saveView();
    }

    resetView() {
        Object.assign(this.state, DEFAULT_VIEW, { query: "" });
        this.configureRefresh();
        this.saveView();
    }

    onSearch(ev) { this.state.query = ev.target.value; }
    clearSearch() { this.state.query = ""; }
    focusTrips() { this.tripHeading.el?.focus(); }

    get filteredTrips() {
        const normalize = value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es");
        const query = normalize(this.state.query).trim();
        return this.state.kpis.recorridos_activos.filter(item =>
            !query || normalize(`${item.name} ${item.ruta} ${item.vehiculo}`).includes(query));
    }

    openRutas() { this.actionService.doAction("fleet_rutas.action_fleet_ruta"); }
    openTelemetria() { this.actionService.doAction("fleet_rutas.action_fleet_posicion_gps"); }

    openRecorridos() {
        this.actionService.doAction("fleet_rutas.action_fleet_recorrido");
    }

    openIncidencias() {
        this.actionService.doAction("fleet_rutas.action_fleet_incidencia");
    }

    openMetricas() {
        this.actionService.doAction("fleet_rutas.action_fleet_metricas");
    }

    openRecorridoDetail(id) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "fleet.recorrido",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

FleetRutasDashboard.template = xml/* xml */`
<div t-att-class="'o_fleet_rutas_dashboard o_action_delegate_scroll' + (state.compact ? ' fleet_compact' : '')" t-att-style="'--fleet-text-scale: ' + state.textScale / 100">
 <div class="fleet_viewport o_content" tabindex="0" role="region" aria-label="Panel de control de flota, desplazamiento vertical">
 <div class="fleet_workspace">
  <a class="fleet_skip_link" href="#fleet_trips_title" t-on-click.prevent="focusTrips">Ir a los recorridos</a>
  <header class="fleet_hero">
   <div class="fleet_heading">
    <span class="fleet_eyebrow">Fleet / Transporte universitario</span>
    <h1>Control de flota</h1>
    <p>Recorridos, puntualidad y calidad del servicio en un solo lugar.</p>
    <div class="fleet_hero_stats"><span><strong t-esc="state.kpis.recorridos_hoy"/> programados hoy</span><span><strong t-esc="state.kpis.completados"/> finalizados en el historial</span></div>
   </div>
   <div class="fleet_hero_controls">
    <span class="fleet_connection" role="status" aria-live="polite"><i t-att-class="state.error ? 'fa fa-exclamation-circle' : 'fa fa-clock-o'" aria-hidden="true"/><t t-if="state.error">Actualización pendiente</t><t t-elif="state.loading">Actualizando indicadores</t><t t-else="">Actualizado <t t-esc="state.lastUpdated"/></t></span>
    <button class="fleet_button fleet_button_primary" t-on-click="onRefresh" t-att-disabled="state.loading"><i class="fa fa-refresh" aria-hidden="true"/> Actualizar panel</button>
    <span class="fleet_refresh_note"><t t-if="state.autoRefresh">Actualización automática cada 30 s</t><t t-else="">Actualización automática pausada</t></span>
   </div>
  </header>
  <section class="fleet_view_controls" aria-label="Personalizar la vista">
   <div class="fleet_scale_control"><label for="fleet_text_scale">Tamaño de texto</label><input id="fleet_text_scale" type="range" min="100" max="140" step="5" t-att-value="state.textScale" t-att-aria-valuetext="state.textScale + ' por ciento'" t-on-input="onTextScale"/><output for="fleet_text_scale"><t t-esc="state.textScale"/>%</output></div>
   <label class="fleet_toggle"><input type="checkbox" t-att-checked="state.compact" t-on-change="onCompact"/> Vista compacta</label>
   <label class="fleet_toggle"><input type="checkbox" t-att-checked="state.autoRefresh" t-on-change="onAutoRefresh"/> Actualización automática</label>
   <button class="fleet_button fleet_button_secondary" t-on-click="resetView" title="Restablecer tamaño de texto, densidad y actualización">Restablecer vista</button>
  </section>
  <div t-if="state.error" class="fleet_notice is_error" role="alert"><span>No se pudieron actualizar los indicadores. <t t-if="state.hasData">Se muestran los últimos datos recibidos.</t></span><button class="fleet_button fleet_button_secondary" t-on-click="onRefresh" t-att-disabled="state.loading">Reintentar</button></div>
  <div t-if="state.loading and !state.hasData" class="fleet_notice" role="status">Cargando los datos de la flota…</div>
  <section class="fleet_kpis" aria-label="Indicadores del servicio">
   <button class="fleet_kpi tone_teal" t-on-click="openRecorridos"><span class="fleet_kpi_top">En curso <i class="fa fa-bus" aria-hidden="true"/></span><strong class="fleet_kpi_value" t-esc="state.kpis.en_curso"/><span class="fleet_kpi_hint">Recorridos activos ahora</span><span class="fleet_kpi_link">Ver operación <i class="fa fa-arrow-right" aria-hidden="true"/></span></button>
   <button class="fleet_kpi tone_blue" t-on-click="openMetricas"><span class="fleet_kpi_top">Puntualidad <i class="fa fa-clock-o" aria-hidden="true"/></span><strong class="fleet_kpi_value"><t t-esc="state.kpis.avg_puntualidad"/><small>%</small></strong><span class="fleet_kpi_hint">Tolerancia de cada parada</span><span class="fleet_kpi_link">Consultar métricas <i class="fa fa-arrow-right" aria-hidden="true"/></span></button>
   <button class="fleet_kpi tone_violet" t-on-click="openMetricas"><span class="fleet_kpi_top">Cumplimiento <i class="fa fa-check-circle-o" aria-hidden="true"/></span><strong class="fleet_kpi_value"><t t-esc="state.kpis.avg_cumplimiento"/><small>%</small></strong><span class="fleet_kpi_hint">Rutas y puntos de control</span><span class="fleet_kpi_link">Evaluar servicio <i class="fa fa-arrow-right" aria-hidden="true"/></span></button>
   <button class="fleet_kpi tone_amber" t-on-click="openIncidencias"><span class="fleet_kpi_top">Incidencias <i class="fa fa-exclamation-triangle" aria-hidden="true"/></span><strong class="fleet_kpi_value" t-esc="state.kpis.incidencias_activas"/><span class="fleet_kpi_hint">Eventos por resolver</span><span class="fleet_kpi_link">Revisar eventos <i class="fa fa-arrow-right" aria-hidden="true"/></span></button>
   <button class="fleet_kpi tone_cyan" t-on-click="openMetricas"><span class="fleet_kpi_top">Integridad GPS <i class="fa fa-signal" aria-hidden="true"/></span><strong class="fleet_kpi_value"><t t-esc="state.kpis.avg_integridad_gps"/><small>%</small></strong><span class="fleet_kpi_hint">Continuidad de señal registrada</span><span class="fleet_kpi_link">Ver calidad GPS <i class="fa fa-arrow-right" aria-hidden="true"/></span></button>
  </section>
  <div class="fleet_content_grid">
   <section class="fleet_panel" aria-labelledby="fleet_trips_title">
    <div class="fleet_panel_header"><div><span class="fleet_eyebrow">Seguimiento operativo</span><h2 id="fleet_trips_title" tabindex="-1" t-ref="tripHeading">Recorridos en tránsito</h2></div><button class="fleet_button fleet_button_secondary" t-on-click="openRecorridos">Ver todos <i class="fa fa-angle-right" aria-hidden="true"/></button></div>
    <div class="fleet_search"><label for="fleet_trip_search">Buscar en los recorridos del panel</label><div class="fleet_search_input"><i class="fa fa-search" aria-hidden="true"/><input id="fleet_trip_search" type="search" placeholder="Ruta, vehículo o recorrido" t-att-value="state.query" t-on-input="onSearch"/><button t-if="state.query" class="fleet_button fleet_button_secondary" t-on-click="clearSearch" aria-label="Limpiar búsqueda">Limpiar</button></div><span class="fleet_search_count" role="status" aria-live="polite"><t t-esc="filteredTrips.length"/> visibles en el panel. Usa «Ver todos» para consultar el historial completo.</span></div>
    <div t-if="!state.hasData" class="fleet_empty"><span class="fleet_empty_icon"><i class="fa fa-info-circle" aria-hidden="true"/></span><h3><t t-if="state.loading">Cargando recorridos</t><t t-else="">Datos no disponibles</t></h3><p><t t-if="state.loading">Estamos consultando la información de la flota.</t><t t-else="">Pulsa Actualizar panel para volver a intentarlo.</t></p></div>
    <div t-elif="state.kpis.recorridos_activos.length === 0" class="fleet_empty"><span class="fleet_empty_icon"><i class="fa fa-road" aria-hidden="true"/></span><h3>Sin recorridos en curso</h3><p>Los vehículos aparecerán aquí cuando se inicie un recorrido.</p><button class="fleet_button fleet_button_secondary" t-on-click="openRecorridos">Consultar recorridos</button></div>
    <div t-elif="filteredTrips.length === 0" class="fleet_empty"><h3>Sin coincidencias</h3><p>Prueba con otro nombre de ruta o vehículo.</p><button class="fleet_button fleet_button_secondary" t-on-click="clearSearch">Limpiar búsqueda</button></div>
    <div t-else="" class="fleet_table_scroll" tabindex="0" role="region" aria-label="Tabla de recorridos activos; desplaza horizontalmente si es necesario"><table class="fleet_table">
     <caption class="fleet_sr_only">Recorridos activos con vehículo, cumplimiento de paradas y estado de ruta</caption>
     <thead><tr><th scope="col">Recorrido / Ruta</th><th scope="col">Vehículo</th><th scope="col">Paradas</th><th scope="col">Estado de ruta</th><th scope="col">Detalle</th></tr></thead>
     <tbody><tr t-foreach="filteredTrips" t-as="item" t-key="item.id">
      <td><strong t-esc="item.name"/><span class="fleet_cell_secondary" t-esc="item.ruta"/></td><td class="fleet_vehicle_cell" t-esc="item.vehiculo"/><td><span class="fleet_badge" t-esc="item.paradas_cumplidas"/></td>
      <td><span t-att-class="'fleet_badge ' + (item.desviacion ? 'is_warning' : 'is_success')"><t t-if="item.desviacion">Desviado</t><t t-else="">En corredor</t></span></td>
      <td><button class="fleet_button fleet_button_secondary" t-att-aria-label="'Abrir recorrido ' + item.name" t-on-click="() => this.openRecorridoDetail(item.id)">Abrir <i class="fa fa-angle-right" aria-hidden="true"/></button></td>
     </tr></tbody>
    </table></div>
   </section>
   <aside class="fleet_panel fleet_shortcuts" aria-labelledby="fleet_shortcuts_title">
    <div class="fleet_panel_header"><div><span class="fleet_eyebrow">Gestión diaria</span><h2 id="fleet_shortcuts_title">Accesos de operación</h2></div></div>
    <nav aria-label="Accesos de transporte">
     <button t-on-click="openRutas"><i class="fa fa-map-signs" aria-hidden="true"/><span><strong>Rutas y paradas</strong><small>Organizar los puntos de control</small></span><i class="fa fa-angle-right" aria-hidden="true"/></button>
     <button t-on-click="openTelemetria"><i class="fa fa-location-arrow" aria-hidden="true"/><span><strong>Telemetría GPS</strong><small>Consultar posiciones e historial</small></span><i class="fa fa-angle-right" aria-hidden="true"/></button>
     <button t-on-click="openMetricas"><i class="fa fa-bar-chart" aria-hidden="true"/><span><strong>Reportes y calidad</strong><small>Analizar el desempeño del servicio</small></span><i class="fa fa-angle-right" aria-hidden="true"/></button>
    </nav>
   </aside>
  </div>
  <footer class="fleet_footer">Usa la rueda, desliza o pulsa Tab para recorrer el panel. La tabla tiene desplazamiento horizontal independiente.</footer>
 </div>
 </div>
</div>
`;
registry.category("actions").add("fleet_rutas.dashboard", FleetRutasDashboard);
