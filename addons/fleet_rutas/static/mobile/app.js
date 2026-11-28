/* Mi Ruta: scoped data comes only from authenticated Odoo endpoints. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let state = null, selected = null, map = null, layers = null, installPrompt = null;
  let historyOffset = 0, busy = false, sw = null, historyBusy = false;
  let seen = new Set(), initialized = false;
  const labels = {activa: 'Ruta activa', suspendida: 'Ruta suspendida', mantenimiento: 'En mantenimiento',
    programado: 'Programado', en_curso: 'En curso', completado: 'Completado',
    cancelado: 'Cancelado', con_incidencias: 'Con incidencias'};
  const date = value => value ? new Date(value).toLocaleString('es-EC', {dateStyle: 'medium', timeStyle: 'short'}) : 'Sin registro';
  function node(tag, text, cls) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
  function message(text) { $('message').textContent = text; $('message').hidden = !text; }
  async function api(path, options = {}) {
    const response = await fetch('/flota/api/' + path, {credentials: 'same-origin', cache: 'no-store', ...options});
    if (response.redirected || response.status === 401 || response.status === 403) {
      location.assign('/web/login?redirect=/flota/app');
      throw new Error('Vuelve a iniciar sesión para consultar tus rutas.');
    }
    if (!response.ok || !(response.headers.get('content-type') || '').includes('application/json')) {
      throw new Error('No pudimos consultar la información. Inténtalo de nuevo.');
    }
    return response.json();
  }
  function initMap() {
    if (map) return true;
    if (!window.L) { message('No se pudo cargar el mapa. Puedes seguir consultando rutas y avisos.'); return false; }
    map = L.map('map').setView([-1.249, -78.617], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(map);
    layers = L.layerGroup().addTo(map);
    return true;
  }
  function drawMap(fit = false, track = null) {
    if (!initMap()) return;
    layers.clearLayers();
    const route = state?.routes.find(r => r.id === selected);
    if (!route && !track) { $('map-title').textContent = 'Sin rutas asignadas'; return; }
    const points = [];
    $('map-title').textContent = track ? 'Historial · ' + track.route : route.name;
    if (track) {
      const line = track.points.map(p => [p.lat, p.lng]);
      if (line.length) {
        L.polyline(line, {color: '#385072', weight: 5}).addTo(layers);
        L.circleMarker(line[0], {radius: 7, color: '#0057ff'}).bindPopup('Inicio GPS').addTo(layers);
        L.circleMarker(line[line.length - 1], {radius: 7, color: '#385072'}).bindPopup('Último punto GPS').addTo(layers);
        points.push(...line);
      }
      $('vehicle-info').textContent = line.length ? 'Trazado GPS histórico · ' + date(track.points[0].at) + ' a ' + date(track.points.at(-1).at) + '. Se simplifican los recorridos largos para facilitar su visualización.' : 'Este recorrido todavía no tiene posiciones GPS registradas.';
    } else {
      const stops = route.stops.map(p => [p.lat, p.lng]);
      // Línea discontinua: la ruta aún no tiene trazado por calles y es aproximada.
      const path = route.path?.length > 1 ? route.path : stops;
      if (path.length > 1) L.polyline(path, {color: '#0057ff', weight: 4, dashArray: route.approximate ? '8 7' : null}).addTo(layers);
      route.stops.forEach((p, i) => {
        L.marker([p.lat, p.lng], {icon: L.divIcon({className: 'stop-marker', html: String(i + 1), iconSize: [26, 26]})})
          .bindPopup(node('span', p.name + ' · ' + p.time)).addTo(layers);
      });
      points.push(...path);
      const vehicles = state.vehicles.filter(v => v.route_id === route.id);
      $('vehicle-info').replaceChildren();
      if (!vehicles.length) $('vehicle-info').textContent = 'No hay un vehículo en recorrido para esta ruta en este momento.';
      vehicles.forEach(v => {
        const info = node('div');
        info.append(node('strong', v.name));
        info.append(node('span', v.position ? (v.position.stale ? 'Señal sin actualizar' : 'Última posición recibida') + ' · ' + v.position.speed.toFixed(0) + ' km/h · ' + date(v.position.at) : 'Esperando la primera posición GPS.'));
        $('vehicle-info').append(info);
        if (v.position) {
          const p = v.position;
          L.marker([p.lat, p.lng], {icon: L.divIcon({className: 'bus-marker', html: '▣', iconSize: [36, 36]})})
            .bindPopup(node('span', v.name + ' · ' + (p.stale ? 'Señal sin actualizar' : p.speed.toFixed(0) + ' km/h'))).addTo(layers);
          points.push([p.lat, p.lng]);
        }
      });
    }
    map.invalidateSize();
    if (fit && points.length) map.fitBounds(L.latLngBounds(points), {padding: [35, 35], maxZoom: 16});
  }
  let viewingTrack = false;
  function selectRoute(id) {
    selected = id; viewingTrack = false;
    document.querySelectorAll('.route-card').forEach(el => {
      el.classList.toggle('selected', Number(el.dataset.id) === id);
      el.setAttribute('aria-pressed', String(Number(el.dataset.id) === id));
    });
    drawMap(true);
  }
  function renderRoutes() {
    const list = $('routes'); list.replaceChildren();
    $('route-count').textContent = state.routes.length + ' rutas';
    if (!state.routes.length) {
      list.append(node('p', 'Aún no tienes rutas asignadas. Solicita al administrador que agregue las rutas que tomas.', 'empty'));
      $('vehicle-info').textContent = 'Tus vehículos aparecerán cuando tengas una ruta asignada.';
    }
    state.routes.forEach(route => {
      const card = node('button', undefined, 'route-card' + (route.id === selected ? ' selected' : ''));
      card.dataset.id = route.id; card.setAttribute('aria-pressed', String(route.id === selected));
      card.append(node('span', labels[route.status] || route.status, 'route-status'));
      card.append(node('strong', route.name), node('small', 'Desde · ' + route.origin), node('small', 'Hasta · ' + route.destination));
      card.append(node('small', route.stops.length + ' paradas · ' + route.duration + ' min estimados', 'route-meta'));
      card.addEventListener('click', () => selectRoute(route.id)); list.append(card);
    });
  }
  function renderAlerts() {
    const list = $('alerts-list'); list.replaceChildren();
    $('alert-count').textContent = state.incidents.length;
    if (!state.incidents.length) list.append(node('p', 'Todo en orden. No hay incidencias pendientes en tus rutas.', 'empty'));
    state.incidents.forEach(inc => {
      const card = node('article', undefined, 'alert-card ' + inc.severity);
      card.append(node('h3', inc.type), node('p', inc.route + ' · Prioridad ' + inc.severity), node('time', date(inc.at)));
      list.append(card);
    });
    const fresh = state.incidents.filter(i => !seen.has(i.id));
    // Do not replay old incidents at every login. Push handles notifications in the background.
    if (initialized && fresh.length) {
      message(fresh[0].type + ' en ' + fresh[0].route + '. Consulta la sección Avisos.');
    }
    seen = new Set(state.incidents.map(i => i.id)); initialized = true;
  }
  async function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const previous = selected;
      state = await api('state');
      if (!state.routes.some(r => r.id === selected)) { selected = state.routes[0]?.id ?? null; viewingTrack = false; }
      $('greeting').textContent = 'HOLA, ' + state.user.toLocaleUpperCase('es');
      $('connection').textContent = 'Actualizado cada 5 s'; $('signal').classList.add('online');
      $('updated').textContent = 'Última consulta · ' + date(state.server_time);
      renderRoutes(); renderAlerts();
      // Authorization changes also invalidate a track that is currently displayed.
      if (!viewingTrack) drawMap(previous !== selected);
      if (!state.push_key) $('push-status').textContent = 'Los avisos están disponibles aquí. El administrador aún debe configurar las notificaciones push.';
    } catch (error) {
      $('connection').textContent = 'Sin conexión · reintentando'; $('signal').classList.remove('online');
      // Avoid presenting stale positions as current after a failed request.
      if (layers) layers.clearLayers();
      $('vehicle-info').textContent = 'Sin conexión. No se pueden mostrar posiciones actualizadas.';
      message(error.message);
    } finally { busy = false; }
  }
  async function loadHistory(reset = false) {
    if (historyBusy) return;
    historyBusy = true; $('more').disabled = true;
    if (reset) { historyOffset = 0; $('history-list').replaceChildren(); }
    try {
      const result = await api('history?offset=' + historyOffset);
      if (!historyOffset && !result.items.length) $('history-list').append(node('p', 'Todavía no hay recorridos registrados en tus rutas.', 'empty'));
      result.items.forEach(trip => {
        const card = node('button', undefined, 'history-card');
        card.append(node('small', date(trip.date)), node('strong', trip.route), node('small', trip.vehicle + ' · ' + trip.distance.toFixed(1) + ' km'), node('small', trip.incidents + ' incidencias registradas'), node('span', labels[trip.status] || trip.status, 'badge'));
        card.addEventListener('click', async () => {
          card.disabled = true;
          try {
            const track = await api('history/' + trip.id);
            selected = trip.route_id; viewingTrack = true;
            showTab('live'); drawMap(true, track); $('map').scrollIntoView({behavior: 'smooth', block: 'center'});
          } catch (error) { message(error.message); } finally { card.disabled = false; }
        });
        $('history-list').append(card);
      });
      historyOffset += result.items.length; $('more').hidden = !result.more;
    } catch (error) { message(error.message); } finally { historyBusy = false; $('more').disabled = false; }
  }
  function showTab(name) {
    document.querySelectorAll('.tab-content').forEach(el => { el.hidden = el.id !== name; });
    document.querySelectorAll('[data-tab]').forEach(el => {
      el.classList.toggle('active', el.dataset.tab === name);
      el.setAttribute('aria-selected', String(el.dataset.tab === name));
    });
    if (name === 'history') loadHistory(true);
    if (name === 'live' && map) setTimeout(() => map.invalidateSize(), 20);
  }
  async function storeSubscription(subscription, remove = false) {
    const body = new URLSearchParams({csrf_token: document.querySelector('meta[name="csrf-token"]').content,
      subscription: JSON.stringify(subscription.toJSON())});
    if (remove) body.set('remove', '1');
    return api('push', {method: 'POST', body});
  }
  function decodeKey(value) {
    const raw = atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4));
    return Uint8Array.from(raw, char => char.charCodeAt(0));
  }
  $('notifications').addEventListener('click', async () => {
    const button = $('notifications'); button.disabled = true;
    try {
      if (!window.isSecureContext || !('PushManager' in window) || !('Notification' in window)) throw new Error('Este navegador necesita HTTPS y soporte Web Push. En iPhone instala primero la app en la pantalla de inicio.');
      if (!state?.push_key) throw new Error('El administrador debe configurar Web Push antes de activar las notificaciones.');
      // The permission prompt is initiated directly by this button click.
      if (await Notification.requestPermission() !== 'granted') throw new Error('Permiso no concedido. Puedes cambiarlo en los ajustes del navegador.');
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription() || await registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: decodeKey(state.push_key)});
      await storeSubscription(subscription);
      $('push-status').textContent = 'Notificaciones activadas en este dispositivo.';
      $('disable-notifications').hidden = false; message('Notificaciones activadas para tus rutas asignadas.');
    } catch (error) { message(error.message); } finally { button.disabled = false; }
  });
  $('disable-notifications').addEventListener('click', async () => {
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) { await storeSubscription(subscription, true); await subscription.unsubscribe(); }
      $('disable-notifications').hidden = true; $('push-status').textContent = 'Notificaciones desactivadas en este dispositivo.';
    } catch (error) { message(error.message); }
  });
  $('logout').addEventListener('click', async event => {
    event.preventDefault();
    try {
      if (sw) {
        const subscription = await sw.pushManager.getSubscription();
        if (subscription) { await storeSubscription(subscription, true); await subscription.unsubscribe(); }
      }
      location.assign('/web/session/logout?redirect=/web/login');
    } catch (_) { message('No se pudo desactivar este dispositivo. Reintenta salir cuando recuperes la conexión.'); }
  });
  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => showTab(button.dataset.tab)));
  $('center').addEventListener('click', () => { viewingTrack = false; drawMap(true); });
  $('history-refresh').addEventListener('click', () => loadHistory(true));
  $('more').addEventListener('click', () => loadHistory());
  window.addEventListener('beforeinstallprompt', event => { event.preventDefault(); installPrompt = event; $('install').hidden = false; });
  $('install').addEventListener('click', async () => {
    if (installPrompt) { await installPrompt.prompt(); installPrompt = null; $('install').hidden = true; }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  window.addEventListener('online', refresh);
  if ('serviceWorker' in navigator && window.isSecureContext) {
    navigator.serviceWorker.register('/flota/sw.js', {scope: '/flota/'}).then(async registration => {
      sw = registration;
      if ('PushManager' in window) {
        const subscription = await registration.pushManager.getSubscription();
        // A shared browser must explicitly opt in again after changing accounts.
        $('disable-notifications').hidden = !subscription;
      }
    }).catch(() => message('No se pudo preparar la instalación de la app. Las rutas siguen disponibles en el navegador.'));
  }
  if (location.hash === '#alerts') showTab('alerts');
  refresh(); setInterval(refresh, 5000);
})();
