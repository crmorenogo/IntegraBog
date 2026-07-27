"""
Construcción del grafo macro completo (estaciones + aristas + costura)
a partir de los datos crudos de TransMilenio.

Junta en un solo punto de entrada lo que loader.py, snapping.py,
builder.py y costura.py resuelven por separado. Nadie fuera de este
archivo debería tener que llamar a esos cuatro módulos en orden a
mano -- si algún día cambia el orden interno o se agrega un paso, se
cambia acá y el resto del proyecto ni se entera.
"""

import networkx as nx

from integrabog.data.loader import cargar_estaciones, cargar_trazado
from integrabog.graph.builder import construir_aristas, construir_nodos
from integrabog.graph.costura import calcular_aristas_costura
from integrabog.graph.snapping import acoplar_estaciones, explotar_tramos


def construir_grafo_macro() -> nx.DiGraph:
    """Arma el grafo macro de punta a punta: carga, acople, nodos,
    aristas y costura.

    Returns:
        Grafo dirigido con las 150 estaciones de TransMilenio como
        nodos y sus conexiones (por tramo + costura) como aristas, listo
        para usarse tal cual o para fusionarse con el grafo micro en
        multilayer.py.
    """
    estaciones = cargar_estaciones()
    tramos = explotar_tramos(cargar_trazado())

    G = nx.DiGraph()
    construir_nodos(G, estaciones)

    acoples = acoplar_estaciones(estaciones, tramos)
    construir_aristas(G, acoples)

    """validación contra el propio dato oficial, no contra un supuesto propio: si el acople
     geométrico (snapping.py) se desvía de lo que dice id_trazado, esto es lo que lo delata"""
    referencia = estaciones.set_index("cod_nodo")["id_trazado"]
    inferido = acoples.set_index("cod_nodo")["id_trazado"]
    coincidencia = (inferido == referencia.loc[inferido.index]).mean() * 100
    print(f"Validación acople vs id_trazado real: {coincidencia:.1f}%")

    """la costura va DESPUÉS de tener ya el grafo base armado -- necesita saber qué tramos
     quedaron sin ninguna estación acoplada, y eso solo se sabe una vez existe 'acoples'"""
    n_costuras = calcular_aristas_costura(G, tramos, acoples)
    print(f"Aristas de costura agregadas: {n_costuras}")

    return G
