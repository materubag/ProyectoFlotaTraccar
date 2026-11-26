/** @odoo-module **/
import { Component, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
class DataOrigin extends Component {
  static props = { ...standardFieldProps };
  static supportedTypes = ["boolean"];
  static template = xml/* xml */`
<span>
  <span t-if="props.readonly" t-att-class="'badge ' + (props.value ? 'text-bg-warning' : 'text-bg-success')" t-esc="props.value ? 'Simulado' : 'Real'" />
  <select t-else="" aria-label="Origen del dato" t-att-value="props.value ? 'simulado' : 'real'" t-on-change="change">
    <option value="real">Real</option>
    <option value="simulado">Simulado</option>
  </select>
</span>
`;
  change(ev) {
    this.props.update(ev.target.value === "simulado");
  }
}
registry.category("fields").add("fleet_data_origin", DataOrigin);
class RoutePreview extends Component {
  static props = { ...standardWidgetProps };
  get document() {
    const points = (this.props.record.data.parada_ids?.records || [])
      .map((r) => r.data)
      .filter((p) => Number.isFinite(p.latitud) && Number.isFinite(p.longitud))
      .map((p) => ({ lat: p.latitud, lon: p.longitud, name: p.name }));
    const accent = getComputedStyle(document.documentElement).getPropertyValue("--bl").trim();
    const color = /^#[0-9a-f]{6}$/i.test(accent) ? accent : "#714b67";
    const data = JSON.stringify(points).replace(/</g, "\\u003c");
    return `<!doctype html><html lang="es"><meta charset="utf-8"><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><style>body{margin:0}#map{height:360px}#status{font:14px system-ui}</style><div id="map"></div><div id="status"></div><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>const points=${data};if(typeof L==='undefined'){document.getElementById('status').textContent='No se pudo cargar el mapa';}else{const map=L.map('map').setView([-1.249,-78.617],13);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(map);const coords=points.map(p=>[p.lat,p.lon]);points.forEach(p=>{const label=document.createElement('span');label.textContent=p.name;L.marker([p.lat,p.lon]).addTo(map).bindPopup(label);});if(coords.length){L.polyline(coords,{color:'${color}'}).addTo(map);map.fitBounds(coords,{padding:[25,25],maxZoom:15});}else{document.getElementById('status').textContent='Añade puntos de control para previsualizar la ruta';}}</script></html>`;
  }
  static template = xml/* xml */`
<iframe title="Vista previa de puntos de control" t-att-srcdoc="document" style="width:100%;height:390px;border:1px solid var(--bd);" sandbox="allow-scripts allow-same-origin" />
`;
}
registry.category("view_widgets").add("fleet_route_preview", RoutePreview);
