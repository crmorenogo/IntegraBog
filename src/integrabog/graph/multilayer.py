import networkx as nx
import osmnx as ox


def _namespacear(G: nx.Graph, prefijo: str, capa: str) -> nx.MultiDiGraph:
    G_renombrado = nx.relabel_nodes(G, {n: f"{prefijo}_{n}" for n in G.nodes})
    nx.set_node_attributes(G_renombrado, capa, "layer")
    nx.set_edge_attributes(G_renombrado, capa, "layer")
    if isinstance(G_renombrado, nx.MultiDiGraph):
        return G_renombrado
    return nx.MultiDiGraph(G_renombrado)


def construir_grafo_multicapa(G_macro: nx.DiGraph, G_micro: nx.MultiDiGraph) -> nx.MultiDiGraph:
    G_macro_capa = _namespacear(G_macro, "macro", "macro")
    G_micro_capa = _namespacear(G_micro, "micro", "micro")

    g_multicapa = nx.compose(G_macro_capa, G_micro_capa)

    estaciones = [(n, d["x"], d["y"]) for n, d in G_macro_capa.nodes(data=True)]
    ids_estacion, xs, ys = zip(*estaciones, strict=False)
    nodos_viales, distancias = ox.distance.nearest_nodes(
        G_micro_capa, X=list(xs), Y=list(ys), return_dist=True
    )

    for id_estacion, id_vial, dist in zip(ids_estacion, nodos_viales, distancias, strict=False):
        peso = round(float(dist), 2)
        g_multicapa.add_edge(id_estacion, id_vial, weight=peso, layer="transferencia")
        g_multicapa.add_edge(id_vial, id_estacion, weight=peso, layer="transferencia")

    return g_multicapa
