/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * applyGlobalTheme
 * Aplica de forma inmediata y reactiva las variables CSS y estilos a todo Odoo,
 * garantizando que la barra superior, botones, filtros y paneles adopten el tema elegido.
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

    // Inyectar etiqueta de estilo dinámico de alta prioridad para asegurar
    // que la barra de navegación, botones y acentos se actualicen sin depender de cachés.
    let styleTag = document.getElementById("uta-theme-dynamic-styles");
    if (!styleTag) {
        styleTag = document.createElement("style");
        styleTag.id = "uta-theme-dynamic-styles";
        document.head.appendChild(styleTag);
    }

    styleTag.textContent = `
        :root, html, body, .o_web_client {
            --bl: ${primary || '#714b67'} !important;
            --bl-hover: ${primaryHover || '#5d3d54'} !important;
            --bls: ${primarySoft || '#f3ebf1'} !important;
            --blt: ${primary || '#714b67'} !important;
            --bg: ${background || '#f4f4f4'} !important;
            --card: ${card || '#ffffff'} !important;
            --tx: ${text || '#161616'} !important;
            --o-brand-odoo: ${primary || '#714b67'} !important;
            --o-brand-primary: ${primary || '#714b67'} !important;
        }

        /* Barra de navegación superior de Odoo */
        .o_main_navbar {
            background-color: ${primary || '#714b67'} !important;
            border-bottom: 1px solid rgba(0, 0, 0, 0.15) !important;
        }

        /* Botones primarios (Guardar, NUEVO, etc.) */
        .btn-primary,
        .o_control_panel .btn-primary,
        .o_cp_buttons .btn-primary,
        .o_list_button_add,
        .o_form_button_save,
        .o_form_view .btn-primary,
        .o_base_settings .o_control_panel .btn-primary {
            background-color: ${primary || '#714b67'} !important;
            border-color: ${primary || '#714b67'} !important;
            color: #ffffff !important;
        }

        .btn-primary:hover,
        .btn-primary:focus,
        .o_control_panel .btn-primary:hover,
        .o_list_button_add:hover,
        .o_form_button_save:hover,
        .o_form_view .btn-primary:hover,
        .o_base_settings .o_control_panel .btn-primary:hover {
            background-color: ${primaryHover || '#5d3d54'} !important;
            border-color: ${primaryHover || '#5d3d54'} !important;
            color: #ffffff !important;
            opacity: 0.95 !important;
        }

        /* Pestaña activa en los Ajustes de Odoo */
        .o_base_settings .settings_tab .selected {
            box-shadow: inset 3px 0 0 ${primary || '#714b67'} !important;
        }

        /* Barra de búsqueda y etiquetas de filtros */
        .o_searchview:focus-within {
            border-color: ${primary || '#714b67'} !important;
            outline: 1px solid ${primary || '#714b67'} !important;
        }

        .o_searchview_facet {
            background-color: ${primarySoft || '#f3ebf1'} !important;
            border-color: rgba(0, 0, 0, 0.12) !important;
            color: ${primary || '#714b67'} !important;
        }

        .o_searchview_facet .o_searchview_facet_label {
            background-color: ${primary || '#714b67'} !important;
            color: #ffffff !important;
        }

        /* Checkboxes y Badges */
        .o_list_record_selector input[type="checkbox"]:checked,
        .form-check-input:checked {
            background-color: ${primary || '#714b67'} !important;
            border-color: ${primary || '#714b67'} !important;
        }

        .badge.text-bg-primary,
        .badge.bg-primary,
        .text-bg-primary {
            background-color: ${primarySoft || '#f3ebf1'} !important;
            color: ${primary || '#714b67'} !important;
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
