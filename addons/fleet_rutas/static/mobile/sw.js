/* Only public static assets are cached. Never store sessions, GPS or passenger data. */
const CACHE = 'fleet-mobile-static-v1';
const ROOT = '/fleet_rutas/static/mobile/';
const ASSETS = ['app.css', 'app.js', 'icon.svg', 'icon-192.png', 'icon-512.png', 'offline.html'].map(f => ROOT + f);
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('fleet-mobile-static-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== 'GET') return;
  if (event.request.mode === 'navigate' && url.pathname.startsWith('/flota/')) {
    event.respondWith(fetch(event.request).catch(() => caches.match(ROOT + 'offline.html')));
  } else if (ASSETS.includes(url.pathname)) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
  }
});
self.addEventListener('push', event => {
  let data = {};
  try { data = event.data.json(); } catch (_) { /* Show a generic notice for malformed messages. */ }
  event.waitUntil(self.registration.showNotification(data.title || 'Aviso de Mi Ruta', {
    body: data.body || 'Hay una novedad en tu ruta. Abre la aplicación para consultarla.',
    icon: ROOT + 'icon-192.png', badge: ROOT + 'icon-192.png',
    tag: data.tag || 'fleet-route', data: {url: '/flota/app#alerts'}
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(async clients => {
    const existing = clients.find(client => new URL(client.url).pathname === '/flota/app');
    if (existing) { await existing.navigate('/flota/app#alerts'); return existing.focus(); }
    return self.clients.openWindow('/flota/app#alerts');
  }));
});
