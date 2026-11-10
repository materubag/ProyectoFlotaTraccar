/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState, onWillUpdateProps, xml } from "@odoo/owl";

/**
 * FleetColorPickerField
 * Componente de campo visual para seleccionar colores en formularios de Odoo.
 * Combina un swatch interactivo con selector de color nativo del sistema
 * y una caja con el código hexadecimal para máxima comodidad.
 */
export class FleetColorPickerField extends Component {
    setup() {
        this.state = useState({
            color: this.props.value || "#714b67",
        });

        onWillUpdateProps((nextProps) => {
            this.state.color = nextProps.value || "#714b67";
        });
    }

    get isReadonly() {
        return Boolean(this.props.readonly || (this.props.record && this.props.record.isReadonly(this.props.name)));
    }

    onColorInput(ev) {
        this.state.color = ev.target.value;
    }

    onColorChange(ev) {
        const val = ev.target.value;
        this.state.color = val;
        this.props.update(val);
    }

    onHexChange(ev) {
        let val = (ev.target.value || "").trim();
        if (!val) return;
        if (!val.startsWith("#")) {
            val = "#" + val;
        }
        if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
            this.state.color = val;
            this.props.update(val);
        }
    }
}

FleetColorPickerField.template = xml/* xml */`
    <div class="uta-color-picker-field d-inline-flex align-items-center">
        <div class="uta-color-swatch-wrapper"
             t-att-class="{ 'disabled': isReadonly }"
             t-attf-style="background-color: #{state.color};"
             title="Haz clic para abrir el selector visual de color">
            <input type="color"
                   class="uta-native-color-input"
                   t-att-value="state.color"
                   t-att-disabled="isReadonly"
                   t-on-input="onColorInput"
                   t-on-change="onColorChange"/>
        </div>
        <input type="text"
               class="uta-hex-text-input"
               t-att-value="state.color"
               t-att-disabled="isReadonly"
               t-on-change="onHexChange"
               placeholder="#000000"
               maxlength="7"
               title="Código hexadecimal de color (ej. #714b67)"/>
    </div>
`;

FleetColorPickerField.props = {
    ...standardFieldProps,
};

FleetColorPickerField.supportedTypes = ["char"];

registry.category("fields").add("fleet_color_picker", FleetColorPickerField);
