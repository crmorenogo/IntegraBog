"""
Motor de sugerencia de infraestructura (Fase 4): compara el tiempo actual
por la red troncal existente contra el tiempo de una ruta nueva propuesta
sobre la malla vial, penalizada según la jerarquía de cada calle.

La jerarquía de cada calle sale del atributo 'class' de Overture Maps (desde
la migración de OpenStreetMap; antes era 'highway'). El modelo de costo no
cambió: misma velocidad BRT y mismos factores por jerarquía, porque las
clases de Overture son las de OSM con otro nombre de campo. La única
diferencia de esquema que importa son las rampas: OSM las marcaba como una
clase aparte (primary_link, ...), y Overture las deja en la clase de la vía
a la que pertenecen con subclass='link'. Como en la tabla anterior cada
*_link ya tenía el mismo factor que su vía, el resultado es el mismo sin
entradas extra.

Overture también trae límites de velocidad, que micro.py guarda en
'velocidad_max_kmh', pero aquí no se usan: la velocidad de un BRT la fija
su operación (carril exclusivo, paradas, semáforos), no la señal de la
calle por la que pasa, y cambiarlo sería otro modelo, que habría que
volver a calibrar.

La ruta de una troncal nueva (ruta_nueva) respeta el sentido de cada vía
(el grafo es dirigido), la factibilidad (aristas_ruta_nueva), los giros
prohibidos de Overture y el giro más cerrado que puede hacer el bus, sin
vueltas en U en los cruces (graph/giros.py). La línea base por la red
troncal existente no los necesita: no pasa por la malla vial.
"""
import unicodedata

import networkx as nx
from pyproj import Transformer
from shapely.geometry import Point
from shapely.strtree import STRtree

from integrabog.config import CLASES_APTAS_TRONCAL, RADIO_ACCESO_TRONCAL_M, TRANSBORDO_MIN
from integrabog.graph.cruces import TIPO_ARISTA_CRUCE
from integrabog.graph.giros import camino_respetando_giros

VELOCIDAD_BRT_KMH = 25.2
VELOCIDAD_CAMINATA_KMH = 4.5
ESPACIADO_ESTACIONES_M = 500.0
"""pares críticos: solo se comparan estaciones a no más de esto en línea recta. Más allá,
 un rodeo grande por la red es lo normal (hay que ir por las troncales que existen), no un
 hueco que una conexión corta pueda cerrar"""
RADIO_PAR_CRITICO_M = 1000.0

ATRIBUTO_CLASE_VIAL = "class"  # jerarquía vial de Overture (en OSM era 'highway')

PENALIZACION_VIAL = {
    "motorway": 1.0,
    "trunk": 1.0,
    "primary": 1.15,
    "secondary": 1.6,
    "tertiary": 3.0,
    "residential": 10.0, "living_street": 10.0, "unclassified": 10.0,
}
PENALIZACION_DEFECTO = 10.0  # incluye 'unknown', la clase de Overture para vías sin clasificar

_TRANSFORMADOR = Transformer.from_crs("EPSG:3116", "EPSG:4326", always_xy=True)


class EstacionNoEncontradaError(Exception):
    """La estación buscada no existe, o el nombre es ambiguo."""


def _sin_tildes(texto: str) -> str:
    """Minúsculas y sin marcas diacríticas ("Toberín" -> "toberin"), para comparar nombres."""
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).lower()


def _resolver_estacion(G_multicapa: nx.MultiDiGraph, identificador: str) -> str:
    identificador = str(identificador).strip()
    if identificador in G_multicapa.nodes:
        return identificador
    id_macro = f"macro_{identificador}"
    if id_macro in G_multicapa.nodes:
        return id_macro

    nodos_macro = [
        n for n, d in G_multicapa.nodes(data=True)
        if d.get("layer") == "macro"
    ]
    """la etiqueta (nombre + troncal cuando el nombre se repite, ver macro._nombrar_estaciones)
     es lo que muestra el mapa; buscarla primero hace que ese texto siempre resuelva a una sola"""
    coincidencias_exactas = [
        n for n in nodos_macro
        if G_multicapa.nodes[n].get("etiqueta") == identificador
    ] or [
        n for n in nodos_macro
        if G_multicapa.nodes[n].get("nombre", "") == identificador
    ]
    if len(coincidencias_exactas) == 1:
        return coincidencias_exactas[0]
    """búsqueda parcial sin distinguir tildes ni mayúsculas: el archivo oficial escribe
     "Toberin - Foundever" sin tilde, y quien busca escribe "Toberín" (y al revés)"""
    buscado = _sin_tildes(identificador)
    coincidencias = [
        n for n in nodos_macro
        if buscado in _sin_tildes(G_multicapa.nodes[n].get("nombre", ""))
    ]
    if len(coincidencias) == 1:
        return coincidencias[0]
    if len(coincidencias) > 1:
        nombres = [G_multicapa.nodes[n]["nombre"] for n in coincidencias]
        raise EstacionNoEncontradaError(f"'{identificador}' es ambiguo: {nombres}")
    raise EstacionNoEncontradaError(f"No se encontró ninguna estación para: '{identificador}'")


def _mejor_penalizacion(clase) -> float:
    """En Overture cada segmento tiene una sola clase; la lista se sigue
    aceptando porque no cuesta nada (OSMnx juntaba varias al simplificar)."""
    valores = clase if isinstance(clase, list) else [clase]
    return min(PENALIZACION_VIAL.get(v, PENALIZACION_DEFECTO) for v in valores)


def calcular_costo_brt(G_multicapa: nx.MultiDiGraph) -> None:
    """Anota 'tiempo_brt_min' en cada arista de la malla vial.

    Raises:
        ValueError: si alguna arista micro no trae ATRIBUTO_CLASE_VIAL. Sin
            esta verificación, un grafo armado con la caché vieja de OSMnx
            (que trae 'highway', no 'class') caería entero en
            PENALIZACION_DEFECTO y daría rutas sin ningún error.
    """
    sin_clase = sum(1 for _, _, d in G_multicapa.edges(data=True)
                    if d.get("layer") == "micro" and ATRIBUTO_CLASE_VIAL not in d)
    if sin_clase:
        raise ValueError(
            f"{sin_clase} aristas de la malla vial no traen '{ATRIBUTO_CLASE_VIAL}' (jerarquía vial de "
            f"Overture). Si vienen de la versión OSMnx, regenerar la malla con obtener_malla_vial()."
        )
    for _, _, datos in G_multicapa.edges(data=True):
        if datos.get("layer") != "micro":
            continue
        largo_m = datos.get("length", 0.0)
        factor = _mejor_penalizacion(datos.get(ATRIBUTO_CLASE_VIAL))
        datos["tiempo_brt_min"] = (largo_m / 1000) / VELOCIDAD_BRT_KMH * 60 * factor


def tiempo_troncal_min(d: dict, transbordo_min: float = TRANSBORDO_MIN) -> float:
    """Minutos de una arista de la red troncal existente: su largo por el
    trazado a VELOCIDAD_BRT_KMH, más config.TRANSBORDO_MIN si es un cruce
    entre troncales (un transbordo). Es la única definición: la usan la ruta
    actual que muestra la app (sugerir_nueva_troncal) y las métricas de la
    red (routing/metricas.py), para que la app y el informe midan igual."""
    transbordo = transbordo_min if d.get("tipo") == TIPO_ARISTA_CRUCE else 0.0
    return (d["weight"] / 1000) / VELOCIDAD_BRT_KMH * 60 + transbordo


def _tiempo_arista(d: dict) -> float | None:
    """Minutos para recorrer una arista, según su capa; None si no es de
    ninguna de las tres (no se puede usar en una ruta)."""
    capa = d.get("layer")
    if capa == "micro":
        return d["tiempo_brt_min"]
    if capa == "transferencia":
        return (d["weight"] / 1000) / VELOCIDAD_CAMINATA_KMH * 60
    if capa == "macro":
        return tiempo_troncal_min(d)
    return None


def _mejor_arista(datos_multi: dict) -> dict:
    mejor, mejor_tiempo = None, float("inf")
    for d in datos_multi.values():
        t = _tiempo_arista(d)
        if t is not None and t < mejor_tiempo:
            mejor_tiempo, mejor = t, d
    return mejor


def _peso_tiempo(u, v, datos_multi):
    """Peso para nx.shortest_path en un MultiDiGraph: la mejor de las aristas paralelas."""
    arista = _mejor_arista(datos_multi)
    return None if arista is None else _tiempo_arista(arista)


def peso_arista(u, v, datos: dict) -> float | None:
    """Peso para graph.giros.camino_respetando_giros: una arista a la vez,
    porque cuál de dos piezas paralelas se puede tomar depende del giro."""
    return _tiempo_arista(datos)


def _arista_del_camino(G_multicapa: nx.MultiDiGraph, camino: list, claves: list | None, i: int) -> dict:
    """Datos de la arista i del camino: la de la clave que usó la ruta si se
    conoce (camino_respetando_giros la devuelve), o la mejor de las paralelas
    (lo que hace nx.shortest_path)."""
    u, v = camino[i], camino[i + 1]
    if claves is not None:
        return G_multicapa.edges[u, v, claves[i]]
    return _mejor_arista(G_multicapa.get_edge_data(u, v))


def _estaciones_intermedias(G_multicapa: nx.MultiDiGraph, camino: list,
                              espaciado_min_m: float = ESPACIADO_ESTACIONES_M, claves: list | None = None) -> list:
    paradas = [camino[0]]
    acumulado = 0.0
    for i in range(len(camino) - 1):
        v = camino[i + 1]
        arista = _arista_del_camino(G_multicapa, camino, claves, i)
        largo_m = arista.get("length", arista.get("weight", 0.0))
        acumulado += largo_m
        if acumulado >= espaciado_min_m and v != camino[-1]:
            paradas.append(v)
            acumulado = 0.0
    if paradas[-1] != camino[-1]:
        paradas.append(camino[-1])
    return paradas


def _geometria_lonlat(G_multicapa, camino):
    """Solo la posición de cada nodo. Sirve para marcar puntos sueltos (las
    paradas); para dibujar un recorrido usar _geometria_ruta_lonlat."""
    coords = []
    for nodo in camino:
        d = G_multicapa.nodes[nodo]
        lon, lat = _TRANSFORMADOR.transform(d["x"], d["y"])
        coords.append([round(lon, 6), round(lat, 6)])
    return coords


def _geometria_ruta_lonlat(G_multicapa, camino, claves: list | None = None):
    """Línea del recorrido siguiendo la forma real de cada calle.

    Por qué no basta con unir los nodos: en la malla un nodo es una
    intersección (un conector de Overture), y entre dos intersecciones la
    calle puede curvarse, rodear un parque o seguir una glorieta. Unir los
    nodos con rectas dibuja la cuerda de esa curva, que pasa por encima de
    manzanas y edificios aunque la ruta calculada sí vaya por la calle.
    La forma está en la 'geometry' de cada arista (EPSG:3116, orientada de
    u a v): en las micro sale de Overture (micro.py) y en las macro, del
    trazado oficial (graph/geometria_troncal.py), así que se concatenan
    esas líneas.

    La posición de los nodos solo se usa en los extremos de la ruta y en
    las aristas sin forma propia (las transferencias, que son una recta
    corta entre la estación y la calle). No se intercala en cada nodo: el
    punto de una estación puede quedar a metros del trazado (hasta ~200 m
    en un portal), y pasar por él en cada estación intermedia dibujaría un
    pico de ida y vuelta.
    """
    if not camino:
        return []
    xs, ys = [], []

    def agregar(puntos):
        for x, y in puntos:
            if xs and abs(xs[-1] - x) < 1e-6 and abs(ys[-1] - y) < 1e-6:
                continue  # el inicio de cada tramo repite el final del anterior
            xs.append(x)
            ys.append(y)

    inicio = G_multicapa.nodes[camino[0]]
    agregar([(inicio["x"], inicio["y"])])
    for i, v in enumerate(camino[1:]):
        arista = _arista_del_camino(G_multicapa, camino, claves, i)  # la misma que usó la ruta
        geom = arista.get("geometry") if arista else None
        if geom is not None and not geom.is_empty:
            agregar(list(geom.coords))
        else:
            destino = G_multicapa.nodes[v]
            agregar([(destino["x"], destino["y"])])
    fin = G_multicapa.nodes[camino[-1]]
    agregar([(fin["x"], fin["y"])])

    lons, lats = _TRANSFORMADOR.transform(xs, ys)
    return [[round(lon, 6), round(lat, 6)] for lon, lat in zip(lons, lats)]


def es_apta_para_troncal(datos: dict) -> bool:
    """¿Puede ir una troncal por esta arista de la malla vial? Clase vial en
    CLASES_APTAS_TRONCAL y sin marca de no apta (superficie, restricción para
    el bus o lista manual; ver micro.py y correcciones.py)."""
    return datos.get("apta_troncal", True) and datos.get(ATRIBUTO_CLASE_VIAL) in CLASES_APTAS_TRONCAL


def aristas_ruta_nueva(G_multicapa: nx.MultiDiGraph, id_origen: str, id_destino: str) -> list[tuple]:
    """Aristas por las que puede ir la ruta de una troncal nueva entre dos
    estaciones: las de la malla vial aptas para una troncal, más las
    transferencias del origen y del destino.

    Excepción de acceso: las aristas de clase vial menor que quedan enteras
    a menos de RADIO_ACCESO_TRONCAL_M de cualquiera de las dos estaciones
    también se permiten (no las marcadas como no aptas por superficie,
    restricción o lista manual). Una estación puede estar enganchada a una
    calle residencial y la ruta tiene que poder llegar desde ahí al
    corredor; más allá del radio, una troncal ya no puede ir por esas vías.

    Es la misma selección para sugerir_nueva_troncal() y para los scripts de
    diagnóstico, para que todos midan la misma ruta.
    """
    claves_acceso, arbol = _indice_acceso(G_multicapa)
    cerca = set()
    for estacion in (id_origen, id_destino):
        circulo = Point(G_multicapa.nodes[estacion]["x"], G_multicapa.nodes[estacion]["y"]).buffer(
            RADIO_ACCESO_TRONCAL_M)
        """la arista tiene que quedar ENTERA dentro del radio, no solo tocarlo: si bastara con
         tocarlo, una calle residencial que arranca junto a la estación y sigue 2 km quedaría
         permitida completa, y la excepción de acceso se volvería un atajo"""
        cerca.update(claves_acceso[i] for i in arbol.query(circulo, predicate="contains"))
    extremos = (id_origen, id_destino)
    return [(u, v, k) for u, v, k, d in G_multicapa.edges(keys=True, data=True)
            if (d.get("layer") == "micro" and (es_apta_para_troncal(d) or (u, v, k) in cerca))
            or (d.get("layer") == "transferencia" and (u in extremos or v in extremos))]


def _indice_acceso(G_multicapa: nx.MultiDiGraph) -> tuple[list, STRtree]:
    """Árbol espacial de las aristas que solo sirven como acceso (clase menor
    pero sin otra marca de no apta). Se arma una vez por grafo y se guarda en
    G.graph: el grafo no cambia después de construir_estado()."""
    cache = G_multicapa.graph.get("_indice_acceso_troncal")
    if cache is None:
        claves, geometrias = [], []
        for u, v, k, d in G_multicapa.edges(keys=True, data=True):
            if (d.get("layer") == "micro" and d.get("apta_troncal", True)
                    and d.get(ATRIBUTO_CLASE_VIAL) not in CLASES_APTAS_TRONCAL):
                claves.append((u, v, k))
                geometrias.append(d["geometry"])
        cache = (claves, STRtree(geometrias))
        G_multicapa.graph["_indice_acceso_troncal"] = cache
    return cache


def ruta_nueva(G_multicapa: nx.MultiDiGraph, id_origen: str, id_destino: str) -> tuple[list, list, float]:
    """La ruta de una troncal nueva entre dos estaciones (ids ya resueltos):
    solo por aristas_ruta_nueva, en el sentido de cada vía, sin giros
    prohibidos y sin vueltas en U (config.GIRO_MAXIMO_BUS_GRADOS). Es la que
    usan sugerir_nueva_troncal() y los diagnósticos.

    Returns:
        (nodos, claves, minutos); ver graph.giros.camino_respetando_giros.

    Raises:
        nx.NetworkXNoPath: si no hay ruta por vías aptas que cumpla las reglas de giro.
    """
    return camino_respetando_giros(G_multicapa, id_origen, id_destino, peso_arista,
                                   aristas=aristas_ruta_nueva(G_multicapa, id_origen, id_destino))


def sugerir_nueva_troncal(G_multicapa: nx.MultiDiGraph, id_origen: str, id_destino: str) -> dict:
    """Compara tiempo actual (solo red troncal existente, con
    config.TRANSBORDO_MIN por cada transbordo, igual que las métricas de la
    red) contra tiempo de una ruta nueva (solo vías aptas para una troncal,
    penalizadas por jerarquía, sin giros prohibidos ni vueltas en U; ver
    ruta_nueva). Requiere haber llamado calcular_costo_brt(G_multicapa) antes.

    Raises:
        nx.NetworkXNoPath: si no hay ruta por vías aptas que cumpla las
            reglas de giro entre las dos estaciones.
    """
    id_origen = _resolver_estacion(G_multicapa, id_origen)
    id_destino = _resolver_estacion(G_multicapa, id_destino)

    resultado = {
        "estacion_origen": id_origen,
        "estacion_destino": id_destino,
        "tiempo_actual_min": None,
        "transbordos_actuales": None,
        "transbordo_min": TRANSBORDO_MIN,
        "geometria_actual_lonlat": None,
        "tiempo_nueva_ruta_min": None,
        "ahorro_min": None,
        "geometria_lonlat": None,
        "estaciones_intermedias_lonlat": None,
    }

    # 1. Línea base: solo la red troncal existente, cobrando cada transbordo (tiempo_troncal_min)
    aristas_macro = [(u, v, k) for u, v, k, d in G_multicapa.edges(keys=True, data=True)
                      if d.get("layer") == "macro"]
    G_macro = G_multicapa.edge_subgraph(aristas_macro)
    try:
        camino_actual = nx.shortest_path(G_macro, id_origen, id_destino, weight=_peso_tiempo)
        usadas = [_mejor_arista(G_macro.get_edge_data(u, v)) for u, v in zip(camino_actual[:-1], camino_actual[1:])]
        resultado["tiempo_actual_min"] = round(sum(_tiempo_arista(d) for d in usadas), 2)
        resultado["transbordos_actuales"] = sum(1 for d in usadas if d.get("tipo") == TIPO_ARISTA_CRUCE)
        resultado["geometria_actual_lonlat"] = _geometria_ruta_lonlat(G_multicapa, camino_actual)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass  # sin conexión directa por troncal existente -- se documenta como limitación

    # 2 y 3. Ruta propuesta: solo vías aptas para una troncal + las 2 transferencias relevantes,
    # sin giros prohibidos ni vueltas en U
    camino, claves, tiempo_nuevo = ruta_nueva(G_multicapa, id_origen, id_destino)

    resultado["tiempo_nueva_ruta_min"] = round(tiempo_nuevo, 2)
    resultado["geometria_lonlat"] = _geometria_ruta_lonlat(G_multicapa, camino, claves)

    paradas = _estaciones_intermedias(G_multicapa, camino, claves=claves)
    resultado["estaciones_intermedias_lonlat"] = _geometria_lonlat(G_multicapa, paradas)

    if resultado["tiempo_actual_min"] is not None:
        resultado["ahorro_min"] = round(resultado["tiempo_actual_min"] - tiempo_nuevo, 2)

    return resultado


def identificar_pares_criticos(G_multicapa: nx.MultiDiGraph, top_n: int = 5,
                               radio_m: float = RADIO_PAR_CRITICO_M) -> list:
    """Pares de estaciones que están cerca en línea recta pero lejos por la
    red troncal: las candidatas de más impacto para una conexión nueva.

    Criterio: para cada par de estaciones a no más de 'radio_m' en línea
    recta, el factor de rodeo = distancia por la red troncal / distancia
    en línea recta. Un par sin ninguna conexión troncal tiene rodeo
    infinito y va primero (entre ellos, el más cercano primero), que es
    exactamente lo que hacía la versión anterior mientras la red estaba
    partida en varios pedazos. Desde que los cruces entre troncales
    (graph/cruces.py) dejaron la red en una sola pieza, comparar pedazos ya
    no daba ningún par; el factor de rodeo generaliza ese criterio sin
    depender de que haya pedazos sueltos.

    Para que el top no se llene de variantes del mismo hueco (cinco pares
    de estaciones vecinas entre las mismas dos troncales), se toma un solo
    par por combinación de troncales (id_trazado), el de mayor rodeo.

    Returns:
        El resultado completo de sugerir_nueva_troncal para los 'top_n'
        pares, más 'distancia_geometrica_m' (línea recta) y
        'factor_rodeo' (None si no hay conexión troncal).
    """
    aristas_macro = [(u, v, k) for u, v, k, d in G_multicapa.edges(keys=True, data=True)
                     if d.get("layer") == "macro"]
    G_macro = G_multicapa.edge_subgraph(aristas_macro)
    """sorted(): el orden de recorrido decide los empates, y con sets dependía de PYTHONHASHSEED"""
    estaciones = sorted(n for n, d in G_multicapa.nodes(data=True) if d.get("layer") == "macro")

    def posicion(n):
        return G_multicapa.nodes[n]["x"], G_multicapa.nodes[n]["y"]

    mejor_por_troncales = {}
    for i, a in enumerate(estaciones):
        xa, ya = posicion(a)
        cercanas = []
        for b in estaciones[i + 1:]:
            xb, yb = posicion(b)
            d = ((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5
            if 0 < d <= radio_m:
                cercanas.append((b, d))
        if not cercanas:
            continue
        por_red = nx.single_source_dijkstra_path_length(G_macro, a, weight="weight") if a in G_macro else {}
        for b, d in cercanas:
            rodeo = por_red[b] / d if b in por_red else float("inf")
            troncales = tuple(sorted((G_multicapa.nodes[a].get("id_trazado", ""),
                                      G_multicapa.nodes[b].get("id_trazado", ""))))
            clave = (-rodeo, d)  # más rodeo primero; a igual rodeo (inf), más cercano primero
            if troncales not in mejor_por_troncales or clave < mejor_por_troncales[troncales][0]:
                mejor_por_troncales[troncales] = (clave, a, b, d, rodeo)

    candidatos = sorted(mejor_por_troncales.values(), key=lambda c: (c[0], c[1], c[2]))
    resultados = []
    for _, a, b, d, rodeo in candidatos:
        if len(resultados) == top_n:
            break
        try:
            r = sugerir_nueva_troncal(G_multicapa, a, b)
        except nx.NetworkXNoPath:
            """sin ruta por vías aptas para una troncal: no hay corredor que proponer entre
             ese par, y no debe tumbar la lista entera; se sigue con el siguiente"""
            continue
        r["distancia_geometrica_m"] = round(d, 1)
        r["factor_rodeo"] = None if rodeo == float("inf") else round(rodeo, 2)
        resultados.append(r)
    return resultados
