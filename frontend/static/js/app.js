// IntegraBog - frontend minimo (sin build step, solo fetch + Leaflet)
// Todas las llamadas van a la misma API que sirve este archivo, por eso
// las URLs son relativas ('/api/...').

const mapa = L.map('mapa').setView([4.65, -74.1], 11); // Bogota aprox.

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap',
  maxZoom: 19,
}).addTo(mapa);

const capaEstaciones = L.layerGroup().addTo(mapa);
const capaRedActual = L.layerGroup().addTo(mapa);
const capaResultados = L.layerGroup().addTo(mapa);

const elEstado = document.getElementById('estado');
const elOrigen = document.getElementById('origen');
const elDestino = document.getElementById('destino');
const elResultado = document.getElementById('resultado');
const elResultadoContenido = document.getElementById('resultado-contenido');

function mostrarEstado(mensaje, esError = false) {
  elEstado.textContent = mensaje;
  elEstado.classList.toggle('error', esError);
}

async function obtenerJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    const cuerpo = await resp.json().catch(() => ({}));
    throw new Error(cuerpo.detail || `Error ${resp.status} al llamar ${url}`);
  }
  return resp.json();
}

// --- Carga inicial: estaciones + red actual ---

async function cargarEstaciones() {
  mostrarEstado('Cargando estaciones...');
  const estaciones = await obtenerJSON('/api/estaciones');

  for (const est of estaciones) {
    const opcionA = document.createElement('option');
    opcionA.value = est.nombre;
    opcionA.textContent = est.nombre;
    elOrigen.appendChild(opcionA);

    const opcionB = opcionA.cloneNode(true);
    elDestino.appendChild(opcionB);

    L.circleMarker([est.lat, est.lon], {
      radius: 4,
      color: '#38bdf8',
      fillColor: '#38bdf8',
      fillOpacity: 0.9,
      weight: 1,
    })
      .bindTooltip(est.nombre)
      .addTo(capaEstaciones);
  }

  if (estaciones.length > 1) {
    elDestino.selectedIndex = 1;
  }

  mostrarEstado(`${estaciones.length} estaciones cargadas.`);
}

async function cargarRedActual() {
  const aristas = await obtenerJSON('/api/red-actual');
  for (const a of aristas) {
    L.polyline(
      [
        [a.origen_lat, a.origen_lon],
        [a.destino_lat, a.destino_lon],
      ],
      { color: '#475569', weight: 2, opacity: 0.7 }
    ).addTo(capaRedActual);
  }
}

// --- Dibujar un resultado de sugerencia ---

function dibujarSugerencia(r) {
  if (r.geometria_actual_lonlat) {
    L.polyline(
      r.geometria_actual_lonlat.map(([lon, lat]) => [lat, lon]),
      { color: '#facc15', weight: 3, dashArray: '6 6' }
    )
      .bindTooltip(`Ruta actual: ${r.tiempo_actual_min} min`)
      .addTo(capaResultados);
  }

  L.polyline(
    r.geometria_lonlat.map(([lon, lat]) => [lat, lon]),
    { color: '#3b82f6', weight: 4, opacity: 0.85 }
  )
    .bindTooltip(`Ruta nueva propuesta: ${r.tiempo_nueva_ruta_min} min`)
    .addTo(capaResultados);

  for (const [lon, lat] of r.estaciones_intermedias_lonlat) {
    L.circleMarker([lat, lon], {
      radius: 7,
      color: '#ca8a04',
      fillColor: '#fef08a',
      fillOpacity: 1,
      weight: 2,
    })
      .bindTooltip('Parada sugerida')
      .addTo(capaResultados);
  }
}

function tarjetaResultado(r) {
  const div = document.createElement('div');
  div.className = 'tarjeta-resultado';

  let lineaAhorro;
  if (r.ahorro_min === null || r.ahorro_min === undefined) {
    lineaAhorro = `<span class="ahorro-nulo">Sin conexión troncal directa hoy</span>`;
  } else if (r.ahorro_min > 0) {
    lineaAhorro = `Ahorro estimado: <span class="ahorro-positivo">${r.ahorro_min} min</span>`;
  } else {
    lineaAhorro = `Ahorro estimado: ${r.ahorro_min} min`;
  }

  div.innerHTML = `
    <div class="titulo">${r.nombre_origen} &harr; ${r.nombre_destino}</div>
    <div>Tiempo actual: ${r.tiempo_actual_min ?? '—'} min</div>
    <div>Tiempo ruta nueva: ${r.tiempo_nueva_ruta_min} min</div>
    <div>${lineaAhorro}</div>
    ${r.distancia_geometrica_m ? `<div>Distancia en línea recta: ${r.distancia_geometrica_m} m</div>` : ''}
  `;
  return div;
}

// --- Acciones de los botones ---

document.getElementById('btn-sugerir').addEventListener('click', async () => {
  const origen = elOrigen.value;
  const destino = elDestino.value;
  if (!origen || !destino || origen === destino) {
    mostrarEstado('Elige dos estaciones distintas.', true);
    return;
  }

  capaResultados.clearLayers();
  mostrarEstado('Calculando sugerencia...');
  try {
    const r = await obtenerJSON(
      `/api/sugerir?origen=${encodeURIComponent(origen)}&destino=${encodeURIComponent(destino)}`
    );
    dibujarSugerencia(r);

    elResultado.classList.remove('oculto');
    elResultadoContenido.innerHTML = '';
    elResultadoContenido.appendChild(tarjetaResultado(r));

    const bounds = L.latLngBounds(r.geometria_lonlat.map(([lon, lat]) => [lat, lon]));
    mapa.fitBounds(bounds, { padding: [30, 30] });

    mostrarEstado('Listo.');
  } catch (err) {
    mostrarEstado(err.message, true);
  }
});

document.getElementById('btn-pares').addEventListener('click', async () => {
  const topN = document.getElementById('top-n').value || 5;

  capaResultados.clearLayers();
  mostrarEstado('Buscando pares críticos (puede tardar unos segundos)...');
  try {
    const resultados = await obtenerJSON(`/api/pares-criticos?top_n=${topN}`);

    elResultado.classList.remove('oculto');
    elResultadoContenido.innerHTML = '';

    const todosLosPuntos = [];
    for (const r of resultados) {
      dibujarSugerencia(r);
      elResultadoContenido.appendChild(tarjetaResultado(r));
      todosLosPuntos.push(...r.geometria_lonlat.map(([lon, lat]) => [lat, lon]));
    }

    if (todosLosPuntos.length) {
      mapa.fitBounds(L.latLngBounds(todosLosPuntos), { padding: [30, 30] });
    }

    mostrarEstado(`${resultados.length} pares críticos encontrados.`);
  } catch (err) {
    mostrarEstado(err.message, true);
  }
});

// --- Arranque ---

(async function iniciar() {
  try {
    await cargarEstaciones();
    await cargarRedActual();
  } catch (err) {
    mostrarEstado(`Error cargando datos iniciales: ${err.message}`, true);
  }
})();
