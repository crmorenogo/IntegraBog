"""
Fusión de los grafos Macro (estaciones TransMilenio) y Micro (malla vial)
en un único grafo multicapa, con aristas de transferencia peatonal entre
cada estación y su intersección vial más cercana.

El problema concreto que resuelve _namespacear(): después de consolidar
intersecciones, OSMnx reasigna los IDs de nodo del grafo micro como
enteros secuenciales desde 0 -- y ese rango se solapa por completo con
los cod_nodo reales de TransMilenio (2.000 a 14.005). Verificado
directo: con un grafo vial de escala real, las 150 de 150 estaciones
tenían un ID que también existía en la malla vial. Fusionar los dos
grafos sin prefijo antes (con nx.compose tal cual) sobreescribe en
silencio los atributos de una estación real con los de una intersección
cualquiera -- sin ningún error, solo datos corruptos. El prefijo
elimina la colisión por construcción.
"""

import networkx as nx
import osmnx as ox


def _namespacear(G: nx.Graph, prefijo: str, capa: str) -> nx.MultiDiGraph:
    """Renombra cada nodo como '{prefijo}_{id_original}' -- elimina de raíz
    cualquier colisión de IDs entre capas -- y marca nodos y aristas con
    el atributo 'layer' para el filtrado visual futuro.

    Args:
        G: grafo de una sola capa (macro o micro), sin namespacing
            todavía.
        prefijo: prefijo a anteponer a cada ID de nodo ('macro' o
            'micro').
        capa: valor del atributo 'layer' a asignar a todos los nodos y
            aristas de G.

    Returns:
        Copia de G con nodos renombrados y atributo 'layer' agregado,
        siempre como MultiDiGraph -- el grafo macro llega como DiGraph
        simple, pero tiene que salir de acá ya convertido, porque
        nx.compose exige que ambos grafos sean del mismo tipo, y el
        grafo final necesita ser MultiDiGraph para no perder aristas
        paralelas reales de la malla vial.
    """
    G_renombrado = nx.relabel_nodes(G, {n: f"{prefijo}_{n}" for n in G.nodes})
    nx.set_node_attributes(G_renombrado, capa, "layer")
    nx.set_edge_attributes(G_renombrado, capa, "layer")
    if isinstance(G_renombrado, nx.MultiDiGraph):
        return G_renombrado
    return nx.MultiDiGraph(G_renombrado)  # DiGraph -> MultiDiGraph, sin pérdida de datos


def construir_grafo_multicapa(G_macro: nx.DiGraph, G_micro: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Combina macro y micro con IDs namespaced, y agrega aristas de
    transferencia bidireccionales entre cada estación y su nodo vial más
    cercano, con peso = distancia euclidiana en metros (EPSG:3116).

    Args:
        G_macro: grafo de estaciones de TransMilenio (construir_grafo_macro()).
        G_micro: grafo de malla vial ya consolidado (obtener_malla_vial()).

    Returns:
        Grafo multicapa único: nodos y aristas de ambas capas con IDs
        prefijados y atributo 'layer', más una arista de transferencia
        en cada sentido por cada estación.
    """
    G_macro_capa = _namespacear(G_macro, "macro", "macro")
    G_micro_capa = _namespacear(G_micro, "micro", "micro")

    G_multicapa = nx.compose(G_macro_capa, G_micro_capa)

    """snapping vectorizado: todas las estaciones contra el grafo vial en una sola llamada,
     no un nearest_nodes por estación -- con 150 estaciones y ~50.000 nodos viales, hacerlo
     de a uno sería 150 búsquedas independientes en vez de una sola búsqueda por lotes"""
    estaciones = [(n, d["x"], d["y"]) for n, d in G_macro_capa.nodes(data=True)]
    ids_estacion, xs, ys = zip(*estaciones, strict=False)
    nodos_viales, distancias = ox.distance.nearest_nodes(
        G_micro_capa, X=list(xs), Y=list(ys), return_dist=True
    )

    for id_estacion, id_vial, dist in zip(ids_estacion, nodos_viales, distancias, strict=False):
        peso = round(float(dist), 2)
        """ambos sentidos: la transferencia es caminar, y se puede entrar o salir de la
        # estación indistintamente por esa intersección"""
        G_multicapa.add_edge(id_estacion, id_vial, weight=peso, layer="transferencia")
        G_multicapa.add_edge(id_vial, id_estacion, weight=peso, layer="transferencia")

    return G_multicapa
