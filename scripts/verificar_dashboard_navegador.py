"""Pruebas visuales aisladas: Owl y CSS reales de Odoo, datos sintéticos sin BD.

Requiere playwright y un Chrome instalado. No usa el perfil del usuario.
"""
import argparse
import json
import re
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--base-url', default='http://localhost:8070')
parser.add_argument('--css-url', required=True, help='URL pública del bundle CSS backend de la instalación')
parser.add_argument('--output', default='docs/dashboard_usabilidad')
parser.add_argument('--compiled-only', action='store_true', help='Usar solo el CSS compilado del servidor, sin añadir el CSS fuente')
args = parser.parse_args()
out = ROOT / args.output
out.mkdir(parents=True, exist_ok=True)


def fetch(path):
    response = requests.get(args.base_url + path, timeout=30)
    response.raise_for_status()
    return response.text


global_css = fetch(args.css_url)
owl_js = fetch('/web/static/lib/owl/owl.js')
source = (ROOT / 'addons/fleet_rutas/static/src/js/fleet_dashboard.js').read_text(encoding='utf-8')
source = re.sub(r'^import .*?;\s*$', '', source, flags=re.M)
source = '''const {Component,useState,useRef,onMounted,onWillUnmount,xml,useEnv}=owl;
const useService=name=>useEnv().services[name];
const registry={category:()=>({add:(_name,component)=>{window.FleetAuditComponent=component;}})};
''' + source
fixture = {
    'recorridos_hoy': 12, 'en_curso': 10, 'completados': 24,
    'incidencias_activas': 2, 'avg_puntualidad': 87.5,
    'avg_cumplimiento': 92.4, 'avg_integridad_gps': 97.8,
    'recorridos_activos': [
        {'id': i, 'name': f'Recorrido de prueba {i} | ' + 'Nombre largo para comprobar la adaptación del panel ' * 2,
         'ruta': 'Intercampús universitario' if i <= 2 else f'Ruta de prueba {i}',
         'vehiculo': 'Autobús de prueba / identificación de vehículo extensa ' + str(i),
         'paradas_cumplidas': '75%', 'desviacion': i == 3} for i in range(1, 11)
    ],
}
html = '''<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>''' + global_css + '''</style><style>
html,body{margin:0;height:100%;width:100%}.audit_nav{height:46px;min-height:46px;padding:10px 20px;background:#65568c;color:white}
</style><body class="o_web_client"><nav class="audit_nav">Fleet · Prueba aislada de interfaz</nav><div class="o_action_manager" id="audit_mount"></div></body></html>'''
custom_css = (ROOT / 'addons/fleet_rutas/static/src/css/fleet_dashboard.css').read_text(encoding='utf-8-sig')
results = {'entorno': 'Chrome aislado, Owl y CSS backend reales; RPC simulado, sin datos de usuario', 'viewports': [], 'controles': [], 'contraste': []}

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True, ignore_default_args=['--hide-scrollbars'])
    context = browser.new_context(viewport={'width': 1440, 'height': 900}, locale='es-EC', reduced_motion='reduce')
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(args.base_url + '/web/health', wait_until='domcontentloaded')
    page.clock.install()
    page.set_content(html)
    if not args.compiled_only:
        page.add_style_tag(content=custom_css)
    page.add_script_tag(content=owl_js)
    page.add_script_tag(content=source)
    page.evaluate('''async (data) => {
        window.audit={calls:0,fail:false,actions:[],pending:false};
        const env={services:{rpc:async()=>{
            audit.calls++;
            if(audit.fail) throw new Error('Fallo de prueba');
            if(audit.pending) await new Promise(resolve=>audit.resolve=resolve);
            return structuredClone(data);
        },action:{doAction:action=>audit.actions.push(action)}}};
        window.auditApp=new owl.App(window.FleetAuditComponent,{env});
        await auditApp.mount(document.getElementById('audit_mount'));
        document.querySelector('.o_fleet_rutas_dashboard').classList.add('o_action');
    }''', fixture)
    page.locator('.fleet_table tbody tr').first.wait_for()
    page.evaluate('document.fonts.ready')
    original_hash = page.evaluate('location.hash')
    page.get_by_role('link', name='Ir a los recorridos', exact=True).focus()
    page.keyboard.press('Enter')
    assert page.evaluate("document.activeElement.id==='fleet_trips_title'")
    assert page.evaluate('location.hash') == original_hash
    results['controles'].append('Saltar a recorridos por teclado sin modificar la ruta de Odoo')

    for width, height in [(320, 640), (360, 740), (390, 844), (768, 800), (1024, 768), (1440, 900), (1920, 1080), (844, 390), (1280, 256)]:
        page.set_viewport_size({'width': width, 'height': height})
        viewport = page.locator('.fleet_viewport')
        geometry = page.evaluate('''() => {
            const v=document.querySelector('.fleet_viewport');
            const t=document.querySelector('.fleet_table_scroll');
            return {width:innerWidth,height:innerHeight,documentWidth:document.documentElement.scrollWidth,
                viewportWidth:v.clientWidth,viewportHeight:v.clientHeight,scrollHeight:v.scrollHeight,
                overflowY:getComputedStyle(v).overflowY,tableScroll:t.scrollWidth>t.clientWidth};
        }''')
        assert geometry['documentWidth'] <= width, geometry
        assert 0 < geometry['viewportHeight'] < height, geometry
        assert geometry['scrollHeight'] > geometry['viewportHeight'], geometry
        viewport.evaluate('(el)=>el.scrollTop=el.scrollHeight')
        bottom = page.evaluate('''() => {
            const v=document.querySelector('.fleet_viewport').getBoundingClientRect();
            const f=document.querySelector('.fleet_footer').getBoundingClientRect();
            return {viewportBottom:v.bottom,footerBottom:f.bottom};
        }''')
        assert bottom['footerBottom'] <= bottom['viewportBottom'] + 1, bottom
        viewport.evaluate('(el)=>el.scrollTop=0')
        if width in (390, 1440):
            page.screenshot(path=str(out / f'dashboard_{width}.png'))
        results['viewports'].append({**geometry, 'footer_alcanzable': True})

    page.set_viewport_size({'width': 390, 'height': 844})
    slider = page.locator('#fleet_text_scale')
    slider.focus()
    slider.press('End')
    assert slider.input_value() == '140'
    expect(page.locator('output')).to_have_text('140%')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(out / 'dashboard_movil_texto_140.png'))
    page.set_viewport_size({'width': 320, 'height': 640})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.set_viewport_size({'width': 390, 'height': 844})
    results['controles'].append('Deslizador por teclado hasta 140%, sin desbordamiento global')
    checkbox = page.get_by_label('Vista compacta', exact=True)
    checkbox.check()
    expect(page.locator('.o_fleet_rutas_dashboard')).to_have_class(re.compile('fleet_compact'))
    results['controles'].append('Vista compacta operativa')

    search = page.locator('#fleet_trip_search')
    search.fill('intercampus')
    expect(page.locator('.fleet_table tbody tr')).to_have_count(2)
    search.fill('zzzz_sin_coincidencias')
    expect(page.get_by_role('heading', name='Sin coincidencias', exact=True)).to_be_visible()
    page.locator('.fleet_empty').get_by_role('button', name='Limpiar búsqueda', exact=True).click()
    expect(page.locator('.fleet_table tbody tr')).to_have_count(10)
    results['controles'].append('Búsqueda sin sensibilidad a tildes, estado sin coincidencias y limpiar')

    auto = page.get_by_label('Actualización automática', exact=True)
    auto.uncheck()
    calls = page.evaluate('audit.calls')
    page.clock.fast_forward(61000)
    assert page.evaluate('audit.calls') == calls
    page.get_by_role('button', name='Actualizar panel', exact=True).click()
    page.get_by_role('button', name='Actualizar panel', exact=True).wait_for(state='visible')
    assert page.evaluate('audit.calls') == calls + 1
    auto.check()
    page.clock.fast_forward(31000)
    assert page.evaluate('audit.calls') == calls + 2
    results['controles'].append('Pausa, actualización manual y reanudación de actualización cada 30 s')

    page.evaluate('audit.pending=true')
    page.get_by_role('button', name='Actualizar panel', exact=True).click()
    expect(page.get_by_role('button', name='Actualizar panel', exact=True)).to_be_disabled()
    in_flight_calls = page.evaluate('audit.calls')
    page.clock.fast_forward(31000)
    assert page.evaluate('audit.calls') == in_flight_calls
    page.evaluate('audit.pending=false; audit.resolve()')
    expect(page.get_by_role('button', name='Actualizar panel', exact=True)).to_be_enabled()
    results['controles'].append('No se superponen peticiones mientras una actualización está pendiente')

    page.evaluate('audit.fail=true')
    page.get_by_role('button', name='Actualizar panel', exact=True).click()
    page.get_by_role('alert').wait_for()
    assert page.locator('.fleet_table tbody tr').count() == 10
    page.evaluate('audit.fail=false')
    page.get_by_role('button', name='Reintentar', exact=True).click()
    page.get_by_role('alert').wait_for(state='detached')
    results['controles'].append('Error recuperable con datos anteriores y reintento')

    page.get_by_role('button', name='Restablecer vista', exact=True).click()
    expect(slider).to_have_value('100')
    assert not checkbox.is_checked()
    saved = page.evaluate("JSON.parse(localStorage.getItem('fleet_rutas.dashboard.view.v1'))")
    assert saved == {'textScale': 100, 'compact': False, 'autoRefresh': True}
    results['controles'].append('Restablecer vista y guardar preferencias locales')

    page.locator('.fleet_table_scroll').focus()
    page.keyboard.press('End')
    scroll = page.locator('.fleet_table_scroll').evaluate('(el)=>{el.scrollLeft=el.scrollWidth;return el.scrollLeft;}')
    assert scroll > 0
    results['controles'].append('Tabla móvil con scroll horizontal independiente')

    results['contraste'] = page.evaluate('''() => {
        function rgb(s){return (s.match(/[\\d.]+/g)||[]).slice(0,3).map(Number);}
        function lum(a){return a.map(c=>{c/=255;return c<=.04045?c/12.92:Math.pow((c+.055)/1.055,2.4);}).reduce((s,c,i)=>s+c*[.2126,.7152,.0722][i],0);}
        return ['.fleet_kpi_hint','.fleet_vehicle_cell','.fleet_cell_secondary','.fleet_search_count','.fleet_button_primary'].map(selector=>{
            const el=document.querySelector(selector);let bg=el;
            while(bg && getComputedStyle(bg).backgroundColor==='rgba(0, 0, 0, 0)')bg=bg.parentElement;
            const color=getComputedStyle(el).color, background=getComputedStyle(bg).backgroundColor;
            const l=[lum(rgb(color)),lum(rgb(background))].sort((a,b)=>b-a);
            return {selector,color,background,ratio:(l[0]+.05)/(l[1]+.05)};
        });
    }''')
    assert all(r['ratio'] >= 4.5 for r in results['contraste']), results['contraste']
    assert not errors, errors
    before_destroy = page.evaluate('audit.calls')
    page.evaluate('auditApp.destroy()')
    page.clock.fast_forward(61000)
    assert page.evaluate('audit.calls') == before_destroy
    results['controles'].append('Temporizador eliminado al salir del panel')
    results['errores_javascript'] = errors
    results['resultado'] = 'aprobado'
    context.close()
    browser.close()

(out / 'resultados_navegador.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=True, indent=2))
