// IntegraBog · centro de mando de la red troncal (MapLibre GL JS, sin build step).
// Todas las llamadas van a la misma API que sirve este archivo, por eso las
// URLs son relativas ('/api/...'). Respecto a la versión con Leaflet solo
// cambia la presentación: las URLs, los nombres y la forma de los datos que
// van y vienen del servidor son los mismos.

// --- Mapa base ---------------------------------------------------------------

// Dark Matter de CARTO, en vectores: la ciudad queda apagada y los datos se
// llevan la atención. Si no carga (sin internet, o CARTO no responde), el mapa
// sigue con un fondo oscuro liso: las capas de datos no dependen de él.
const ESTILO_OSCURO = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
const ESTILO_RESPALDO = {
  version: 8,
  sources: {},
  layers: [{ id: 'fondo', type: 'background', paint: { 'background-color': '#060708' } }],
};
const ESPERA_ESTILO_MS = 8000;

const reducirMovimiento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const mapa = new maplibregl.Map({
  container: 'mapa',
  style: ESTILO_OSCURO,
  center: [-74.1, 4.65], // Bogotá aprox.
  zoom: 10.2,
  pitch: 0,
  maxPitch: 70,
  attributionControl: { compact: true },
});

// --- Controles de navegación -------------------------------------------------------

// Las dos vistas entre las que alterna el botón de la brújula. La de centro de mando es
// la misma de la entrada de cámara (entradaDeCamara).
const VISTA_CENITAL = { pitch: 0, bearing: 0 };
const VISTA_CENTRO_DE_MANDO = { pitch: 52, bearing: -16 };

// Diferencia entre dos rumbos en grados, dentro de [-180, 180): de 170° a -170° hay 20°.
function diferenciaDeRumbo(a, b) {
  return ((((a - b) % 360) + 540) % 360) - 180;
}

function enVistaDeCentroDeMando() {
  return Math.abs(mapa.getPitch() - VISTA_CENTRO_DE_MANDO.pitch) < 1
    && Math.abs(diferenciaDeRumbo(mapa.getBearing(), VISTA_CENTRO_DE_MANDO.bearing)) < 1;
}

// Vista hacia la que va la cámara por un clic en la brújula, mientras dura la animación.
// Cualquier fin de movimiento (la animación que termina, el usuario que arrastra) la borra.
let vistaPedida = null;
mapa.on('moveend', () => { vistaPedida = null; });

// La brújula de NavigationControl solo sabe volver a la vista cenital (resetNorthPitch):
// si el mapa ya está así, el clic no hace nada, y nunca devuelve los 52°. Aquí el clic
// alterna entre las dos vistas, y lo que hace se decide con la cámara de ese momento, no
// con una variable que quede desactualizada cuando el usuario mueve el mapa a mano: en la
// vista de centro de mando pasa a la cenital; desde cualquier otra posición (la cenital,
// o girado e inclinado con el mouse) vuelve a la de centro de mando. Un clic en plena
// animación la invierte.
function alternarVista() {
  const enCentro = vistaPedida ? vistaPedida === VISTA_CENTRO_DE_MANDO : enVistaDeCentroDeMando();
  const destino = enCentro ? VISTA_CENITAL : VISTA_CENTRO_DE_MANDO;
  mapa.easeTo({ ...destino, duration: reducirMovimiento ? 0 : 1200, easing: (t) => 1 - Math.pow(1 - t, 3) });
  // easeTo detiene la animación anterior y el moveend de esa ya borró vistaPedida; si no
  // hay animación (movimiento reducido), la cámara ya llegó y no queda nada pendiente.
  vistaPedida = mapa.isMoving() ? destino : null;
}

// Zoom y brújula con los íconos de MapLibre (y el estilo de style.css), como antes, pero
// con la brújula conectada a alternarVista.
mapa.addControl({
  onAdd() {
    this._contenedor = document.createElement('div');
    this._contenedor.className = 'maplibregl-ctrl maplibregl-ctrl-group';
    this._contenedor.addEventListener('contextmenu', (e) => e.preventDefault());
    const crearBoton = (clase, titulo, accion) => {
      const boton = document.createElement('button');
      boton.type = 'button';
      boton.className = clase;
      boton.title = titulo;
      boton.setAttribute('aria-label', titulo);
      boton.innerHTML = '<span class="maplibregl-ctrl-icon" aria-hidden="true"></span>';
      boton.addEventListener('click', accion);
      this._contenedor.appendChild(boton);
      return boton;
    };
    const acercar = crearBoton('maplibregl-ctrl-zoom-in', 'Acercar', () => mapa.zoomIn());
    const alejar = crearBoton('maplibregl-ctrl-zoom-out', 'Alejar', () => mapa.zoomOut());
    const brujula = crearBoton('maplibregl-ctrl-compass', '', alternarVista);

    // Como en MapLibre, el ícono de la brújula se inclina y gira con la cámara. Su título
    // anuncia la vista a la que lleva el clic.
    this._seguirCamara = () => {
      const pitch = mapa.getPitch();
      brujula.firstChild.style.transform =
        `scale(${1 / Math.sqrt(Math.cos((pitch * Math.PI) / 180))}) rotateX(${pitch}deg) rotateZ(${-mapa.getBearing()}deg)`;
      acercar.disabled = mapa.getZoom() >= mapa.getMaxZoom();
      alejar.disabled = mapa.getZoom() <= mapa.getMinZoom();
    };
    this._rotular = () => {
      const titulo = enVistaDeCentroDeMando() ? 'Vista cenital (2D)' : 'Vista de centro de mando (3D)';
      brujula.title = titulo;
      brujula.setAttribute('aria-label', titulo);
    };
    mapa.on('move', this._seguirCamara);
    mapa.on('moveend', this._rotular);
    this._seguirCamara();
    this._rotular();
    return this._contenedor;
  },
  onRemove() {
    mapa.off('move', this._seguirCamara);
    mapa.off('moveend', this._rotular);
    this._contenedor.remove();
  },
}, 'bottom-right');

// Las cuatro capas del mapa. Cada una es una fuente GeoJSON con varias capas
// de dibujo encima (resplandor, halo y núcleo, para el efecto neón). El orden
// en que se agregan es el orden de dibujo: el trazado oficial queda al fondo,
// las estaciones y los resultados encima.
const capaTrazado = 'ib-trazado';
// Costuras y cruces: conexiones que infiere el modelo, no troncales reales.
// Ocultas por defecto; se muestran con el interruptor del panel.
const capaConexionesModelo = 'ib-conexiones';
const capaEstaciones = 'ib-estaciones';
const capaResultados = 'ib-resultados';

// Escala de titanio: todo es gris, plata o blanco, y cada elemento se distingue por
// su luminosidad y su textura, no por el tono. De lo más tenue a lo más brillante:
// las troncales (gris plata oscuro, resplandor sutil), las conexiones del modelo
// (gris punteado), la ruta de hoy (plata media, con guiones) y la ruta propuesta
// (blanco platino, con el resplandor más intenso de la pantalla). Las estaciones son
// puntos plata con el centro blanco; el origen se marca en blanco y el destino, en
// plata clara.
const COLOR_TRAZADO = '#686e77';
const COLOR_TRAZADO_AL_PASAR = '#dfe3e8';
const COLOR_CONEXION_MODELO = '#8f969f';
const COLOR_RUTA_ACTUAL = '#c6cbd2';
const COLOR_RUTA_NUEVA = '#ffffff';
const COLOR_RUTA_NUEVA_NUCLEO = '#d2d8df'; // un punto bajo el blanco, para que se vean los pulsos de luz
const COLOR_ESTACION = '#878f99';
const COLOR_ORIGEN = '#ffffff';
const COLOR_DESTINO = '#afb5bc';

const elEstado = document.getElementById('estado');
const elOrigen = document.getElementById('origen');
const elDestino = document.getElementById('destino');
const elResultado = document.getElementById('resultado');
const elResultadoContenido = document.getElementById('resultado-contenido');

// --- Utilidades ----------------------------------------------------------------

function mostrarEstado(mensaje, esError = false) {
  elEstado.textContent = mensaje;
  elEstado.classList.toggle('error', esError);
  // Los mensajes que terminan en '...' son trabajo en curso: el indicador parpadea.
  elEstado.classList.toggle('ocupado', !esError && mensaje.endsWith('...'));
}

async function obtenerJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    const cuerpo = await resp.json().catch(() => ({}));
    throw new Error(cuerpo.detail || `Error ${resp.status} al llamar ${url}`);
  }
  return resp.json();
}

const formatoDecimal = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const formatoEntero = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 });

function minutos(valor) {
  return formatoDecimal.format(valor);
}

function escapar(texto) {
  return String(texto ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function coleccion(features) {
  return { type: 'FeatureCollection', features };
}

function linea(coordenadas, propiedades) {
  return { type: 'Feature', properties: propiedades, geometry: { type: 'LineString', coordinates: coordenadas } };
}

function punto(coordenada, propiedades) {
  return { type: 'Feature', properties: propiedades, geometry: { type: 'Point', coordinates: coordenada } };
}

function actualizarFuente(id, features) {
  const fuente = mapa.getSource(id);
  if (fuente) fuente.setData(coleccion(features));
}

// Botón ocupado mientras espera al servidor: se apaga (evita doble clic) y
// enciende su indicador de carga.
function enProceso(boton, activo) {
  boton.disabled = activo;
  boton.classList.toggle('cargando', activo);
}

// Cuenta de 0 al valor en los números de la telemetría.
function contar(elemento, valor) {
  if (!elemento) return;
  if (reducirMovimiento) {
    elemento.textContent = formatoEntero.format(valor);
    return;
  }
  const inicio = performance.now();
  const duracion = 900;
  function paso(ahora) {
    const t = Math.min(1, (ahora - inicio) / duracion);
    const suave = 1 - Math.pow(1 - t, 3);
    elemento.textContent = formatoEntero.format(Math.round(valor * suave));
    if (t < 1) requestAnimationFrame(paso);
  }
  requestAnimationFrame(paso);
}

// --- Estilo listo y capas ----------------------------------------------------------

const estiloListo = new Promise((resolver) => {
  let listo = false;
  let respaldoPedido = false;
  const usarRespaldo = () => {
    if (listo || respaldoPedido || mapa.isStyleLoaded()) return;
    respaldoPedido = true;
    mapa.setStyle(ESTILO_RESPALDO);
  };
  mapa.on('style.load', () => {
    if (listo) return;
    listo = true;
    atenuarMapaBase();
    prepararCapas();
    resolver();
  });
  mapa.on('error', usarRespaldo);
  setTimeout(usarRespaldo, ESPERA_ESTILO_MS);
});

// Apaga un poco más la ciudad: etiquetas y vías tenues sobre un fondo carbón, y el
// agua apenas más clara. Con troncales grises, una ciudad muy visible les quitaría
// el contraste.
function atenuarMapaBase() {
  for (const capa of mapa.getStyle().layers) {
    try {
      if (capa.type === 'background') {
        mapa.setPaintProperty(capa.id, 'background-color', '#060708');
      } else if (capa.type === 'symbol') {
        mapa.setPaintProperty(capa.id, 'text-opacity', 0.45);
        mapa.setPaintProperty(capa.id, 'icon-opacity', 0.3);
      } else if (capa.type === 'line') {
        mapa.setPaintProperty(capa.id, 'line-opacity', 0.55);
      } else if (capa.type === 'fill' && /water|agua/i.test(capa.id)) {
        mapa.setPaintProperty(capa.id, 'fill-color', '#0b0c0f');
      }
    } catch {
      // Una capa del estilo base que no admite la propiedad: se deja como está.
    }
  }
}

// Grosor que crece con el zoom (y opcionalmente con un factor, como el resaltado
// al pasar el puntero). 'pares' son [zoom, ancho].
function porZoom(pares, factor = null) {
  const salida = ['interpolate', ['exponential', 1.5], ['zoom']];
  for (const [zoom, valor] of pares) salida.push(zoom, factor ? ['*', valor, factor] : valor);
  return salida;
}

// Secuencia de guiones que, mostrada en orden, hace avanzar los trazos a lo largo de la línea.
const SECUENCIA_FLUJO = [
  [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0],
  [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5],
];

const EN_HOVER = ['boolean', ['feature-state', 'hover'], false];
const AL_PASAR = ['case', EN_HOVER, 1.9, 1];
// Al pasar el puntero, la troncal entera se enciende en plata clara.
const COLOR_DE_TRONCAL = ['case', EN_HOVER, COLOR_TRAZADO_AL_PASAR, ['coalesce', ['get', 'color'], COLOR_TRAZADO]];
const ESTADO_SELECCION = ['coalesce', ['feature-state', 'seleccion'], 'ninguna'];
const LINEAS_REDONDAS = { 'line-join': 'round', 'line-cap': 'round' };

function prepararCapas() {
  for (const id of [capaTrazado, capaConexionesModelo, capaResultados, capaEstaciones]) {
    mapa.addSource(id, { type: 'geojson', data: coleccion([]), generateId: true });
  }

  // Trazado oficial: un tubo gris plata por troncal (resplandor, halo, núcleo y un brillo
  // blanco muy tenue). Es el fondo de la información: no compite con los resultados.
  mapa.addLayer({
    id: 'ib-trazado-resplandor', type: 'line', source: capaTrazado, layout: LINEAS_REDONDAS,
    paint: {
      // Con la red completa en pantalla las líneas son finas: el resplandor se refuerza
      // un poco en los zooms bajos para que el brillo se note también en la vista general.
      'line-color': COLOR_DE_TRONCAL, 'line-opacity': ['interpolate', ['linear'], ['zoom'], 10, 0.22, 13, 0.1],
      'line-width': porZoom([[9, 7], [12, 14], [16, 30]], AL_PASAR),
      'line-blur': porZoom([[9, 5], [12, 10], [16, 22]]),
    },
  });
  mapa.addLayer({
    id: 'ib-trazado-halo', type: 'line', source: capaTrazado, layout: LINEAS_REDONDAS,
    paint: {
      'line-color': COLOR_DE_TRONCAL, 'line-opacity': 0.22,
      'line-width': porZoom([[9, 2.8], [12, 5], [16, 10]], AL_PASAR),
      'line-blur': porZoom([[9, 1.5], [12, 2.5], [16, 5]]),
    },
  });
  mapa.addLayer({
    id: 'ib-trazado-nucleo', type: 'line', source: capaTrazado, layout: LINEAS_REDONDAS,
    paint: {
      'line-color': COLOR_DE_TRONCAL, 'line-opacity': 0.78,
      'line-width': porZoom([[9, 1.4], [12, 2.4], [16, 4.5]], AL_PASAR),
    },
  });
  mapa.addLayer({
    id: 'ib-trazado-brillo', type: 'line', source: capaTrazado, layout: LINEAS_REDONDAS,
    paint: { 'line-color': '#ffffff', 'line-opacity': 0.06, 'line-width': porZoom([[9, 0.35], [12, 0.7], [16, 1.4]]) },
  });

  // Conexiones del modelo: puntos grises, una textura que no se confunde ni con una
  // troncal (línea continua) ni con la ruta de hoy (guiones).
  const oculta = { ...LINEAS_REDONDAS, visibility: 'none' };
  mapa.addLayer({
    id: 'ib-conexiones-resplandor', type: 'line', source: capaConexionesModelo, layout: oculta,
    paint: {
      'line-color': COLOR_CONEXION_MODELO, 'line-opacity': 0.12,
      'line-width': porZoom([[9, 6], [12, 12], [16, 22]]), 'line-blur': porZoom([[9, 4], [12, 8], [16, 14]]),
    },
  });
  mapa.addLayer({
    id: 'ib-conexiones-linea', type: 'line', source: capaConexionesModelo, layout: oculta,
    paint: {
      // guiones de largo 0 con puntas redondas: cada uno se dibuja como un punto
      'line-color': COLOR_CONEXION_MODELO, 'line-opacity': 0.95,
      'line-width': porZoom([[9, 1.8], [12, 2.6], [16, 4]]), 'line-dasharray': [0, 2],
    },
  });

  // Resultados: la ruta de hoy en plata media, con guiones; la propuesta en blanco platino,
  // el elemento más luminoso de la pantalla, con pulsos de luz que avanzan por ella.
  const deClase = (clase) => ['==', ['get', 'clase'], clase];
  mapa.addLayer({
    id: 'ib-resultados-actual-resplandor', type: 'line', source: capaResultados, filter: deClase('actual'),
    layout: LINEAS_REDONDAS,
    paint: {
      'line-color': COLOR_RUTA_ACTUAL, 'line-opacity': 0.2,
      'line-width': porZoom([[9, 6], [12, 12], [16, 22]]), 'line-blur': porZoom([[9, 4], [12, 8], [16, 14]]),
    },
  });
  mapa.addLayer({
    id: 'ib-resultados-actual', type: 'line', source: capaResultados, filter: deClase('actual'),
    layout: { 'line-join': 'round' },
    paint: {
      'line-color': COLOR_RUTA_ACTUAL, 'line-opacity': 0.95,
      'line-width': porZoom([[9, 2], [12, 3.2], [16, 5.4]]), 'line-dasharray': [2, 1.6],
    },
  });
  mapa.addLayer({
    id: 'ib-resultados-resaltado', type: 'line', source: capaResultados,
    filter: ['all', deClase('nueva'), ['==', ['get', 'indice'], -1]], layout: LINEAS_REDONDAS,
    paint: {
      'line-color': '#ffffff', 'line-opacity': 0.45,
      'line-width': porZoom([[9, 16], [12, 28], [16, 48]]), 'line-blur': porZoom([[9, 10], [12, 18], [16, 30]]),
    },
  });
  mapa.addLayer({
    id: 'ib-resultados-nueva-resplandor', type: 'line', source: capaResultados, filter: deClase('nueva'),
    layout: LINEAS_REDONDAS,
    paint: {
      'line-color': COLOR_RUTA_NUEVA, 'line-opacity': 0.62,
      'line-width': porZoom([[9, 12], [12, 24], [16, 44]]), 'line-blur': porZoom([[9, 8], [12, 16], [16, 30]]),
    },
  });
  mapa.addLayer({
    id: 'ib-resultados-nueva', type: 'line', source: capaResultados, filter: deClase('nueva'),
    layout: LINEAS_REDONDAS,
    paint: { 'line-color': COLOR_RUTA_NUEVA_NUCLEO, 'line-width': porZoom([[9, 2.8], [12, 4.8], [16, 8]]) },
  });
  mapa.addLayer({
    id: 'ib-resultados-nueva-flujo', type: 'line', source: capaResultados, filter: deClase('nueva'),
    layout: { 'line-join': 'round' },
    paint: {
      'line-color': COLOR_RUTA_NUEVA, 'line-opacity': 1,
      'line-width': porZoom([[9, 3], [12, 5], [16, 8.5]]), 'line-blur': porZoom([[9, 1.5], [12, 2.5], [16, 4]]),
      'line-dasharray': SECUENCIA_FLUJO[0],
    },
  });
  mapa.addLayer({
    id: 'ib-resultados-paradas', type: 'circle', source: capaResultados, filter: deClase('parada'),
    paint: {
      'circle-radius': porZoom([[9, 2.6], [12, 4.2], [16, 7]]), 'circle-color': '#0c0d10',
      'circle-stroke-color': COLOR_RUTA_NUEVA, 'circle-stroke-width': porZoom([[9, 1.2], [12, 1.8], [16, 2.6]]),
    },
  });

  // Estaciones: puntos plata con el centro blanco y un resplandor muy tenue. Origen y destino
  // llevan un anillo (blanco y más grueso el origen; plata clara y más fino el destino) y una
  // onda de radar del mismo color.
  mapa.addLayer({
    id: 'ib-estaciones-resplandor', type: 'circle', source: capaEstaciones,
    paint: {
      'circle-radius': porZoom([[9, 5], [12, 9], [16, 18]], ['case', ['boolean', ['feature-state', 'hover'], false], 1.7, 1]),
      'circle-color': '#d5dae0', 'circle-blur': 1, 'circle-opacity': 0.08,
    },
  });
  mapa.addLayer({
    id: 'ib-estaciones-punto', type: 'circle', source: capaEstaciones,
    paint: {
      'circle-radius': porZoom([[9, 1.4], [12, 2.4], [16, 5]], ['case', EN_HOVER, 1.7, 1]),
      'circle-color': '#f3f5f7', 'circle-stroke-color': COLOR_ESTACION,
      'circle-stroke-width': porZoom([[9, 0.7], [12, 1.2], [16, 2]]),
    },
  });
  const colorSeleccion = ['match', ESTADO_SELECCION, 'origen', COLOR_ORIGEN, 'destino', COLOR_DESTINO, 'rgba(0,0,0,0)'];
  mapa.addLayer({
    id: 'ib-estaciones-seleccion', type: 'circle', source: capaEstaciones,
    paint: {
      'circle-radius': porZoom([[9, 6], [12, 10], [16, 18]]), 'circle-color': 'rgba(0,0,0,0)',
      'circle-stroke-width': ['match', ESTADO_SELECCION, 'origen', 2.4, 'destino', 1.6, 0],
      'circle-stroke-color': colorSeleccion,
      'circle-stroke-opacity': ['match', ESTADO_SELECCION, 'ninguna', 0, 1],
    },
  });
  mapa.addLayer({
    id: 'ib-estaciones-pulso', type: 'circle', source: capaEstaciones,
    paint: {
      'circle-radius': porZoom([[9, 6], [16, 18]]), 'circle-color': 'rgba(0,0,0,0)',
      'circle-stroke-width': 1.5, 'circle-stroke-color': colorSeleccion, 'circle-stroke-opacity': 0,
    },
  });
}

// --- Animación: flujo sobre la ruta nueva y pulso de radar en origen y destino ---

let pasoFlujo = -1;
let ultimoPulso = 0;
const featuresResultados = [];
const seleccion = { origen: null, destino: null }; // id de la feature de cada estación elegida

function animar(ahora) {
  if (mapa.getLayer('ib-resultados-nueva-flujo') && featuresResultados.length) {
    const paso = Math.floor(ahora / 55) % SECUENCIA_FLUJO.length;
    if (paso !== pasoFlujo) {
      pasoFlujo = paso;
      mapa.setPaintProperty('ib-resultados-nueva-flujo', 'line-dasharray', SECUENCIA_FLUJO[paso]);
    }
  }
  if (mapa.getLayer('ib-estaciones-pulso') && (seleccion.origen !== null || seleccion.destino !== null)
      && ahora - ultimoPulso > 33) {
    ultimoPulso = ahora;
    const t = (ahora % 1800) / 1800;
    mapa.setPaintProperty('ib-estaciones-pulso', 'circle-radius', porZoom([[9, 6 + 14 * t], [16, 18 + 26 * t]]));
    mapa.setPaintProperty('ib-estaciones-pulso', 'circle-stroke-opacity',
      ['match', ESTADO_SELECCION, 'ninguna', 0, 0.9 * (1 - t)]);
  }
  requestAnimationFrame(animar);
}
if (!reducirMovimiento) requestAnimationFrame(animar);

// --- Carga inicial: estaciones + red actual ---------------------------------------

const idFeaturePorEstacion = new Map();
// Todas las coordenadas de la red (estaciones y trazado), para encuadrarla al arrancar.
const coordenadasRed = [];

async function cargarEstaciones() {
  mostrarEstado('Cargando estaciones...');
  const estaciones = await obtenerJSON('/api/estaciones');

  const features = [];
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

    // generateId numera las features en orden: así se ubica cada estación para resaltarla.
    idFeaturePorEstacion.set(est.id, features.length);
    features.push(punto([est.lon, est.lat], { id: est.id, etiqueta: est.etiqueta, troncal: est.troncal || '' }));
    coordenadasRed.push([est.lon, est.lat]);
  }

  if (estaciones.length > 1) {
    elDestino.selectedIndex = 1;
  }

  await estiloListo;
  actualizarFuente(capaEstaciones, features);
  marcarSeleccion();
  contar(document.getElementById('hud-estaciones'), estaciones.length);
  mostrarEstado(`${estaciones.length} estaciones cargadas.`);
}

// Las troncales van en una banda estrecha de grises plata, del 40 % al 50 % de
// luminosidad, con el matiz frío casi imperceptible del titanio. Los valores se
// reparten con la razón áurea: dos troncales seguidas en orden alfabético quedan en
// grises distintos, lo que ayuda a separarlas donde corren paralelas. La diferencia
// es sutil a propósito: el trazado es el fondo de la información.
function colorDeTroncal(indice) {
  const luz = 40 + 10 * ((indice * 0.6180339887) % 1);
  return `hsl(214, 7%, ${luz.toFixed(0)}%)`;
}

const idsPorTroncal = new Map();

// Mapa base: el trazado oficial de Datos Abiertos, tal como viene. Antes se
// dibujaban las aristas del grafo como rectas entre estaciones, que cortaban
// las curvas y mostraban costuras y cruces como si fueran troncales.
async function cargarTrazado() {
  const troncales = await obtenerJSON('/api/trazado');
  const nombres = [...new Set(troncales.map((t) => t.nom_tronc || t.nom_traz || t.id_trazado))].sort();
  const colores = new Map(nombres.map((n, i) => [n, colorDeTroncal(i)]));

  const features = [];
  for (const t of troncales) {
    const nombre = t.nom_tronc || t.nom_traz || t.id_trazado;
    for (const lineaTrazado of t.lineas_lonlat) {
      if (!idsPorTroncal.has(nombre)) idsPorTroncal.set(nombre, []);
      idsPorTroncal.get(nombre).push(features.length);
      features.push(linea(lineaTrazado, { nombre, color: colores.get(nombre) || COLOR_TRAZADO }));
      for (const c of lineaTrazado) coordenadasRed.push(c);
    }
  }

  await estiloListo;
  actualizarFuente(capaTrazado, features);
  contar(document.getElementById('hud-troncales'), nombres.length);
}

// Costuras y cruces, cada uno con su recorrido por el trazado. Se dibujan
// punteados y en otro color para que nunca se confundan con una troncal.
async function cargarConexionesModelo() {
  const aristas = await obtenerJSON('/api/red-actual?tipo=costura&tipo=cruce');
  const features = aristas.map((a) => {
    const nombreTipo = a.tipo === 'cruce' ? 'Cruce entre troncales' : 'Costura del trazado';
    return linea(a.geometria_lonlat, { titulo: `${nombreTipo} (inferida)`, detalle: `${a.origen} ↔ ${a.destino}` });
  });

  await estiloListo;
  actualizarFuente(capaConexionesModelo, features);
  contar(document.getElementById('hud-conexiones'), aristas.length);
  return aristas.length;
}

// Telemetría del grafo multicapa. No bloquea la carga: el servidor tarda unos
// segundos en contar las componentes de toda la malla vial.
async function cargarTelemetria() {
  try {
    const d = await obtenerJSON('/api/diagnostico');
    contar(document.getElementById('hud-nodos'), d.nodos);
    contar(document.getElementById('hud-aristas'), d.aristas);
    contar(document.getElementById('hud-componentes'), d.componentes_conexas);
    const nota = document.getElementById('hud-nota');
    if (nota) nota.textContent = `Grafo construido en ${minutos(d.segundos_construccion_grafo)} s`;
  } catch {
    const nota = document.getElementById('hud-nota');
    if (nota) nota.textContent = 'Telemetría del grafo no disponible';
  }
}

document.getElementById('ver-conexiones').addEventListener('change', (evento) => {
  const visible = evento.target.checked ? 'visible' : 'none';
  for (const id of ['ib-conexiones-resplandor', 'ib-conexiones-linea']) {
    if (mapa.getLayer(id)) mapa.setLayoutProperty(id, 'visibility', visible);
  }
});

// --- Selección de origen y destino (en la lista o con un clic en el mapa) ---------

function marcarSeleccion() {
  for (const [rol, select] of [['origen', elOrigen], ['destino', elDestino]]) {
    if (seleccion[rol] !== null) {
      mapa.setFeatureState({ source: capaEstaciones, id: seleccion[rol] }, { seleccion: null });
    }
    const id = idFeaturePorEstacion.get(select.value);
    seleccion[rol] = id ?? null;
  }
  // Si origen y destino son la misma estación, gana el origen.
  if (seleccion.destino !== null) {
    mapa.setFeatureState({ source: capaEstaciones, id: seleccion.destino }, { seleccion: 'destino' });
  }
  if (seleccion.origen !== null) {
    mapa.setFeatureState({ source: capaEstaciones, id: seleccion.origen }, { seleccion: 'origen' });
  }
}

elOrigen.addEventListener('change', marcarSeleccion);
elDestino.addEventListener('change', marcarSeleccion);

let siguienteEnMapa = 'origen';
mapa.on('click', 'ib-estaciones-resplandor', (e) => {
  const est = e.features[0].properties;
  const select = siguienteEnMapa === 'origen' ? elOrigen : elDestino;
  select.value = est.id;
  marcarSeleccion();
  mostrarEstado(siguienteEnMapa === 'origen'
    ? `Origen: ${est.etiqueta}. Ahora elige el destino.`
    : `Destino: ${est.etiqueta}. Listo para calcular.`);
  siguienteEnMapa = siguienteEnMapa === 'origen' ? 'destino' : 'origen';
});

// --- Globo de información al pasar el puntero --------------------------------------

const globo = new maplibregl.Popup({
  closeButton: false, closeOnClick: false, className: 'ib-globo', offset: 14, maxWidth: '320px',
});
// Del elemento de más arriba al de más abajo: si hay varios bajo el puntero, gana el primero.
const CAPAS_CON_GLOBO = [
  'ib-estaciones-resplandor', 'ib-resultados-paradas', 'ib-resultados-nueva-resplandor',
  'ib-resultados-actual-resplandor', 'ib-conexiones-resplandor', 'ib-trazado-halo',
];
let resaltadas = []; // [{source, id}] con hover activo

function quitarResaltado() {
  for (const f of resaltadas) mapa.setFeatureState(f, { hover: false });
  resaltadas = [];
}

function contenidoGlobo(capa, p) {
  switch (capa) {
    case 'ib-estaciones-resplandor':
      return `<strong>${escapar(p.etiqueta)}</strong>${p.troncal ? `<span>${escapar(p.troncal)}</span>` : ''}`;
    case 'ib-resultados-paradas':
      return '<strong>Parada sugerida</strong><span>Ruta nueva propuesta</span>';
    case 'ib-conexiones-resplandor':
      return `<strong>${escapar(p.titulo)}</strong><span>${escapar(p.detalle)}</span>`;
    case 'ib-trazado-halo':
      return `<strong>${escapar(p.nombre)}</strong><span>Trazado oficial</span>`;
    default:
      return `<strong>${escapar(p.titulo)}</strong>${p.detalle ? `<span>${escapar(p.detalle)}</span>` : ''}`;
  }
}

mapa.on('mousemove', (e) => {
  if (!mapa.getLayer('ib-trazado-halo')) return;
  const { x, y } = e.point;
  const capas = CAPAS_CON_GLOBO.filter((id) => mapa.getLayer(id));
  const f = mapa.queryRenderedFeatures([[x - 5, y - 5], [x + 5, y + 5]], { layers: capas })[0];
  quitarResaltado();
  if (!f) {
    globo.remove();
    mapa.getCanvas().style.cursor = '';
    return;
  }
  if (f.source === capaTrazado) {
    resaltadas = (idsPorTroncal.get(f.properties.nombre) || []).map((id) => ({ source: capaTrazado, id }));
  } else if (f.source === capaEstaciones) {
    resaltadas = [{ source: capaEstaciones, id: f.id }];
  }
  for (const r of resaltadas) mapa.setFeatureState(r, { hover: true });
  mapa.getCanvas().style.cursor = f.source === capaEstaciones ? 'pointer' : 'crosshair';
  const enPunto = f.geometry.type === 'Point';
  globo.setLngLat(enPunto ? f.geometry.coordinates : e.lngLat)
    .setHTML(contenidoGlobo(f.layer.id, f.properties))
    .addTo(mapa);
});

mapa.on('mouseout', () => {
  quitarResaltado();
  globo.remove();
});

// --- Dibujar un resultado de sugerencia ----------------------------------------------

// " (incluye 2 transbordos de 5 min)": el tiempo actual ya los trae sumados, con el mismo
// costo por transbordo que usan las métricas de la red (config.TRANSBORDO_MIN).
function textoTransbordos(r) {
  const n = r.transbordos_actuales;
  if (!n) return '';
  return ` (incluye ${n} transbordo${n === 1 ? '' : 's'} de ${r.transbordo_min} min)`;
}

function dibujarSugerencia(r, indice = 0) {
  if (r.geometria_actual_lonlat) {
    featuresResultados.push(linea(r.geometria_actual_lonlat, {
      clase: 'actual', indice,
      titulo: `Ruta actual: ${minutos(r.tiempo_actual_min)} min`, detalle: textoTransbordos(r).trim(),
    }));
  }

  featuresResultados.push(linea(r.geometria_lonlat, {
    clase: 'nueva', indice, titulo: `Ruta nueva propuesta: ${minutos(r.tiempo_nueva_ruta_min)} min`,
    detalle: `${r.nombre_origen} ↔ ${r.nombre_destino}`,
  }));

  for (const [lon, lat] of r.estaciones_intermedias_lonlat) {
    featuresResultados.push(punto([lon, lat], { clase: 'parada', indice }));
  }
  actualizarFuente(capaResultados, featuresResultados);
}

function limpiarResultados() {
  featuresResultados.length = 0;
  actualizarFuente(capaResultados, featuresResultados);
  resaltarResultado(-1);
}

// Al pasar por una tarjeta, su ruta se ilumina y las de los demás pares se atenúan
// (MapLibre anima el cambio de opacidad). [capa, propiedad, opacidad normal].
const OPACIDADES_RESULTADOS = [
  ['ib-resultados-actual-resplandor', 'line-opacity', 0.2],
  ['ib-resultados-actual', 'line-opacity', 0.95],
  ['ib-resultados-nueva-resplandor', 'line-opacity', 0.62],
  ['ib-resultados-nueva', 'line-opacity', 1],
  ['ib-resultados-nueva-flujo', 'line-opacity', 1],
  ['ib-resultados-paradas', 'circle-opacity', 1],
  ['ib-resultados-paradas', 'circle-stroke-opacity', 1],
];

function resaltarResultado(indice) {
  if (!mapa.getLayer('ib-resultados-resaltado')) return;
  mapa.setFilter('ib-resultados-resaltado', ['all', ['==', ['get', 'clase'], 'nueva'], ['==', ['get', 'indice'], indice]]);
  for (const [capa, propiedad, normal] of OPACIDADES_RESULTADOS) {
    mapa.setPaintProperty(capa, propiedad,
      indice < 0 ? normal : ['case', ['==', ['get', 'indice'], indice], normal, normal * 0.22]);
  }
}

// --- Encuadre con la cámara inclinada -------------------------------------------------

// Lo que tapan los paneles flotantes no cuenta como mapa visible. Este margen se le
// entrega a la cámara de MapLibre, que corre hacia la zona libre el punto de fuga y el
// centro de sus movimientos (también el de los botones de zoom).
function paddingPaneles() {
  const ancho = window.innerWidth;
  const alto = window.innerHeight;
  // En pantallas angostas (los paneles arriba y abajo, como en style.css) cada píxel cuenta.
  const angosta = ancho <= 820;
  const margen = angosta ? 16 : 40;
  const p = { top: margen, bottom: margen + 30, left: margen, right: margen };
  const panel = document.getElementById('panel').getBoundingClientRect();
  const derecha = document.querySelector('.columna-derecha').getBoundingClientRect();
  if (!angosta) {
    p.left = panel.right + margen;
    if (derecha.width) p.right = ancho - derecha.left + margen;
  } else {
    // La consola de estado flota justo encima del panel de abajo: también se descuenta.
    p.bottom = Math.max(alto - panel.top + margen + 40, margen);
    if (derecha.height) p.top = derecha.bottom + margen;
  }
  // Si los paneles no dejan espacio, se encuadra sobre toda la pantalla.
  if (p.left + p.right > ancho - 120) { p.left = margen; p.right = margen; }
  if (p.top + p.bottom > alto - 120) { p.top = margen; p.bottom = margen; }
  return p;
}

// fitBounds de MapLibre encuadra como si el mapa se viera desde arriba: con la cámara
// inclinada, lo cercano (abajo en la pantalla) se agranda y lo lejano se encoge, así que
// un encuadre cenital puede salirse por las esquinas de abajo. Además suma su margen al
// que ya tiene la cámara, y con los paneles descontados dos veces el encuadre no cabe.
// Por eso el encuadre se calcula aquí: cada punto se proyecta con la misma perspectiva
// de MapLibre (campo de visión vertical de 36,87°, que deja la cámara a 1,5 alturas de
// pantalla del centro) y se busca el zoom más alto con el que todos caben en la zona
// libre. Luego se corre el centro para que el dibujo quede centrado en la pantalla, no
// solo en el suelo, y se vuelve a buscar el zoom.
const DISTANCIA_CAMARA_EN_ALTURAS = 0.5 / Math.tan(0.6435011087932844 / 2);

function camaraParaVer(coordenadas, { inclinacion, rumbo, padding, zoomMinimo = 8, zoomMaximo = 15.5 }) {
  const lienzo = mapa.getContainer();
  const mitadAncho = (lienzo.clientWidth - padding.left - padding.right) / 2;
  const mitadAlto = (lienzo.clientHeight - padding.top - padding.bottom) / 2;
  const distancia = DISTANCIA_CAMARA_EN_ALTURAS * lienzo.clientHeight;
  const seno = Math.sin(inclinacion * Math.PI / 180);
  const coseno = Math.cos(inclinacion * Math.PI / 180);
  const cosGiro = Math.cos(-rumbo * Math.PI / 180);
  const senGiro = Math.sin(-rumbo * Math.PI / 180);

  // Coordenadas Mercator (de 0 a 1). El centro arranca en el del rectángulo que encierra los puntos.
  const puntos = coordenadas.map((c) => maplibregl.MercatorCoordinate.fromLngLat(c));
  let minX = Infinity; let maxX = -Infinity; let minY = Infinity; let maxY = -Infinity;
  for (const m of puntos) {
    minX = Math.min(minX, m.x); maxX = Math.max(maxX, m.x);
    minY = Math.min(minY, m.y); maxY = Math.max(maxY, m.y);
  }
  let centroX = (minX + maxX) / 2;
  let centroY = (minY + maxY) / 2;

  // Extensión del dibujo en pantalla, medida desde el centro de la zona libre (null si
  // algún punto queda detrás de la cámara).
  function extension(zoom) {
    const escala = 512 * 2 ** zoom; // ancho del mundo en píxeles: teselas de 512
    const e = { x0: Infinity, x1: -Infinity, y0: Infinity, y1: -Infinity };
    for (const m of puntos) {
      const dx = (m.x - centroX) * escala;
      const dy = (m.y - centroY) * escala;
      const sx = dx * cosGiro - dy * senGiro; // girado según el rumbo
      const sy = dx * senGiro + dy * cosGiro;
      const profundidad = distancia - sy * seno; // lo de abajo queda más cerca de la cámara
      if (profundidad < distancia * 0.1) return null;
      const x = (sx * distancia) / profundidad;
      const y = (sy * coseno * distancia) / profundidad;
      e.x0 = Math.min(e.x0, x); e.x1 = Math.max(e.x1, x);
      e.y0 = Math.min(e.y0, y); e.y1 = Math.max(e.y1, y);
    }
    return e;
  }
  const cabe = (e) => e !== null && Math.max(-e.x0, e.x1) <= mitadAncho && Math.max(-e.y0, e.y1) <= mitadAlto;

  // El zoom más alto que cabe, por bisección.
  function buscarZoom() {
    if (cabe(extension(zoomMaximo))) return zoomMaximo;
    let bajo = zoomMinimo;
    let alto = zoomMaximo;
    for (let i = 0; i < 18; i++) {
      const medio = (bajo + alto) / 2;
      if (cabe(extension(medio))) bajo = medio; else alto = medio;
    }
    return bajo;
  }

  let zoom = buscarZoom();
  for (let vuelta = 0; vuelta < 3; vuelta++) {
    const e = extension(zoom);
    if (!e) break;
    const xMedio = (e.x0 + e.x1) / 2;
    const yMedio = (e.y0 + e.y1) / 2;
    if (Math.abs(xMedio) < 0.5 && Math.abs(yMedio) < 0.5) break;
    // Punto del suelo que se ve en el medio del dibujo (la proyección, invertida): pasa a ser el centro.
    const sy = (yMedio * distancia) / (coseno * distancia + yMedio * seno);
    const sx = (xMedio * (distancia - sy * seno)) / distancia;
    const escala = 512 * 2 ** zoom;
    centroX += (sx * cosGiro + sy * senGiro) / escala;
    centroY += (-sx * senGiro + sy * cosGiro) / escala;
    zoom = buscarZoom();
  }
  return { center: new maplibregl.MercatorCoordinate(centroX, centroY).toLngLat(), zoom };
}

// Los resultados se muestran con algo de inclinación, para no perder la profundidad,
// pero sin pasar de 45°, donde la ruta empieza a perder legibilidad. Si el usuario dejó
// el mapa más plano, se respeta; también el rumbo que tenga.
const INCLINACION_RESULTADOS = 45;

function encuadrar(coordenadas) {
  if (!coordenadas.length) return;
  const padding = paddingPaneles();
  const inclinacion = Math.min(mapa.getPitch(), INCLINACION_RESULTADOS);
  const rumbo = mapa.getBearing();
  const { center, zoom } = camaraParaVer(coordenadas, { inclinacion, rumbo, padding });
  mapa.flyTo({ center, zoom, pitch: inclinacion, bearing: rumbo, padding, duration: reducirMovimiento ? 0 : 1800 });
}

// Si cambia el tamaño de la ventana, cambia también la zona libre entre los paneles.
let esperaRedimension = null;
window.addEventListener('resize', () => {
  clearTimeout(esperaRedimension);
  esperaRedimension = setTimeout(() => mapa.setPadding(paddingPaneles()), 200);
});

function coordenadasDe(r) {
  return [...r.geometria_lonlat, ...(r.geometria_actual_lonlat || [])];
}

// Barra comparativa: tiempo de hoy contra tiempo de la propuesta, en la misma escala.
function barras(r) {
  const actual = r.tiempo_actual_min;
  const nueva = r.tiempo_nueva_ruta_min;
  const maximo = Math.max(actual ?? 0, nueva, 0.001);
  const barra = (clase, etiqueta, valor) => `
    <div class="barra ${clase}">
      <span class="barra-etiqueta">${etiqueta}</span>
      <span class="barra-pista"><span class="barra-relleno" style="--proporcion:${(valor / maximo).toFixed(4)}"></span></span>
    </div>`;
  return `<div class="barras">${actual != null ? barra('barra-actual', 'Hoy', actual) : ''}${barra('barra-nueva', 'Propuesta', nueva)}</div>`;
}

function tarjetaResultado(r, indice = 0) {
  const div = document.createElement('div');
  div.className = 'tarjeta-resultado';
  div.tabIndex = 0;
  div.dataset.indice = indice;
  div.style.setProperty('--retardo', `${Math.min(indice, 10) * 60}ms`);

  let lineaAhorro;
  let valorAhorro;
  if (r.ahorro_min === null || r.ahorro_min === undefined) {
    lineaAhorro = '<span class="ahorro-nulo">Sin conexión troncal directa hoy</span>';
    valorAhorro = '<span class="kpi-valor ahorro-nulo">—</span>';
  } else if (r.ahorro_min > 0) {
    lineaAhorro = `Ahorro estimado: <span class="ahorro-positivo num">${minutos(r.ahorro_min)} min</span>`;
    valorAhorro = `<span class="kpi-valor ahorro-positivo">${minutos(r.ahorro_min)}</span>`;
  } else {
    lineaAhorro = `Ahorro estimado: <span class="num">${minutos(r.ahorro_min)} min</span>`;
    valorAhorro = `<span class="kpi-valor">${minutos(r.ahorro_min)}</span>`;
  }

  const n = r.transbordos_actuales;
  div.innerHTML = `
    <div class="tarjeta-cabecera">
      <span class="tarjeta-indice">${String(indice + 1).padStart(2, '0')}</span>
      <div class="titulo">${escapar(r.nombre_origen)} <span class="flecha">&harr;</span> ${escapar(r.nombre_destino)}</div>
    </div>
    <div class="kpis">
      <div class="kpi kpi-actual">
        <span class="kpi-etiqueta">Hoy</span>
        <span class="kpi-valor">${r.tiempo_actual_min != null ? minutos(r.tiempo_actual_min) : '—'}</span>
        <span class="kpi-unidad">min</span>
      </div>
      <div class="kpi kpi-nueva">
        <span class="kpi-etiqueta">Propuesta</span>
        <span class="kpi-valor">${minutos(r.tiempo_nueva_ruta_min)}</span>
        <span class="kpi-unidad">min</span>
      </div>
      <div class="kpi kpi-ahorro">
        <span class="kpi-etiqueta">Ahorro</span>
        ${valorAhorro}
        <span class="kpi-unidad">min</span>
      </div>
    </div>
    ${barras(r)}
    <div class="detalles">
      <div>${lineaAhorro}</div>
      ${n ? `<div>El tiempo de hoy incluye <span class="num">${n}</span> transbordo${n === 1 ? '' : 's'} de <span class="num">${r.transbordo_min}</span> min</div>` : ''}
      ${r.distancia_geometrica_m ? `<div>Distancia en línea recta: <span class="num">${formatoEntero.format(r.distancia_geometrica_m)} m</span></div>` : ''}
      ${r.factor_rodeo ? `<div>Por la red troncal: <span class="num">${formatoDecimal.format(r.factor_rodeo)}×</span> la línea recta</div>` : ''}
    </div>
  `;

  div.addEventListener('mouseenter', () => resaltarResultado(indice));
  div.addEventListener('mouseleave', () => resaltarResultado(-1));
  div.addEventListener('focus', () => resaltarResultado(indice));
  div.addEventListener('blur', () => resaltarResultado(-1));
  div.addEventListener('click', () => encuadrar(coordenadasDe(r)));
  div.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      encuadrar(coordenadasDe(r));
    }
  });
  return div;
}

// --- Acciones de los botones ---------------------------------------------------------

document.getElementById('btn-sugerir').addEventListener('click', async (evento) => {
  const origen = elOrigen.value;
  const destino = elDestino.value;
  if (!origen || !destino || origen === destino) {
    mostrarEstado('Elige dos estaciones distintas.', true);
    return;
  }

  const boton = evento.currentTarget;
  limpiarResultados();
  enProceso(boton, true);
  mostrarEstado('Calculando sugerencia...');
  try {
    const r = await obtenerJSON(
      `/api/sugerir?origen=${encodeURIComponent(origen)}&destino=${encodeURIComponent(destino)}`
    );
    await estiloListo;
    dibujarSugerencia(r, 0);

    elResultado.classList.remove('oculto');
    elResultadoContenido.innerHTML = '';
    elResultadoContenido.appendChild(tarjetaResultado(r, 0));

    encuadrar(coordenadasDe(r));
    mostrarEstado('Listo.');
  } catch (err) {
    mostrarEstado(err.message, true);
  } finally {
    enProceso(boton, false);
  }
});

document.getElementById('btn-pares').addEventListener('click', async (evento) => {
  const topN = document.getElementById('top-n').value || 5;

  const boton = evento.currentTarget;
  limpiarResultados();
  enProceso(boton, true);
  mostrarEstado('Buscando pares críticos (puede tardar unos segundos)...');
  try {
    const resultados = await obtenerJSON(`/api/pares-criticos?top_n=${topN}`);
    await estiloListo;

    elResultado.classList.remove('oculto');
    elResultadoContenido.innerHTML = '';

    const todosLosPuntos = [];
    resultados.forEach((r, i) => {
      dibujarSugerencia(r, i);
      elResultadoContenido.appendChild(tarjetaResultado(r, i));
      todosLosPuntos.push(...r.geometria_lonlat);
    });

    encuadrar(todosLosPuntos);
    mostrarEstado(`${resultados.length} pares críticos encontrados.`);
  } catch (err) {
    mostrarEstado(err.message, true);
  } finally {
    enProceso(boton, false);
  }
});

// --- Arranque ----------------------------------------------------------------

// Entrada de cámara: de la vista cenital a una inclinada, como en una sala de control,
// con toda la red encuadrada en la zona libre entre los paneles.
function entradaDeCamara() {
  if (!coordenadasRed.length) return;
  const padding = paddingPaneles();
  const vista = { inclinacion: 52, rumbo: -16, padding, zoomMaximo: 13 };
  const { center, zoom } = camaraParaVer(coordenadasRed, vista);
  mapa.easeTo({
    center, zoom, pitch: vista.inclinacion, bearing: vista.rumbo, padding,
    duration: reducirMovimiento ? 0 : 3400, easing: (t) => 1 - Math.pow(1 - t, 3),
  });
}

(async function iniciar() {
  try {
    await cargarEstaciones();
    await cargarTrazado();
    const n = await cargarConexionesModelo();
    document.getElementById('n-conexiones').textContent = `(${n})`;
    entradaDeCamara();
  } catch (err) {
    mostrarEstado(`Error cargando datos iniciales: ${err.message}`, true);
  }
  cargarTelemetria();
})();
