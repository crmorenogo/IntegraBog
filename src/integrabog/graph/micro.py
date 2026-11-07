"""
Grafo Micro (malla vial) construido a partir de Overture Maps, con City2Graph
como motor de ingesta. Reemplaza la versión basada en OpenStreetMap/OSMnx.

Cómo llega Overture hasta aquí (paso 1, todo dentro de City2Graph):
    city2graph.data.load_overture_data() no habla con Overture por su cuenta:
    arma y ejecuta el CLI oficial de Overture,
        overturemaps download --bbox=<min_lon,min_lat,max_lon,max_lat>
                              -f geojson --type=segment [-r <release>] -o <archivo>
    (y lo mismo con --type=connector). El CLI consulta primero el catálogo
    STAC del release (stac.overturemaps.org) para saber cuáles de los miles de
    archivos GeoParquet del tema transportation se cruzan con el bbox, y luego
    lee solo esos desde el bucket público de S3 (sin credenciales), filtrando
    elemento por elemento con la columna 'bbox' que trae cada uno. City2Graph
    lee el GeoJSON resultante con GeoPandas, descarta lo que no sea LineString
    y explota los MultiLineString.

    El área se pasa como bbox (lista) y NO como polígono, a propósito: con un
    polígono, City2Graph recorta la geometría de los segmentos en el borde, y
    las posiciones 'at' de sus conectores quedarían referidas a una geometría
    que ya no existe (todas apuntarían a sitios corridos).

Qué se hace después con los datos, y por qué:

  2. Filtro vehicular: subtype='road' y 'class' en CLASES_VIALES_VEHICULARES
     (el equivalente al network_type="drive" de OSMnx; ver config.py).

  3. Partición en conectores con city2graph.data.process_overture_segments().
     En Overture un segmento no termina en cada cruce: puede atravesar varias
     intersecciones, que vienen marcadas en su lista 'connectors' como
     posiciones relativas 'at' (0 = inicio, 1 = fin). City2Graph lo parte en
     una pieza por cada par de conectores consecutivos -- cada pieza es una
     arista del grafo.

  4. Topología por ID de conector, no por coordenadas. Este es el único paso
     donde no se usa la herramienta de City2Graph prevista para eso
     (segments_to_graph), y es deliberado. segments_to_graph decide qué
     extremos son el mismo nodo comparando coordenadas, y eso choca con dos
     reglas de la especificación de Overture:
       - "dos segmentos NO están conectados si no comparten un conector,
         aunque sus geometrías se toquen o compartan una coordenada" (un
         puente sobre una avenida, por ejemplo): por coordenadas quedarían
         unidos;
       - los 'at' se calculan con distancia GEODÉSICA sobre el elipsoide
         WGS84, y City2Graph parte con distancia PLANA (en EPSG:3116): el
         punto de corte queda a fracciones de milímetro del vértice real, y
         su agrupamiento por celdas de grilla puede dejar sin unir dos
         extremos que estaban a 1 mm si caen a lados distintos de un borde de
         celda. Por coordenadas quedarían separados.
     Por eso cada pieza se ancla a sus conectores: el nodo de origen y el de
     destino son los IDs GERS de los conectores en sus posiciones de corte, y
     los extremos de la geometría se mueven a la coordenada exacta del
     conector (que según la especificación siempre es un vértice del
     segmento). Esos IDs GERS son además estables entre releases de Overture,
     a diferencia de los enteros 0..N que asignaba OSMnx al consolidar.

  5. Sentido de circulación y velocidad máxima. Overture no tiene un campo
     'oneway': una vía de un solo sentido es una regla de acceso
     {access_type: denied, when: {heading: backward}}. Las reglas se evalúan
     con el algoritmo de la especificación ("de las reglas que aplican, decide
     la última") para el caso de un carro particular en tránsito, a cualquier
     hora: no aplican las reglas acotadas a horarios ('during'), a dimensiones
     de vehículo ('vehicle'), a un propósito ('using', p. ej. solo para
     llegar a destino) ni a un estatus ('recognized', p. ej. privado). Una
     regla limitada a un tramo ('between') aplica a una pieza si cubre al
     menos la mitad de ella.

     5b. Sentido que Overture no trae: calzadas separadas a las que les falta
     la regla y rotondas con huecos se completan en graph/sentido.py, más
     las correcciones a mano de config.SENTIDOS_FORZADOS. Sin esto, una ruta
     que entraba por la calzada equivocada de una avenida seguía por ella en
     contravía (caso Toberín -> San Mateo, Av. Carrera 72).

     5c. Factibilidad para una troncal: cada arista lleva 'apta_troncal' y,
     si no lo es, 'motivo_no_apta'. Aquí se marca lo que sale de los datos de
     Overture: superficie no pavimentada (SUPERFICIES_NO_APTAS) y
     restricciones por dimensión o peso que le aplican al bus de referencia
     (PERFIL_BUS_TRONCAL; p. ej. "prohibido a más de 10 t"). Las vías que se
     descartan por conocimiento local (VIAS_NO_APTAS_TRONCAL) se marcan al
     cargar, y la clase vial se filtra al calcular la ruta
     (routing/network_design.py). Nada de esto quita aristas: la malla sigue
     sirviendo para todo lo demás; solo la ruta de una troncal nueva las evita.

  6. Vías sin salida (CONSERVAR_VIAS_SIN_SALIDA) y componente fuertemente
     conexa más grande, igual que en la versión OSMnx.

     6b. Giros prohibidos ('prohibited_transitions' de Overture): se
     traducen a las aristas de la malla ya podada y se guardan en la arista
     por la que se llega al giro (graph/giros.py). Solo las reglas que le
     aplican al bus de referencia, con el mismo criterio que la factibilidad
     (5c): sin horarios, propósitos ni estatus, con los modos del bus y sus
     dimensiones. El grafo sigue siendo por intersecciones; es la búsqueda de
     la ruta (graph.giros.camino_respetando_giros) la que no los toma. Cada
     arista guarda además su rumbo de entrada y de salida, para que esa
     búsqueda tampoco haga giros en U (config.GIRO_MAXIMO_BUS_GRADOS).

  7. Dos cachés, por la misma razón de tiempo que antes: la descarga cruda
     (data/raw/overture/, con el release usado en un JSON aparte) y la malla
     ya procesada (data/processed/, GeoParquet). La procesada se regenera
     sola, desde la cruda y sin volver a descargar, si cambia algún
     parámetro de config.py que la afecte.

Contrato de salida (el mismo de antes): nx.MultiDiGraph en EPSG:3116, nodos
con 'x' e 'y'; aristas con 'length' y 'weight' (ambas en metros), 'class'
(la jerarquía vial de Overture, que lee la función de costo BRT), 'subclass'
cuando existe ('link' = rampa), 'name', 'oneway', 'reversed',
'velocidad_max_kmh' cuando Overture la trae y 'geometry'. Además:
'apta_troncal' (bool), 'motivo_no_apta', 'superficie' y 'sentido_inferido'
cuando aplican (ver 5b y 5c), 'rumbo_inicial' y 'rumbo_final' (grados) y
'giros_prohibidos' (texto JSON) en las aristas de las que sale algún giro
prohibido (6b).
"""
import ast
import importlib.metadata
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from city2graph.data import load_overture_data, process_overture_segments
from scipy.spatial import cKDTree

from integrabog.config import (
    AREA_ESTUDIO_BBOX,
    CLASES_VIALES_VEHICULARES,
    CONSERVAR_VIAS_SIN_SALIDA,
    CRS_METRICO,
    OVERTURE_RELEASE,
    AVENIDAS_CON_SEPARADOR,
    PERFIL_BUS_TRONCAL,
    PREFIJO_OVERTURE,
    RUTA_MALLA_PROCESADA,
    RUTA_OVERTURE_CRUDO,
    SENTIDOS_FORZADOS,
    SUPERFICIES_NO_APTAS,
    UMBRAL_EXTREMOS_M,
    VIAS_NO_APTAS_TRONCAL,
)
from integrabog.graph.conversion import es_celda_vacia
from integrabog.graph.correcciones import aplicar_vias_no_aptas
from integrabog.graph.giros import anotar_giros_prohibidos, anotar_rumbos
from integrabog.graph.sentido import completar_sentidos

Bbox = tuple[float, float, float, float]

"""el carro particular es el caso que define la red: una regla aplica si no nombra ningún
 modo, o si nombra alguno que incluya al carro -- 'vehicle' y 'motor_vehicle' lo incluyen,
 'bus', 'hgv' o 'bicycle' no"""
MODOS_TRAFICO_GENERAL = frozenset({"vehicle", "motor_vehicle", "car"})
_ALCANCES_CONDICIONALES = ("during", "vehicle", "using", "recognized")
_COBERTURA_MINIMA = 0.5  # fracción de la pieza que una regla con 'between' debe cubrir para aplicarle
FLAGS_EXCLUYENTES = frozenset({"is_under_construction", "is_abandoned"})
_MPH_A_KMH = 1.609344
_TOLERANCIA_AT = 1e-9  # las posiciones de corte de City2Graph son los mismos 'at', copiados tal cual

COLUMNAS_ANIDADAS = ("connectors", "access_restrictions", "speed_limits", "road_flags", "names", "road_surface",
                     "prohibited_transitions")

"""el bus de una troncal, para la factibilidad (ver evaluar_para_bus): 'motor_vehicle' lo
 incluye aunque el esquema de Overture solo nombre "car, truck and motorcycle" como ejemplos"""
MODOS_BUS = frozenset({"vehicle", "motor_vehicle", "bus"})
_A_METROS = {"in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344, "cm": 0.01, "m": 1.0, "km": 1000.0}
_A_TONELADAS = {"oz": 2.8349523125e-05, "lb": 0.00045359237, "st": 0.90718474, "lt": 1.0160469088,
                "g": 1e-06, "kg": 0.001, "t": 1.0}


def obtener_malla_vial(
    *,
    forzar_descarga: bool = False,
    area: Bbox = AREA_ESTUDIO_BBOX,
    release: str | None = OVERTURE_RELEASE,
) -> nx.MultiDiGraph:
    """Entrega la malla vial lista para usar: descargada de Overture,
    filtrada a vías vehiculares, con topología por conectores, sentido de
    circulación, sin vías sin salida y reducida a su componente fuertemente
    conexa más grande.

    Los parámetros son solo por nombre a propósito: la versión OSMnx recibía
    el lugar como primer argumento posicional, y una llamada vieja como
    obtener_malla_vial("Bogotá, Colombia") caería en forzar_descarga=True
    sin avisar. Así falla con un TypeError explícito.

    Args:
        forzar_descarga: si es True, ignora ambas cachés y vuelve a bajar
            todo de Overture.
        area: bbox (min_lon, min_lat, max_lon, max_lat) en WGS84.
        release: release de Overture; None = el más reciente (ver config.py).

    Returns:
        Grafo vial (nx.MultiDiGraph, EPSG:3116). Nodos: IDs GERS de los
        conectores de Overture. G.graph guarda el release usado y el bbox.

    Raises:
        RuntimeError: si hay que descargar y no hay acceso a Overture; el
            mensaje explica cómo bajar los archivos a mano.
    """
    parametros = _parametros_proceso(area)
    G = None if forzar_descarga else _cargar_malla_procesada(parametros)
    if G is None:
        segmentos, conectores, metadatos = _obtener_crudo(area, release, forzar_descarga)
        G = construir_malla_desde_overture(segmentos, conectores, area=area)
        G.graph["overture_release"] = metadatos.get("release")
        _guardar_malla_procesada(G, parametros, metadatos)

    """después de guardar la caché, a propósito: así editar la lista de config.py no obliga a
     regenerar la malla (unos minutos); se aplica de nuevo cada vez que se carga"""
    aplicar_vias_no_aptas(G, VIAS_NO_APTAS_TRONCAL)
    return G


def construir_malla_desde_overture(segmentos: gpd.GeoDataFrame, conectores: gpd.GeoDataFrame,
                                   area: Bbox = AREA_ESTUDIO_BBOX) -> nx.MultiDiGraph:
    """Pasos 2 a 6 del docstring del módulo, sobre datos ya descargados.

    Está separada de obtener_malla_vial() para poder construir la malla a
    partir de cualquier extracto de Overture (un archivo bajado a mano, un
    área de prueba) sin pasar por la descarga ni por las cachés.

    Args:
        segmentos: features 'segment' de Overture, en cualquier CRS (se
            reproyectan). Columnas anidadas como listas/dicts, texto JSON o
            arreglos de numpy (según venga de GeoJSON o de GeoParquet).
        conectores: features 'connector' de Overture, con columna 'id'.
        area: se guarda en G.graph['area_estudio_bbox']; multilayer.py la
            usa para verificar que todas las estaciones caigan dentro.

    Returns:
        Ver obtener_malla_vial().
    """
    segmentos = segmentos.to_crs(CRS_METRICO)
    conectores = conectores.to_crs(CRS_METRICO)

    viales = _filtrar_vias_vehiculares(segmentos)
    for columna in COLUMNAS_ANIDADAS:
        if columna in viales.columns:
            viales[columna] = viales[columna].map(_a_python)
    if "connectors" not in viales.columns:
        raise ValueError("Los segmentos no traen la columna 'connectors': sin ella no hay topología.")

    print(f"Partiendo {len(viales)} segmentos en sus conectores (City2Graph)...")
    """get_barriers=False: las 'barrier_geometry' sirven para el grafo morfológico de City2Graph
     (manzanas, espacio público), no para una red de circulación"""
    partes = process_overture_segments(
        viales, get_barriers=False, connectors_gdf=conectores[["id", "geometry"]], threshold=UMBRAL_EXTREMOS_M,
    )
    print(f"  {len(viales)} segmentos -> {len(partes)} piezas entre conectores")

    partes = _anclar_a_conectores(partes, conectores)
    aristas = _aristas_dirigidas(partes)
    aristas = completar_sentidos(aristas)

    G = nx.MultiDiGraph(crs=CRS_METRICO, fuente="Overture Maps (vía City2Graph)",
                        area_estudio_bbox=list(area))
    usados = pd.unique(np.concatenate([aristas["u"].to_numpy(), aristas["v"].to_numpy()]))
    puntos = conectores.drop_duplicates("id").set_index("id").geometry.loc[usados]
    _reportar_conectores_vecinos(puntos)
    G.add_nodes_from((nodo, {"x": float(p.x), "y": float(p.y)}) for nodo, p in puntos.items())
    G.add_edges_from(_registros_aristas(aristas))
    print(f"Malla dirigida: {G.number_of_nodes()} nodos, {G.number_of_edges()} aristas")

    if not CONSERVAR_VIAS_SIN_SALIDA:
        G = _quitar_vias_sin_salida(G)
    G = _componente_fuerte_principal(G)
    _reportar_giros(anotar_giros_prohibidos(G, viales, alcance_para_bus))
    anotar_rumbos(G)
    return G


def _reportar_giros(informe: Counter) -> None:
    no_aplican = {k.removeprefix("no aplica: "): n for k, n in informe.items() if k.startswith("no aplica: ")}
    total = sum(n for k, n in informe.items() if k != "aristas de llegada")
    detalle = f" {no_aplican}" if no_aplican else ""
    print(f"Giros prohibidos de Overture: {total} reglas | aplicadas al bus: {informe['aplicada']} "
          f"(desde {informe['aristas de llegada']} aristas de llegada) | fuera de la malla podada: "
          f"{informe['fuera de la malla']} | no le aplican al bus: {sum(no_aplican.values())}{detalle} | "
          f"inconsistentes: {informe['inconsistente']}")


# --- Paso 1: descarga y caché cruda -----------------------------------------------------

def _ruta_cruda(tipo: str, extension: str) -> Path:
    return RUTA_OVERTURE_CRUDO / f"{PREFIJO_OVERTURE}{tipo}.{extension}"


def _ruta_metadatos_crudo() -> Path:
    return RUTA_OVERTURE_CRUDO / f"{PREFIJO_OVERTURE}metadatos.json"


def _obtener_crudo(area: Bbox, release: str | None,
                   forzar_descarga: bool) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict]:
    """Segmentos y conectores crudos, desde la caché si existe.

    La caché acepta GeoJSON (lo que escribe City2Graph) o GeoParquet (lo que
    deja el CLI de Overture con -f geoparquet, si se bajó a mano), con los
    nombres de _ruta_cruda(). Si sus metadatos dicen que se bajó para otra
    área, se vuelve a descargar; una descarga manual sin metadatos se toma
    tal cual.
    """
    segmentos, conectores = _leer_crudo("segment"), _leer_crudo("connector")
    if forzar_descarga or segmentos is None or conectores is None:
        return _descargar(area, release)

    ruta_meta = _ruta_metadatos_crudo()
    metadatos = json.loads(ruta_meta.read_text(encoding="utf-8")) if ruta_meta.exists() else {}
    if metadatos.get("bbox") not in (None, list(area)):
        print(f"La caché cruda se descargó para otra área ({metadatos['bbox']}): se descarga de nuevo.")
        return _descargar(area, release)
    print(f"Cargando Overture crudo desde caché: {RUTA_OVERTURE_CRUDO} "
          f"(release {metadatos.get('release', 'no registrado')})")
    return segmentos, conectores, metadatos


def _leer_crudo(tipo: str) -> gpd.GeoDataFrame | None:
    if (ruta := _ruta_cruda(tipo, "parquet")).exists():
        return gpd.read_parquet(ruta)
    if (ruta := _ruta_cruda(tipo, "geojson")).exists():
        return gpd.read_file(ruta, encoding="utf-8")
    return None


def _descargar(area: Bbox, release: str | None) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict]:
    """Descarga segmentos y conectores con City2Graph y registra el release.

    El release se resuelve ANTES de descargar y se le pasa explícito a
    City2Graph, para que el que queda anotado en los metadatos sea con
    certeza el que se bajó (si se dejara en None, el CLI elegiría el más
    reciente por su cuenta y no habría forma de saber cuál fue).
    """
    instrucciones = (
        "Sin acceso a Overture Maps (stac.overturemaps.org y el bucket S3 'overturemaps-us-west-2'). "
        "Se puede bajar a mano, desde un equipo con acceso, y dejar en " + str(RUTA_OVERTURE_CRUDO) + ":\n"
        + "\n".join(
            f"  overturemaps download --bbox={','.join(str(c) for c in area)} -f geoparquet "
            f"--type={tipo} -o {_ruta_cruda(tipo, 'parquet')}"
            for tipo in ("segment", "connector")
        )
    )
    RUTA_OVERTURE_CRUDO.mkdir(parents=True, exist_ok=True)  # existe aunque falle, para poder dejar ahí la descarga manual
    try:
        if release is None:
            from overturemaps.core import get_latest_release
            release = get_latest_release()
        print(f"Descargando Overture Maps (release {release}) para bbox {area} vía City2Graph...")
        datos = load_overture_data(
            area=list(area), types=["segment", "connector"], output_dir=str(RUTA_OVERTURE_CRUDO),
            prefix=PREFIJO_OVERTURE, save_to_file=True, return_data=True, release=release,
        )
    except Exception as error:  # el CLI y el catálogo STAC lanzan tipos variados al no tener red
        raise RuntimeError(f"{instrucciones}\nError original: {error!r}") from error

    metadatos = {
        "release": release,
        "bbox": list(area),
        "descargado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "city2graph": importlib.metadata.version("city2graph"),
        "overturemaps": importlib.metadata.version("overturemaps"),
    }
    _ruta_metadatos_crudo().write_text(json.dumps(metadatos, indent=2), encoding="utf-8")
    return datos["segment"], datos["connector"], metadatos


# --- Paso 2: filtro vehicular -----------------------------------------------------------

def _filtrar_vias_vehiculares(segmentos: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    es_via = segmentos["subtype"] == "road"
    vehicular = es_via & segmentos["class"].isin(CLASES_VIALES_VEHICULARES)
    descartadas = segmentos.loc[es_via & ~vehicular, "class"].value_counts()
    print(f"Segmentos Overture: {len(segmentos)} | vías vehiculares: {int(vehicular.sum())} | "
          f"no viales (rail/water): {int((~es_via).sum())}")
    if not descartadas.empty:
        print(f"  Clases viales descartadas: {descartadas.to_dict()}")
    return segmentos[vehicular].copy()


def _a_python(valor: object) -> object:
    """Normaliza un valor anidado de Overture a listas/dicts de Python.

    El mismo dato llega en cuatro formas según el camino que haya hecho:
      - lista/dict: GeoJSON del CLI de Overture leído con GDAL reciente;
      - texto JSON: el mismo GeoJSON con GDAL más viejo;
      - texto con repr de Python ("[{'access_type': 'denied', ... None}]"):
        City2Graph REESCRIBE el GeoJSON de segmentos después de descargarlo,
        y GeoPandas guarda así las columnas que mezclan listas con celdas
        vacías -- en la práctica access_restrictions, speed_limits y
        road_flags. Sin este caso, todas las restricciones de sentido se
        leerían como texto y se ignorarían sin ningún error;
      - arreglos de numpy: GeoParquet vía pyarrow. City2Graph tampoco los
        entiende: su lector de 'connectors' devuelve una lista vacía y el
        segmento no se parte en ningún cruce.
    """
    if isinstance(valor, str):
        texto = valor.strip()
        if texto[:1] not in ("[", "{"):
            return valor
        try:
            return _a_python(json.loads(texto))
        except json.JSONDecodeError:
            pass
        try:
            return _a_python(ast.literal_eval(texto))  # solo literales: no ejecuta código
        except (ValueError, SyntaxError):
            return valor
    if isinstance(valor, np.ndarray):
        return [_a_python(v) for v in valor.tolist()]
    if isinstance(valor, (list, tuple)):
        return [_a_python(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _a_python(v) for k, v in valor.items()}
    if isinstance(valor, np.generic):
        return valor.item()
    return None if es_celda_vacia(valor) else valor


# --- Paso 4: topología por conectores ---------------------------------------------------

def _anclar_a_conectores(partes: gpd.GeoDataFrame, conectores: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Asigna a cada pieza sus conectores de inicio y fin (columnas
    'conector_inicio'/'conector_fin') y mueve los extremos de su geometría a
    la coordenada exacta de esos conectores. Ver punto 4 del docstring del
    módulo.

    Las piezas con algún extremo sin conector descargado se descartan: son
    segmentos que cruzan el borde del bbox y siguen hasta un conector que
    quedó por fuera. El área tiene 5-8 km de margen alrededor de la red
    troncal, así que no afecta a ninguna estación.
    """
    partes = partes.reset_index(drop=True)
    desde = partes["split_from"].fillna(0.0) if "split_from" in partes else pd.Series(0.0, index=partes.index)
    hasta = partes["split_to"].fillna(1.0) if "split_to" in partes else pd.Series(1.0, index=partes.index)

    validos = set(conectores["id"])
    referencias = pd.DataFrame({
        "_parte": np.arange(len(partes)), "_ref": partes["connectors"].to_numpy(),
        "_desde": desde.to_numpy(dtype=float), "_hasta": hasta.to_numpy(dtype=float),
    }).explode("_ref")
    referencias = referencias[referencias["_ref"].map(lambda r: isinstance(r, dict))]
    referencias["_id"] = referencias["_ref"].map(lambda r: r.get("connector_id"))
    referencias["_at"] = referencias["_ref"].map(lambda r: r.get("at")).astype(float)
    referencias = referencias[referencias["_id"].isin(validos)]

    def _conector_en(columna: str) -> np.ndarray:
        coincide = np.isclose(referencias["_at"], referencias[columna], rtol=0.0, atol=_TOLERANCIA_AT)
        return (referencias[coincide].drop_duplicates("_parte").set_index("_parte")["_id"]
                .reindex(range(len(partes))).to_numpy())

    partes["conector_inicio"], partes["conector_fin"] = _conector_en("_desde"), _conector_en("_hasta")
    completas = partes["conector_inicio"].notna() & partes["conector_fin"].notna()
    if (~completas).any():
        print(f"  Piezas descartadas por salir del área de estudio (conector fuera del bbox): {int((~completas).sum())}")
    partes = partes[completas].reset_index(drop=True)

    punto = conectores.drop_duplicates("id").set_index("id").geometry
    xy_inicio = shapely.get_coordinates(punto.loc[partes["conector_inicio"]].to_numpy())
    xy_fin = shapely.get_coordinates(punto.loc[partes["conector_fin"]].to_numpy())

    geometrias = partes.geometry.to_numpy()
    coords, indice = shapely.get_coordinates(geometrias, return_index=True)
    primero = np.flatnonzero(np.r_[True, indice[1:] != indice[:-1]])
    ultimo = np.r_[primero[1:] - 1, len(coords) - 1]
    desplazamiento = np.r_[np.hypot(*(coords[primero] - xy_inicio).T), np.hypot(*(coords[ultimo] - xy_fin).T)]
    coords[primero], coords[ultimo] = xy_inicio, xy_fin
    partes = partes.set_geometry(gpd.GeoSeries(shapely.set_coordinates(geometrias.copy(), coords),
                                               index=partes.index, crs=partes.crs))
    partes["length"] = partes.geometry.length  # se recalcula: los extremos se movieron

    """diagnóstico, no corrección: cuánto había quedado corrido cada extremo respecto de su
     conector después de City2Graph (corte con distancia plana + agrupamiento por grilla)"""
    print(f"  Anclaje a conectores: extremos corridos más de 1 µm: {np.mean(desplazamiento > 1e-6) * 100:.1f}% | "
          f"desplazamiento p99={np.percentile(desplazamiento, 99) * 1000:.4f} mm, "
          f"máx={desplazamiento.max() * 1000:.4f} mm")

    degeneradas = (partes["conector_inicio"] == partes["conector_fin"]) & (partes["length"] < 1e-6)
    return partes[~degeneradas].reset_index(drop=True)


def _reportar_conectores_vecinos(puntos: gpd.GeoSeries) -> None:
    """Diagnóstico del punto 4 del docstring del módulo sobre los datos
    reales: cuántos pares de conectores DISTINTOS están a menos de
    UMBRAL_EXTREMOS_M (o en la misma coordenada, como el extremo de un puente
    sobre un cruce). Decidiendo los nodos por coordenadas, como
    segments_to_graph, esos pares se habrían fusionado en un solo nodo; por
    ID de conector quedan separados, como manda la especificación."""
    xy = shapely.get_coordinates(puntos.to_numpy())
    pares = cKDTree(xy).query_pairs(r=UMBRAL_EXTREMOS_M, output_type="ndarray")
    mismos = int(np.sum(np.all(xy[pares[:, 0]] == xy[pares[:, 1]], axis=1))) if len(pares) else 0
    print(f"  Conectores distintos a menos de {UMBRAL_EXTREMOS_M:g} m entre sí: {len(pares)} pares "
          f"({mismos} en la misma coordenada exacta) -- por coordenadas se habrían fusionado")


# --- Paso 5: sentido de circulación y velocidad -----------------------------------------

def _aristas_dirigidas(partes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Una fila por sentido circulable de cada pieza: la del sentido de
    dibujo (inicio -> fin) si 'forward' está permitido, y la inversa, con la
    geometría invertida, si 'backward' lo está.

    Returns:
        GeoDataFrame con columnas u, v, key y los atributos de arista del
        contrato (ver docstring del módulo).
    """
    columnas = {c: partes[c].to_numpy() if c in partes else np.full(len(partes), None, dtype=object)
                for c in ("access_restrictions", "speed_limits", "road_flags", "road_surface", "split_from", "split_to")}
    filas_ida, filas_vuelta, extra_ida, extra_vuelta = [], [], [], []
    excluidas = sin_sentido = 0
    for i in range(len(partes)):
        tramo = (_fraccion(columnas["split_from"][i], 0.0), _fraccion(columnas["split_to"][i], 1.0))
        if excluida_por_flags(columnas["road_flags"][i], tramo):
            excluidas += 1
            continue
        reglas = columnas["access_restrictions"][i]
        ida, vuelta = es_circulable(reglas, "forward", tramo), es_circulable(reglas, "backward", tramo)
        if not (ida or vuelta):
            sin_sentido += 1
            continue
        superficie = superficie_de(columnas["road_surface"][i], tramo)
        for sentido, circulable, filas, extra in (("forward", ida, filas_ida, extra_ida),
                                                  ("backward", vuelta, filas_vuelta, extra_vuelta)):
            if circulable:
                filas.append(i)
                extra.append(_atributos_de_sentido(reglas, columnas["speed_limits"][i], superficie, sentido, tramo))
    print(f"  Piezas fuera de servicio (en construcción/abandonadas): {excluidas} | "
          f"sin paso para carros en ningún sentido: {sin_sentido}")

    doble = set(filas_ida) & set(filas_vuelta)
    ida = _orientar(partes, filas_ida, extra_ida, invertir=False, doble_sentido=doble)
    vuelta = _orientar(partes, filas_vuelta, extra_vuelta, invertir=True, doble_sentido=doble)
    aristas = pd.concat([ida, vuelta], ignore_index=True)
    aristas["key"] = aristas.groupby(["u", "v"], sort=False).cumcount()
    print(f"  Aristas dirigidas: {len(aristas)} ({len(doble)} piezas de doble sentido, "
          f"{len(filas_ida) + len(filas_vuelta) - 2 * len(doble)} de un solo sentido)")
    motivos = Counter(m.split(":")[0] for m in aristas["motivo_no_apta"].dropna())
    print(f"  No aptas para troncal según los datos: {int((~aristas['apta_troncal']).sum())} aristas "
          f"{dict(motivos) if motivos else ''}")
    return aristas


def _atributos_de_sentido(reglas, reglas_velocidad, superficie, sentido: str, tramo) -> dict:
    """Lo que depende del sentido de circulación: velocidad máxima y aptitud
    para el bus de una troncal (ver 5c en el docstring del módulo)."""
    motivo = None
    if superficie in SUPERFICIES_NO_APTAS:
        motivo = f"superficie: {superficie}"
    else:
        regla = evaluar_para_bus(reglas, sentido, tramo)
        if regla is not None and regla.get("access_type") == "denied":
            motivo = f"restricción para el bus: {_describir_vehiculo(regla)}"
    return {"velocidad_max_kmh": velocidad_maxima_kmh(reglas_velocidad, sentido, tramo),
            "superficie": superficie, "apta_troncal": motivo is None, "motivo_no_apta": motivo}


def _orientar(partes: gpd.GeoDataFrame, filas: list[int], extra: list[dict], *,
              invertir: bool, doble_sentido: set[int]) -> gpd.GeoDataFrame:
    sel = partes.iloc[filas]
    geometria = sel.geometry.reverse() if invertir else sel.geometry
    nombres = sel["names"] if "names" in sel else pd.Series(None, index=sel.index)
    return gpd.GeoDataFrame({
        "u": (sel["conector_fin"] if invertir else sel["conector_inicio"]).to_numpy(),
        "v": (sel["conector_inicio"] if invertir else sel["conector_fin"]).to_numpy(),
        "overture_id": sel["id"].to_numpy(),
        "class": sel["class"].to_numpy(),
        "subclass": sel["subclass"].to_numpy() if "subclass" in sel else None,
        "name": [n.get("primary") if isinstance(n, dict) else None for n in nombres],
        "length": sel["length"].to_numpy(),
        "weight": sel["length"].to_numpy(),  # el peso del contrato: la distancia física, en metros
        "oneway": [f not in doble_sentido for f in filas],
        "reversed": invertir,
        "velocidad_max_kmh": np.array([np.nan if e["velocidad_max_kmh"] is None else e["velocidad_max_kmh"]
                                       for e in extra], dtype=float),
        "superficie": [e["superficie"] for e in extra],
        "apta_troncal": np.array([e["apta_troncal"] for e in extra], dtype=bool),
        "motivo_no_apta": [e["motivo_no_apta"] for e in extra],
    }, geometry=geometria.to_numpy(), crs=partes.crs)


def _registros_aristas(aristas: gpd.GeoDataFrame):
    for fila in aristas.to_dict("records"):
        u, v, clave = fila.pop("u"), fila.pop("v"), fila.pop("key")
        yield u, v, clave, {k: val for k, val in fila.items() if not es_celda_vacia(val)}


def _fraccion(valor: object, por_defecto: float) -> float:
    return por_defecto if es_celda_vacia(valor) else float(valor)


def regla_aplica(regla: dict, sentido: str, tramo: tuple[float, float]) -> bool:
    """¿La regla (de acceso o de velocidad) aplica a un carro particular en
    tránsito, en el sentido dado ('forward'/'backward'), sobre la pieza
    [desde, hasta] del segmento? Ver punto 5 del docstring del módulo."""
    cuando = regla.get("when") or {}
    if any(cuando.get(alcance) for alcance in _ALCANCES_CONDICIONALES):
        return False
    if cuando.get("heading") not in (None, sentido):
        return False
    modos = cuando.get("mode")
    if modos and not MODOS_TRAFICO_GENERAL.intersection(modos):
        return False
    return _cubre(regla.get("between"), tramo)


def _cubre(entre: list[float] | None, tramo: tuple[float, float]) -> bool:
    if not entre:
        return True
    (inicio_regla, fin_regla), (desde, hasta) = entre, tramo
    if hasta <= desde:
        return inicio_regla <= desde <= fin_regla
    traslape = max(0.0, min(hasta, fin_regla) - max(desde, inicio_regla))
    return traslape >= _COBERTURA_MINIMA * (hasta - desde) - _TOLERANCIA_AT  # 0.3-0.2 no da 0.1 exacto


def _regla_determinante(reglas: list[dict] | None, sentido: str, tramo: tuple[float, float]) -> dict | None:
    """Algoritmo de evaluación de la especificación de Overture: de las
    reglas que aplican, la que decide es la ÚLTIMA de la lista."""
    determinante = None
    for regla in reglas or []:
        if isinstance(regla, dict) and regla_aplica(regla, sentido, tramo):
            determinante = regla
    return determinante


def es_circulable(reglas_acceso: list[dict] | None, sentido: str, tramo: tuple[float, float] = (0.0, 1.0)) -> bool:
    """Sin regla que aplique, rige el acceso implícito de la clase vial: en
    las clases vehiculares, los carros pasan."""
    regla = _regla_determinante(reglas_acceso, sentido, tramo)
    return regla is None or regla.get("access_type") != "denied"


def velocidad_maxima_kmh(reglas_velocidad: list[dict] | None, sentido: str,
                         tramo: tuple[float, float] = (0.0, 1.0)) -> float | None:
    con_maxima = [r for r in reglas_velocidad or [] if isinstance(r, dict) and r.get("max_speed")]
    regla = _regla_determinante(con_maxima, sentido, tramo)
    if regla is None:
        return None
    maxima = regla["max_speed"]
    valor = float(maxima["value"])
    return round(valor * _MPH_A_KMH, 1) if maxima.get("unit") == "mph" else valor


def evaluar_para_bus(reglas_acceso: list[dict] | None, sentido: str, tramo: tuple[float, float] = (0.0, 1.0),
                     perfil: dict = PERFIL_BUS_TRONCAL) -> dict | None:
    """La regla de acceso que decide para el bus de una troncal, o None si
    ninguna le aplica. Igual que para el carro (la última que aplica decide,
    sin horarios, propósitos ni estatus), con dos diferencias: los modos son
    los del bus (MODOS_BUS) y las reglas por dimensión o peso del vehículo
    ('when.vehicle') SÍ se evalúan, contra el perfil. Si una regla trae
    varias condiciones de vehículo, tienen que cumplirse todas (así se lee
    el ejemplo de tarifas del esquema de Overture: menos de 3 ejes Y hasta
    18 pies)."""
    determinante = None
    for regla in reglas_acceso or []:
        if not isinstance(regla, dict) or alcance_para_bus(regla, perfil) is not None:
            continue
        if (regla.get("when") or {}).get("heading") not in (None, sentido):
            continue
        if _cubre(regla.get("between"), tramo):
            determinante = regla
    return determinante


def alcance_para_bus(regla: dict, perfil: dict = PERFIL_BUS_TRONCAL) -> str | None:
    """None si la regla (de acceso o de giro) le aplica al bus de una
    troncal, sin mirar sentido ni tramo; si no, el motivo. Es el criterio de
    evaluar_para_bus, y el mismo para los giros prohibidos (graph/giros.py).
    Las reglas por horario, propósito o estatus quedan por fuera, como en el
    resto del modelo (punto 5): el modelo no distingue horas del día ni
    tipos de usuario, y esas reglas son excepciones de una parte del día o
    de ciertos usuarios."""
    cuando = regla.get("when") or {}
    if any(cuando.get(alcance) for alcance in ("during", "using", "recognized")):
        return "horario, propósito o estatus"
    modos = cuando.get("mode")
    if modos and not MODOS_BUS.intersection(modos):
        return "otro modo"
    condiciones = cuando.get("vehicle")
    if condiciones and not all(_cumple_condicion(c, perfil) for c in condiciones):
        return "otro vehículo"
    return None


def _cumple_condicion(condicion: dict, perfil: dict) -> bool:
    """¿El vehículo del perfil cumple una condición {dimension, comparison,
    value, unit} de Overture? Una unidad desconocida se toma como que no la
    cumple: mejor no aplicar una restricción que no se entiende."""
    if not isinstance(condicion, dict) or condicion.get("dimension") not in perfil:
        return False
    try:
        umbral = float(condicion["value"])
    except (KeyError, TypeError, ValueError):
        return False
    dimension, unidad = condicion["dimension"], condicion.get("unit")
    if dimension == "weight":
        if unidad not in _A_TONELADAS:
            return False
        umbral *= _A_TONELADAS[unidad]
    elif dimension != "axle_count":
        if unidad not in _A_METROS:
            return False
        umbral *= _A_METROS[unidad]
    valor = perfil[dimension]
    comparar = {"greater_than": valor > umbral, "greater_than_equal": valor >= umbral, "equal": valor == umbral,
                "less_than": valor < umbral, "less_than_equal": valor <= umbral}
    return comparar.get(condicion.get("comparison"), False)


def _describir_vehiculo(regla: dict) -> str:
    """Texto corto de la restricción, para el reporte y el mapa."""
    condiciones = (regla.get("when") or {}).get("vehicle") or []
    signo = {"greater_than": ">", "greater_than_equal": ">=", "equal": "=", "less_than": "<", "less_than_equal": "<="}
    partes = [f"{c.get('dimension')} {signo.get(c.get('comparison'), '?')} {c.get('value')} {c.get('unit') or ''}".strip()
              for c in condiciones if isinstance(c, dict)]
    modos = (regla.get("when") or {}).get("mode")
    return " y ".join(partes) or (f"prohibido a {', '.join(modos)}" if modos else "acceso prohibido")


def superficie_de(reglas_superficie, tramo: tuple[float, float] = (0.0, 1.0)) -> str | None:
    """Superficie de la pieza: la última regla que la cubre (como las de
    acceso). Overture la da como lista de reglas {value, between} o, en su
    forma global, como un solo valor."""
    if isinstance(reglas_superficie, str):
        return reglas_superficie
    valor = None
    for regla in reglas_superficie or []:
        if isinstance(regla, str):
            valor = regla
        elif isinstance(regla, dict) and _cubre(regla.get("between"), tramo):
            valor = regla.get("value")
    return valor


def excluida_por_flags(flags: list | None, tramo: tuple[float, float] = (0.0, 1.0)) -> bool:
    """road_flags admite dos formas: lista de reglas {values, between} o,
    en su forma absoluta, una lista simple de valores."""
    for regla in flags or []:
        valores, entre = ([regla], None) if isinstance(regla, str) else (regla.get("values") or [], regla.get("between"))
        if FLAGS_EXCLUYENTES.intersection(valores) and _cubre(entre, tramo):
            return True
    return False


# --- Paso 6: vías sin salida y componente fuertemente conexa ----------------------------

def _quitar_vias_sin_salida(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Una sola pasada, como ox.consolidate_intersections(dead_ends=False):
    un nodo es 'sin salida' si toca una sola calle, es decir, si tiene un
    único vecino distinto de sí mismo (contando en ambos sentidos)."""
    sin_salida = [n for n in G if len((set(G.successors(n)) | set(G.predecessors(n))) - {n}) <= 1]
    G = G.copy()
    G.remove_nodes_from(sin_salida)
    print(f"Vías sin salida eliminadas: {len(sin_salida)} nodos")
    return G


def _componente_fuerte_principal(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """ medir ANTES de quedarse solo con la componente más grande -- si se descartara a
     ciegas y resultara que el segundo componente también es grande, se estaría
     perdiendo una porción real de la ciudad sin enterarse"""
    componentes = sorted(nx.strongly_connected_components(G), key=len, reverse=True)
    total = G.number_of_nodes()
    print(f"Componentes fuertemente conexas: {len(componentes)}")
    print(f"Tamaños (top 10): {[len(c) for c in componentes[:10]]}")
    print(f"El componente más grande retiene {len(componentes[0])}/{total} nodos "
          f"({len(componentes[0]) / total * 100:.1f}%)")
    return G.subgraph(componentes[0]).copy()


# --- Paso 7: caché de la malla procesada ------------------------------------------------

def _parametros_proceso(area: Bbox) -> dict:
    """Todo lo que cambia el resultado del procesamiento. Si cualquiera de
    estos valores cambia en config.py, la caché procesada deja de servir."""
    return {
        "area_estudio_bbox": list(area),
        "clases_viales": sorted(CLASES_VIALES_VEHICULARES),
        "umbral_extremos_m": UMBRAL_EXTREMOS_M,
        "conservar_vias_sin_salida": CONSERVAR_VIAS_SIN_SALIDA,
        # por JSON de ida y vuelta: las tuplas de config.py vuelven como listas al leer la
        # caché, y sin esto la comparación de parámetros daría siempre distinto
        "sentidos_forzados": json.loads(json.dumps(SENTIDOS_FORZADOS)),
        "avenidas_con_separador": json.loads(json.dumps(AVENIDAS_CON_SEPARADOR)),
        "perfil_bus_troncal": dict(sorted(PERFIL_BUS_TRONCAL.items())),
        "superficies_no_aptas": sorted(SUPERFICIES_NO_APTAS),
        "version_proceso": 5,  # subir si cambia la lógica de este módulo (2: sentido y aptitud; 3: giros
                               # prohibidos; 4: rumbo de cada tramo, sin giros en U; 5: piezas cortas)
    }


def _rutas_procesadas() -> tuple[Path, Path, Path]:
    base = RUTA_MALLA_PROCESADA
    return (base.with_name(base.name + "_nodos.parquet"), base.with_name(base.name + "_aristas.parquet"),
            base.with_name(base.name + "_metadatos.json"))


def _guardar_malla_procesada(G: nx.MultiDiGraph, parametros: dict, metadatos_crudo: dict) -> None:
    ruta_nodos, ruta_aristas, ruta_meta = _rutas_procesadas()
    ruta_nodos.parent.mkdir(parents=True, exist_ok=True)

    ids, datos = zip(*G.nodes(data=True))
    nodos = gpd.GeoDataFrame(list(datos), index=pd.Index(ids, name="id"),
                             geometry=gpd.points_from_xy([d["x"] for d in datos], [d["y"] for d in datos]),
                             crs=CRS_METRICO)
    filas = [{"u": u, "v": v, "key": k, **d} for u, v, k, d in G.edges(keys=True, data=True)]
    aristas = gpd.GeoDataFrame(filas, geometry="geometry", crs=CRS_METRICO)
    nodos.to_parquet(ruta_nodos)
    aristas.to_parquet(ruta_aristas)

    meta = {"parametros": parametros, "crudo": metadatos_crudo,
            "grafo": {k: v for k, v in G.graph.items() if k != "crs"},
            "nodos": G.number_of_nodes(), "aristas": G.number_of_edges()}
    ruta_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Malla procesada guardada en caché: {ruta_nodos.parent}")


def _cargar_malla_procesada(parametros: dict) -> nx.MultiDiGraph | None:
    ruta_nodos, ruta_aristas, ruta_meta = _rutas_procesadas()
    if not (ruta_nodos.exists() and ruta_aristas.exists() and ruta_meta.exists()):
        return None
    meta = json.loads(ruta_meta.read_text(encoding="utf-8"))
    if meta.get("parametros") != parametros:
        print("La caché procesada de la malla vial se hizo con otros parámetros de config.py: "
              "se regenera desde la caché cruda (sin descargar).")
        return None

    print(f"Cargando malla vial Overture (release {meta['crudo'].get('release', 'no registrado')}) "
          f"desde caché: {ruta_nodos.parent}")
    nodos = gpd.read_parquet(ruta_nodos)
    aristas = gpd.read_parquet(ruta_aristas)
    G = nx.MultiDiGraph(crs=CRS_METRICO, **meta["grafo"])
    G.add_nodes_from((nodo, {"x": float(x), "y": float(y)})
                     for nodo, x, y in zip(nodos.index, nodos["x"], nodos["y"]))
    G.add_edges_from(_registros_aristas(aristas))
    return G

