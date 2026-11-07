"""
Configuración central del proyecto IntegraBog.
Aquí viven las rutas y constantes que usan los demás módulos, para no
tener valores sueltos ("magic values") dentro de la lógica de negocio.
"""
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
RUTA_ESTACIONES = RAIZ_PROYECTO / "data" / "raw" / "Estaciones_Troncales_de_TRANSMILENIO.geojson"
RUTA_TRAZADO = RAIZ_PROYECTO / "data" / "raw" / "Trazados_Troncales_de_TRANSMILENIO.geojson"

""" Tolerancia máxima (m) para aceptar el acople de una estación a un
 tramo. Se definió revisando la distribución real de distancias: la
 mayoría cae a ~0 m; el único grupo que se aleja son las estaciones
 tipo Portal (tipo_esta == 1), hasta ~256 m."""
TOLERANCIA_ACOPLE_M = 300.0

""" CRS métrico oficial para Bogotá (MAGNA-SIRGAS / Colombia Bogotá zone).
 Los GeoJSON originales vienen en CRS84 (grados) — no sirve para
 calcular distancias euclidianas correctamente. Ver Paso 2."""
CRS_METRICO = "EPSG:3116"

""" Acceso estación <-> malla vial (graph/multilayer.py). Cada estación se
 engancha a su intersección más cercana y, además, a todas las que estén a
 no más de MARGEN_ACCESO_M metros por encima de esa distancia mínima, con un
 tope absoluto de RADIO_ACCESO_MAX_M. Con una sola intersección, una estación
 ubicada en el separador de una vía de doble calzada quedaba amarrada a la
 calzada de un solo sentido que cayera más cerca, y la ruta propuesta tenía
 que dar la vuelta completa para ir hacia el otro lado (Escuela Militar <->
 San Martín: 4,4 km por la malla para 306 m en línea recta). 75 m alcanza
 para cruzar el separador de las troncales anchas (Calle 80, NQS, Av.
 Caracas) sin enganchar calles de la manzana siguiente."""
"""Costura del grafo macro (graph/costura.py): dos extremos de piezas del
 trazado que quedan a menos de esto se consideran el mismo punto físico, sean
 de la misma troncal o de troncales distintas. Medido sobre el trazado
 oficial: los cortes de digitalización dentro de una troncal llegan a 48 m
 (Américas, Biblioteca Tintal -> Transversal 86), y en los cruces entre
 troncales donde hay transbordo real (Héroes, NQS con Calle 6 y Comuneros,
 Calle 6 con Carrera 10) los extremos quedan entre 28 y 55 m. Con 5 m, que
 era el valor anterior, la red troncal quedaba partida en 12 pedazos.
 Para revisar qué conexiones produce sobre unos datos nuevos:
 python -m integrabog.scripts.diagnostico_costura"""
TOLERANCIA_COSTURA_M = 50.0

"""Aristas de cruce entre troncales (graph/cruces.py). Dos troncales se
 consideran cruzadas donde sus piezas se tocan o quedan a menos de
 TOLERANCIA_CRUCE_M (el mismo margen que la costura). En cada cruce se une la
 estación más cercana a cada lado del punto, en las dos troncales, siempre
 que quede a no más de DISTANCIA_MAX_CRUCE_M del cruce por el trazado.
 Medido sobre el trazado oficial: con 600 m la red troncal ya queda en una
 sola pieza, pero se pierden estaciones del lado lejano de cruces largos
 (Biblioteca - Socorro en el empalme de Tunal con la Caracas Sur, por
 ejemplo), y sin ellas un viaje que siga en ese sentido tendría que pasar
 por la estación del otro lado y devolverse. Entre 1.200 y 1.500 m el
 resultado no cambia (35 pares); por encima ya entran estaciones que no son
 "las del cruce"."""
TOLERANCIA_CRUCE_M = TOLERANCIA_COSTURA_M
DISTANCIA_MAX_CRUCE_M = 1200.0

"""Minutos que cuesta un transbordo: cada vez que un viaje pasa por una
 arista de cruce entre troncales. Representa la caminata entre vagones o
 por los túneles y la espera promedio de la siguiente ruta (valor fijado por
 el equipo, nov-2026). Por ahora lo usan las métricas de la red
 (routing/metricas.py). Las costuras no cuentan: son continuaciones del
 trazado, no un cambio de troncal."""
TRANSBORDO_MIN = 5.0

"""Correcciones manuales a las conexiones que infieren la costura y los cruces
 (graph/correcciones.py), con lo que se sabe de la operación real. Se identifican
 por cod_nodo, no por nombre (los nombres cambian con los patrocinios). Cada
 entrada lleva su motivo.
 - BLOQUEADAS: se quitan del grafo en los dos sentidos.
 - VERIFICADAS: se dejan como están; diagnostico_costura.py deja de marcarlas
   con REVISAR y muestra el motivo."""
CONEXIONES_BLOQUEADAS = [
    (2302, 7101, "Virrey <-> La Castellana: en el puente de la Calle 92 los buses pasan de "
                 "la NQS a la Autopista Norte solo hacia el norte (hacia Calle 100); el giro "
                 "hacia el sur, a Virrey, no existe."),
]
CONEXIONES_VERIFICADAS = [
    (6107, 7108, "Ciudad Universitaria <-> AV. ElDorado: en el intercambiador de la Calle 26 "
                 "con NQS los buses sí hacen este giro por los conectores del puente "
                 "(p. ej. la ruta B16/K16)."),
]

MARGEN_ACCESO_M = 75.0
RADIO_ACCESO_MAX_M = 300.0


# --- CONFIGURACIÓN FASE 2: MALLA VIAL DESDE OVERTURE MAPS (vía City2Graph) ---

"""Área de estudio como bbox (min_lon, min_lat, max_lon, max_lat) en WGS84:
 Bogotá urbana + Soacha, ~29 x 42 km. Cubre todas las estaciones (entre
 -74.205/-74.044 de longitud y 4.532/4.768 de latitud) con 5 a 8 km de
 margen por cada lado, para que la ruta propuesta entre dos estaciones nunca tenga que
 salir del área para encontrar su mejor camino. Es un bbox y no un
 límite administrativo a propósito: el polígono de Bogotá D.C. incluye
 Sumapaz (rural, sin relevancia para corredores BRT), y City2Graph recorta
 la geometría de los segmentos cuando recibe un polígono -- ver micro.py.
 multilayer.py verifica que todas las estaciones caigan dentro."""
AREA_ESTUDIO_BBOX = (-74.25, 4.46, -73.99, 4.84)

"""Release de Overture a descargar ('2026-09-17.0', por ejemplo). None =
 el más reciente en el momento de la descarga. Overture solo mantiene en
 línea los releases de los últimos ~2 meses, así que fijar uno aquí deja
 de funcionar al poco tiempo: la reproducibilidad la da la caché cruda,
 que guarda el release que se usó en su archivo de metadatos."""
OVERTURE_RELEASE: str | None = None

RUTA_OVERTURE_CRUDO = RAIZ_PROYECTO / "data" / "raw" / "overture"
PREFIJO_OVERTURE = "bogota_"  # archivos: bogota_segment.geojson, bogota_connector.geojson
RUTA_MALLA_PROCESADA = RAIZ_PROYECTO / "data" / "processed" / "malla_vial_overture"

"""Clases viales de Overture (atributo 'class') que forman la red para
 vehículos. Es el equivalente al network_type="drive" que se usaba con
 OSMnx: deja por fuera 'service' (accesos a parqueaderos, entradas de
 edificios), las peatonales (pedestrian, footway, steps), las de
 bicicleta/caballo y las trochas (track, path). Las rampas no son una clase
 aparte: en Overture son subclass='link' de la clase a la que pertenecen
 (antes, en OSM, eran primary_link, etc.). 'unknown' se conserva porque
 OSMnx también conservaba highway=road, que es su equivalente."""
CLASES_VIALES_VEHICULARES = frozenset({
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential", "living_street", "unknown",
})

"""Umbral (m) que se le pasa a process_overture_segments de City2Graph para
 agrupar extremos de segmento cercanos. Aquí NO define la topología: los
 nodos salen de los IDs de conector de Overture (ver micro.py), así que no
 hay equivalente a la antigua TOLERANCIA_CONSOLIDACION_M de OSMnx. Se deja
 en el valor por defecto de City2Graph."""
UMBRAL_EXTREMOS_M = 1.0

"""Política de red vial: ¿conservar nodos donde solo toca una calle (vías
 sin salida / culs-de-sac)? En False se eliminan en una sola pasada, igual
 que hacía ox.consolidate_intersections(dead_ends=False) con OSM (allí
 eran ~8.300 nodos, 14% del grafo base). Se fija en False porque un
 corredor BRT no puede terminar en una vía sin salida."""
CONSERVAR_VIAS_SIN_SALIDA = False


# --- SENTIDO DE CIRCULACIÓN QUE OVERTURE NO TRAE (graph/sentido.py) ---

"""Correcciones a mano del sentido de un tramo de la malla vial, para lo que
 graph/sentido.py no alcance a deducir. Cada entrada: (id del segmento de
 Overture, sentido, motivo). El id es el 'overture_id' que muestra
 diagnostico_sentido_ruta.geojson; vale con o sin el sufijo '_<n>' (sin
 sufijo, aplica a todas las piezas del segmento). El sentido se da por
 rumbo, no por el orden de dibujo de Overture, que nadie ve en el mapa:
 "norte", "sur", "oriente", "occidente" (se conserva el sentido de
 circulación que vaya hacia allá) o "ninguno" (el tramo sale de la malla).
 Cambiar esta lista regenera la caché procesada de la malla (unos minutos,
 sin descargar)."""
SENTIDOS_FORZADOS: list[tuple[str, str, str]] = []

"""Avenidas de calzadas separadas (cada calzada de un solo sentido), confirmadas
 por quien conoce la ciudad. graph/sentido.py completa el sentido de una calzada
 sin regla tomando el contrario al de la otra calzada; pero si las DOS vienen sin
 regla no hay de dónde partir, y la geometría sola no distingue esa avenida de
 dos calles paralelas de doble sentido con el mismo nombre. Para las avenidas de
 esta lista se usa entonces solo la regla del separador: cada calzada va en el
 sentido que deja a la otra a su izquierda (tránsito por la derecha). Las piezas
 sin otra calzada al lado (donde la avenida es de una sola calzada) no se tocan.
 Por nombre, tal como lo trae Overture; 'cerca_de' (lat, lon) y 'radio_m' la
 limitan a una zona. diagnostico_sentido.py, sección 2, lista las avenidas que
 están en este caso. Cambiar esta lista regenera la caché procesada."""
_SEPARADOR_CONFIRMADO = ("Separador central físico; cada calzada opera en un solo sentido (confirmado por "
                         "el equipo, nov-2026).")
AVENIDAS_CON_SEPARADOR: list[dict] = [
    {"nombre": "Avenida Carrera 72",
     "motivo": "Calzadas separadas de un solo sentido: la ruta Toberín -> San Mateo iba 3 km en contravía "
               "por la calzada oriental desde la Calle 153 (reportado por el equipo, oct-2026)."},
    {"nombre": "Avenida Calle 116", "motivo": _SEPARADOR_CONFIRMADO},
    {"nombre": "Avenida Calle 72", "motivo": _SEPARADOR_CONFIRMADO},
    {"nombre": "Avenida Carrera 7", "motivo": _SEPARADOR_CONFIRMADO},
    {"nombre": "Avenida Carrera 60", "motivo": _SEPARADOR_CONFIRMADO},
    {"nombre": "Avenida Calle 59 Sur", "motivo": _SEPARADOR_CONFIRMADO},
]


# --- FACTIBILIDAD DE CORREDORES PARA UNA TRONCAL (graph/micro.py, routing/network_design.py) ---

"""Clases viales de Overture por las que puede ir una troncal propuesta. En
 Bogotá las troncales van por la malla arterial; las vías terciarias,
 residenciales y sin clasificar casi nunca tienen la calzada ni los radios
 de giro de un articulado. Antes solo se penalizaban (x3 y x10 en el costo),
 así que una ruta podía meterse por ellas si ahorraba suficiente; ahora no
 pueden usarse, salvo en los primeros y últimos RADIO_ACCESO_TRONCAL_M de
 la ruta: una estación puede estar enganchada a una calle menor y hay que
 dejar llegar desde ella al corredor. 'secondary' también queda por fuera
 (confirmado por el equipo, nov-2026): los carriles exclusivos y las
 estaciones centrales de TransMilenio solo caben en vías arteriales. Se deja
 'motorway', la clase arterial más alta, aunque en la malla de Bogotá no hay
 ninguna vía con ella."""
CLASES_APTAS_TRONCAL = frozenset({"motorway", "trunk", "primary"})
RADIO_ACCESO_TRONCAL_M = 300.0

"""Bus de referencia para las restricciones por dimensión o peso que trae
 Overture (when.vehicle: p. ej. "prohibido a vehículos de más de 10 t", en
 1.468 segmentos de Bogotá). Es el biarticulado, el más exigente de la flota
 troncal. Valores del equipo (nov-2026): 2,60 m de ancho, 3,40 m de alto,
 28 m de largo y 40-42 t; se usa 42 t, el caso más exigente. Los 4 ejes son
 de referencia. En la práctica pesan poco, porque las restricciones reales
 son de 3,5 a 20 t, de 4,5 m de alto o de 12 m de largo, y el bus las supera
 todas."""
PERFIL_BUS_TRONCAL = {"length": 28.0, "width": 2.6, "height": 3.4, "weight": 42.0, "axle_count": 4}

"""Superficies (road_surface de Overture) por las que no puede ir una
 troncal. En Bogotá, 8.366 segmentos vehiculares vienen 'unpaved'."""
SUPERFICIES_NO_APTAS = frozenset({"unpaved", "gravel", "dirt"})

"""Giro más cerrado que puede hacer el bus de una troncal entre dos tramos
 seguidos de la malla, en grados (0 = sigue derecho, 180 = se devuelve por
 donde vino). Más que esto es un giro en U en un cruce, y un biarticulado no
 lo puede hacer: para devolverse necesita una rotonda o un retorno, que en
 los datos son piezas propias y se recorren con giros mucho más abiertos en
 cada punta. Sin este tope, la ruta sorteaba un giro prohibido de Overture
 dando la vuelta en U en un tramo de 10 m de la Av. Carrera 72 junto a la
 Calle 153 (corrida de nov-2026). El rumbo de cada tramo se mide sobre sus
 primeros y últimos 20 m (graph/giros.py)."""
GIRO_MAXIMO_BUS_GRADOS = 150.0

"""Vías que la clase vial no alcanza a descartar pero que no sirven para una
 troncal, según conocimiento local. Cada entrada es un dict con 'motivo' y
 una de estas dos llaves:
   - 'nombre': nombre de la vía tal como lo trae Overture (sin distinguir
     tildes ni mayúsculas). Con 'cerca_de' (lat, lon) y 'radio_m' se limita
     a esa zona, para cuando solo un tramo de la vía es angosto.
   - 'overture_id': un segmento puntual (ver SENTIDOS_FORZADOS).
 Se aplica al cargar la malla, sin regenerar la caché."""
VIAS_NO_APTAS_TRONCAL: list[dict] = [
    {"nombre": "Avenida Calle 153",
     "motivo": "No tiene el ancho de calzada ni el radio de giro que exigen articulados y biarticulados, "
               "tampoco en la rotonda con la Av. Boyacá (conocimiento local del equipo, oct-2026)."},
]
