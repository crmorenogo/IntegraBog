"""
Diagnóstico genérico de un grafo: tamaño, conexidad y nodos aislados.
Sirve igual para el grafo macro solo que para el multicapa completo.
"""
import networkx as nx


def diagnosticar_grafo(G: nx.Graph, etiqueta_nodo: str = "nombre") -> None:
    """Imprime nodos, aristas, componentes conexas y nodos de grado 0.
    'etiqueta_nodo' es el atributo a mostrar por cada aislado -- 'nombre'
    sirve para el grafo macro; en el multicapa, los nodos del micro no
    tienen ese atributo, así que se usa el propio ID como respaldo."""
    G_no_dirigido = G.to_undirected() if G.is_directed() else G
    print(f"Nodos: {G.number_of_nodes()} | Aristas: {G.number_of_edges()}")
    print(f"Componentes conexas: {nx.number_connected_components(G_no_dirigido)}")

    aislados = [n for n, grado in G.degree() if grado == 0]
    if aislados:
        print(f"Nodos con grado 0 ({len(aislados)}):")
        for n in aislados:
            print(f"  - {G.nodes[n].get(etiqueta_nodo, n)}")
