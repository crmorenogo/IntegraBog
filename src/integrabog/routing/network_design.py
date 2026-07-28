"""
Motor de sugerencia de infraestructura (Fase 4): compara el tiempo actual
por la red troncal existente contra el tiempo de una ruta nueva propuesta
sobre la malla vial, penalizada según la jerarquía de cada calle.
"""

import networkx as nx
from pyproj import Transformer

VELOCIDAD_BRT_KMH = 25.2
VELOCIDAD_CAMINATA_KMH = 4.5
ESPACIADO_ESTACIONES_M = 500.0

PENALIZACION_VIAL = {
    "motorway": 1.0,
    "motorway_link": 1.0,
    "trunk": 1.0,
    "trunk_link": 1.0,
    "primary": 1.15,
    "primary_link": 1.15,
    "secondary": 1.6,
    "secondary_link": 1.6,
    "tertiary": 3.0,
    "tertiary_link": 3.0,
    "residential": 10.0,
    "living_street": 10.0,
    "unclassified": 10.0,
}
PENALIZACION_DEFECTO = 10.0

_TRANSFORMADOR = Transformer.from_crs("EPSG:3116", "EPSG:4326", always_xy=True)


class EstacionNoEncontradaError(Exception):
    """La estación buscada no existe, o el nombre es ambiguo."""


def _resolver_estacion(G_multicapa: nx.MultiDiGraph, identificador: str) -> str:
    identificador = str(identificador).strip()
    if identificador in G_multicapa.nodes:
        return identificador
    id_macro = f"macro_{identificador}"
    if id_macro in G_multicapa.nodes:
        return id_macro
    coincidencias = [
        n
        for n, d in G_multicapa.nodes(data=True)
        if d.get("layer") == "macro" and identificador.lower() in d.get("nombre", "").lower()
    ]
    if len(coincidencias) == 1:
        return coincidencias[0]
    if len(coincidencias) > 1:
        nombres = [G_multicapa.nodes[n]["nombre"] for n in coincidencias]
        raise EstacionNoEncontradaError(f"'{identificador}' es ambiguo: {nombres}")
    raise EstacionNoEncontradaError(f"No se encontró ninguna estación para: '{identificador}'")


def _mejor_penalizacion(highway) -> float:
    valores = highway if isinstance(highway, list) else [highway]
    return min(PENALIZACION_VIAL.get(v, PENALIZACION_DEFECTO) for v in valores)


def calcular_costo_brt(G_multicapa: nx.MultiDiGraph) -> None:
    for _, _, datos in G_multicapa.edges(data=True):
        if datos.get("layer") != "micro":
            continue
        largo_m = datos.get("length", 0.0)
        factor = _mejor_penalizacion(datos.get("highway"))
        datos["tiempo_brt_min"] = (largo_m / 1000) / VELOCIDAD_BRT_KMH * 60 * factor


def _mejor_arista(datos_multi: dict) -> dict | None:
    mejor, mejor_tiempo = None, float("inf")
    for d in datos_multi.values():
        capa = d.get("layer")
        if capa == "micro":
            t = d["tiempo_brt_min"]
        elif capa == "transferencia":
            t = (d["weight"] / 1000) / VELOCIDAD_CAMINATA_KMH * 60
        elif capa == "macro":
            t = (d["weight"] / 1000) / VELOCIDAD_BRT_KMH * 60
        else:
            continue
        if t < mejor_tiempo:
            mejor_tiempo, mejor = t, d
    return mejor


def _peso_tiempo(_u, _v, datos_multi):
    arista = _mejor_arista(datos_multi)
    if arista is None:
        return None
    capa = arista.get("layer")
    if capa == "micro":
        return arista["tiempo_brt_min"]
    if capa == "transferencia":
        return (arista["weight"] / 1000) / VELOCIDAD_CAMINATA_KMH * 60
    return (arista["weight"] / 1000) / VELOCIDAD_BRT_KMH * 60


def _estaciones_intermedias(
    G_multicapa: nx.MultiDiGraph, camino: list, espaciado_min_m: float = ESPACIADO_ESTACIONES_M
) -> list:
    paradas = [camino[0]]
    acumulado = 0.0
    for i in range(len(camino) - 1):
        u, v = camino[i], camino[i + 1]
        arista = _mejor_arista(G_multicapa.get_edge_data(u, v))
        if arista is None:
            continue
        largo_m = arista.get("length", arista.get("weight", 0.0))
        acumulado += largo_m
        if acumulado >= espaciado_min_m and v != camino[-1]:
            paradas.append(v)
            acumulado = 0.0
    if paradas[-1] != camino[-1]:
        paradas.append(camino[-1])
    return paradas


def _geometria_lonlat(G_multicapa, camino):
    coords = []
    for nodo in camino:
        d = G_multicapa.nodes[nodo]
        lon, lat = _TRANSFORMADOR.transform(d["x"], d["y"])
        coords.append([round(lon, 6), round(lat, 6)])
    return coords


def sugerir_nueva_troncal(G_multicapa: nx.MultiDiGraph, id_origen: str, id_destino: str) -> dict:
    """Compara tiempo actual (solo red troncal existente) contra tiempo
    de una ruta nueva (solo malla vial, penalizada). Requiere haber
    llamado calcular_costo_brt(G_multicapa) antes."""
    id_origen = _resolver_estacion(G_multicapa, id_origen)
    id_destino = _resolver_estacion(G_multicapa, id_destino)

    resultado = {
        "estacion_origen": id_origen,
        "estacion_destino": id_destino,
        "tiempo_actual_min": None,
        "geometria_actual_lonlat": None,
        "tiempo_nueva_ruta_min": None,
        "ahorro_min": None,
        "geometria_lonlat": None,
        "estaciones_intermedias_lonlat": None,
    }

    # 1. Línea base: solo la red troncal existente
    aristas_macro = [
        (u, v, k)
        for u, v, k, d in G_multicapa.edges(keys=True, data=True)
        if d.get("layer") == "macro"
    ]
    G_macro = G_multicapa.edge_subgraph(aristas_macro)
    try:
        camino_actual = nx.shortest_path(G_macro, id_origen, id_destino, weight=_peso_tiempo)
        resultado["tiempo_actual_min"] = round(
            nx.shortest_path_length(G_macro, id_origen, id_destino, weight=_peso_tiempo), 2
        )
        resultado["geometria_actual_lonlat"] = _geometria_lonlat(G_multicapa, camino_actual)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass  # sin conexión directa por troncal existente -- se documenta como limitación

    # 2 y 3. Ruta propuesta: solo malla vial + las 2 transferencias relevantes
    aristas_ruta = [
        (u, v, k)
        for u, v, k, d in G_multicapa.edges(keys=True, data=True)
        if d.get("layer") == "micro"
        or (
            d.get("layer") == "transferencia"
            and (u in (id_origen, id_destino) or v in (id_origen, id_destino))
        )
    ]
    G_ruta = G_multicapa.edge_subgraph(aristas_ruta)
    camino = nx.shortest_path(G_ruta, id_origen, id_destino, weight=_peso_tiempo)
    tiempo_nuevo = nx.shortest_path_length(G_ruta, id_origen, id_destino, weight=_peso_tiempo)

    resultado["tiempo_nueva_ruta_min"] = round(tiempo_nuevo, 2)
    resultado["geometria_lonlat"] = _geometria_lonlat(G_multicapa, camino)

    paradas = _estaciones_intermedias(G_multicapa, camino)
    resultado["estaciones_intermedias_lonlat"] = _geometria_lonlat(G_multicapa, paradas)

    if resultado["tiempo_actual_min"] is not None:
        resultado["ahorro_min"] = round(resultado["tiempo_actual_min"] - tiempo_nuevo, 2)

    return resultado


def identificar_pares_criticos(G_multicapa: nx.MultiDiGraph, top_n: int = 5) -> list:
    """Para cada par de componentes conexas del grafo macro (troncales que
    hoy no comparten estación), halla las dos estaciones geométricamente
    más cercanas entre sí -- candidatas de alto impacto porque están
    físicamente cerca pero desconectadas en la red actual. Devuelve el
    resultado completo de sugerir_nueva_troncal para los 'top_n' pares
    más cercanos, más su distancia geométrica en línea recta."""
    aristas_macro = [
        (u, v, k)
        for u, v, k, d in G_multicapa.edges(keys=True, data=True)
        if d.get("layer") == "macro"
    ]
    G_macro = G_multicapa.edge_subgraph(aristas_macro)
    componentes = list(nx.weakly_connected_components(G_macro))

    candidatos = []
    for i in range(len(componentes)):
        for j in range(i + 1, len(componentes)):
            mejor_dist, mejor_par = float("inf"), None
            for a in componentes[i]:
                xa, ya = G_multicapa.nodes[a]["x"], G_multicapa.nodes[a]["y"]
                for b in componentes[j]:
                    xb, yb = G_multicapa.nodes[b]["x"], G_multicapa.nodes[b]["y"]
                    d = ((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5
                    if d < mejor_dist:
                        mejor_dist, mejor_par = d, (a, b)
            if mejor_par is not None:
                candidatos.append((mejor_dist, mejor_par))

    candidatos.sort(key=lambda c: c[0])
    resultados = []
    for dist_geometrica, (a, b) in candidatos[:top_n]:
        r = sugerir_nueva_troncal(G_multicapa, a, b)
        r["distancia_geometrica_m"] = round(dist_geometrica, 1)
        resultados.append(r)
    return resultados
