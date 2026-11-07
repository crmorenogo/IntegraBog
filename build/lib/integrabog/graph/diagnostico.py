"""
Diagnóstico genérico de un grafo: tamaño, conexidad y nodos aislados.
Sirve igual para el grafo macro solo que para el multicapa completo --
por eso vive aparte y no dentro de macro.py o multilayer.py, para no
terminar con la misma función copiada dos veces con un print distinto
cada vez.
"""
import networkx as nx


def diagnosticar_grafo(G: nx.Graph, etiqueta_nodo: str = "nombre") -> None:
    """Imprime nodos, aristas, componentes conexas y nodos de grado 0.

    Args:
        G: grafo a diagnosticar, dirigido o no. Si es dirigido se
            convierte a no dirigido solo para contar componentes --
            "conexo" acá significa alcanzable ignorando sentido, no
            fuertemente conexo.
        etiqueta_nodo: atributo a mostrar por cada nodo aislado.
            'nombre' sirve para el grafo macro; en el multicapa, los
            nodos de la capa micro no tienen ese atributo (son
            intersecciones, no estaciones), así que si falta se cae al
            propio ID del nodo en vez de reventar con KeyError.
    """
    G_no_dirigido = G.to_undirected() if G.is_directed() else G
    print(f"Nodos: {G.number_of_nodes()} | Aristas: {G.number_of_edges()}")
    print(f"Componentes conexas: {nx.number_connected_components(G_no_dirigido)}")

    aislados = [n for n, grado in G.degree() if grado == 0]
    if aislados:
        print(f"Nodos con grado 0 ({len(aislados)}):")
        for n in aislados:
            # .get() con respaldo, no acceso directo -- ver docstring del parámetro etiqueta_nodo
            print(f"  - {G.nodes[n].get(etiqueta_nodo, n)}")