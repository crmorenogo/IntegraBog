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

// --- estado de simulación what‑if ---

let simulacionActiva = false;
let simulacionDatos = null; // { estacion_origen, estacion_destino, nombre_origen, ... }

const elBannerSimulacion = document.getElementById('banner-simulacion');
const elBannerNombres = document.getElementById('banner-nombres');
const elBtnRestaurar = document.getElementById('btn-restaurar');

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

async function enviarJSON(url, body) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
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

// --- Dibujar un resultado de sugerencia ---

function dibujarSugerencia(r) {
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
      color: '#FFD100',
      weight: esMejorNueva ? 5 : 3,
      opacity: esMejorNueva ? 1 : 0.65,
    }
  )
    .bindTooltip(`Ruta propuesta: ${r.tiempo_nueva_ruta_min} min${esMejorNueva ? ' (mejor opción)' : ''}`)
    .addTo(capaResultados);

  for (const [lon, lat] of r.estaciones_intermedias_lonlat) {
    L.circleMarker([lat, lon], {
      radius: 6,
      color: '#FFD100',
      fillColor: '#1A1A1A',
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
    ${r.simulacion_activa ? '<div class="nota-simulacion">Resultado con red simulada</div>' : ''}
    <button class="btn-simular activado" style="display:none" disabled>Activado</button>
    <button class="btn-simular">Activar simulación</button>
  `;

  // Configurar botones de activación
  const [btnActivado, btnActivar] = div.querySelectorAll('.btn-simular');
  const estaActivado = simulacionActiva
    && simulacionDatos
    && simulacionDatos.estacion_origen === r.estacion_origen
    && simulacionDatos.estacion_destino === r.estacion_destino;

  if (estaActivado) {
    btnActivado.style.display = 'block';
    btnActivar.style.display = 'none';
  }

  btnActivar.addEventListener('click', () => activarSimulacion(r));

  return div;
}

// --- activación / desactivación de simulación what‑if ---

function mostrarBannerSimulacion(datos) {
  elBannerNombres.textContent = `${datos.nombre_origen} ↔ ${datos.nombre_destino} (${datos.tiempo_nueva_ruta_min} min)`;
  elBannerSimulacion.classList.remove('oculto');
}

function ocultarBannerSimulacion() {
  elBannerSimulacion.classList.add('oculto');
}

async function activarSimulacion(r) {
  mostrarEstado('Activando simulación...');
  try {
    const datos = await enviarJSON('/api/activar-conexion', {
      estacion_origen: r.estacion_origen,
      estacion_destino: r.estacion_destino,
      nombre_origen: r.nombre_origen,
      nombre_destino: r.nombre_destino,
      tiempo_nueva_ruta_min: r.tiempo_nueva_ruta_min,
      geometria_lonlat: r.geometria_lonlat,
      estaciones_intermedias_lonlat: r.estaciones_intermedias_lonlat,
    });

    simulacionActiva = datos.activa;
    simulacionDatos = {
      estacion_origen: r.estacion_origen,
      estacion_destino: r.estacion_destino,
      nombre_origen: r.nombre_origen,
      nombre_destino: r.nombre_destino,
      tiempo_nueva_ruta_min: r.tiempo_nueva_ruta_min,
    };

    mostrarBannerSimulacion(simulacionDatos);

    // Re-dibujar las tarjetas para que el botón activado se muestre
    const tarjetas = elResultadoContenido.querySelectorAll('.tarjeta-resultado');
    for (const tarjeta of tarjetas) {
      const botones = tarjeta.querySelectorAll('.btn-simular');
      if (botones.length === 2) {
        const [btnOk, btnAct] = botones;
        const titulo = tarjeta.querySelector('.titulo');
        const estaPar = titulo && titulo.textContent.includes(r.nombre_origen) && titulo.textContent.includes(r.nombre_destino);
        if (estaPar) {
          btnOk.style.display = 'block';
          btnAct.style.display = 'none';
        }
      }
    }

    mostrarEstado('Simulación activa. El formulario «Sugerir troncal» ahora opera sobre la red aumentada.');
  } catch (err) {
    mostrarEstado(err.message, true);
  }
}

async function desactivarSimulacion() {
  mostrarEstado('Restaurando red original...');
  try {
    await enviarJSON('/api/desactivar-conexion', {});
    simulacionActiva = false;
    simulacionDatos = null;
    ocultarBannerSimulacion();
    mostrarEstado('Red original restaurada.');
  } catch (err) {
    mostrarEstado(err.message, true);
  }
}

elBtnRestaurar.addEventListener('click', desactivarSimulacion);

// --- consulta inicial: ¿hay simulación activa en el servidor? ---

async function consultarSimulacionActiva() {
  try {
    const datos = await obtenerJSON('/api/conexion-activa');
    if (datos.activa) {
      simulacionActiva = true;
      simulacionDatos = {
        estacion_origen: datos.estacion_origen,
        estacion_destino: datos.estacion_destino,
        nombre_origen: datos.nombre_origen,
        nombre_destino: datos.nombre_destino,
        tiempo_nueva_ruta_min: datos.tiempo_nueva_ruta_min,
      };
      mostrarBannerSimulacion(simulacionDatos);
    }
  } catch {
    // si el endpoint falla (ej. servidor caído), ignoramos silenciosamente
  }
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

    if (r.simulacion_activa && simulacionDatos) {
      const nota = document.createElement('div');
      nota.className = 'nota-simulacion';
      nota.textContent = `Red simulada (${simulacionDatos.nombre_origen} ↔ ${simulacionDatos.nombre_destino})`;
      elResultadoContenido.appendChild(nota);
    }

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

    // Guía de simulación — una sola vez
    if (!window._guiaSimulacionMostrada) {
      window._guiaSimulacionMostrada = true;
      const guia = document.createElement('div');
      guia.className = 'nota-simulacion';
      guia.style.padding = '6px 0';
      guia.textContent = 'Usa «Activar simulación» en cualquier par para evaluar su impacto en otras rutas.';
      elResultadoContenido.appendChild(guia);
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
    await consultarSimulacionActiva();
  } catch (err) {
    mostrarEstado(`Error cargando datos iniciales: ${err.message}`, true);
  }
})();
