/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * applyGlobalTheme
 * Aplica de forma inmediata y reactiva las variables CSS y estilos a todo Odoo y al dashboard,
 * garantizando que la barra superior, botones, tablas, gráficos, rutas y paneles adopten el tema elegido.
 */
export function applyGlobalTheme(colors) {
    if (!colors) return;
    const root = document.documentElement;

    const primary = colors.primary || colors.fleet_color_primary;
    const primaryHover = colors.primary_hover || colors.fleet_color_primary_hover || primary;
    const primarySoft = colors.primary_soft || colors.fleet_color_primary_soft;
    const background = colors.background || colors.fleet_color_background;
    const card = colors.card || colors.fleet_color_card;
    const text = colors.text || colors.fleet_color_text;

    if (primary) {
        root.style.setProperty("--bl", primary);
        root.style.setProperty("--blt", primary);
        root.style.setProperty("--o-brand-odoo", primary);
        root.style.setProperty("--o-brand-primary", primary);
    }
    if (primaryHover) {
        root.style.setProperty("--bl-hover", primaryHover);
    }
    if (primarySoft) {
        root.style.setProperty("--bls", primarySoft);
    }
    if (background) {
        root.style.setProperty("--bg", background);
    }
    if (card) {
        root.style.setProperty("--card", card);
    }
    if (text) {
        root.style.setProperty("--tx", text);
    }

    // Aplicar también directamente a los contenedores del dashboard en el DOM
    document.querySelectorAll(".o_fleet_rutas_dashboard, .o_uta, .fleet_main").forEach((el) => {
        if (primary) {
            el.style.setProperty("--bl", primary);
            el.style.setProperty("--blt", primary);
        }
        if (primaryHover) el.style.setProperty("--bl-hover", primaryHover);
        if (primarySoft) el.style.setProperty("--bls", primarySoft);
        if (background) el.style.setProperty("--bg", background);
        if (card) el.style.setProperty("--card", card);
        if (text) el.style.setProperty("--tx", text);
    });

    // Inyectar etiqueta de estilo dinámico de alta prioridad para asegurar
    // que la barra de navegación, botones, gráficos y acentos se actualicen sin depender de cachés.
    let styleTag = document.getElementById("uta-theme-dynamic-styles");
    if (!styleTag) {
        styleTag = document.createElement("style");
        styleTag.id = "uta-theme-dynamic-styles";
        document.head.appendChild(styleTag);
    }

    const pColor = primary || '#714b67';
    const pHover = primaryHover || '#5d3d54';
    const pSoft = primarySoft || '#f3ebf1';
    const bgCol = background || '#f4f4f4';
    const cdCol = card || '#ffffff';
    const txCol = text || '#161616';

    styleTag.textContent = `
        :root, html, body, .o_web_client, .o_fleet_rutas_dashboard, .o_uta {
            --bl: ${pColor} !important;
            --bl-hover: ${pHover} !important;
            --bls: ${pSoft} !important;
            --blt: ${pColor} !important;
            --bg: ${bgCol} !important;
            --card: ${cdCol} !important;
            --tx: ${txCol} !important;
            --o-brand-odoo: ${pColor} !important;
            --o-brand-primary: ${pColor} !important;
        }

        /* ── Barra de navegación superior de Odoo ── */
        .o_main_navbar {
            background-color: ${pColor} !important;
            border-bottom: 1px solid rgba(0, 0, 0, 0.15) !important;
        }

        /* ── Botones de Acción (Gestionar rutas en Odoo, Ver tabla en Odoo, Administrar en Odoo, Guardar, Actualizar) ── */
        .btn-primary,
        .o_control_panel .btn-primary,
        .o_cp_buttons .btn-primary,
        .o_list_button_add,
        .o_form_button_save,
        .o_form_view .btn-primary,
        .o_base_settings .o_control_panel .btn-primary,
        .uta-btn-primary,
        .o_fleet_rutas_dashboard .btn.p,
        .o_fleet_rutas_dashboard .uta-btn-primary,
        .o_uta .uta-btn-primary,
        button.uta-btn-primary,
        button.btn.p {
            background-color: ${pColor} !important;
            border-color: ${pColor} !important;
            color: #ffffff !important;
        }

        .btn-primary:hover,
        .btn-primary:focus,
        .o_control_panel .btn-primary:hover,
        .o_list_button_add:hover,
        .o_form_button_save:hover,
        .o_form_view .btn-primary:hover,
        .o_base_settings .o_control_panel .btn-primary:hover,
        .uta-btn-primary:hover,
        .o_fleet_rutas_dashboard .btn.p:hover,
        .o_fleet_rutas_dashboard .uta-btn-primary:hover,
        .o_uta .uta-btn-primary:hover,
        button.uta-btn-primary:hover,
        button.btn.p:hover {
            background-color: ${pHover} !important;
            border-color: ${pHover} !important;
            color: #ffffff !important;
            opacity: 0.95 !important;
        }

        /* ── Tarjetas de Ruta Seleccionada (en pestaña Rutas y paradas) ── */
        .uta-route.on,
        .o_uta .uta-route.on,
        .o_fleet_rutas_dashboard .uta-route.on {
            background-color: ${pSoft} !important;
            border-left-color: ${pColor} !important;
            border-left-width: 4px !important;
        }

        /* ── Barra Lateral de Navegación del Dashboard ── */
        .o_fleet_rutas_dashboard .fleet_nav_item.on {
            background-color: ${pSoft} !important;
            color: ${pColor} !important;
            border-left-color: ${pColor} !important;
            border-left-width: 4px !important;
            font-weight: 600 !important;
        }

        .o_fleet_rutas_dashboard .fleet_nav_item.on i {
            color: ${pColor} !important;
        }

        /* ── Ícono institucional y acentos ── */
        .o_fleet_rutas_dashboard .fleet_brand i {
            color: ${pColor} !important;
        }

        /* ── Gráficos de barras (Puntualidad por ruta) ── */
        .o_fleet_rutas_dashboard .bars i,
        .o_fleet_rutas_dashboard .bars div i {
            background-color: ${pColor} !important;
        }

        /* ── Barras horizontales de progreso (Incidencias reales por tipo) ── */
        .o_fleet_rutas_dashboard .hb u i {
            background-color: ${pColor} !important;
        }

        /* ── Chips y Badges activos ── */
        .o_fleet_rutas_dashboard .chip.on {
            background-color: ${pColor} !important;
            border-color: ${pColor} !important;
            color: #ffffff !important;
        }

        /* ── Pestaña activa en los Ajustes de Odoo ── */
        .o_base_settings .settings_tab .selected {
            box-shadow: inset 3px 0 0 ${pColor} !important;
        }

        /* ── Barra de búsqueda y etiquetas de filtros ── */
        .o_searchview:focus-within {
            border-color: ${pColor} !important;
            outline: 1px solid ${pColor} !important;
        }

        .o_searchview_facet {
            background-color: ${pSoft} !important;
            border-color: rgba(0, 0, 0, 0.12) !important;
            color: ${pColor} !important;
        }

        .o_searchview_facet .o_searchview_facet_label {
            background-color: ${pColor} !important;
            color: #ffffff !important;
        }

        /* ── Checkboxes y Badges primarios ── */
        .o_list_record_selector input[type="checkbox"]:checked,
        .form-check-input:checked {
            background-color: ${pColor} !important;
            border-color: ${pColor} !important;
        }

        .badge.text-bg-primary,
        .badge.bg-primary,
        .text-bg-primary {
            background-color: ${pSoft} !important;
            color: ${pColor} !important;
        }
    `;
}

// 1. Aplicación instantánea al evaluar el script (antes de la renderización del DOM)
try {
    const cached = window.localStorage.getItem("fleet_theme_colors");
    if (cached) {
        applyGlobalTheme(JSON.parse(cached));
    }
} catch (e) {
    // Silencioso si no hay acceso a storage
}

// 2. Servicio Odoo para sincronizar con la base de datos de Odoo
export const fleetThemeService = {
    dependencies: ["rpc"],
    async start(env, { rpc }) {
        try {
            const serverColors = await rpc("/web/dataset/call_kw", {
                model: "res.config.settings",
                method: "get_theme_colors",
                args: [],
                kwargs: {},
            });
            if (serverColors) {
                applyGlobalTheme(serverColors);
                window.localStorage.setItem("fleet_theme_colors", JSON.stringify(serverColors));
            }
        } catch (err) {
            console.warn("No se pudieron cargar colores del servidor Odoo:", err);
        }

        // Escuchar eventos de cambio de color dentro de la aplicación
        window.addEventListener("uta-theme-changed", (ev) => {
            if (ev.detail) {
                applyGlobalTheme(ev.detail);
                window.localStorage.setItem("fleet_theme_colors", JSON.stringify(ev.detail));
            }
        });

        return {
            apply: (colors) => {
                applyGlobalTheme(colors);
                window.localStorage.setItem("fleet_theme_colors", JSON.stringify(colors));
                window.dispatchEvent(new CustomEvent("uta-theme-changed", { detail: colors }));
            },
        };
    },
};

registry.category("services").add("fleet_theme", fleetThemeService);
