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
    <div class="dashboard_header">
        <div class="title_section">
            <h2>🚌 Monitoreo y Evaluación de Rutas Universitarias</h2>
            <span class="subtitle">Indicadores Operativos y Calidad ISO/IEC 25010 en Tiempo Real</span>
        </div>
        <div class="action_section">
            <span class="badge bg-light text-dark me-2">Actualizado: <t t-esc="state.lastUpdated"/></span>
            <button class="btn btn-primary btn-sm" t-on-click="onRefresh">
                <i class="fa fa-refresh me-1"/> Actualizar
            </button>
        </div>
    </div>

    <div t-if="state.error" class="alert alert-danger" role="alert">No se pudieron actualizar los indicadores. Intenta actualizar de nuevo.</div>
    <div t-if="state.loading" role="status" class="alert alert-info">Cargando indicadores…</div>
    <!-- KPI Grid -->
    <div class="kpi_grid">
        <div class="kpi_card bg-primary-subtle" t-on-click="openRecorridos">
            <div class="kpi_icon text-primary">🚍</div>
            <div class="kpi_body">
                <span class="kpi_val"><t t-esc="state.kpis.en_curso"/></span>
                <span class="kpi_label">En Curso Ahora</span>
                <small class="text-muted"><t t-esc="state.kpis.recorridos_hoy"/> programados hoy</small>
            </div>
        </div>

        <div class="kpi_card bg-success-subtle" t-on-click="openMetricas">
            <div class="kpi_icon text-success">⏱️</div>
            <div class="kpi_body">
                <span class="kpi_val"><t t-esc="state.kpis.avg_puntualidad"/>%</span>
                <span class="kpi_label">Puntualidad Global</span>
                <small class="text-muted">Tolerancia configurada por parada</small>
            </div>
        </div>

        <div class="kpi_card bg-info-subtle" t-on-click="openMetricas">
            <div class="kpi_icon text-info">🎯</div>
            <div class="kpi_body">
                <span class="kpi_val"><t t-esc="state.kpis.avg_cumplimiento"/>%</span>
                <span class="kpi_label">Cumplimiento de Rutas</span>
                <small class="text-muted">Paradas y recorrido</small>
            </div>
        </div>

        <div class="kpi_card bg-warning-subtle" t-on-click="openIncidencias">
            <div class="kpi_icon text-warning">⚠️</div>
            <div class="kpi_body">
                <span class="kpi_val"><t t-esc="state.kpis.incidencias_activas"/></span>
                <span class="kpi_label">Incidencias Activas</span>
                <small class="text-muted">Desvíos, retrasos, señal</small>
            </div>
        </div>

        <div class="kpi_card bg-secondary-subtle" t-on-click="openMetricas">
            <div class="kpi_icon text-dark">📡</div>
            <div class="kpi_body">
                <span class="kpi_val"><t t-esc="state.kpis.avg_integridad_gps"/>%</span>
                <span class="kpi_label">Integridad GPS (ISO 25010)</span>
                <small class="text-muted">Disponibilidad de señal</small>
            </div>
        </div>
    </div>

    <!-- Tabla de Recorridos Activos -->
    <div class="active_trips_panel card mt-4 shadow-sm">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0">🛣️ Recorridos Activos en Tránsito</h5>
            <button class="btn btn-outline-secondary btn-sm" t-on-click="openRecorridos">Ver Todos</button>
        </div>
        <div class="card-body p-0">
            <div class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>Recorrido</th>
                            <th>Ruta</th>
                            <th>Vehículo</th>
                            <th>Cumplimiento Paradas</th>
                            <th>Desviación</th>
                            <th>Acción</th>
                        </tr>
                    </thead>
                    <tbody>
                        <t t-if="state.kpis.recorridos_activos.length === 0">
                            <tr>
                                <td colspan="6" class="text-center py-4 text-muted">
                                    No hay recorridos en curso en este momento.
                                </td>
                            </tr>
                        </t>
                        <t t-foreach="state.kpis.recorridos_activos" t-as="item" t-key="item.id">
                            <tr>
                                <td><strong><t t-esc="item.name"/></strong></td>
                                <td><t t-esc="item.ruta"/></td>
                                <td><span class="badge bg-dark"><t t-esc="item.vehiculo"/></span></td>
                                <td><span class="badge bg-primary"><t t-esc="item.paradas_cumplidas"/></span></td>
                                <td>
                                    <t t-if="item.desviacion">
                                        <span class="badge bg-danger">Desviado</span>
                                    </t>
                                    <t t-else="">
                                        <span class="badge bg-success">En Corredor</span>
                                    </t>
                                </td>
                                <td>
                                    <button class="btn btn-outline-primary btn-sm" t-on-click="() => this.openRecorridoDetail(item.id)">
                                        Monitorear
                                    </button>
                                </td>
                            </tr>
                        </t>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>
`;

registry.category("actions").add("fleet_rutas.dashboard", FleetRutasDashboard);

