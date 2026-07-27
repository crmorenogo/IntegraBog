"""
Fusión de los grafos Macro (estaciones TransMilenio) y Micro (malla vial)
en un único grafo multicapa, con aristas de transferencia peatonal entre
cada estación y su intersección vial más cercana.
"""
import networkx as nx
import osmnx as ox


def _namespacear(G: nx.Graph, prefijo: str, capa: str) -> nx.MultiDiGraph:
    """Renombra cada nodo como '{prefijo}_{id_original}' -- elimina de raíz
    cualquier colisión de IDs entre capas -- y marca nodos y aristas con
    el atributo 'layer' para el filtrado visual futuro."""
    G_renombrado = nx.relabel_nodes(G, {n: f"{prefijo}_{n}" for n in G.nodes})
    nx.set_node_attributes(G_renombrado, capa, "layer")
    nx.set_edge_attributes(G_renombrado, capa, "layer")
    if isinstance(G_renombrado, nx.MultiDiGraph):
        return G_renombrado
    return nx.MultiDiGraph(G_renombrado)  # DiGraph -> MultiDiGraph, sin pérdida de datos


def construir_grafo_multicapa(G_macro: nx.DiGraph, G_micro: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Combina macro y micro con IDs namespaced, y agrega aristas de
    transferencia bidireccionales entre cada estación y su nodo vial más
    cercano, con peso = distancia euclidiana en metros (EPSG:3116)."""
    G_macro_capa = _namespacear(G_macro, "macro", "macro")
    G_micro_capa = _namespacear(G_micro, "micro", "micro")

    G_multicapa = nx.compose(G_macro_capa, G_micro_capa)

    # snapping vectorizado: todas las estaciones contra el grafo vial en una sola llamada
    estaciones = [(n, d["x"], d["y"]) for n, d in G_macro_capa.nodes(data=True)]
    ids_estacion, xs, ys = zip(*estaciones, strict=False)
    nodos_viales, distancias = ox.distance.nearest_nodes(
        G_micro_capa, X=list(xs), Y=list(ys), return_dist=True
    )

    for id_estacion, id_vial, dist in zip(ids_estacion, nodos_viales, distancias, strict=False):
        peso = round(float(dist), 2)
        G_multicapa.add_edge(id_estacion, id_vial, weight=peso, layer="transferencia")
        G_multicapa.add_edge(id_vial, id_estacion, weight=peso, layer="transferencia")

    return G_multicapa
