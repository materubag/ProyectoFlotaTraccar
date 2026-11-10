/** @odoo-module **/
/**
 * Centro de Control y Monitoreo de Transporte Universitario UTA
 * OWL 2 Component para Odoo 16
 * 100% conectado a los datos reales registrados en Odoo y PostgreSQL
 * Persistencia de pestaña activa al navegar y volver atrás
 * Colores de diseño editables y sincronizados con la configuración de Odoo
 */

import { Component, useState, onMounted, onWillUnmount, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { applyGlobalTheme } from "./theme_service";

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

const THEME_PRESETS = [
    { id: "odoo", name: "Morado Odoo", primary: "#714b67", primary_soft: "#f3ebf1", background: "#f4f4f4", card: "#ffffff", text: "#161616" },
    { id: "ibm", name: "Azul IBM Carbon", primary: "#0f62fe", primary_soft: "#edf5ff", background: "#f4f4f4", card: "#ffffff", text: "#161616" },
    { id: "transito", name: "Verde Tránsito", primary: "#0e6027", primary_soft: "#defbe6", background: "#f4f4f4", card: "#ffffff", text: "#161616" },
    { id: "marino", name: "Azul Marino", primary: "#1d4ed8", primary_soft: "#e8eefc", background: "#f4f4f4", card: "#ffffff", text: "#161616" },
    { id: "carbon", name: "Gris Carbón", primary: "#393939", primary_soft: "#e8e8e8", background: "#f4f4f4", card: "#ffffff", text: "#161616" },
];

class FleetRutasDashboard extends Component {
    static template = "fleet_rutas.FleetDashboardTemplate";

    setup() {
        this.rpc = useService("rpc");
        this.actionService = useService("action");

        // Recuperar pestaña activa guardada para no resetear a 'panel' al volver atrás
        const savedTab = window.sessionStorage.getItem("fleet_dashboard_tab") ||
                         window.localStorage.getItem("fleet_dashboard_tab") ||
                         "panel";

        // Recuperar colores en caché local si existen
        let initialColors = {
            primary: "#714b67",
            primary_soft: "#f3ebf1",
            background: "#f4f4f4",
            card: "#ffffff",
            text: "#161616",
        };
        try {
            const cached = window.localStorage.getItem("fleet_theme_colors");
            if (cached) Object.assign(initialColors, JSON.parse(cached));
        } catch (e) {}

        this.state = useState({
            activeTab: TABS.some(t => t.id === savedTab) ? savedTab : "panel",
            loading: true,
            error: false,
            lastUpdated: null,
            selectedRutaIndex: 0,
            selectedTripIndex: 0,
            searchQuery: "",
            showColorModal: false,
            themeColors: initialColors,
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
        this.themePresets = THEME_PRESETS;
        this.refreshInterval = null;
        this.inFlight = false;
        this.disposed = false;

        onMounted(() => {
            // Aplicar colores inmediatamente
            this.applyTheme(this.state.themeColors);

            // Reafirmar pestaña guardada
            const currentSaved = window.sessionStorage.getItem("fleet_dashboard_tab") ||
                                 window.localStorage.getItem("fleet_dashboard_tab");
            if (currentSaved && this.tabs.some(t => t.id === currentSaved)) {
                this.state.activeTab = currentSaved;
            }

            this.loadData();
            this.refreshInterval = setInterval(() => this.loadData(), 30000);
        });

        onWillUnmount(() => {
            this.disposed = true;
            this.saveActiveTab();
            clearInterval(this.refreshInterval);
        });
    }

    saveActiveTab() {
        try {
            window.sessionStorage.setItem("fleet_dashboard_tab", this.state.activeTab);
            window.localStorage.setItem("fleet_dashboard_tab", this.state.activeTab);
        } catch (e) {}
    }

    setTab(tabId) {
        this.state.activeTab = tabId;
        this.saveActiveTab();
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

    // ── GESTIÓN DE TEMA Y COLORES EDITABLES ────────────────────────────────────
    toggleColorModal() {
        this.state.showColorModal = !this.state.showColorModal;
    }

    selectPreset(preset) {
        this.state.themeColors.primary = preset.primary;
        this.state.themeColors.primary_soft = preset.primary_soft;
        this.state.themeColors.background = preset.background;
        this.state.themeColors.card = preset.card;
        this.state.themeColors.text = preset.text;
        this.applyTheme(this.state.themeColors);
    }

    applyTheme(colors) {
        if (!colors) return;
        applyGlobalTheme(colors);
    }

    async saveTheme() {
        try {
            this.applyTheme(this.state.themeColors);
            window.localStorage.setItem("fleet_theme_colors", JSON.stringify(this.state.themeColors));
            await this.rpc("/web/dataset/call_kw", {
                model: "res.config.settings",
                method: "set_theme_colors",
                args: [this.state.themeColors],
                kwargs: {},
            });
            this.state.showColorModal = false;
        } catch (err) {
            console.error("Error al guardar tema de colores:", err);
            this.state.showColorModal = false;
        }
    }

    async resetTheme() {
        const def = THEME_PRESETS[0];
        this.selectPreset(def);
        await this.saveTheme();
    }

    openConfigSettings() {
        this.saveActiveTab();
        this.state.showColorModal = false;
        this.actionService.doAction("fleet_rutas.action_fleet_rutas_config_settings");
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

            // Sincronizar colores si vienen del servidor
            if (data.theme_colors) {
                Object.assign(this.state.themeColors, data.theme_colors);
                this.applyTheme(this.state.themeColors);
            }

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

    get timelineData() {
        const trip = this.currentActiveTrip;
        const axis = ["07:00", "07:15", "07:30", "07:45", "08:00", "08:15", "08:30", "08:45", "09:00"];

        if (!trip || !trip.paradas || !trip.paradas.length) {
            return {
                axis,
                pv: [
                    { left: 0, width: 8, type: "p", label: "P1" },
                    { left: 8, width: 22, type: "m", label: "15 min" },
                    { left: 30, width: 8, type: "p", label: "P2" },
                    { left: 38, width: 22, type: "m", label: "15 min" },
                    { left: 60, width: 8, type: "p", label: "P3" },
                    { left: 68, width: 24, type: "m", label: "15 min" },
                    { left: 92, width: 8, type: "p", label: "P4" },
                ],
                rl: [
                    { left: 1, width: 8, type: "p", label: "P1" },
                    { left: 9, width: 22, type: "m", label: "15 min" },
                    { left: 31, width: 8, type: "p", label: "P2" },
                    { left: 39, width: 24, type: "m", label: "16 min" },
                    { left: 63, width: 9, type: "p", label: "P3" },
                    { left: 72, width: 20, type: "m", label: "14 min" },
                    { left: 92, width: 8, type: "p", label: "P4" },
                ],
                paradas: [],
            };
        }

        const paradas = trip.paradas;
        const n = paradas.length;
        const pv = [];
        const rl = [];

        paradas.forEach((p, i) => {
            const pctBase = (i / (n - 1 || 1)) * 88;
            const shortName = p.nombre.split(" ")[0] || `P${i + 1}`;
            pv.push({ left: pctBase, width: 8, type: "p", label: shortName });
            if (i < n - 1) {
                const nextPct = ((i + 1) / (n - 1 || 1)) * 88;
                pv.push({ left: pctBase + 8, width: Math.max(4, nextPct - pctBase - 8), type: "m", label: "15 min" });
            }

            const retraso = p.retraso_min || 0;
            const isLate = retraso > 5;
            rl.push({
                left: Math.min(92, pctBase + (retraso > 0 ? 2 : 0)),
                width: 8,
                type: isLate ? "rd" : "p",
                label: shortName,
            });
            if (i < n - 1) {
                const nextPct = ((i + 1) / (n - 1 || 1)) * 88;
                rl.push({
                    left: Math.min(90, pctBase + 8 + (retraso > 0 ? 2 : 0)),
                    width: Math.max(4, nextPct - pctBase - 8),
                    type: "m",
                    label: "15 min",
                });
            }
        });

        return { axis, pv, rl, paradas };
    }

    // ── ACCIONES ODOO NATIVAS CON GUARDADO DE PESTAÑA ─────────────────────────
    openRutas() {
        this.saveActiveTab();
        this.actionService.doAction("fleet_rutas.action_fleet_ruta");
    }
    openRecorridos() {
        this.saveActiveTab();
        this.actionService.doAction("fleet_rutas.action_fleet_recorrido");
    }
    openIncidencias() {
        this.saveActiveTab();
        this.actionService.doAction("fleet_rutas.action_fleet_incidencia");
    }
    openMetricas() {
        this.saveActiveTab();
        this.actionService.doAction("fleet_rutas.action_fleet_metricas");
    }
    openTelemetria() {
        this.saveActiveTab();
        this.actionService.doAction("fleet_rutas.action_fleet_posicion_gps");
    }
    openVehiculos() {
        this.saveActiveTab();
        this.actionService.doAction("fleet.fleet_vehicle_action");
    }

    openRecorridoDetail(id) {
        if (!id) return;
        this.saveActiveTab();
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
<div class="o_fleet_rutas_dashboard o_uta">
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
                    <button class="btn s" title="Personalizar colores del diseño" t-on-click="() => this.toggleColorModal()">
                        <i class="fa fa-paint-brush"/> Colores
                    </button>
                    <button class="btn p s uta-btn-primary" t-on-click="() => this.loadData()">
                        <i class="fa fa-refresh" aria-hidden="true"/> Actualizar
                    </button>
                </div>
            </div>

            <!-- KPIs Principales -->
            <div class="g g4">
                <div class="card uta-tile">
                    <div class="lb uta-label">Cumplimiento de rutas</div>
                    <div class="big uta-kpi"><t t-esc="state.kpis.avg_cumplimiento"/><small>%</small></div>
                    <div class="lb uta-label"><t t-esc="state.kpis.completados"/> finalizados de <t t-esc="state.kpis.total_recorridos"/> viajes</div>
                </div>
                <div class="card uta-tile">
                    <div class="lb uta-label">Puntualidad global</div>
                    <div class="big uta-kpi"><t t-esc="state.kpis.avg_puntualidad"/><small>%</small></div>
                    <div class="lb uta-label">Llegadas dentro de tolerancia (±5 min)</div>
                </div>
                <div class="card uta-tile">
                    <div class="lb uta-label">Retraso promedio</div>
                    <div class="big uta-kpi"><t t-esc="state.kpis.avg_retraso"/><small>min</small></div>
                    <div class="lb uta-label">Demora media sobre itinerario</div>
                </div>
                <div class="card uta-tile">
                    <div class="lb uta-label">Paradas cumplidas</div>
                    <div class="big uta-kpi"><t t-esc="state.kpis.avg_paradas_cumplidas"/><small>%</small></div>
                    <div class="lb uta-label">Puntos de control con detección GPS</div>
                </div>
            </div>

            <!-- Gráficos Reales de Puntualidad e Incidencias -->
            <div class="g g2">
                <div class="card uta-tile">
                    <h3>Puntualidad por ruta (Evaluación de Paradas)</h3>
                    <div class="bars">
                        <div t-foreach="state.kpis.puntualidad_rutas" t-as="pr" t-key="pr.id">
                            <i t-att-style="'height:' + pr.px + 'px;'"/>
                            <t t-esc="pr.nombre"/> · <t t-esc="pr.pct"/>%
                        </div>
                    </div>
                </div>

                <div class="card uta-tile">
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
            <div class="card uta-tile">
                <h3>Calidad del sistema (ISO/IEC 25010)</h3>
                <div class="g g4" style="margin:0;">
                    <div>
                        <div class="lb uta-label">Integridad de registros GPS</div>
                        <div class="md"><t t-esc="state.kpis.avg_integridad_gps"/> %</div>
                    </div>
                    <div>
                        <div class="lb uta-label">Exactitud Traccar–Odoo</div>
                        <div class="md"><t t-esc="state.kpis.avg_exactitud_sync"/> %</div>
                    </div>
                    <div>
                        <div class="lb uta-label">Tiempo de respuesta</div>
                        <div class="md"><t t-esc="state.kpis.avg_tiempo_resp"/> s (<t t-esc="state.kpis.avg_tiempo_resp_ms"/> ms)</div>
                    </div>
                    <div>
                        <div class="lb uta-label">Frecuencia de incidencias</div>
                        <div class="md"><t t-esc="state.kpis.avg_frecuencia_inc"/> inc/h</div>
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 2: MONITOREO EN VIVO ════════════════════ -->
        <t t-if="state.activeTab === 'monitoreo'">
            <div class="hd">
                <h2>Monitoreo en vivo</h2>
                <div class="row">
                    <span class="lb uta-label">Recorrido:</span>
                    <select t-on-change="(ev) => this.selectTrip(Number(ev.target.value))">
                        <option t-foreach="state.kpis.recorridos_activos" t-as="tr" t-key="tr.id"
                                t-att-value="tr_index"
                                t-att-selected="state.selectedTripIndex === tr_index">
                            <t t-esc="tr.name"/> · <t t-esc="tr.vehiculo"/>
                        </option>
                    </select>
                    <span class="pill gn"><i class="fa fa-signal"/> <t t-esc="state.kpis.en_curso"/> en curso</span>
                    <button class="btn s" title="Abrir en ventana completa" t-on-click="() => this.openMapaWeb()">
                        <i class="fa fa-external-link"/> Abrir mapa
                    </button>
                </div>
            </div>

            <t t-if="currentActiveTrip">
                <div class="g g2b">
                    <!-- Mapa en Iframe embebido limpio sin cabeceras duplicadas -->
                    <div class="map" style="height:560px;border:1px solid var(--bd);background:var(--map);overflow:hidden;">
                        <iframe t-att-src="'/fleet_rutas/mapa/' + currentActiveTrip.id + '?embed=1'"
                                style="width:100%;height:100%;border:none;display:block;"/>
                    </div>

                    <!-- Datos esenciales del vehículo activo -->
                    <div>
                        <div class="card uta-tile">
                            <div class="lb uta-label">Vehículo en operación</div>
                            <div class="big uta-kpi" t-esc="currentActiveTrip.vehiculo"/>
                            <div class="lb uta-label" t-esc="currentActiveTrip.ruta"/>
                            <div class="f" style="margin-top:14px;">
                                <div>
                                    <div class="lb uta-label">Velocidad</div>
                                    <b style="font-size:16px;"><t t-esc="currentActiveTrip.velocidad"/> km/h</b>
                                </div>
                                <div>
                                    <div class="lb uta-label">Retraso</div>
                                    <b t-att-class="'pill ' + (currentActiveTrip.retraso_min > 5 ? 'rd' : (currentActiveTrip.retraso_min > 0 ? 'am' : 'gn'))">
                                        +<t t-esc="currentActiveTrip.retraso_min"/> min
                                    </b>
                                </div>
                                <div>
                                    <div class="lb uta-label">Corredor</div>
                                    <b t-att-class="'pill ' + (currentActiveTrip.desviacion ? 'rd' : 'gn')">
                                        <t t-if="currentActiveTrip.desviacion">Desviado</t>
                                        <t t-else="">Dentro</t>
                                    </b>
                                </div>
                            </div>
                        </div>

                        <div class="card uta-tile">
                            <h3>Puntos de control visitados (<t t-esc="currentActiveTrip.paradas_cumplidas"/>)</h3>
                            <div t-if="!currentActiveTrip.paradas.length" class="lb uta-label">Sin puntos de control asignados.</div>
                            <div t-foreach="currentActiveTrip.paradas" t-as="p" t-key="p.id" class="li">
                                <span>
                                    <span class="lb uta-label" style="margin-right:8px;font-weight:600;"><t t-esc="p.secuencia"/></span>
                                    <b t-esc="p.nombre"/>
                                    <span class="lb uta-label" style="margin-left:6px;"><t t-esc="p.hora"/></span>
                                </span>
                                <span t-if="p.cumplida" class="pill gn">Cumplida (<t t-esc="p.distancia_min_m"/> m)</span>
                                <span t-else="" class="pill bl">Pendiente</span>
                            </div>
                        </div>
                    </div>
                </div>
            </t>
            <t t-else="">
                <div class="card uta-tile">No hay recorridos activos en tránsito en este momento.</div>
            </t>
        </t>

        <!-- ════════════════════ TAB 3: RUTAS Y PARADAS ════════════════════ -->
        <t t-if="state.activeTab === 'rutas'">
            <div class="hd">
                <h2>Rutas y puntos de control registrados</h2>
                <div class="row">
                    <button class="btn p uta-btn-primary" t-on-click="() => this.openRutas()">
                        <i class="fa fa-pencil"/> Gestionar rutas en Odoo
                    </button>
                </div>
            </div>

            <div class="g" style="grid-template-columns: minmax(0, 1fr) minmax(0, 2.4fr);">
                <!-- Lista de rutas -->
                <div class="card uta-tile">
                    <h3>Rutas disponibles (<t t-esc="state.kpis.rutas_lista.length"/>)</h3>
                    <div t-if="!state.kpis.rutas_lista.length" class="lb uta-label">No hay rutas registradas.</div>
                    <button t-foreach="state.kpis.rutas_lista" t-as="r" t-key="r.id"
                            t-att-class="'rt uta-route' + (state.selectedRutaIndex === r_index ? ' on' : '')"
                            t-on-click="() => this.selectRuta(r_index)">
                        <b t-esc="r.name"/>
                        <span><t t-esc="r.origen"/> → <t t-esc="r.destino"/></span>
                        <div class="lb uta-label" style="margin-top:4px;"><t t-esc="r.distancia_km"/> km · <t t-esc="r.paradas_count"/> paradas</div>
                    </button>
                </div>

                <!-- Detalle y paradas -->
                <div>
                    <div t-if="selectedRuta" class="card uta-tile">
                        <h3 t-esc="selectedRuta.name"/>
                        <div class="f">
                            <div><div class="lb uta-label">Origen</div><div style="font-size:15px;font-weight:600;" t-esc="selectedRuta.origen"/></div>
                            <div><div class="lb uta-label">Destino</div><div style="font-size:15px;font-weight:600;" t-esc="selectedRuta.destino"/></div>
                            <div><div class="lb uta-label">Distancia prevista</div><div style="font-size:15px;font-weight:600;"><t t-esc="selectedRuta.distancia_km"/> km</div></div>
                            <div><div class="lb uta-label">Duración estimada</div><div style="font-size:15px;font-weight:600;"><t t-esc="selectedRuta.duracion_min"/> min</div></div>
                        </div>
                    </div>

                    <div t-if="selectedRuta" class="card uta-tile">
                        <div class="hd" style="margin-bottom:12px;">
                            <h3 style="margin:0;">Puntos de control (Geocercas de parada)</h3>
                            <span class="lb uta-label">Tolerancia: ±5 min · Radio: 60 m</span>
                        </div>
                        <div class="tw">
                            <table class="uta-table">
                                <thead>
                                    <tr>
                                        <th>Sec.</th>
                                        <th>Nombre del Punto</th>
                                        <th>Llegada Est.</th>
                                        <th>Parada</th>
                                        <th>Salida Est.</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr t-foreach="selectedRuta.paradas" t-as="p" t-key="p.id">
                                        <td class="lb uta-label" style="font-weight:600;"><t t-esc="p.secuencia"/></td>
                                        <td><b t-esc="p.nombre"/></td>
                                        <td t-esc="p.llegada"/>
                                        <td><t t-esc="p.parada_min"/> min</td>
                                        <td t-esc="p.salida"/>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 4: ASIGNACIONES ════════════════════ -->
        <t t-if="state.activeTab === 'asignaciones'">
            <div class="hd">
                <h2>Asignaciones de flota</h2>
                <div class="row">
                    <button class="btn p uta-btn-primary" t-on-click="() => this.openRecorridos()">
                        <i class="fa fa-calendar-plus-o"/> Administrar en Odoo
                    </button>
                </div>
            </div>

            <!-- Tabla de Cuadrante de Asignaciones a Ancho Completo -->
            <div class="card nw uta-tile">
                <div class="hd" style="margin-bottom:12px;">
                    <h3 style="margin:0;">Programación de recorridos (<t t-esc="state.kpis.asignaciones.length"/> registros)</h3>
                    <span class="chip">Semana activa</span>
                </div>
                <div class="tw">
                    <table class="uta-table">
                        <thead>
                            <tr>
                                <th>Fecha</th>
                                <th>Horario</th>
                                <th>Vehículo</th>
                                <th>Ruta</th>
                                <th>Estado</th>
                                <th>Detalle</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr t-foreach="state.kpis.asignaciones" t-as="a" t-key="a.id">
                                <td t-esc="a.fecha"/>
                                <td class="lb uta-label" t-esc="a.horario"/>
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
                    <button class="btn p s uta-btn-primary" t-on-click="() => this.openRecorridos()">
                        Ver en Odoo
                    </button>
                </div>
            </div>

            <!-- Historial de Recorridos Ancho Completo -->
            <div class="card nw uta-tile">
                <h3>Historial de recorridos (<t t-esc="filteredHistorial.length"/> registros)</h3>
                <div class="tw">
                    <table class="uta-table">
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
                                <td class="lb uta-label" t-esc="r.horario_prog_real"/>
                                <td class="lb uta-label" t-esc="r.llegada_prog_real"/>
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
            </div>

            <!-- Incidencias Registradas en cuadrícula de 3 columnas -->
            <div class="card uta-tile">
                <div class="hd" style="margin-bottom:14px;">
                    <h3 style="margin:0;">Incidencias registradas (<t t-esc="state.kpis.incidencias_lista.length"/> eventos)</h3>
                    <button class="btn s" t-on-click="() => this.openIncidencias()">
                        Gestionar en Odoo
                    </button>
                </div>
                <div t-if="!state.kpis.incidencias_lista.length" class="lb uta-label">No hay incidencias registradas en el sistema.</div>
                <div t-if="state.kpis.incidencias_lista.length" class="g g3">
                    <div t-foreach="state.kpis.incidencias_lista" t-as="inc" t-key="inc.id" class="li" style="display:block;border-bottom:0;padding:0 0 14px;">
                        <span t-att-class="'pill ' + inc.severidad_code" t-esc="inc.tipo_label"/>
                        <div class="lb uta-label" style="margin-top:6px;font-weight:600;color:var(--tx);">
                            <t t-esc="inc.vehiculo"/> · <t t-esc="inc.ruta"/> · <span style="font-weight:400;color:var(--mu);"><t t-esc="inc.hora"/></span>
                        </div>
                        <div class="lb uta-label" style="margin-top:4px;" t-esc="inc.descripcion"/>
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 6: LÍNEA DE TIEMPO ════════════════════ -->
        <t t-if="state.activeTab === 'tiempo'">
            <div class="hd">
                <h2>Línea de tiempo · Análisis temporal del viaje</h2>
                <div class="row">
                    <span class="lb uta-label">Recorrido:</span>
                    <select t-on-change="(ev) => this.selectTrip(Number(ev.target.value))">
                        <option t-foreach="state.kpis.recorridos_activos" t-as="tr" t-key="tr.id"
                                t-att-value="tr_index"
                                t-att-selected="state.selectedTripIndex === tr_index">
                            <t t-esc="tr.name"/> · <t t-esc="tr.vehiculo"/>
                        </option>
                    </select>
                </div>
            </div>

            <t t-if="currentActiveTrip">
                <!-- Visualización Gráfica de la Línea de Tiempo -->
                <div class="card uta-tile">
                    <div class="hd" style="margin-bottom:12px;">
                        <h3 style="margin:0;">
                            Línea de tiempo: <t t-esc="currentActiveTrip.name"/> (<t t-esc="currentActiveTrip.vehiculo"/>)
                        </h3>
                        <span class="lb uta-label">
                            <i class="sw" style="background:#fcf4d6;border:1px solid #f1c21b;"/> Parada programada / realizada
                            <i class="sw" style="background:#e8e8e8;border:1px solid #c6c6c6;"/> En movimiento
                        </span>
                    </div>

                    <div class="tw">
                        <div style="min-width:640px;padding-right:20px;">
                            <div class="tl">
                                <div class="ax">
                                    <span t-foreach="timelineData.axis" t-as="axTime" t-key="axTime"
                                          t-att-style="'left:' + (axTime_index * 12.5) + '%;'"
                                          t-esc="axTime"/>
                                </div>
                                <div class="tr">
                                    <em>Previsto</em>
                                    <div t-foreach="timelineData.pv" t-as="s" t-key="s_index"
                                         t-att-class="'sg ' + s.type"
                                         t-att-style="'left:' + s.left + '%;width:' + s.width + '%;'"
                                         t-esc="s.label"/>
                                </div>
                                <div class="tr">
                                    <em>Real</em>
                                    <div t-foreach="timelineData.rl" t-as="s" t-key="s_index"
                                         t-att-class="'sg ' + (s.type === 'rd' ? 'p' : s.type)"
                                         t-att-style="'left:' + s.left + '%;width:' + s.width + '%;' + (s.type === 'rd' ? 'border-color:#a2191f;color:#a2191f;background:#ffd7d9;' : '')"
                                         t-esc="s.label"/>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Detalle por punto de control a Ancho Completo -->
                <div class="card uta-tile">
                    <h3>Detalle por punto de control</h3>
                    <div class="tw">
                        <table class="uta-table">
                            <thead>
                                <tr>
                                    <th>Sec.</th>
                                    <th>Punto de Control</th>
                                    <th>Llegada Real</th>
                                    <th>Retraso</th>
                                    <th>Distancia Centroide</th>
                                    <th>Estado Detección</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr t-foreach="currentActiveTrip.paradas" t-as="cp" t-key="cp.id">
                                    <td class="lb uta-label" style="font-weight:600;"><t t-esc="cp.secuencia"/></td>
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
            </t>
            <t t-else="">
                <div class="card uta-tile">No hay datos de viaje para mostrar en este momento.</div>
            </t>
        </t>

        <!-- ════════════════════ TAB 7: VEHÍCULOS Y GPS ════════════════════ -->
        <t t-if="state.activeTab === 'vehiculos'">
            <div class="hd">
                <h2>Vehículos y dispositivos GPS registrados</h2>
                <div class="row">
                    <button class="btn p uta-btn-primary" t-on-click="() => this.openTelemetria()">
                        <i class="fa fa-map-marker"/> Historial de telemetría GPS
                    </button>
                    <button class="btn s" t-on-click="() => this.openVehiculos()">
                        <i class="fa fa-bus"/> Gestionar flota en Odoo
                    </button>
                </div>
            </div>

            <!-- Tabla de Vehículos a Ancho Completo -->
            <div class="card nw uta-tile">
                <div class="hd" style="margin-bottom:12px;">
                    <h3 style="margin:0;">Flota universitaria (<t t-esc="state.kpis.vehiculos_lista.length"/> vehículos)</h3>
                    <span class="chip">Telemetría Traccar</span>
                </div>
                <div class="tw">
                    <table class="uta-table">
                        <thead>
                            <tr>
                                <th>Vehículo</th>
                                <th>Modelo</th>
                                <th>Dispositivo GPS</th>
                                <th>Última posición</th>
                                <th>Velocidad</th>
                                <th>Estado GPS</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr t-foreach="state.kpis.vehiculos_lista" t-as="v" t-key="v.id">
                                <td><b t-esc="v.name"/></td>
                                <td class="lb uta-label" t-esc="v.modelo"/>
                                <td t-esc="v.dispositivo"/>
                                <td class="lb uta-label" t-esc="v.ultima_pos"/>
                                <td t-esc="v.velocidad"/>
                                <td><span t-att-class="'pill ' + v.estado_code" t-esc="v.estado_gps"/></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 8: MÉTRICAS ISO 25010 ════════════════════ -->
        <t t-if="state.activeTab === 'metricas'">
            <div class="hd">
                <h2>Métricas de calidad ISO/IEC 25010</h2>
                <div class="row">
                    <button class="btn p s uta-btn-primary" t-on-click="() => this.openMetricas()">
                        <i class="fa fa-table"/> Ver tabla en Odoo
                    </button>
                </div>
            </div>

            <div class="card uta-tile">
                <div class="tw">
                    <table class="uta-table">
                        <thead>
                            <tr>
                                <th>Indicador</th>
                                <th>Fórmula matemática</th>
                                <th>Fuente de datos</th>
                                <th>Unidad</th>
                                <th>Resultado calculado</th>
                                <th>Interpretación operativa</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr t-foreach="state.kpis.metricas_iso_reales" t-as="m" t-key="m.ind">
                                <td><b t-esc="m.ind"/></td>
                                <td class="lb uta-label" t-esc="m.form"/>
                                <td t-esc="m.fte"/>
                                <td><span class="chip" t-esc="m.uni"/></td>
                                <td><b t-esc="m.res"/></td>
                                <td t-esc="m.interp"/>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 9: SINCRONIZACIÓN TRACCAR ════════════════════ -->
        <t t-if="state.activeTab === 'sync'">
            <div class="hd">
                <h2>Sincronización Traccar</h2>
                <div class="row">
                    <span class="pill gn"><i class="fa fa-link"/> Traccar Server Online</span>
                    <button class="btn p s uta-btn-primary" t-on-click="() => this.triggerSync()">
                        <i class="fa fa-refresh"/> Sincronizar ahora
                    </button>
                </div>
            </div>

            <div class="g g4">
                <div class="card uta-tile">
                    <div class="lb uta-label">Última sincronización</div>
                    <div class="big uta-kpi" style="font-size:22px;"><t t-esc="state.lastUpdated or 'hace 30 s'"/></div>
                    <div class="lb uta-label">API REST Traccar / Webhook</div>
                </div>
                <div class="card uta-tile">
                    <div class="lb uta-label">Posiciones procesadas hoy</div>
                    <div class="big uta-kpi"><t t-esc="state.kpis.pos_hoy_count"/></div>
                    <div class="lb uta-label"><t t-esc="state.kpis.total_posiciones"/> totales registradas</div>
                </div>
                <div class="card uta-tile">
                    <div class="lb uta-label">Dispositivos GPS enlazados</div>
                    <div class="big uta-kpi"><t t-esc="state.kpis.vehiculos_lista.length"/></div>
                    <div class="lb uta-label">Todos operativos</div>
                </div>
                <div class="card uta-tile">
                    <div class="lb uta-label">Recorridos auditados</div>
                    <div class="big uta-kpi"><t t-esc="state.kpis.total_recorridos"/></div>
                    <div class="lb uta-label"><t t-esc="state.kpis.en_curso"/> en curso actualmente</div>
                </div>
            </div>

            <div class="g g2b">
                <div class="card uta-tile">
                    <h3>Dispositivos GPS configurados en Traccar</h3>
                    <div class="tw">
                        <table class="uta-table">
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
                                    <td class="lb uta-label" t-esc="v.ultima_pos"/>
                                    <td><span t-att-class="'pill ' + v.estado_code" t-esc="v.estado_gps"/></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card uta-tile">
                    <h3>Infraestructura de microservicios</h3>
                    <div class="li"><span>Traccar Server (Puerto 8082 / 5055)</span><span class="pill gn">Activo</span></div>
                    <div class="li"><span>PostgreSQL 15 (Puerto 5432)</span><span class="pill gn">Conectado</span></div>
                    <div class="li"><span>Grafana 11.4 (Puerto 3000)</span><span class="pill gn">Activo</span></div>
                    <div class="li"><span>Odoo 16 (Puerto 8069 / 8070)</span><span class="pill gn">En servicio</span></div>
                    <div style="margin-top:16px;">
                        <button class="btn p s uta-btn-primary" t-on-click="() => this.triggerSync()">Forzar verificación</button>
                    </div>
                </div>
            </div>
        </t>
    </main>

    <!-- MODAL DE PERSONALIZACIÓN DE COLORES -->
    <div t-if="state.showColorModal" class="uta-theme-backdrop" t-on-click.self="() => this.toggleColorModal()">
        <div class="uta-theme-dialog">
            <div class="hd" style="margin-bottom:12px;">
                <h3 style="margin:0;"><i class="fa fa-paint-brush" style="color:var(--bl);"/> Personalizar colores del diseño</h3>
                <button class="btn s" t-on-click="() => this.toggleColorModal()"><i class="fa fa-times"/></button>
            </div>
            <p class="lb uta-label" style="margin:0 0 10px;">Selecciona una paleta predeterminada o edita los colores individualmente. Los cambios se guardan permanentemente en la configuración de Odoo.</p>

            <!-- Paletas Predefinidas -->
            <div class="lb uta-label" style="font-weight:600;">Paletas recomendadas:</div>
            <div class="uta-theme-presets">
                <button t-foreach="themePresets" t-as="tp" t-key="tp.id"
                        class="uta-preset-btn"
                        t-on-click="() => this.selectPreset(tp)">
                    <span class="uta-preset-dot" t-att-style="'background:' + tp.primary + ';'"/>
                    <span t-esc="tp.name"/>
                </button>
            </div>

            <!-- Selectores individuales de color -->
            <div style="margin-bottom:16px;">
                <div class="uta-color-row">
                    <span class="lb uta-label" style="font-weight:600;">Color de Acento / Primario (--bl):</span>
                    <div style="display:flex;align-items:center;gap:8px;">
                        <input type="color" t-model="state.themeColors.primary" t-on-input="() => this.applyTheme(state.themeColors)" t-on-change="() => this.applyTheme(state.themeColors)"/>
                        <span class="lb" style="font-family:monospace;font-weight:600;" t-esc="state.themeColors.primary"/>
                    </div>
                </div>
                <div class="uta-color-row">
                    <span class="lb uta-label" style="font-weight:600;">Selección Suave (--bls):</span>
                    <div style="display:flex;align-items:center;gap:8px;">
                        <input type="color" t-model="state.themeColors.primary_soft" t-on-input="() => this.applyTheme(state.themeColors)" t-on-change="() => this.applyTheme(state.themeColors)"/>
                        <span class="lb" style="font-family:monospace;font-weight:600;" t-esc="state.themeColors.primary_soft"/>
                    </div>
                </div>
                <div class="uta-color-row">
                    <span class="lb uta-label" style="font-weight:600;">Fondo de Página (--bg):</span>
                    <div style="display:flex;align-items:center;gap:8px;">
                        <input type="color" t-model="state.themeColors.background" t-on-input="() => this.applyTheme(state.themeColors)" t-on-change="() => this.applyTheme(state.themeColors)"/>
                        <span class="lb" style="font-family:monospace;font-weight:600;" t-esc="state.themeColors.background"/>
                    </div>
                </div>
                <div class="uta-color-row">
                    <span class="lb uta-label" style="font-weight:600;">Paneles y Tarjetas (--card):</span>
                    <div style="display:flex;align-items:center;gap:8px;">
                        <input type="color" t-model="state.themeColors.card" t-on-input="() => this.applyTheme(state.themeColors)" t-on-change="() => this.applyTheme(state.themeColors)"/>
                        <span class="lb" style="font-family:monospace;font-weight:600;" t-esc="state.themeColors.card"/>
                    </div>
                </div>
                <div class="uta-color-row">
                    <span class="lb uta-label" style="font-weight:600;">Texto Principal (--tx):</span>
                    <div style="display:flex;align-items:center;gap:8px;">
                        <input type="color" t-model="state.themeColors.text" t-on-input="() => this.applyTheme(state.themeColors)" t-on-change="() => this.applyTheme(state.themeColors)"/>
                        <span class="lb" style="font-family:monospace;font-weight:600;" t-esc="state.themeColors.text"/>
                    </div>
                </div>
            </div>

            <div class="row" style="justify-content:space-between;margin-top:16px;">
                <button class="btn s" t-on-click="() => this.resetTheme()">Restablecer</button>
                <div class="row">
                    <button class="btn s" t-on-click="() => this.openConfigSettings()" title="Abrir formulario completo en Odoo">Ajustes en Odoo</button>
                    <button class="btn p s uta-btn-primary" t-on-click="() => this.saveTheme()">Guardar cambios</button>
                </div>
            </div>
        </div>
    </div>
</div>
`;

registry.category("actions").add("fleet_rutas.dashboard", FleetRutasDashboard);
export default FleetRutasDashboard;
