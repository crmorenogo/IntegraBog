"""
Construcción del grafo macro completo (estaciones + aristas + costura)
a partir de los datos crudos de TransMilenio.
"""

import networkx as nx

from integrabog.data.loader import cargar_estaciones, cargar_trazado
from integrabog.graph.builder import construir_aristas, construir_nodos
from integrabog.graph.costura import calcular_aristas_costura
from integrabog.graph.snapping import acoplar_estaciones, explotar_tramos


def construir_grafo_macro() -> nx.DiGraph:
    """Arma el grafo macro de punta a punta: carga, acople, nodos, aristas
    y costura."""
    estaciones = cargar_estaciones()
    tramos = explotar_tramos(cargar_trazado())

    G = nx.DiGraph()
    construir_nodos(G, estaciones)

    acoples = acoplar_estaciones(estaciones, tramos)
    construir_aristas(G, acoples)

    referencia = estaciones.set_index("cod_nodo")["id_trazado"]
    inferido = acoples.set_index("cod_nodo")["id_trazado"]
    coincidencia = (inferido == referencia.loc[inferido.index]).mean() * 100
    print(f"Validación acople vs id_trazado real: {coincidencia:.1f}%")

    n_costuras = calcular_aristas_costura(G, tramos, acoples)
    print(f"Aristas de costura agregadas: {n_costuras}")

    return G
