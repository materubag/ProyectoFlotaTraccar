/** @odoo-module **/
/**
 * Centro de Control y Monitoreo de Transporte Universitario
 * OWL 2 Component para Odoo 16
 * 100% conectado a los datos reales registrados en Odoo y PostgreSQL
 * Diseño técnico de alta precisión con bordes planos (0-radius)
 */

import { Component, useState, onMounted, onWillUnmount, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const TABS = [
    { id: "panel", label: "Panel", icon: "fa-dashboard" },
    { id: "monitoreo", label: "Monitoreo en vivo", icon: "fa-map-marker" },
    { id: "rutas", label: "Rutas y paradas", icon: "fa-map-signs" },
    { id: "asignaciones", label: "Asignaciones", icon: "fa-calendar" },
    { id: "recorridos", label: "Recorridos e incidencias", icon: "fa-road" },
    { id: "tiempo", label: "Línea de tiempo", icon: "fa-clock-o" },
    { id: "vehiculos", label: "Vehículos y GPS", icon: "fa-bus" },
    { id: "metricas", label: "Métricas ISO 25010", icon: "fa-bar-chart" },
    { id: "sync", label: "Sincronización", icon: "fa-refresh" },
];

class FleetRutasDashboard extends Component {
    static template = "fleet_rutas.FleetDashboardTemplate";

    setup() {
        this.rpc = useService("rpc");
        this.actionService = useService("action");

        this.state = useState({
            activeTab: "panel",
            loading: true,
            error: false,
            lastUpdated: null,
            selectedRutaIndex: 0,
            selectedTripIndex: 0,
            searchQuery: "",
            kpis: {
                recorridos_hoy: 0,
                en_curso: 0,
                completados: 0,
                total_recorridos: 0,
                incidencias_activas: 0,
                total_incidencias: 0,
                avg_puntualidad: 0.0,
                avg_cumplimiento: 0.0,
                avg_integridad_gps: 0.0,
                avg_retraso: 0.0,
                avg_paradas_cumplidas: 0.0,
                avg_exactitud_sync: 0.0,
                avg_tiempo_resp: 0.0,
                avg_tiempo_resp_ms: 0.0,
                avg_frecuencia_inc: 0.0,
                avg_desviacion: 0.0,
                recorridos_activos: [],
                recorridos_historial: [],
                asignaciones: [],
                incidencias_lista: [],
                rutas_lista: [],
                vehiculos_lista: [],
                total_posiciones: 0,
                pos_hoy_count: 0,
                puntualidad_rutas: [],
                incidencias_por_tipo: [],
                metricas_iso_reales: [],
            },
        });

        this.tabs = TABS;
        this.refreshInterval = null;
        this.inFlight = false;
        this.disposed = false;

        onMounted(() => {
            this.loadData();
            this.refreshInterval = setInterval(() => this.loadData(), 30000);
        });

        onWillUnmount(() => {
            this.disposed = true;
            clearInterval(this.refreshInterval);
        });
    }

    async loadData() {
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
            Object.assign(this.state.kpis, data);
            this.state.error = false;
            this.state.lastUpdated = new Date().toLocaleTimeString();
        } catch (err) {
            if (this.disposed) return;
            console.error("Error al cargar datos del panel de rutas:", err);
            this.state.error = true;
        } finally {
            this.inFlight = false;
            if (!this.disposed) this.state.loading = false;
        }
    }

    setTab(tabId) {
        this.state.activeTab = tabId;
    }

    selectRuta(index) {
        this.state.selectedRutaIndex = index;
    }

    selectTrip(index) {
        this.state.selectedTripIndex = index;
    }

    onSearch(ev) {
        this.state.searchQuery = ev.target.value.toLowerCase();
    }

    get selectedRuta() {
        const rutas = this.state.kpis.rutas_lista || [];
        if (!rutas.length) return null;
        return rutas[this.state.selectedRutaIndex] || rutas[0];
    }

    get currentActiveTrip() {
        const activos = this.state.kpis.recorridos_activos || [];
        if (!activos.length) return null;
        return activos[this.state.selectedTripIndex] || activos[0];
    }

    get filteredHistorial() {
        const q = (this.state.searchQuery || "").trim().toLowerCase();
        const historial = this.state.kpis.recorridos_historial || [];
        if (!q) return historial;
        return historial.filter(r =>
            (r.vehiculo || "").toLowerCase().includes(q) ||
            (r.ruta || "").toLowerCase().includes(q) ||
            (r.estado_label || "").toLowerCase().includes(q)
        );
    }

    // ── ACCIONES ODOO NATIVAS ────────────────────────────────────────────────
    openRutas() { this.actionService.doAction("fleet_rutas.action_fleet_ruta"); }
    openRecorridos() { this.actionService.doAction("fleet_rutas.action_fleet_recorrido"); }
    openIncidencias() { this.actionService.doAction("fleet_rutas.action_fleet_incidencia"); }
    openMetricas() { this.actionService.doAction("fleet_rutas.action_fleet_metricas"); }
    openTelemetria() { this.actionService.doAction("fleet_rutas.action_fleet_posicion_gps"); }
    openNewRuta() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "fleet.ruta",
            views: [[false, "form"]],
            target: "current",
        });
    }
    openNewAsignacion() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "fleet.recorrido",
            views: [[false, "form"]],
            target: "current",
        });
    }
    openNewVehiculo() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "fleet.vehicle",
            views: [[false, "form"]],
            target: "current",
        });
    }

    openRecorridoDetail(id) {
        if (!id) return;
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "fleet.recorrido",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openMapaWeb(id) {
        const tripId = id || (this.currentActiveTrip ? this.currentActiveTrip.id : null);
        if (tripId) {
            window.open(`/fleet_rutas/mapa/${tripId}`, "_blank");
        } else {
            this.openRecorridos();
        }
    }

    triggerSync() {
        this.loadData();
    }
}

FleetRutasDashboard.template = xml/* xml */`
<div class="o_fleet_rutas_dashboard">
    <!-- BARRA LATERAL DE NAVEGACIÓN -->
    <nav class="fleet_sidebar" aria-label="Navegación del centro de control">
        <div class="fleet_brand">
            <i class="fa fa-bus" aria-hidden="true"/>
            <span>Transporte UTA</span>
        </div>
        <button t-foreach="tabs" t-as="tab" t-key="tab.id"
                t-att-class="'fleet_nav_item' + (state.activeTab === tab.id ? ' on' : '')"
                t-on-click="() => this.setTab(tab.id)">
            <i t-att-class="'fa ' + tab.icon" aria-hidden="true"/>
            <span t-esc="tab.label"/>
        </button>
    </nav>

    <!-- ÁREA PRINCIPAL -->
    <main class="fleet_main">
        <!-- AVISO DE ERROR SI LO HUBIERE -->
        <div t-if="state.error" class="fleet_notice is_error" role="alert">
            <span>No se pudieron actualizar los datos en tiempo real. Mostrando última información registrada.</span>
            <button class="btn s" t-on-click="() => this.loadData()">Reintentar</button>
        </div>

        <!-- ════════════════════ TAB 1: PANEL ════════════════════ -->
        <t t-if="state.activeTab === 'panel'">
            <div class="hd">
                <h2>Panel de indicadores</h2>
                <div class="row">
                    <span class="chip">Todos los recorridos</span>
                    <span class="chip"><t t-esc="state.kpis.total_recorridos"/> registros</span>
                    <button class="btn p s" t-on-click="() => this.loadData()">
                        <i class="fa fa-refresh" aria-hidden="true"/> Actualizar
                    </button>
                </div>
            </div>

            <!-- KPIs Principales Calculados de la Base de Datos -->
            <div class="g g4">
                <div class="card">
                    <div class="lb">Cumplimiento de rutas</div>
                    <div class="big"><t t-esc="state.kpis.avg_cumplimiento"/><small>%</small></div>
                    <div class="lb"><t t-esc="state.kpis.completados"/> finalizados de <t t-esc="state.kpis.total_recorridos"/> viajes</div>
                </div>
                <div class="card">
                    <div class="lb">Puntualidad global</div>
                    <div class="big"><t t-esc="state.kpis.avg_puntualidad"/><small>%</small></div>
                    <div class="lb">Llegadas dentro de tolerancia (±5 min)</div>
                </div>
                <div class="card">
                    <div class="lb">Retraso promedio</div>
                    <div class="big"><t t-esc="state.kpis.avg_retraso"/><small>min</small></div>
                    <div class="lb">Demora media sobre itinerario</div>
                </div>
                <div class="card">
                    <div class="lb">Paradas cumplidas</div>
                    <div class="big"><t t-esc="state.kpis.avg_paradas_cumplidas"/><small>%</small></div>
                    <div class="lb">Puntos de control con detección GPS</div>
                </div>
            </div>

            <!-- Gráficos Reales de Puntualidad e Incidencias -->
            <div class="g g2">
                <div class="card">
                    <h3>Puntualidad por ruta (Evaluación de Paradas)</h3>
                    <div class="bars">
                        <div t-foreach="state.kpis.puntualidad_rutas" t-as="pr" t-key="pr.id">
                            <i t-att-style="'height:' + pr.px + 'px;'"/>
                            <t t-esc="pr.nombre"/> · <t t-esc="pr.pct"/>%
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h3>Incidencias reales por tipo (<t t-esc="state.kpis.total_incidencias"/> eventos)</h3>
                    <div t-foreach="state.kpis.incidencias_por_tipo" t-as="it" t-key="it.tipo" class="hb">
                        <p><span t-esc="it.label"/><b><t t-esc="it.count"/></b></p>
                        <u><i t-att-style="'width:' + it.pct + '%;'"/></u>
                    </div>
                    <div style="margin-top:20px;">
                        <button class="btn s" t-on-click="() => this.openIncidencias()">
                            Ver todas las incidencias registradas
                        </button>
                    </div>
                </div>
            </div>

            <!-- Calidad del Sistema ISO/IEC 25010 -->
            <div class="card">
                <h3>Calidad del sistema (ISO/IEC 25010)</h3>
                <div class="g g4" style="margin:0;">
                    <div>
                        <div class="lb">Integridad de registros GPS</div>
                        <div class="md"><t t-esc="state.kpis.avg_integridad_gps"/> %</div>
                    </div>
                    <div>
                        <div class="lb">Exactitud Traccar–Odoo</div>
                        <div class="md"><t t-esc="state.kpis.avg_exactitud_sync"/> %</div>
                    </div>
                    <div>
                        <div class="lb">Tiempo de respuesta</div>
                        <div class="md"><t t-esc="state.kpis.avg_tiempo_resp"/> s (<t t-esc="state.kpis.avg_tiempo_resp_ms"/> ms)</div>
                    </div>
                    <div>
                        <div class="lb">Frecuencia de incidencias</div>
                        <div class="md"><t t-esc="state.kpis.avg_frecuencia_inc"/> inc/h</div>
                    </div>
                </div>
            </div>
            <p class="note">Métricas agregadas calculadas en tiempo real a partir de los recorridos y telemetría GPS registrada en PostgreSQL.</p>
        </t>

        <!-- ════════════════════ TAB 2: MONITOREO EN VIVO ════════════════════ -->
        <t t-if="state.activeTab === 'monitoreo'">
            <div class="hd">
                <h2>Monitoreo en vivo</h2>
                <div class="row">
                    <!-- Selector de viaje en tránsito -->
                    <span class="lb" style="margin-right:4px;">Recorrido activo:</span>
                    <select style="width:auto;display:inline-block;padding:4px 8px;font-size:13px;"
                            t-on-change="(ev) => this.selectTrip(Number(ev.target.value))">
                        <option t-foreach="state.kpis.recorridos_activos" t-as="tr" t-key="tr.id"
                                t-att-value="tr_index"
                                t-att-selected="state.selectedTripIndex === tr_index">
                            <t t-esc="tr.name"/> · <t t-esc="tr.vehiculo"/>
                        </option>
                    </select>

                    <span class="pill gn"><i class="fa fa-signal"/> <t t-esc="state.kpis.en_curso"/> en curso</span>
                    <button class="btn p s" t-on-click="() => this.openMapaWeb()">
                        <i class="fa fa-external-link"/> Abrir en Leaflet
                    </button>
                </div>
            </div>

            <t t-if="currentActiveTrip">
                <div class="g g2b">
                    <!-- Visualizador / Mapa del recorrido seleccionado -->
                    <div class="card" style="padding:0;overflow:hidden;min-height:380px;display:flex;flex-direction:column;">
                        <iframe t-att-src="'/fleet_rutas/mapa/' + currentActiveTrip.id"
                                style="width:100%;height:380px;border:none;flex:1;background:var(--map);"/>
                    </div>

                    <!-- Detalles operativos del vehículo activo -->
                    <div>
                        <div class="card">
                            <div class="lb">Vehículo en operación</div>
                            <div class="big" t-esc="currentActiveTrip.vehiculo"/>
                            <div class="lb" t-esc="currentActiveTrip.ruta"/>
                            <div class="f" style="margin-top:14px;">
                                <div>
                                    <div class="lb">Velocidad actual</div>
                                    <b style="font-size:16px;"><t t-esc="currentActiveTrip.velocidad"/> km/h</b>
                                </div>
                                <div>
                                    <div class="lb">Retraso acumulado</div>
                                    <b t-att-class="'pill ' + (currentActiveTrip.retraso_min > 5 ? 'rd' : 'gn')">
                                        +<t t-esc="currentActiveTrip.retraso_min"/> min
                                    </b>
                                </div>
                                <div>
                                    <div class="lb">Corredor</div>
                                    <b t-att-class="'pill ' + (currentActiveTrip.desviacion ? 'rd' : 'gn')">
                                        <t t-if="currentActiveTrip.desviacion">Desviado</t>
                                        <t t-else="">Dentro</t>
                                    </b>
                                </div>
                            </div>
                        </div>

                        <div class="card">
                            <h3>Puntos de control visitados (<t t-esc="currentActiveTrip.paradas_cumplidas"/>)</h3>
                            <div t-if="!currentActiveTrip.paradas.length" class="lb">Sin puntos de control asignados.</div>
                            <div t-foreach="currentActiveTrip.paradas" t-as="p" t-key="p.id" class="li">
                                <span>
                                    <b t-esc="p.nombre"/>
                                    <span class="lb" style="margin-left:6px;"><t t-esc="p.hora"/></span>
                                </span>
                                <span t-if="p.cumplida" class="pill gn">Cumplida (<t t-esc="p.distancia_min_m"/> m)</span>
                                <span t-else="" class="pill bl">Pendiente</span>
                            </div>
                        </div>
                    </div>
                </div>
            </t>
            <t t-else="">
                <div class="card">No hay recorridos activos en tránsito en este momento.</div>
            </t>
        </t>

        <!-- ════════════════════ TAB 3: RUTAS Y PARADAS ════════════════════ -->
        <t t-if="state.activeTab === 'rutas'">
            <div class="hd">
                <h2>Rutas y puntos de control registrados</h2>
                <div class="row">
                    <button class="btn p" t-on-click="() => this.openRutas()">
                        <i class="fa fa-plus"/> Gestionar rutas en Odoo
                    </button>
                </div>
            </div>

            <div class="g" style="grid-template-columns: minmax(0, 1fr) minmax(0, 2.3fr);">
                <!-- Lista de rutas reales -->
                <div class="card">
                    <h3>Rutas disponibles (<t t-esc="state.kpis.rutas_lista.length"/>)</h3>
                    <div t-if="!state.kpis.rutas_lista.length" class="lb">No hay rutas registradas.</div>
                    <button t-foreach="state.kpis.rutas_lista" t-as="r" t-key="r.id"
                            t-att-class="'rt' + (state.selectedRutaIndex === r_index ? ' on' : '')"
                            t-on-click="() => this.selectRuta(r_index)">
                        <b t-esc="r.name"/>
                        <span><t t-esc="r.origen"/> → <t t-esc="r.destino"/></span>
                        <div class="lb" style="margin-top:4px;"><t t-esc="r.distancia_km"/> km · <t t-esc="r.paradas_count"/> puntos de control</div>
                    </button>
                </div>

                <!-- Detalle y paradas reales de la ruta seleccionada -->
                <div>
                    <div t-if="selectedRuta" class="card">
                        <h3 t-esc="selectedRuta.name"/>
                        <div class="f">
                            <div><div class="lb">Origen</div><div style="font-size:15px;font-weight:600;" t-esc="selectedRuta.origen"/></div>
                            <div><div class="lb">Destino</div><div style="font-size:15px;font-weight:600;" t-esc="selectedRuta.destino"/></div>
                            <div><div class="lb">Distancia prevista</div><div style="font-size:15px;font-weight:600;"><t t-esc="selectedRuta.distancia_km"/> km</div></div>
                            <div><div class="lb">Corredor de tolerancia</div><div style="font-size:15px;font-weight:600;"><t t-esc="selectedRuta.corredor_m"/> m</div></div>
                        </div>
                    </div>

                    <div t-if="selectedRuta" class="card">
                        <h3>Puntos de control (Geocercas de parada)</h3>
                        <div class="tw">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Sec.</th>
                                        <th>Nombre del Punto</th>
                                        <th>Coordenadas GPS</th>
                                        <th>Llegada Est.</th>
                                        <th>Parada</th>
                                        <th>Salida Est.</th>
                                        <th>Tolerancia</th>
                                        <th>Radio</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr t-foreach="selectedRuta.paradas" t-as="p" t-key="p.id">
                                        <td><span class="pill bl" t-esc="p.secuencia"/></td>
                                        <td><b t-esc="p.name"/></td>
                                        <td class="lb" t-esc="p.coords"/>
                                        <td t-esc="p.llegada"/>
                                        <td><t t-esc="p.parada_min"/> min</td>
                                        <td t-esc="p.salida"/>
                                        <td t-esc="p.tolerancia"/>
                                        <td t-esc="p.radio"/>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                        <p class="note">Puntos geográficos extraídos directamente del modelo fleet.parada asociados a la ruta.</p>
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 4: ASIGNACIONES ════════════════════ -->
        <t t-if="state.activeTab === 'asignaciones'">
            <div class="hd">
                <h2>Asignaciones de flota</h2>
                <div class="row">
                    <button class="btn p" t-on-click="() => this.openRecorridos()">
                        <i class="fa fa-calendar-plus-o"/> Administrar en Odoo
                    </button>
                </div>
            </div>

            <div class="g g2b">
                <div class="card">
                    <h3>Programación de recorridos (<t t-esc="state.kpis.asignaciones.length"/> asignaciones)</h3>
                    <div class="tw">
                        <table>
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Horario</th>
                                    <th>Vehículo</th>
                                    <th>Ruta</th>
                                    <th>Estado</th>
                                    <th>Acción</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr t-foreach="state.kpis.asignaciones" t-as="a" t-key="a.id">
                                    <td t-esc="a.fecha"/>
                                    <td class="lb" t-esc="a.horario"/>
                                    <td><b t-esc="a.vehiculo"/></td>
                                    <td t-esc="a.ruta"/>
                                    <td><span t-att-class="'pill ' + a.estado_code" t-esc="a.estado_label"/></td>
                                    <td>
                                        <button class="btn s" t-on-click="() => this.openRecorridoDetail(a.id)">
                                            Ver
                                        </button>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card">
                    <h3>Validación de asignaciones operativas</h3>
                    <div style="display:grid;gap:12px;">
                        <div class="li"><span>1. Un vehículo solo puede asignarse a un recorrido a la vez.</span></div>
                        <div class="li"><span>2. Se valida la superposición temporal entre itinerarios del mismo bus.</span></div>
                        <div class="li"><span>3. Telemetría GPS de Traccar vinculada automáticamente por IMEI.</span></div>
                    </div>
                    <div style="margin-top:16px;">
                        <button class="btn p s" t-on-click="() => this.openRecorridos()">Abrir recorridos de flota</button>
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 5: RECORRIDOS E INCIDENCIAS ════════════════════ -->
        <t t-if="state.activeTab === 'recorridos'">
            <div class="hd">
                <h2>Recorridos e incidencias</h2>
                <div class="row">
                    <input type="search" placeholder="Filtrar vehículo, ruta o estado..."
                           style="width:240px;padding:6px 10px;"
                           t-on-input="onSearch"/>
                    <span class="chip">Todas las rutas</span>
                    <span class="chip">Todos los estados</span>
                    <button class="btn p s" t-on-click="() => this.openRecorridos()">
                        Ver en Odoo
                    </button>
                </div>
            </div>

            <!-- 1. Tarjeta Ancho Completo: Historial de Recorridos (card nw) -->
            <div class="card nw">
                <h3>Historial de recorridos (<t t-esc="filteredHistorial.length"/> registros)</h3>
                <div class="tw">
                    <table>
                        <thead>
                            <tr>
                                <th>Fecha</th>
                                <th>Vehículo</th>
                                <th>Ruta</th>
                                <th>Inicio prog. / real</th>
                                <th>Llegada prog. / real</th>
                                <th>Distancia est. / rec.</th>
                                <th>Estado</th>
                                <th>Detalle</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr t-foreach="filteredHistorial" t-as="r" t-key="r.id">
                                <td t-esc="r.fecha"/>
                                <td><b t-esc="r.vehiculo"/></td>
                                <td t-esc="r.ruta"/>
                                <td class="lb" t-esc="r.horario_prog_real"/>
                                <td class="lb" t-esc="r.llegada_prog_real"/>
                                <td t-esc="r.distancia_est_rec"/>
                                <td><span t-att-class="'pill ' + r.estado_code" t-esc="r.estado_label"/></td>
                                <td>
                                    <button class="btn s" t-on-click="() => this.openRecorridoDetail(r.id)">
                                        Ver detalle
                                    </button>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                <p class="note">Selecciona un recorrido con estado Incumple o Con retraso para abrir su ficha completa en Odoo.</p>
            </div>

            <!-- 2. Tarjeta Ancho Completo: Incidencias Registradas en cuadrícula de 3 columnas (g g3) -->
            <div class="card">
                <div class="hd" style="margin-bottom:14px;">
                    <h3 style="margin:0;">Incidencias registradas · <t t-esc="state.kpis.incidencias_lista.length"/> eventos</h3>
                    <button class="btn s" t-on-click="() => this.openIncidencias()">
                        Gestionar todas las incidencias en Odoo
                    </button>
                </div>
                <div t-if="!state.kpis.incidencias_lista.length" class="lb">No hay incidencias registradas en el sistema.</div>
                <div t-if="state.kpis.incidencias_lista.length" class="g g3">
                    <div t-foreach="state.kpis.incidencias_lista" t-as="inc" t-key="inc.id" class="li" style="display:block;border-bottom:0;padding:0 0 14px;">
                        <span t-att-class="'pill ' + inc.severidad_code" t-esc="inc.tipo_label"/>
                        <div class="lb" style="margin-top:6px;font-weight:600;color:var(--tx);">
                            <t t-esc="inc.vehiculo"/> · <t t-esc="inc.ruta"/> · <span style="font-weight:400;color:var(--mu);"><t t-esc="inc.hora"/></span>
                        </div>
                        <div class="lb" style="margin-top:4px;" t-esc="inc.descripcion"/>
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 6: LÍNEA DE TIEMPO ════════════════════ -->
        <t t-if="state.activeTab === 'tiempo'">
            <div class="hd">
                <h2>Línea de tiempo · Análisis temporal del viaje</h2>
                <div class="row">
                    <span class="lb" style="margin-right:4px;">Recorrido seleccionado:</span>
                    <select style="width:auto;display:inline-block;padding:4px 8px;font-size:13px;"
                            t-on-change="(ev) => this.selectTrip(Number(ev.target.value))">
                        <option t-foreach="state.kpis.recorridos_activos" t-as="tr" t-key="tr.id"
                                t-att-value="tr_index"
                                t-att-selected="state.selectedTripIndex === tr_index">
                            <t t-esc="tr.name"/> · <t t-esc="tr.vehiculo"/>
                        </option>
                    </select>
                </div>
            </div>

            <t t-if="currentActiveTrip">
                <div class="card">
                    <div class="hd" style="margin-bottom:12px;">
                        <h3 style="margin:0;">
                            Progreso de viaje: <t t-esc="currentActiveTrip.name"/> (<t t-esc="currentActiveTrip.vehiculo"/>)
                        </h3>
                        <span class="lb">
                            <i class="sw" style="background:#fee2a4;border:1px solid #e8c25f;"/> Puntos cumplidos
                            <i class="sw" style="background:var(--bls);border:1px solid var(--bd);"/> En tránsito
                        </span>
                    </div>

                    <!-- Detalle por punto de control real del recorrido -->
                    <div class="tw">
                        <table>
                            <thead>
                                <tr>
                                    <th>Secuencia</th>
                                    <th>Punto de Control</th>
                                    <th>Hora Llegada Real</th>
                                    <th>Retraso en Punto</th>
                                    <th>Distancia al Centroide</th>
                                    <th>Estado de Detección</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr t-foreach="currentActiveTrip.paradas" t-as="cp" t-key="cp.id">
                                    <td><span class="pill bl" t-esc="cp.secuencia"/></td>
                                    <td><b t-esc="cp.nombre"/></td>
                                    <td t-esc="cp.hora"/>
                                    <td>
                                        <span t-att-class="'pill ' + (cp.retraso_min > 5 ? 'rd' : (cp.retraso_min > 0 ? 'am' : 'gn'))">
                                            +<t t-esc="cp.retraso_min"/> min
                                        </span>
                                    </td>
                                    <td><t t-esc="cp.distancia_min_m"/> m</td>
                                    <td>
                                        <span t-if="cp.cumplida" class="pill gn">Cumplida</span>
                                        <span t-else="" class="pill bl">Pendiente</span>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="g g2b">
                    <div class="card">
                        <h3>Resumen del viaje en curso</h3>
                        <div class="f">
                            <div><div class="lb">Ruta</div><b t-esc="currentActiveTrip.ruta"/></div>
                            <div><div class="lb">Inicio del viaje</div><b t-esc="currentActiveTrip.fecha_inicio"/></div>
                            <div><div class="lb">Velocidad promedio</div><b><t t-esc="currentActiveTrip.velocidad"/> km/h</b></div>
                            <div><div class="lb">Cumplimiento paradas</div><b><t t-esc="currentActiveTrip.paradas_cumplidas"/></b></div>
                        </div>
                    </div>

                    <div class="card">
                        <h3>Reglas de tiempo de transporte</h3>
                        <div class="li" style="display:block;">
                            <b>Llegada:</b> Primera posición registrada dentro del radio geográfico de la parada.
                        </div>
                        <div class="li" style="display:block;">
                            <b>Tolerancia:</b> Margen de ±5 min sobre el horario programado sin considerarse retraso.
                        </div>
                    </div>
                </div>
            </t>
            <t t-else="">
                <div class="card">No hay datos de viaje para mostrar en este momento.</div>
            </t>
        </t>

        <!-- ════════════════════ TAB 7: VEHÍCULOS Y GPS ════════════════════ -->
        <t t-if="state.activeTab === 'vehiculos'">
            <div class="hd">
                <h2>Vehículos y dispositivos GPS registrados</h2>
                <div class="row">
                    <button class="btn p" t-on-click="() => this.openTelemetria()">
                        <i class="fa fa-map-marker"/> Historial de telemetría GPS
                    </button>
                </div>
            </div>

            <div class="g g2b">
                <div class="card">
                    <h3>Flota registrada (<t t-esc="state.kpis.vehiculos_lista.length"/> vehículos)</h3>
                    <div class="tw">
                        <table>
                            <thead>
                                <tr>
                                    <th>Placa / Bus</th>
                                    <th>Modelo</th>
                                    <th>Dispositivo Traccar</th>
                                    <th>IMEI / ID</th>
                                    <th>Velocidad</th>
                                    <th>Última posición</th>
                                    <th>Estado GPS</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr t-foreach="state.kpis.vehiculos_lista" t-as="v" t-key="v.id">
                                    <td><b t-esc="v.name"/></td>
                                    <td class="lb" t-esc="v.modelo"/>
                                    <td t-esc="v.dispositivo"/>
                                    <td class="lb" t-esc="v.imei"/>
                                    <td t-esc="v.velocidad"/>
                                    <td class="lb" t-esc="v.ultima_pos"/>
                                    <td><span t-att-class="'pill ' + v.estado_code" t-esc="v.estado_gps"/></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card">
                    <h3>Dispositivos GPS asociados</h3>
                    <div style="display:grid;gap:12px;">
                        <div t-foreach="state.kpis.vehiculos_lista" t-as="vh" t-key="vh.id" class="li">
                            <span><b t-esc="vh.name"/> · <t t-esc="vh.modelo"/></span>
                            <span class="pill gn" t-esc="vh.dispositivo"/>
                        </div>
                        <p class="note" style="margin:0;">Los vehículos están asociados directamente por ID numérico en Traccar Server.</p>
                        <div>
                            <button class="btn p s" t-on-click="() => this.loadData()">Comprobar enlaces</button>
                        </div>
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 8: MÉTRICAS ISO 25010 ════════════════════ -->
        <t t-if="state.activeTab === 'metricas'">
            <div class="hd">
                <h2>Métricas reales ISO/IEC 25010</h2>
                <div class="row">
                    <button class="btn p s" t-on-click="() => this.openMetricas()">
                        <i class="fa fa-table"/> Ver tabla relacional en Odoo
                    </button>
                </div>
            </div>

            <div class="card">
                <div class="tw">
                    <table>
                        <thead>
                            <tr>
                                <th>Indicador</th>
                                <th>Fórmula matemática</th>
                                <th>Fuente de datos</th>
                                <th>Unidad</th>
                                <th>Resultado real calculado</th>
                                <th>Interpretación operativa</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr t-foreach="state.kpis.metricas_iso_reales" t-as="m" t-key="m.ind">
                                <td><b t-esc="m.ind"/></td>
                                <td class="lb" t-esc="m.form"/>
                                <td t-esc="m.fte"/>
                                <td><span class="chip" t-esc="m.uni"/></td>
                                <td><b t-esc="m.res"/></td>
                                <td t-esc="m.interp"/>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
            <p class="note">Todos los resultados mostrados provienen del cálculo relacional en tiempo real del modelo fleet.metricas.recorrido.</p>
        </t>

        <!-- ════════════════════ TAB 9: SINCRONIZACIÓN TRACCAR ════════════════════ -->
        <t t-if="state.activeTab === 'sync'">
            <div class="hd">
                <h2>Sincronización Traccar</h2>
                <div class="row">
                    <span class="pill gn"><i class="fa fa-link"/> Traccar Server Online</span>
                    <button class="btn p s" t-on-click="() => this.triggerSync()">
                        <i class="fa fa-refresh"/> Sincronizar ahora
                    </button>
                </div>
            </div>

            <div class="g g4">
                <div class="card">
                    <div class="lb">Última sincronización</div>
                    <div class="big" style="font-size:22px;"><t t-esc="state.lastUpdated or 'hace 30 s'"/></div>
                    <div class="lb">API REST Traccar / Webhook</div>
                </div>
                <div class="card">
                    <div class="lb">Posiciones GPS procesadas hoy</div>
                    <div class="big"><t t-esc="state.kpis.pos_hoy_count"/></div>
                    <div class="lb"><t t-esc="state.kpis.total_posiciones"/> totales registradas</div>
                </div>
                <div class="card">
                    <div class="lb">Dispositivos GPS enlazados</div>
                    <div class="big"><t t-esc="state.kpis.vehiculos_lista.length"/></div>
                    <div class="lb">Todos operativos</div>
                </div>
                <div class="card">
                    <div class="lb">Recorridos auditados</div>
                    <div class="big"><t t-esc="state.kpis.total_recorridos"/></div>
                    <div class="lb"><t t-esc="state.kpis.en_curso"/> en curso actualmente</div>
                </div>
            </div>

            <div class="g g2b">
                <div class="card">
                    <h3>Dispositivos GPS configurados en Traccar</h3>
                    <div class="tw">
                        <table>
                            <thead>
                                <tr>
                                    <th>Dispositivo</th>
                                    <th>Vehículo</th>
                                    <th>Velocidad</th>
                                    <th>Última posición</th>
                                    <th>Estado</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr t-foreach="state.kpis.vehiculos_lista" t-as="v" t-key="v.id">
                                    <td><b t-esc="v.dispositivo"/></td>
                                    <td><b t-esc="v.name"/> (<t t-esc="v.modelo"/>)</td>
                                    <td t-esc="v.velocidad"/>
                                    <td class="lb" t-esc="v.ultima_pos"/>
                                    <td><span t-att-class="'pill ' + v.estado_code" t-esc="v.estado_gps"/></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card">
                    <h3>Infraestructura de microservicios</h3>
                    <div class="li"><span>Traccar Server (Puerto 8082 / 5055)</span><span class="pill gn">Activo</span></div>
                    <div class="li"><span>PostgreSQL 15 (Puerto 5432)</span><span class="pill gn">Conectado</span></div>
                    <div class="li"><span>Grafana 11.4 (Puerto 3000)</span><span class="pill gn">Activo</span></div>
                    <div class="li"><span>Odoo 16 (Puerto 8069 / 8070)</span><span class="pill gn">En servicio</span></div>
                    <div style="margin-top:16px;">
                        <button class="btn p s" t-on-click="() => this.triggerSync()">Forzar verificación</button>
                    </div>
                </div>
            </div>
        </t>
    </main>
</div>
`;

registry.category("actions").add("fleet_rutas.dashboard", FleetRutasDashboard);
export default FleetRutasDashboard;
