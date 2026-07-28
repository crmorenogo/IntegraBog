const mapa = L.map('mapa').setView([4.65, -74.1], 11);

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
      color: '#DA291C',
      fillColor: '#DA291C',
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
      { color: '#DA291C', weight: 2, opacity: 0.55 }
    ).addTo(capaRedActual);
  }
}

const COLORES_RUTAS = [
  '#FFD100',
  '#3B82F6',
  '#22C55E',
  '#A855F7',
  '#F97316',
  '#EC4899',
  '#06B6D4',
  '#84CC16',
];

let _indiceColorGlobal = 0;

function siguienteColorRuta() {
  const c = COLORES_RUTAS[_indiceColorGlobal % COLORES_RUTAS.length];
  _indiceColorGlobal++;
  return c;
}

function resetearIndiceColor() {
  _indiceColorGlobal = 0;
}

function dibujarSugerencia(r, colorRuta = '#FFD100') {
  if (r.geometria_actual_lonlat) {
    const esMejorActual = r.recomendacion === 'ruta_actual';
    L.polyline(
      r.geometria_actual_lonlat.map(([lon, lat]) => [lat, lon]),
      {
        color: '#DA291C',
        weight: esMejorActual ? 5 : 2,
        dashArray: esMejorActual ? null : '8 6',
        opacity: esMejorActual ? 1 : 0.5,
      }
    )
      .bindTooltip(`Red actual: ${r.tiempo_actual_min} min${esMejorActual ? ' (mejor opción)' : ''}`)
      .addTo(capaResultados);
  }

  const esMejorNueva = r.recomendacion === 'ruta_nueva';
  L.polyline(
    r.geometria_lonlat.map(([lon, lat]) => [lat, lon]),
    {
      color: colorRuta,
      weight: esMejorNueva ? 5 : 3,
      opacity: esMejorNueva ? 1 : 0.65,
    }
  )
    .bindTooltip(`Ruta propuesta: ${r.tiempo_nueva_ruta_min} min${esMejorNueva ? ' (mejor opción)' : ''}`)
    .addTo(capaResultados);

  for (const [lon, lat] of r.estaciones_intermedias_lonlat) {
    L.circleMarker([lat, lon], {
      radius: 6,
      color: colorRuta,
      fillColor: '#1A1A1A',
      fillOpacity: 1,
      weight: 2,
    })
      .bindTooltip('Parada sugerida')
      .addTo(capaResultados);
  }
}

function tarjetaResultado(r, colorBorde = '#DA291C') {
  const div = document.createElement('div');
  div.className = 'tarjeta-resultado';
  div.style.borderLeftColor = colorBorde;

  let lineaAhorro;
  let recomendacionHTML = '';

  if (r.recomendacion === 'ruta_actual') {
    recomendacionHTML = '<div class="recomendacion actual">La red actual ya es la mejor opción</div>';
  } else if (r.recomendacion === 'ruta_nueva') {
    recomendacionHTML = '<div class="recomendacion nueva">Una troncal nueva reduciría los tiempos</div>';
  } else {
    recomendacionHTML = '<div class="recomendacion sin-conexion">Sin conexión troncal directa</div>';
  }

  if (r.ahorro_min === null || r.ahorro_min === undefined) {
    lineaAhorro = `<span class="ahorro-nulo">Sin conexión troncal directa hoy</span>`;
  } else if (r.ahorro_min > 0) {
    lineaAhorro = `Ahorro estimado: <span class="ahorro-positivo">${r.ahorro_min} min</span>`;
  } else {
    lineaAhorro = `Ahorro estimado: ${r.ahorro_min} min (la ruta actual es más rápida)`;
  }

  div.innerHTML = `
    <div class="titulo">${r.nombre_origen} &harr; ${r.nombre_destino}</div>
    ${recomendacionHTML}
    <div>Tiempo actual: ${r.tiempo_actual_min ?? '—'} min</div>
    <div>Tiempo ruta nueva: ${r.tiempo_nueva_ruta_min} min</div>
    <div>${lineaAhorro}</div>
    ${r.distancia_geometrica_m ? `<div>Distancia en línea recta: ${r.distancia_geometrica_m} m</div>` : ''}
  `;
  return div;
}

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
    resetearIndiceColor();
    const colorRuta = siguienteColorRuta();
    dibujarSugerencia(r, colorRuta);

    elResultado.classList.remove('oculto');
    elResultadoContenido.innerHTML = '';
    elResultadoContenido.appendChild(tarjetaResultado(r, colorRuta));

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

    resetearIndiceColor();
    const todosLosPuntos = [];
    for (const r of resultados) {
      const colorRuta = siguienteColorRuta();
      dibujarSugerencia(r, colorRuta);
      elResultadoContenido.appendChild(tarjetaResultado(r, colorRuta));
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
