/** @odoo-module **/
/**
 * fleet_reports — Grafana Embedded Dashboard Widget
 * Compatible con Odoo 16 (OWL 2 / owl.Component)
 *
 * Flujo:
 * 1. Al montar, llama vía RPC a fleet.reports.dashboard.get_grafana_config()
 * 2. Construye la URL del iframe Grafana en modo kiosk
 * 3. Refresca el iframe automáticamente según el intervalo configurado
 * 4. Muestra barra de progreso de cuenta regresiva
 * 5. Permite cambiar rango de tiempo y forzar refresh manual
 */

import { Component, useState, onMounted, onWillUnmount, useRef, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const TIME_RANGES = [
    { value: "now-15m", label: "Últimos 15 min" },
    { value: "now-30m", label: "Últimos 30 min" },
    { value: "now-1h",  label: "Última hora" },
    { value: "now-3h",  label: "Últimas 3 horas" },
    { value: "now-6h",  label: "Últimas 6 horas" },
    { value: "now-12h", label: "Últimas 12 horas" },
    { value: "now-24h", label: "Últimas 24 horas" },
    { value: "now-7d",  label: "Últimos 7 días" },
];

class FleetReportsDashboard extends Component {
    static template = "fleet_reports.GrafanaDashboard";

    setup() {
        this.rpc     = useService("rpc");
        this.iframeRef = useRef("grafanaIframe");

        this.state = useState({
            loading:         true,
            error:           false,
            errorMsg:        "",
            iframeUrl:       "",
            grafanaBaseUrl:  "http://localhost:3000",
            dashboardUid:    "fleet-traccar-main",
            refreshInterval: 30,    // segundos
            timeFrom:        "now-6h",
            countdown:       30,    // cuenta regresiva actual
            isFullscreen:    false,
            lastRefresh:     null,
            timeRanges:      TIME_RANGES,
        });

        this._refreshTimer  = null;
        this._countdownTimer = null;

        onMounted(() => this._init());
        onWillUnmount(() => this._clearTimers());
    }

    // ── Inicialización ──────────────────────────────────────────────────────
    async _init() {
        this.state.error = false;
        this.state.loading = true;
        try {
            const config = await this.rpc("/web/dataset/call_kw", {
                model:  "fleet.reports.dashboard",
                method: "get_grafana_config",
                args:   [],
                kwargs: {},
            });

            this.state.grafanaBaseUrl  = config.base_url;
            this.state.dashboardUid   = config.dashboard_uid;
            this.state.refreshInterval = config.refresh_interval;
            this.state.timeFrom        = config.time_from;
            this.state.countdown       = config.refresh_interval;
            this.state.iframeUrl       = config.embed_url;
            this.state.loading         = false;
            this.state.lastRefresh     = new Date();

            this._startAutoRefresh();
        } catch (err) {
            console.error("[FleetReports] Error al obtener configuración Grafana:", err);
            this.state.loading = false;
            this.state.error   = true;
            this.state.errorMsg = String(err?.message || err || "Error desconocido");
            // Intentar con URL por defecto
            this._buildAndSetUrl();
        }
    }

    // ── Constructor de URL ──────────────────────────────────────────────────
    _buildUrl(timeFrom) {
        const base = this.state.grafanaBaseUrl.replace(/\/$/, "");
        const uid  = encodeURIComponent(this.state.dashboardUid);
        const slug = "flota-vehicular-gps-traccar";
        const ref  = `${this.state.refreshInterval}s`;
        return (
            `${base}/d/${uid}/${slug}` +
            `?orgId=1&from=${timeFrom}&to=now` +
            `&kiosk=tv&refresh=${ref}&theme=dark`
        );
    }

    _buildAndSetUrl() {
        this.state.iframeUrl = this._buildUrl(this.state.timeFrom);
        this.state.loading   = false;
    }

    // ── Auto-refresh ────────────────────────────────────────────────────────
    _startAutoRefresh() {
        this._clearTimers();
        const interval = this.state.refreshInterval * 1000;

        // Refresca el iframe recargando su src
        this._refreshTimer = setInterval(() => {
            this._reloadIframe();
            this.state.countdown  = this.state.refreshInterval;
            this.state.lastRefresh = new Date();
        }, interval);

        // Cuenta regresiva cada segundo
        this._countdownTimer = setInterval(() => {
            if (this.state.countdown > 0) {
                this.state.countdown -= 1;
            }
        }, 1000);
    }

    _clearTimers() {
        if (this._refreshTimer)   clearInterval(this._refreshTimer);
        if (this._countdownTimer) clearInterval(this._countdownTimer);
        this._refreshTimer   = null;
        this._countdownTimer = null;
    }

    _reloadIframe() {
        const iframe = this.iframeRef.el;
        if (iframe) {
            // Reconstruye la URL para forzar un reload limpio del iframe
            const current = iframe.src;
            iframe.src = "";
            requestAnimationFrame(() => { iframe.src = current; });
        }
    }

    // ── Handlers de la UI ───────────────────────────────────────────────────

    onTimeRangeChange(ev) {
        this.state.timeFrom  = ev.target.value;
        this.state.iframeUrl = this._buildUrl(this.state.timeFrom);
        this.state.countdown = this.state.refreshInterval;
        this._startAutoRefresh();
    }

    onManualRefresh() {
        if (this.state.error) {
            this._init();
            return;
        }
        this.state.countdown = this.state.refreshInterval;
        this.state.lastRefresh = new Date();
        this._reloadIframe();
        this._startAutoRefresh();
    }

    onToggleFullscreen() {
        this.state.isFullscreen = !this.state.isFullscreen;
    }

    onOpenGrafana() {
        window.open(this.state.grafanaBaseUrl, "_blank", "noopener,noreferrer");
    }

    onIframeLoad() {
        this.state.loading = false;
        this.state.error   = false;
    }

    onIframeError() {
        this.state.loading = false;
        this.state.error   = true;
        this.state.errorMsg = (
            "No se pudo conectar con Grafana. Verifica que el servicio esté " +
            "corriendo y que la URL esté correctamente configurada."
        );
    }

    // ── Computed helpers ────────────────────────────────────────────────────

    get countdownPercent() {
        const pct = (this.state.countdown / this.state.refreshInterval) * 100;
        return Math.max(0, Math.min(100, pct));
    }

    get lastRefreshLabel() {
        const d = this.state.lastRefresh;
        if (!d) return "—";
        return d.toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    get countdownLabel() {
        const s = this.state.countdown;
        return s > 0 ? `${s}s` : "Actualizando…";
    }
}

// ── Template OWL (inline XML) ───────────────────────────────────────────────
FleetReportsDashboard.template = xml/* xml */`
<div t-attf-class="o_fleet_reports_dashboard {{ state.isFullscreen ? 'fullscreen' : '' }}">

  <!-- ── Barra superior ─────────────────────────────────────── -->
  <div class="o_fleet_reports_topbar">

    <div class="o_fleet_reports_title">
      <span class="icon-fleet">🚗</span>
      <h2>Reportes de Flota Vehicular</h2>
    </div>

    <div class="o_fleet_reports_controls">

      <!-- Selector de rango de tiempo -->
      <label for="fleet_time_range">Período</label>
      <select id="fleet_time_range"
              t-on-change="onTimeRangeChange"
              t-att-value="state.timeFrom">
        <t t-foreach="state.timeRanges" t-as="tr" t-key="tr.value">
          <option t-att-value="tr.value"
                  t-att-selected="tr.value === state.timeFrom">
            <t t-esc="tr.label"/>
          </option>
        </t>
      </select>

      <!-- Badge de estado en vivo -->
      <div class="o_fleet_refresh_badge">
        <span t-attf-class="dot {{ state.loading ? 'loading' : (state.error ? 'error' : '') }}"/>
        <span t-if="!state.error">En vivo</span>
        <span t-if="state.error" style="color:#f44336">Sin conexión</span>
      </div>

      <!-- Botón refresh manual -->
      <button class="o_fleet_btn o_fleet_btn-secondary"
              t-on-click="onManualRefresh"
              title="Actualizar ahora">
        ↻ Actualizar
      </button>

      <!-- Botón abrir Grafana en nueva pestaña -->
      <button class="o_fleet_btn o_fleet_btn-secondary"
              t-on-click="onOpenGrafana"
              title="Abrir Grafana completo">
        ↗ Grafana
      </button>

      <!-- Botón pantalla completa -->
      <button class="o_fleet_btn o_fleet_btn-primary"
              t-on-click="onToggleFullscreen"
              title="Pantalla completa">
        <t t-if="!state.isFullscreen">⛶ Pantalla Completa</t>
        <t t-else="">✕ Salir</t>
      </button>

    </div>
  </div>

  <!-- ── Área del iframe ────────────────────────────────────── -->
  <div class="o_fleet_reports_iframe_wrapper">

    <!-- Cargando -->
    <div t-attf-class="o_fleet_loading_overlay {{ !state.loading ? 'hidden' : '' }}">
      <div class="o_fleet_spinner"/>
      <span class="o_fleet_loading_text">Conectando con Grafana…</span>
    </div>

    <!-- Error -->
    <div t-attf-class="o_fleet_error_overlay {{ state.error ? 'visible' : '' }}">
      <span class="o_fleet_error_icon">📡</span>
      <h3 class="o_fleet_error_title">Sin conexión con Grafana</h3>
      <p class="o_fleet_error_msg">
        <t t-esc="state.errorMsg"/>
      </p>
      <span class="o_fleet_error_url">
        <t t-esc="state.iframeUrl"/>
      </span>
      <button class="o_fleet_btn o_fleet_btn-primary"
              t-on-click="onManualRefresh"
              style="margin-top:8px">
        ↻ Reintentar
      </button>
    </div>

    <!-- Iframe Grafana -->
    <t t-if="!state.error and state.iframeUrl">
      <iframe
        t-ref="grafanaIframe"
        t-att-src="state.iframeUrl"
        title="Dashboard de Flota Vehicular — Grafana"
        allow="fullscreen"
        loading="lazy"
        t-on-load="onIframeLoad"
        t-on-error="onIframeError"
      />
    </t>

  </div>

  <!-- ── Barra de estado inferior ──────────────────────────── -->
  <div class="o_fleet_reports_statusbar">
    <span>Última actualización: <strong t-esc="lastRefreshLabel"/></span>

    <div class="o_fleet_countdown">
      <span>Próximo refresh: <strong t-esc="countdownLabel"/></span>
      <div class="o_fleet_countdown_bar">
        <div class="o_fleet_countdown_fill"
             t-attf-style="width: {{ countdownPercent }}%"/>
      </div>
    </div>

    <span style="color:#3d4a5c">
      Grafana: <t t-esc="state.grafanaBaseUrl"/>
    </span>
  </div>

</div>
`;

// ── Registrar la acción cliente en Odoo ────────────────────────────────────
registry.category("actions").add("fleet_reports.grafana_dashboard", FleetReportsDashboard);
