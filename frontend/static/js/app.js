// IntegraBog - frontend minimo (sin build step, solo fetch + Leaflet)
// Todas las llamadas van a la misma API que sirve este archivo, por eso
// las URLs son relativas ('/api/...').

const mapa = L.map('mapa').setView([4.65, -74.1], 11); // Bogota aprox.

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap',
  maxZoom: 19,
}).addTo(mapa);

// Orden de las capas = orden de dibujo: el trazado oficial queda al fondo,
// las estaciones y los resultados encima.
const capaTrazado = L.layerGroup().addTo(mapa);
// Costuras y cruces: conexiones que infiere el modelo, no troncales reales.
// Ocultas por defecto; se muestran con el interruptor del panel.
const capaConexionesModelo = L.layerGroup();
// featureGroup (y no layerGroup) para poder devolverlas al frente con
// bringToFront() cuando se encienden las conexiones del modelo.
const capaEstaciones = L.featureGroup().addTo(mapa);
const capaResultados = L.featureGroup().addTo(mapa);

const COLOR_TRAZADO = '#475569';
const COLOR_CONEXION_MODELO = '#f97316';

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
    // value = ID del nodo, no el nombre: hay nombres repetidos en los datos
    // oficiales ("Temporal AV. Jiménez - Inter Eléctricas" son dos estaciones)
    // y la API no puede saber cuál de las dos se eligió. La etiqueta trae la
    // troncal entre paréntesis justo en esos casos.
    const opcionA = document.createElement('option');
    opcionA.value = est.id;
    opcionA.textContent = est.etiqueta;
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
      .bindTooltip(est.troncal ? `${est.etiqueta} · ${est.troncal}` : est.etiqueta)
      .addTo(capaEstaciones);
  }

  if (estaciones.length > 1) {
    elDestino.selectedIndex = 1;
  }

  mostrarEstado(`${estaciones.length} estaciones cargadas.`);
}

// Mapa base: el trazado oficial de Datos Abiertos, tal como viene. Antes se
// dibujaban las aristas del grafo como rectas entre estaciones, que cortaban
// las curvas y mostraban costuras y cruces como si fueran troncales.
async function cargarTrazado() {
  const troncales = await obtenerJSON('/api/trazado');
  for (const t of troncales) {
    for (const linea of t.lineas_lonlat) {
      L.polyline(
        linea.map(([lon, lat]) => [lat, lon]),
        { color: COLOR_TRAZADO, weight: 3, opacity: 0.75 }
      )
        .bindTooltip(t.nom_tronc || t.nom_traz || t.id_trazado, { sticky: true })
        .addTo(capaTrazado);
    }
  }
}

// Costuras y cruces, cada uno con su recorrido por el trazado. Se dibujan
// punteados y en otro color para que nunca se confundan con una troncal.
async function cargarConexionesModelo() {
  const aristas = await obtenerJSON('/api/red-actual?tipo=costura&tipo=cruce');
  for (const a of aristas) {
    const nombreTipo = a.tipo === 'cruce' ? 'Cruce entre troncales' : 'Costura del trazado';
    L.polyline(
      a.geometria_lonlat.map(([lon, lat]) => [lat, lon]),
      { color: COLOR_CONEXION_MODELO, weight: 3, opacity: 0.9, dashArray: '4 6' }
    )
      .bindTooltip(`${nombreTipo} (inferida): ${a.origen} ↔ ${a.destino}`, { sticky: true })
      .addTo(capaConexionesModelo);
  }
  return aristas.length;
}

document.getElementById('ver-conexiones').addEventListener('change', (evento) => {
  if (evento.target.checked) {
    capaConexionesModelo.addTo(mapa);
    capaResultados.bringToFront();
    capaEstaciones.bringToFront();
  } else {
    mapa.removeLayer(capaConexionesModelo);
  }
});

// --- Dibujar un resultado de sugerencia ---

// " (incluye 2 transbordos de 5 min)": el tiempo actual ya los trae sumados, con el mismo
// costo por transbordo que usan las métricas de la red (config.TRANSBORDO_MIN).
function textoTransbordos(r) {
  const n = r.transbordos_actuales;
  if (!n) return '';
  return ` (incluye ${n} transbordo${n === 1 ? '' : 's'} de ${r.transbordo_min} min)`;
}

function dibujarSugerencia(r) {
  if (r.geometria_actual_lonlat) {
    L.polyline(
      r.geometria_actual_lonlat.map(([lon, lat]) => [lat, lon]),
      { color: '#facc15', weight: 3, dashArray: '6 6' }
    )
      .bindTooltip(`Ruta actual: ${r.tiempo_actual_min} min${textoTransbordos(r)}`)
      .addTo(capaResultados);
  }

  L.polyline(
    r.geometria_lonlat.map(([lon, lat]) => [lat, lon]),
    { color: '#22c55e', weight: 4 }
  )
    .bindTooltip(`Ruta nueva propuesta: ${r.tiempo_nueva_ruta_min} min`)
    .addTo(capaResultados);

  for (const [lon, lat] of r.estaciones_intermedias_lonlat) {
    L.circleMarker([lat, lon], {
      radius: 5,
      color: '#22c55e',
      fillColor: '#0f172a',
      fillOpacity: 1,
      weight: 2,
    }).addTo(capaResultados);
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
    <div>Tiempo actual: ${r.tiempo_actual_min ?? '—'} min${textoTransbordos(r)}</div>
    <div>Tiempo ruta nueva: ${r.tiempo_nueva_ruta_min} min</div>
    <div>${lineaAhorro}</div>
    ${r.distancia_geometrica_m ? `<div>Distancia en línea recta: ${r.distancia_geometrica_m} m</div>` : ''}
    ${r.factor_rodeo ? `<div>Por la red troncal: ${r.factor_rodeo}× la línea recta</div>` : ''}
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
    await cargarTrazado();
    const n = await cargarConexionesModelo();
    document.getElementById('n-conexiones').textContent = `(${n})`;
  } catch (err) {
    mostrarEstado(`Error cargando datos iniciales: ${err.message}`, true);
  }
})();
