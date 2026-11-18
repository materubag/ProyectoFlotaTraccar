import json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2]
out=root/'docs/ui_cleanup';out.mkdir(exist_ok=True)
import argparse
parser=argparse.ArgumentParser(description='Verificar navegación de Odoo con una sesión de pruebas autorizada')
parser.add_argument('--session-file',type=Path,required=True)
args=parser.parse_args()
errors=[];result={}
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
 context=browser.new_context(viewport={'width':1440,'height':1000},locale='es-EC')
 context.add_cookies([{'name':'session_id','value':args.session_file.read_text().strip(),'url':'http://localhost:8070','httpOnly':True}])
 page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://localhost:8070/web?ui_check=dashboard#action=169&menu_id=126',wait_until='domcontentloaded')
 page.wait_for_timeout(2500)
 page.screenshot(path=str(out/'initial.png'),full_page=True)

 try:
  page.locator('.fleet_sidebar').wait_for(timeout=15000)
  result['tabs']=page.locator('.fleet_nav_item').all_inner_texts()
  for name in result['tabs']:
   page.locator('.fleet_nav_item').filter(has_text=name).click()
   page.wait_for_timeout(500)
   result[name]={'overflow':page.evaluate('document.documentElement.scrollWidth>innerWidth'),'text':page.locator('.fleet_main').inner_text()[:900]}
   page.screenshot(path=str(out/(name.replace(' ','_')+'.png')),full_page=True)
 except Exception as e:result['failure']=str(e)
 # Persistencia al volver desde una lista nativa de Odoo.
 page.locator('.fleet_nav_item').filter(has_text='Rutas y programación').click()
 page.get_by_role('button',name='Programación',exact=True).click()
 page.get_by_role('button',name='Ver registros',exact=True).click()
 page.locator('.o_list_view').wait_for()
 result['breadcrumbs']=page.locator('.breadcrumb').inner_text()
 links=page.locator('.breadcrumb a')
 if links.count(): links.first.click()
 else: page.go_back(wait_until='domcontentloaded')
 page.locator('.fleet_sidebar').wait_for()
 page.get_by_role('heading',name='Programación de salidas',exact=True).wait_for()
 result['route_persistence']=True
 page.locator('.fleet_nav_item').filter(has_text='Recorridos').click()
 page.locator('.fleet_detail_links button[aria-label=Horarios]').first.click()
 page.get_by_role('heading',name='Horario previsto frente a real',exact=True).wait_for()
 page.get_by_role('button',name='Ver registros',exact=True).click()
 page.locator('.o_list_view').wait_for()
 links=page.locator('.breadcrumb a')
 if links.count():links.first.click()
 else:page.go_back(wait_until='domcontentloaded')
 page.get_by_role('heading',name='Horario previsto frente a real',exact=True).wait_for()
 result['trip_persistence']=True
 page.get_by_role('button',name='Incidencias',exact=True).click()
 page.get_by_text('Sin incidencias registradas.',exact=True).wait_for()
 result['detail_incidents']=page.locator('.fleet_main').inner_text()[-500:]
 page.get_by_role('button',name='Mapa',exact=True).click()
 page.locator('iframe').wait_for()
 result['map_frame_status']=page.request.get('http://localhost:8070'+page.locator('iframe').get_attribute('src')).status
 # Formulario de ruta y mapa de vista previa.
 page.goto('http://localhost:8070/web?ui_check=route#action=176',wait_until='domcontentloaded')
 page.locator('.o_data_row').first.click()
 page.locator('.o_form_view').wait_for()
 result['route_form']=page.locator('.o_form_view').inner_text()[:900]
 page.get_by_role('tab',name='Vista previa',exact=True).click()
 frame=page.frame_locator('iframe[title="Vista previa de puntos de control"]')
 frame.locator('.leaflet-marker-icon').first.wait_for(timeout=15000)
 result['preview_points']=frame.locator('.leaflet-marker-icon').count()
 page.wait_for_timeout(2000)
 page.screenshot(path=str(out/'route_form.png'),full_page=True)
 # Vehículo: dispositivo existente y telemetría.
 page.goto('http://localhost:8070/web?ui_check=vehicles#action=131',wait_until='domcontentloaded')
 response=page.request.post('http://localhost:8070/web/dataset/call_kw',data={'jsonrpc':'2.0','method':'call','params':{'model':'fleet.vehicle','method':'search_read','args':[],'kwargs':{'fields':['id'],'limit':1}}}).json()
 vehicle_id=response['result'][0]['id']
 page.goto(f'http://localhost:8070/web?ui_check=vehicles#action=131&model=fleet.vehicle&view_type=form&id={vehicle_id}',wait_until='domcontentloaded')
 page.get_by_role('tab',name='Dispositivo y última posición',exact=True).click()
 result['vehicle_form']=page.locator('.o_form_view').inner_text()[-1200:]
 page.screenshot(path=str(out/'vehicle_form.png'),full_page=True)
 # Ajustes unificados.
 page.goto('http://localhost:8070/web?ui_check=settings#action=178',wait_until='domcontentloaded')
 page.locator('.o_form_view').wait_for()
 page.locator('.o_field_widget[name=traccar_server_url]').wait_for()
 result['settings']=page.locator('.o_form_view').inner_text()
 page.screenshot(path=str(out/'settings.png'),full_page=True)
 # Sin scroll horizontal de página ni del panel a 1280 y 1440.
 page.goto('http://localhost:8070/web?ui_check=dashboard#action=169&menu_id=126',wait_until='domcontentloaded')
 page.locator('.fleet_sidebar').wait_for()
 page.locator('.fleet_nav_item').filter(has_text='Métricas').click()
 result['layout']=[]
 for width in [1280,1440,390]:
  page.set_viewport_size({'width':width,'height':900})
  result['layout'].append(page.evaluate("""() => ({width:innerWidth,pageOverflow:document.documentElement.scrollWidth>innerWidth,mainOverflow:document.querySelector('.fleet_main').scrollWidth>document.querySelector('.fleet_main').clientWidth,headerRows:[...document.querySelectorAll('thead th')].map(n=>n.getBoundingClientRect().height),dataRows:[...document.querySelectorAll('tbody tr')].slice(0,2).map(n=>n.getBoundingClientRect().height)})"""))
  page.screenshot(path=str(out/f'metrics_{width}.png'),full_page=True)
 # Verificar acciones nativas y los filtros de presentación.
 page.set_viewport_size({'width':1440,'height':1000})
 result['native_actions']={}
 for action,model in [(131,'fleet.vehicle'),(174,'fleet.recorrido'),(170,'fleet.incidencia'),(172,'fleet.posicion.gps'),(173,'fleet.metricas.recorrido'),(128,'fleet.vehicle.model'),(129,'fleet.vehicle.model.brand')]:
  page.goto(f'http://localhost:8070/web?ui_native={action}#action={action}',wait_until='domcontentloaded')
  page.locator('.o_list_view, .o_kanban_view').wait_for()
  page.locator('.o_data_row, .o_group_header, .o_kanban_record:not(.o_kanban_ghost)').first.wait_for()
  rows=page.locator('.o_data_row, .o_group_header, .o_kanban_record:not(.o_kanban_ghost)').count()
  result['native_actions'][model]={'rows':rows,'error_dialogs':page.locator('.o_error_dialog').count()}
  assert rows>0, model
 page.goto('http://localhost:8070/web?ui_filters=1#action=169&menu_id=126',wait_until='domcontentloaded')
 page.locator('.fleet_sidebar').wait_for()
 page.locator('.fleet_nav_item').filter(has_text='Panel').click()
 page.locator('.fleet_main .big').first.wait_for()
 route_select=page.locator('.fleet_filters select').nth(0)
 route_value=route_select.locator('option').nth(1).get_attribute('value')
 route_select.select_option(route_value)
 page.wait_for_timeout(100)
 result['route_filter']=page.locator('.fleet_filters').inner_text()
 page.locator('.fleet_filters select').nth(1).select_option('7')
 page.wait_for_timeout(100)
 result['period_filter']=page.locator('.fleet_filters').inner_text()
 result['no_sample']=page.locator('.big').first.inner_text()
 result['errors']=errors
 (out/'browser_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:result.get(k) for k in ['route_persistence','trip_persistence','preview_points','map_frame_status','layout','native_actions','no_sample','errors']},ensure_ascii=True))
 browser.close()
