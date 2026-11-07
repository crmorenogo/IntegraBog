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

    # --- EXTENSIÓN PREVISTA (no implementada): diámetro del grafo ---
    # Va aquí, justo después de contar componentes, porque nx.diameter solo está
    # definido sobre un grafo conexo (lanza NetworkXError si no): se calcula sobre la
    # componente conexa más grande de G_no_dirigido, no sobre G entero. El macro tiene
    # varias componentes (troncales que no comparten estación), así que esto aplica a
    # los dos grafos por igual:
    #     principal = G_no_dirigido.subgraph(max(nx.connected_components(G_no_dirigido), key=len))
    #     print(f"Diámetro (saltos, componente principal): {nx.diameter(principal)}")
    # Ojo con el costo: nx.diameter corre un BFS desde cada nodo, O(n·m). En el macro
    # (150 nodos) es instantáneo; en el multicapa (~55.000 nodos, ~143.000 aristas) son
    # ~55.000 BFS -- ahí conviene nx.approximation.diameter (cota inferior por barridos
    # dobles, segundos en vez de horas) o restringirlo a la capa macro.

    aislados = [n for n, grado in G.degree() if grado == 0]
    if aislados:
        print(f"Nodos con grado 0 ({len(aislados)}):")
        for n in aislados:
            # .get() con respaldo, no acceso directo -- ver docstring del parámetro etiqueta_nodo
            print(f"  - {G.nodes[n].get(etiqueta_nodo, n)}")
