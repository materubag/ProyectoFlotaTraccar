const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname,
    '../addons/fleet_reports/static/src/js/fleet_reports_widget.js'), 'utf8')
    .replace(/^import .*;\r?\n/gm, '');
let Widget;
const config = {base_url: 'http://192.168.1.20:3000', dashboard_uid: 'custom-uid',
    refresh_interval: 30, time_from: 'now-6h'};
const context = {
    Component: class {}, useState: state => state, useRef: () => ({el: {}}),
    useService: () => async () => config, onMounted: () => {}, onWillUnmount: () => {},
    xml: strings => strings.join(''), registry: {category: () => ({add: (_, cls) => {Widget = cls;}})},
    URL, Date, console,
    // Cualquier intento de reinstalar la recarga automática hace fallar la prueba.
    setInterval: () => {throw Error('No debe recargarse el iframe mediante temporizadores');},
};
vm.runInNewContext(source, context);
(async () => {
    const widget = new Widget();
    widget.setup();
    await widget._init();
    assert.equal(widget.state.error, false);
    const url = new URL(widget.state.iframeUrl);
    assert.equal(url.hostname, '192.168.1.20');
    assert.equal(url.searchParams.get('refresh'), '30s');
    assert.ok(url.pathname.includes('/custom-uid/'));
    widget.onTimeRangeChange({target: {value: 'now-24h'}});
    assert.equal(new URL(widget.state.iframeUrl).searchParams.get('from'), 'now-24h');
    assert.equal(widget.state.lastRefresh, null);
    widget.onManualRefresh();
    assert.ok(new URL(widget.state.iframeUrl).searchParams.has('_reload'));
    assert.equal(widget.state.lastRefresh, null);
    widget.onIframeLoad();
    assert.ok(widget.state.lastRefresh instanceof Date);
    console.log('PASS URL, UID, rango, refresco nativo y recarga manual sin temporizadores');
})().catch(error => {console.error(error); process.exitCode = 1;});
