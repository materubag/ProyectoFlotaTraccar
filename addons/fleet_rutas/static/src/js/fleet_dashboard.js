/** @odoo-module **/
/**
 * Centro de Control de Transporte Universitario - OWL Dashboard Widget
 * Compatible con Odoo 16 (OWL 2)
 */

import { Component, useState, onMounted, onWillUnmount, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class FleetRutasDashboard extends Component {
    static template = "fleet_rutas.FleetDashboardTemplate";

    setup() {
        this.rpc = useService("rpc");
        this.actionService = useService("action");

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
            lastUpdated: new Date().toLocaleTimeString(),
        });

        this.refreshInterval = null;

        onMounted(() => {
            this.loadKpis();
            this.refreshInterval = setInterval(() => this.loadKpis(), 30000);
        });

        onWillUnmount(() => {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
            }
        });
    }

    async loadKpis() {
        try {
            const data = await this.rpc("/web/dataset/call_kw", {
                model: "fleet.metricas.recorrido",
                method: "get_dashboard_kpis",
                args: [],
                kwargs: {},
            });
            this.state.kpis = data;
            this.state.error = false;
            this.state.lastUpdated = new Date().toLocaleTimeString();
            this.state.loading = false;
        } catch (err) {
            console.error("Error al cargar KPIs del dashboard de rutas:", err);
            this.state.error = true;
            this.state.loading = false;
        }
    }

    onRefresh() {
        this.state.loading = true;
        this.loadKpis();
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
<div class="o_fleet_rutas_dashboard">
 <div class="fleet_workspace">
  <header class="fleet_hero">
   <div class="fleet_heading">
    <span class="fleet_eyebrow">Fleet / Transporte universitario</span>
    <h1>Control de flota</h1>
    <p>Recorridos, puntualidad y calidad del servicio en un solo lugar.</p>
    <div class="fleet_hero_stats"><span><strong t-esc="state.kpis.recorridos_hoy"/> programados hoy</span><span><strong t-esc="state.kpis.completados"/> finalizados en el historial</span></div>
   </div>
   <div class="fleet_hero_controls">
    <span class="fleet_connection" role="status"><i t-att-class="state.error ? 'fa fa-exclamation-circle' : 'fa fa-clock-o'" aria-hidden="true"/><t t-if="state.error">Actualización pendiente</t><t t-elif="state.loading">Actualizando indicadores</t><t t-else="">Actualizado <t t-esc="state.lastUpdated"/></t></span>
    <button class="fleet_button fleet_button_primary" t-on-click="onRefresh" t-att-disabled="state.loading"><i class="fa fa-refresh" aria-hidden="true"/> Actualizar panel</button>
    <span class="fleet_refresh_note">Actualización automática cada 30 s</span>
   </div>
  </header>
  <div t-if="state.error" class="fleet_notice is_error" role="alert">No se pudieron actualizar los indicadores. Se conservan los últimos datos recibidos.</div>
  <div t-if="state.loading" class="fleet_notice" role="status">Actualizando los datos de la flota…</div>
  <section class="fleet_kpis" aria-label="Indicadores del servicio">
   <button class="fleet_kpi tone_teal" t-on-click="openRecorridos"><span class="fleet_kpi_top">En curso <i class="fa fa-bus" aria-hidden="true"/></span><strong class="fleet_kpi_value" t-esc="state.kpis.en_curso"/><span class="fleet_kpi_hint">Recorridos activos ahora</span><span class="fleet_kpi_link">Ver operación <i class="fa fa-arrow-right" aria-hidden="true"/></span></button>
   <button class="fleet_kpi tone_blue" t-on-click="openMetricas"><span class="fleet_kpi_top">Puntualidad <i class="fa fa-clock-o" aria-hidden="true"/></span><strong class="fleet_kpi_value"><t t-esc="state.kpis.avg_puntualidad"/><small>%</small></strong><span class="fleet_kpi_hint">Tolerancia de cada parada</span><span class="fleet_kpi_link">Consultar métricas <i class="fa fa-arrow-right" aria-hidden="true"/></span></button>
   <button class="fleet_kpi tone_violet" t-on-click="openMetricas"><span class="fleet_kpi_top">Cumplimiento <i class="fa fa-check-circle-o" aria-hidden="true"/></span><strong class="fleet_kpi_value"><t t-esc="state.kpis.avg_cumplimiento"/><small>%</small></strong><span class="fleet_kpi_hint">Rutas y puntos de control</span><span class="fleet_kpi_link">Evaluar servicio <i class="fa fa-arrow-right" aria-hidden="true"/></span></button>
   <button class="fleet_kpi tone_amber" t-on-click="openIncidencias"><span class="fleet_kpi_top">Incidencias <i class="fa fa-exclamation-triangle" aria-hidden="true"/></span><strong class="fleet_kpi_value" t-esc="state.kpis.incidencias_activas"/><span class="fleet_kpi_hint">Eventos por resolver</span><span class="fleet_kpi_link">Revisar eventos <i class="fa fa-arrow-right" aria-hidden="true"/></span></button>
   <button class="fleet_kpi tone_cyan" t-on-click="openMetricas"><span class="fleet_kpi_top">Integridad GPS <i class="fa fa-signal" aria-hidden="true"/></span><strong class="fleet_kpi_value"><t t-esc="state.kpis.avg_integridad_gps"/><small>%</small></strong><span class="fleet_kpi_hint">Continuidad de señal registrada</span><span class="fleet_kpi_link">Ver calidad GPS <i class="fa fa-arrow-right" aria-hidden="true"/></span></button>
  </section>
  <div class="fleet_content_grid">
   <section class="fleet_panel" aria-labelledby="fleet_trips_title">
    <div class="fleet_panel_header"><div><span class="fleet_eyebrow">Seguimiento operativo</span><h2 id="fleet_trips_title">Recorridos en tránsito</h2></div><button class="fleet_button fleet_button_secondary" t-on-click="openRecorridos">Ver todos <i class="fa fa-angle-right" aria-hidden="true"/></button></div>
    <div t-if="state.kpis.recorridos_activos.length === 0" class="fleet_empty"><span class="fleet_empty_icon"><i class="fa fa-road" aria-hidden="true"/></span><h3>Sin recorridos en curso</h3><p>Los vehículos aparecerán aquí cuando se inicie un recorrido.</p><button class="fleet_button fleet_button_secondary" t-on-click="openRecorridos">Consultar recorridos</button></div>
    <div t-else="" class="fleet_table_scroll" tabindex="0" aria-label="Tabla de recorridos activos"><table class="fleet_table">
     <thead><tr><th scope="col">Recorrido / Ruta</th><th scope="col">Vehículo</th><th scope="col">Paradas</th><th scope="col">Estado de ruta</th><th scope="col">Detalle</th></tr></thead>
     <tbody><tr t-foreach="state.kpis.recorridos_activos" t-as="item" t-key="item.id">
      <td><strong t-esc="item.name"/><span class="fleet_cell_secondary" t-esc="item.ruta"/></td><td t-esc="item.vehiculo"/><td><span class="fleet_badge" t-esc="item.paradas_cumplidas"/></td>
      <td><span t-att-class="'fleet_badge ' + (item.desviacion ? 'is_warning' : 'is_success')"><t t-if="item.desviacion">Desviado</t><t t-else="">En corredor</t></span></td>
      <td><button class="fleet_button fleet_button_secondary" t-on-click="() => this.openRecorridoDetail(item.id)">Abrir <i class="fa fa-angle-right" aria-hidden="true"/></button></td>
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
 </div>
</div>
`;
registry.category("actions").add("fleet_rutas.dashboard", FleetRutasDashboard);
