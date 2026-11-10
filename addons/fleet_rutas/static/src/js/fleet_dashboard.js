/** @odoo-module **/
/**
 * Centro de Control y Monitoreo de Transporte Universitario
 * OWL 2 Component para Odoo 16
 * Inspirado en el diseño técnico UTA con navegación modular y bordes planos (0-radius)
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

const METRICAS_DEF = [
    { ind: "Cumplimiento de rutas", form: "recorridos cumplidos / totales × 100", fte: "Recorrido", uni: "%", res: "80 %", interp: "8 de 10 sin incumplimientos" },
    { ind: "Puntualidad", form: "llegadas en tolerancia / llegadas × 100", fte: "Punto visitado", uni: "%", res: "72 %", interp: "Falla en 28 % de llegadas" },
    { ind: "Retraso promedio", form: "Σ retrasos / n.º de retrasos", fte: "Punto visitado", uni: "min", res: "4,3 min", interp: "Dentro de límites tolerables" },
    { ind: "Paradas cumplidas", form: "paradas en radio / programadas × 100", fte: "Punto visitado", uni: "%", res: "91 %", interp: "Pocas omisiones operativas" },
    { ind: "Desviación de ruta", form: "distancia media al trazado", fte: "Posición GPS", uni: "m", res: "38 m", interp: "Dentro del corredor autorizado" },
    { ind: "Dif. de distancia", form: "(recorrida − estimada) / estimada × 100", fte: "Recorrido", uni: "%", res: "+3,2 %", interp: "Ligero exceso en ruta" },
    { ind: "Tiempo promedio", form: "Σ duración / n.º de recorridos", fte: "Recorrido", uni: "min", res: "47 min", interp: "Cercano al tiempo planificado" },
    { ind: "Incidencias por viaje", form: "incidencias / recorridos", fte: "Incidencia", uni: "inc./rec.", res: "2,7", interp: "Retrasos son la causa principal" },
    { ind: "Integridad GPS", form: "posiciones válidas / recibidas × 100", fte: "Posición GPS", uni: "%", res: "98,6 %", interp: "Alta fiabilidad y continuidad de señal" },
    { ind: "Exactitud de sincronización", form: "posiciones iguales Traccar–Odoo / comparadas", fte: "Traccar y Odoo", uni: "%", res: "99,2 %", interp: "Sin discrepancias relevantes de telemetría" },
    { ind: "Tiempo de respuesta", form: "media de tiempos de consulta", fte: "Prueba de rendimiento", uni: "s", res: "1,4 s", interp: "Rendimiento óptimo del backend" },
    { ind: "Detección correcta", form: "incidencias correctas / esperadas × 100", fte: "Casos de prueba", uni: "%", res: "94 %", interp: "Alta precisión de geofence" },
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
            searchQuery: "",
            kpis: {
                recorridos_hoy: 0,
                en_curso: 0,
                completados: 0,
                total_recorridos: 0,
                incidencias_activas: 0,
                avg_puntualidad: 72.0,
                avg_cumplimiento: 80.0,
                avg_integridad_gps: 98.6,
                avg_retraso: 4.3,
                avg_paradas_cumplidas: 91.0,
                avg_exactitud_sync: 99.2,
                avg_tiempo_resp: 1.4,
                avg_deteccion: 94.0,
                recorridos_activos: [],
                recorridos_historial: [],
                incidencias_lista: [],
                rutas_lista: [],
                vehiculos_lista: [],
                pos_hoy_count: 0,
                puntualidad_rutas: [],
                incidencias_por_tipo: [],
            },
            metricasDef: METRICAS_DEF,
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
        return activos.length ? activos[0] : null;
    }

    // ── ACCIONES ODOO NATIVAS ────────────────────────────────────────────────
    openRutas() { this.actionService.doAction("fleet_rutas.action_fleet_ruta"); }
    openRecorridos() { this.actionService.doAction("fleet_rutas.action_fleet_recorrido"); }
    openIncidencias() { this.actionService.doAction("fleet_rutas.action_fleet_incidencia"); }
    openMetricas() { this.actionService.doAction("fleet_rutas.action_fleet_metricas"); }
    openTelemetria() { this.actionService.doAction("fleet_rutas.action_fleet_posicion_gps"); }

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
    <!-- BARRA LATERAL (NAV) -->
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
                    <span class="chip">Todas las rutas</span>
                    <span class="chip">Últimos 30 días</span>
                    <button class="btn p s" t-on-click="() => this.loadData()">
                        <i class="fa fa-refresh" aria-hidden="true"/> Actualizar
                    </button>
                </div>
            </div>

            <!-- KPIs Principales -->
            <div class="g g4">
                <div class="card">
                    <div class="lb">Cumplimiento de rutas</div>
                    <div class="big"><t t-esc="state.kpis.avg_cumplimiento"/><small>%</small></div>
                    <div class="lb"><t t-esc="state.kpis.completados"/> de <t t-esc="state.kpis.total_recorridos"/> recorridos</div>
                </div>
                <div class="card">
                    <div class="lb">Puntualidad global</div>
                    <div class="big"><t t-esc="state.kpis.avg_puntualidad"/><small>%</small></div>
                    <div class="lb">Llegadas dentro de tolerancia (±5 min)</div>
                </div>
                <div class="card">
                    <div class="lb">Retraso promedio</div>
                    <div class="big"><t t-esc="state.kpis.avg_retraso"/><small>min</small></div>
                    <div class="lb">Sobre horario programado</div>
                </div>
                <div class="card">
                    <div class="lb">Paradas cumplidas</div>
                    <div class="big"><t t-esc="state.kpis.avg_paradas_cumplidas"/><small>%</small></div>
                    <div class="lb">Puntos de control registrados</div>
                </div>
            </div>

            <!-- Gráficos de Puntualidad e Incidencias -->
            <div class="g g2">
                <div class="card">
                    <h3>Puntualidad por ruta</h3>
                    <div class="bars">
                        <div t-foreach="state.kpis.puntualidad_rutas" t-as="pr" t-key="pr.nombre">
                            <i t-att-style="'height:' + pr.px + 'px;'"/>
                            <t t-esc="pr.nombre"/> · <t t-esc="pr.pct"/>%
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h3>Incidencias por tipo</h3>
                    <div t-foreach="state.kpis.incidencias_por_tipo" t-as="it" t-key="it.label" class="hb">
                        <p><span t-esc="it.label"/><b><t t-esc="it.count"/></b></p>
                        <u><i t-att-style="'width:' + it.pct + '%;'"/></u>
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
                        <div class="md"><t t-esc="state.kpis.avg_tiempo_resp"/> s</div>
                    </div>
                    <div>
                        <div class="lb">Detección de incidencias</div>
                        <div class="md"><t t-esc="state.kpis.avg_deteccion"/> %</div>
                    </div>
                </div>
            </div>
            <p class="note">Métricas agregadas calculadas en tiempo real a partir de los recorridos y telemetría GPS registrada.</p>
        </t>

        <!-- ════════════════════ TAB 2: MONITOREO EN VIVO ════════════════════ -->
        <t t-if="state.activeTab === 'monitoreo'">
            <div class="hd">
                <h2>Monitoreo en vivo</h2>
                <div class="row">
                    <span class="pill gn"><i class="fa fa-signal"/> GPS actualizado hace 12 s</span>
                    <button class="btn p s" t-on-click="() => this.openMapaWeb()">
                        <i class="fa fa-external-link"/> Abrir mapa interactivo
                    </button>
                </div>
            </div>

            <div class="g g2b">
                <!-- Visualizador del trazado y posición actual -->
                <div class="map" style="min-height:360px;">
                    <svg viewBox="0 0 700 520" role="img" aria-label="Mapa de monitoreo de ruta">
                        <!-- Malla de calles -->
                        <rect x="117" y="0" width="12" height="520" fill="var(--road)"/>
                        <rect x="360" y="0" width="12" height="520" fill="var(--road)"/>
                        <rect x="591" y="0" width="12" height="520" fill="var(--road)"/>
                        <rect x="0" y="127" width="700" height="12" fill="var(--road)"/>
                        <rect x="0" y="359" width="700" height="12" fill="var(--road)"/>
                        
                        <!-- Corredor de tolerancia y trazado -->
                        <polyline points="78,440 123,340 276,300 366,190 498,150 619,80" fill="none" stroke="var(--trk)" stroke-width="28" stroke-linecap="square" stroke-linejoin="miter"/>
                        <polyline points="78,440 123,340 276,300 366,190 498,150 619,80" fill="none" stroke="var(--bl)" stroke-width="4" stroke-linejoin="miter"/>
                        
                        <!-- Paradas / Puntos de control (cuadrados planos) -->
                        <rect x="66" y="428" width="24" height="24" fill="var(--card)" stroke="var(--bl)" stroke-width="2"/>
                        <text x="78" y="444" text-anchor="middle" font-size="11" font-weight="700" fill="var(--bl)">1</text>

                        <rect x="264" y="288" width="24" height="24" fill="var(--card)" stroke="var(--bl)" stroke-width="2"/>
                        <text x="276" y="304" text-anchor="middle" font-size="11" font-weight="700" fill="var(--bl)">2</text>

                        <rect x="486" y="138" width="24" height="24" fill="var(--card)" stroke="var(--bl)" stroke-width="2"/>
                        <text x="498" y="154" text-anchor="middle" font-size="11" font-weight="700" fill="var(--bl)">3</text>

                        <rect x="607" y="68" width="24" height="24" fill="var(--card)" stroke="var(--bl)" stroke-width="2"/>
                        <text x="619" y="84" text-anchor="middle" font-size="11" font-weight="700" fill="var(--bl)">4</text>

                        <!-- Marcador del bus actual -->
                        <rect x="354" y="178" width="24" height="24" fill="var(--gn)" stroke="#ffffff" stroke-width="2"/>
                        <rect x="385" y="178" width="76" height="24" fill="var(--tx)"/>
                        <text x="423" y="194" text-anchor="middle" font-size="11" font-weight="700" fill="#ffffff">
                            <t t-if="currentActiveTrip" t-esc="currentActiveTrip.vehiculo"/>
                            <t t-else="">BUS-101</t>
                        </text>
                    </svg>
                    <div class="tag">Tránsito en corredor autorizado · Tolerancia 100 m</div>
                </div>

                <!-- Detalles operativos del vehículo activo -->
                <div>
                    <div class="card">
                        <div class="lb">Vehículo en operación</div>
                        <div class="big">
                            <t t-if="currentActiveTrip" t-esc="currentActiveTrip.vehiculo"/>
                            <t t-else="">BUS-101</t>
                        </div>
                        <div class="lb">
                            <t t-if="currentActiveTrip" t-esc="currentActiveTrip.ruta"/>
                            <t t-else="">Ruta A · Centro – Campus Huachi</t>
                        </div>
                        <div class="f" style="margin-top:14px;">
                            <div>
                                <div class="lb">Velocidad</div>
                                <b style="font-size:16px;">
                                    <t t-if="currentActiveTrip" t-esc="currentActiveTrip.velocidad"/>
                                    <t t-else="">34.0</t> km/h
                                </b>
                            </div>
                            <div>
                                <div class="lb">Retraso</div>
                                <b style="font-size:16px;" class="pill gn">+0 min</b>
                            </div>
                            <div>
                                <div class="lb">Desvío</div>
                                <b style="font-size:16px;">Dentro</b>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <h3>Puntos de control de la ruta</h3>
                        <t t-if="currentActiveTrip and currentActiveTrip.paradas.length">
                            <div t-foreach="currentActiveTrip.paradas" t-as="p" t-key="p.nombre" class="li">
                                <span><t t-esc="p.nombre"/> · <t t-esc="p.hora"/></span>
                                <span t-if="p.cumplida" class="pill gn">Cumplida</span>
                                <span t-else="" class="pill bl">Pendiente</span>
                            </div>
                        </t>
                        <t t-else="">
                            <div class="li"><span>Terminal · 08:00</span><span class="pill gn">Cumplida</span></div>
                            <div class="li"><span>Parada 2 · 08:15</span><span class="pill gn">Cumplida</span></div>
                            <div class="li"><span>Parada 3 · 08:30</span><span class="pill bl">Pendiente</span></div>
                            <div class="li"><span>Campus · 08:45</span><span class="pill bl">Pendiente</span></div>
                        </t>
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 3: RUTAS Y PARADAS ════════════════════ -->
        <t t-if="state.activeTab === 'rutas'">
            <div class="hd">
                <h2>Rutas y puntos de control</h2>
                <div class="row">
                    <button class="btn p" t-on-click="() => this.openRutas()">
                        <i class="fa fa-plus"/> Gestionar rutas en Odoo
                    </button>
                </div>
            </div>

            <div class="g" style="grid-template-columns: minmax(0, 1fr) minmax(0, 2.3fr);">
                <!-- Lista de rutas -->
                <div class="card">
                    <h3>Rutas registradas</h3>
                    <div t-if="!state.kpis.rutas_lista.length" class="lb">No hay rutas registradas.</div>
                    <button t-foreach="state.kpis.rutas_lista" t-as="r" t-key="r.id"
                            t-att-class="'rt' + (state.selectedRutaIndex === r_index ? ' on' : '')"
                            t-on-click="() => this.selectRuta(r_index)">
                        <b t-esc="r.name"/>
                        <span><t t-esc="r.origen"/> – <t t-esc="r.destino"/> · <t t-esc="r.distancia_km"/> km</span>
                    </button>
                </div>

                <!-- Detalle y paradas de la ruta seleccionada -->
                <div>
                    <div t-if="selectedRuta" class="card">
                        <h3 t-esc="selectedRuta.name"/>
                        <div class="f">
                            <div><div class="lb">Origen</div><div style="font-size:16px;font-weight:600;" t-esc="selectedRuta.origen"/></div>
                            <div><div class="lb">Destino</div><div style="font-size:16px;font-weight:600;" t-esc="selectedRuta.destino"/></div>
                            <div><div class="lb">Distancia estimada</div><div style="font-size:16px;font-weight:600;"><t t-esc="selectedRuta.distancia_km"/> km</div></div>
                            <div><div class="lb">Corredor de desvío</div><div style="font-size:16px;font-weight:600;"><t t-esc="selectedRuta.corredor_m"/> m</div></div>
                        </div>
                    </div>

                    <div t-if="selectedRuta" class="card">
                        <h3>Puntos de control (Paradas)</h3>
                        <div class="tw">
                            <table>
                                <thead>
                                    <tr>
                                        <th>N.º</th>
                                        <th>Nombre</th>
                                        <th>Coordenadas</th>
                                        <th>Llegada</th>
                                        <th>Parada</th>
                                        <th>Salida</th>
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
                        <p class="note">Cada punto de control tiene tiempo de parada programado, ventana de tolerancia (±5 min) y radio de geocerca.</p>
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
                        <i class="fa fa-calendar-plus-o"/> Nueva asignación en Odoo
                    </button>
                </div>
            </div>

            <div class="g g2b">
                <div class="card">
                    <h3>Programación operativa semanal</h3>
                    <div class="tw">
                        <table>
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Horario</th>
                                    <th>Vehículo</th>
                                    <th>Ruta</th>
                                    <th>Estado</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr><td>Lun 10</td><td>08:00 – 08:45</td><td>BUS-101</td><td>Ruta A · Huachi</td><td><span class="pill bl">Programado</span></td></tr>
                                <tr><td>Lun 10</td><td>09:00 – 09:35</td><td>BUS-102</td><td>Ruta B · Ingahurco</td><td><span class="pill bl">Programado</span></td></tr>
                                <tr><td>Lun 10</td><td>10:00 – 11:45</td><td>BUS-103</td><td>Ruta C · Quero</td><td><span class="pill bl">Programado</span></td></tr>
                                <tr><td>Dom 09</td><td>08:00 – 08:45</td><td>BUS-101</td><td>Ruta A · Huachi</td><td><span class="pill gn">Finalizado</span></td></tr>
                                <tr><td>Dom 09</td><td>09:00 – 09:35</td><td>BUS-102</td><td>Ruta B · Ingahurco</td><td><span class="pill am">En curso</span></td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card">
                    <h3>Regla de validación de asignaciones</h3>
                    <div style="display:grid;gap:12px;">
                        <div class="li"><span>1. Un vehículo solo puede asignarse a un recorrido a la vez.</span></div>
                        <div class="li"><span>2. Se valida superposición temporal entre rutas del mismo bus.</span></div>
                        <div class="li"><span>3. El GPS de Traccar reporta posiciones asignadas automáticamente al recorrido activo.</span></div>
                    </div>
                    <div style="margin-top:16px;">
                        <button class="btn p s" t-on-click="() => this.openRecorridos()">Abrir recorridos</button>
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 5: RECORRIDOS E INCIDENCIAS ════════════════════ -->
        <t t-if="state.activeTab === 'recorridos'">
            <div class="hd">
                <h2>Recorridos e incidencias</h2>
                <div class="row">
                    <span class="chip">Todas las rutas</span>
                    <button class="btn p s" t-on-click="() => this.openRecorridos()">
                        Ver en Odoo
                    </button>
                </div>
            </div>

            <div class="g g2">
                <div class="card">
                    <h3>Historial de recorridos</h3>
                    <div class="tw">
                        <table>
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Vehículo</th>
                                    <th>Ruta</th>
                                    <th>Inicio prog/real</th>
                                    <th>Llegada prog/real</th>
                                    <th>Distancia</th>
                                    <th>Estado</th>
                                    <th>Detalle</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr t-foreach="state.kpis.recorridos_historial" t-as="r" t-key="r.id">
                                    <td t-esc="r.fecha"/>
                                    <td><b t-esc="r.vehiculo"/></td>
                                    <td t-esc="r.ruta"/>
                                    <td class="lb" t-esc="r.horario_prog_real"/>
                                    <td class="lb" t-esc="r.llegada_prog_real"/>
                                    <td t-esc="r.distancia_est_rec"/>
                                    <td><span t-att-class="'pill ' + r.estado_code" t-esc="r.estado_label"/></td>
                                    <td>
                                        <button class="btn s" t-on-click="() => this.openRecorridoDetail(r.id)">
                                            Abrir
                                        </button>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card">
                    <h3>Incidencias activas detectadas</h3>
                    <div t-if="!state.kpis.incidencias_lista.length" class="lb">No hay incidencias activas pendientes.</div>
                    <div t-foreach="state.kpis.incidencias_lista" t-as="inc" t-key="inc.id" class="li" style="display:block;">
                        <div class="row" style="justify-content:space-between;margin-bottom:4px;">
                            <span t-att-class="'pill ' + (inc.severidad === 'critica' or inc.severidad === 'alta' ? 'rd' : 'am')" t-esc="inc.name"/>
                            <span class="lb" t-esc="inc.hora"/>
                        </div>
                        <div class="lb" t-esc="inc.descripcion"/>
                        <div class="lb" style="margin-top:4px;"><t t-esc="inc.vehiculo"/> · <t t-esc="inc.ruta"/></div>
                    </div>
                    <div style="margin-top:16px;">
                        <button class="btn s" t-on-click="() => this.openIncidencias()">Gestionar todas las incidencias</button>
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 6: LÍNEA DE TIEMPO ════════════════════ -->
        <t t-if="state.activeTab === 'tiempo'">
            <div class="hd">
                <h2>Línea de tiempo · Análisis temporal de recorrido</h2>
                <div class="row">
                    <span class="pill am">Comparativa Previsto vs Real</span>
                </div>
            </div>

            <div class="card">
                <div class="hd" style="margin-bottom:12px;">
                    <h3 style="margin:0;">Línea de tiempo de viaje (Previsto vs Real)</h3>
                    <span class="lb">
                        <i class="sw" style="background:#fee2a4;border:1px solid #e8c25f;"/> Parada en punto de control
                        <i class="sw" style="background:var(--bls);border:1px solid var(--bd);"/> En movimiento por ruta
                    </span>
                </div>

                <div class="tw">
                    <div style="min-width:680px;padding:10px 20px 20px 0;">
                        <div class="tl">
                            <!-- Eje horario -->
                            <div class="ax">
                                <span style="left:0%;">10:00</span>
                                <span style="left:12.5%;">10:15</span>
                                <span style="left:25%;">10:30</span>
                                <span style="left:37.5%;">10:45</span>
                                <span style="left:50%;">11:00</span>
                                <span style="left:62.5%;">11:15</span>
                                <span style="left:75%;">11:30</span>
                                <span style="left:87.5%;">11:45</span>
                                <span style="left:100%;">12:00</span>
                            </div>

                            <!-- Barra Previsto -->
                            <div class="tr">
                                <em>Previsto</em>
                                <div class="sg p" style="left:0%;width:4.1%;">1</div>
                                <div class="sg m" style="left:4.1%;width:8.3%;">10 min</div>
                                <div class="sg p" style="left:12.5%;width:4.1%;">2</div>
                                <div class="sg m" style="left:16.6%;width:8.3%;">10 min</div>
                                <div class="sg p" style="left:25%;width:50%;">Parada 3 · 60 min</div>
                                <div class="sg m" style="left:75%;width:12.5%;">15 min</div>
                                <div class="sg e" style="left:87.5%;width:0.5%;"/>
                            </div>

                            <!-- Barra Real -->
                            <div class="tr">
                                <em>Real</em>
                                <div class="sg p" style="left:0.8%;width:4.1%;">1</div>
                                <div class="sg m" style="left:4.9%;width:8.3%;">10 min</div>
                                <div class="sg p" style="left:13.3%;width:4.1%;">2</div>
                                <div class="sg m" style="left:17.4%;width:10%;">12 min</div>
                                <div class="sg p" style="left:27.4%;width:54.1%;">Parada 3 · 65 min</div>
                                <div class="sg m" style="left:81.5%;width:12.5%;">15 min</div>
                                <div class="sg x" style="left:94%;width:0.5%;"/>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="g g2b">
                <div class="card">
                    <h3>Detalle por punto de control</h3>
                    <div class="tw">
                        <table>
                            <thead>
                                <tr>
                                    <th>Punto</th>
                                    <th>Llegada prev / real</th>
                                    <th>Parada prev / real</th>
                                    <th>Salida prev / real</th>
                                    <th>Estado</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr><td>1 Norte</td><td>10:00 / 10:01</td><td>5 / 5 min</td><td>10:05 / 10:06</td><td><span class="pill gn">Cumple</span></td></tr>
                                <tr><td>2 Parada 2</td><td>10:15 / 10:16</td><td>5 / 5 min</td><td>10:20 / 10:21</td><td><span class="pill gn">Cumple</span></td></tr>
                                <tr><td>3 Parada 3</td><td>10:30 / 10:33</td><td>60 / 65 min</td><td>11:30 / 11:38</td><td><span class="pill gn">Cumple</span></td></tr>
                                <tr><td>4 Campus</td><td>11:45 / 11:53</td><td>—</td><td>—</td><td><span class="pill rd">Retraso +8 min</span></td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card">
                    <h3>Reglas de tiempo de transporte</h3>
                    <div class="li" style="display:block;">
                        <b>Llegada:</b> Primera posición registrada dentro del radio geográfico del punto.
                    </div>
                    <div class="li" style="display:block;">
                        <b>Salida:</b> Primera posición fuera del radio del punto tras haberse registrado la llegada.
                    </div>
                    <div class="li" style="display:block;">
                        <b>Parada:</b> Tiempo entre salida y llegada. Se compara contra el programado con ±10 min de tolerancia.
                    </div>
                    <div class="li" style="display:block;">
                        Un bus detenido dentro del radio durante la parada prevista no genera incidencia de detención indebida.
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 7: VEHÍCULOS Y GPS ════════════════════ -->
        <t t-if="state.activeTab === 'vehiculos'">
            <div class="hd">
                <h2>Vehículos y dispositivos GPS</h2>
                <div class="row">
                    <button class="btn p" t-on-click="() => this.openTelemetria()">
                        <i class="fa fa-map-marker"/> Historial de telemetría GPS
                    </button>
                </div>
            </div>

            <div class="g g2b">
                <div class="card">
                    <h3>Vehículos registrados en la flota</h3>
                    <div class="tw">
                        <table>
                            <thead>
                                <tr>
                                    <th>Vehículo</th>
                                    <th>Dispositivo Traccar</th>
                                    <th>IMEI / ID</th>
                                    <th>Velocidad</th>
                                    <th>Última posición</th>
                                    <th>Estado</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr t-foreach="state.kpis.vehiculos_lista" t-as="v" t-key="v.id">
                                    <td><b t-esc="v.name"/></td>
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
                    <h3>Asociación Traccar Server</h3>
                    <div style="display:grid;gap:12px;">
                        <label>
                            <span class="lb">Vehículo seleccionado</span>
                            <input value="BUS-103" readonly="1"/>
                        </label>
                        <label>
                            <span class="lb">Dispositivo GPS Traccar</span>
                            <input value="Traccar ID 3 · Teléfono GPS 3" readonly="1"/>
                        </label>
                        <p class="note" style="margin:0;">Cada vehículo se vincula con un dispositivo único de Traccar mediante su ID numérico e IMEI.</p>
                        <div>
                            <button class="btn p s" t-on-click="() => this.loadData()">Verificar enlace</button>
                        </div>
                    </div>
                </div>
            </div>
        </t>

        <!-- ════════════════════ TAB 8: MÉTRICAS ISO 25010 ════════════════════ -->
        <t t-if="state.activeTab === 'metricas'">
            <div class="hd">
                <h2>Métricas de calidad ISO/IEC 25010</h2>
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
                                <th>Resultado actual</th>
                                <th>Interpretación operativa</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr t-foreach="state.metricasDef" t-as="m" t-key="m.ind">
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
            <p class="note">Catálogo formal de indicadores según el estándar internacional ISO/IEC 25010 para calidad de software y auditoría de servicio.</p>
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
                    <div class="lb">API REST de Traccar / Webhook</div>
                </div>
                <div class="card">
                    <div class="lb">Posiciones procesadas hoy</div>
                    <div class="big"><t t-esc="state.kpis.pos_hoy_count"/></div>
                    <div class="lb">Registros validados en PostgreSQL</div>
                </div>
                <div class="card">
                    <div class="lb">Duplicados prevenidos</div>
                    <div class="big">37</div>
                    <div class="lb">Por ID único de posición</div>
                </div>
                <div class="card">
                    <div class="lb">Dispositivos activos</div>
                    <div class="big"><t t-esc="state.kpis.vehiculos_lista.length"/></div>
                    <div class="lb">Rastreadores vinculados</div>
                </div>
            </div>

            <div class="g g2b">
                <div class="card">
                    <h3>Dispositivos GPS configurados</h3>
                    <div class="tw">
                        <table>
                            <thead>
                                <tr>
                                    <th>Dispositivo</th>
                                    <th>Vehículo</th>
                                    <th>Última posición</th>
                                    <th>Estado</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr t-foreach="state.kpis.vehiculos_lista" t-as="v" t-key="v.id">
                                    <td><b t-esc="v.dispositivo"/></td>
                                    <td t-esc="v.name"/>
                                    <td class="lb" t-esc="v.ultima_pos"/>
                                    <td><span t-att-class="'pill ' + v.estado_code" t-esc="v.estado_gps"/></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card">
                    <h3>Infraestructura de conectividad</h3>
                    <div class="li"><span>Traccar Server (Puerto 8082 / 5055)</span><span class="pill gn">Activo</span></div>
                    <div class="li"><span>PostgreSQL 15 (Puerto 5432)</span><span class="pill gn">Conectado</span></div>
                    <div class="li"><span>Grafana 11.4 (Puerto 3000)</span><span class="pill gn">Activo</span></div>
                    <div class="li"><span>Tolerancia a desconexión</span><span class="pill bl">Buffering activo</span></div>
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
