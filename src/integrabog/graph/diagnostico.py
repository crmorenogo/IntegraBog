import networkx as nx


def diagnosticar_grafo(G: nx.Graph, etiqueta_nodo: str = "nombre") -> None:
    G_no_dirigido = G.to_undirected() if G.is_directed() else G
    print(f"Nodos: {G.number_of_nodes()} | Aristas: {G.number_of_edges()}")
    print(f"Componentes conexas: {nx.number_connected_components(G_no_dirigido)}")

    aislados = [n for n, grado in G.degree() if grado == 0]
    if aislados:
        print(f"Nodos con grado 0 ({len(aislados)}):")
        for n in aislados:
            print(f"  - {G.nodes[n].get(etiqueta_nodo, n)}")
