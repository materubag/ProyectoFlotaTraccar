/* Vista previa del trazado: nada se guarda hasta pulsar "Guardar propuesta". */
(() => {
  'use strict';
  const datos = JSON.parse(document.getElementById('datos').textContent);
  const $ = (id) => document.getElementById(id);
  let propuesta = null;
  // Paso final del asistente de rutas (se llega desde el editor de paradas).
  const asistente = new URLSearchParams(location.search).has('paso');
  const panel = '/web#menu_id=0&action=fleet_rutas.action_fleet_rutas_dashboard';

  $('titulo').textContent = datos.nombre;
  if (!datos.trazado) {
    $('estado').textContent = 'Sin trazado: se evalúa con rectas entre paradas (aproximado).';
    $('estado').className = 'aviso';
  } else if (!datos.vigente) {
    $('estado').textContent = 'Las paradas cambiaron: regenere el trazado. Mientras tanto se usan rectas.';
    $('estado').className = 'aviso';
  } else {
    $('estado').textContent = `Trazado vigente: ${datos.origen}, ${datos.distancia_km.toFixed(2)} km.` +
      (datos.referencia ? ` Referencia: ${datos.referencia}.` : '');
  }
  $('quitar').disabled = !datos.trazado;
  datos.recorridos.forEach((r) => $('recorrido').add(new Option(r.nombre, r.id)));
  if (!datos.recorridos.length) {
    $('recorrido').add(new Option('No hay recorridos con posiciones', ''));
    $('gps').disabled = true;
  }

  let mapa = null;
  let capaPropuesta = null;
  if (window.L) {
    mapa = L.map('map').setView([-1.249, -78.617], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '© OpenStreetMap'
    }).addTo(mapa);
    const rectas = datos.paradas.map((p) => p.punto);
    L.polyline(rectas, { color: '#8a93a3', weight: 3, dashArray: '6 6' }).addTo(mapa);
    if (datos.trazado) L.polyline(datos.trazado, { color: '#2f6df0', weight: 6, opacity: 0.6 }).addTo(mapa);
    datos.paradas.forEach((p, i) => {
      const texto = document.createElement('span');
      texto.textContent = `${i + 1}. ${p.nombre}`;
      L.circleMarker(p.punto, { radius: 7, color: '#714b67', fillOpacity: 0.9 }).bindPopup(texto).addTo(mapa);
    });
    const todos = rectas.concat(datos.trazado || []);
    if (todos.length) mapa.fitBounds(L.latLngBounds(todos).pad(0.15));
  } else {
    $('mensaje').textContent = 'No se pudo cargar el mapa.';
  }

  async function enviar(accion, campos = {}) {
    const respuesta = await fetch(`/fleet_rutas/trazado/${datos.id}/${accion}`, {
      method: 'POST', body: new URLSearchParams({ csrf_token: datos.csrf, ...campos })
    });
    const cuerpo = await respuesta.json().catch(() => ({}));
    if (!respuesta.ok) throw new Error(cuerpo.message || 'No se pudo completar la operación.');
    return cuerpo;
  }

  function limpiar() {
    propuesta = null;
    if (capaPropuesta) capaPropuesta.remove();
    $('guardar').disabled = $('descartar').disabled = true;
  }

  async function proponer(campos) {
    limpiar();
    $('mensaje').className = '';
    $('mensaje').textContent = 'Calculando…';
    $('osrm').disabled = $('gps').disabled = true;
    try {
      propuesta = await enviar('propuesta', campos);
      if (mapa) {
        capaPropuesta = L.polyline(propuesta.puntos, { color: '#ea580c', weight: 4 }).addTo(mapa);
        mapa.fitBounds(capaPropuesta.getBounds().pad(0.15));
      }
      let texto = `Propuesta: ${propuesta.distancia_km.toFixed(2)} km por el trazado; ` +
        `${propuesta.distancia_recta_km.toFixed(2)} km en rectas. Revise que siga las calles del bus.`;
      if (propuesta.paradas_lejanas.length) {
        texto += ' Paradas lejos del trazado: ' +
          propuesta.paradas_lejanas.map((p) => `${p.nombre} (${p.distancia_m} m)`).join(', ') + '.';
      }
      const rodeo = propuesta.distancia_km > 2 * propuesta.distancia_recta_km;
      if (rodeo) texto += ' Es más del doble que en rectas: revise si hay rodeos o paradas en la calzada contraria.';
      if (propuesta.simulado) texto += ' Proviene de datos SIMULADOS.';
      $('mensaje').textContent = texto;
      $('mensaje').className = propuesta.paradas_lejanas.length || propuesta.simulado || rodeo ? 'aviso' : '';
      $('guardar').disabled = $('descartar').disabled = false;
    } catch (error) {
      $('mensaje').textContent = error.message;
      $('mensaje').className = 'error';
    } finally {
      $('osrm').disabled = false;
      $('gps').disabled = !datos.recorridos.length;
    }
  }

  async function aplicar(accion, campos) {
    $('guardar').disabled = true;
    try {
      await enviar(accion, campos);
      if (asistente && accion === 'guardar') location.assign(panel);
      else location.reload();
    } catch (error) {
      $('mensaje').textContent = error.message;
      $('mensaje').className = 'error';
    }
  }

  $('osrm').addEventListener('click', () => proponer({ origen: 'osrm' }));
  $('gps').addEventListener('click', () => proponer({ origen: 'gps', recorrido_id: $('recorrido').value }));
  $('descartar').addEventListener('click', () => { limpiar(); $('mensaje').textContent = ''; });
  $('guardar').addEventListener('click', () => aplicar('guardar', {
    origen: propuesta.origen, puntos: JSON.stringify(propuesta.puntos),
    recorrido_id: propuesta.recorrido_id || ''
  }));
  $('quitar').addEventListener('click', () => {
    if (window.confirm('¿Quitar el trazado guardado de esta ruta?')) aplicar('quitar', {});
  });

  if (asistente) {
    $('paso').hidden = $('navegacion').hidden = false;
    $('quitar').hidden = true;
    $('guardar').textContent = 'Guardar trazado y finalizar';
    $('volver').addEventListener('click', () => location.assign(`/fleet_rutas/rutas/nueva?route_id=${datos.id}`));
    $('sinTrazado').addEventListener('click', () => location.assign(panel));
    if (datos.vigente) {
      $('sinTrazado').textContent = 'Finalizar con el trazado actual';
    } else {
      proponer({ origen: 'osrm' });
    }
  }
})();
