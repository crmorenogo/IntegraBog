"""
Costura del grafo macro sobre los datos oficiales de data/raw/.

Las pruebas buscan las estaciones por nombre y no por cod_nodo, y miden
distancias con margen, para que sigan valiendo cuando se actualicen los
archivos de Datos Abiertos.
"""
import math

import networkx as nx
import pytest

from integrabog.graph.macro import construir_grafo_macro


@pytest.fixture(scope="module")
def macro():
    return construir_grafo_macro()


def _nodo(G, nombre):
    encontrados = [n for n, d in G.nodes(data=True) if d["nombre"] == nombre]
    if not encontrados:
        pytest.skip(f"'{nombre}' no está en los datos de estaciones")
    return encontrados[0]


def _conectadas(G, a, b):
    return nx.has_path(G, _nodo(G, a), _nodo(G, b))


def test_tintal_conecta_con_transversal_86_en_ambos_sentidos(macro):
    """Corte de digitalización de 48 m dentro de la troncal Américas."""
    tintal, tv86 = _nodo(macro, "Biblioteca Tintal"), _nodo(macro, "Transversal 86")
    assert macro.has_edge(tintal, tv86) and macro.has_edge(tv86, tintal)
    a, b = macro.nodes[tintal], macro.nodes[tv86]
    recta = math.dist((a["x"], a["y"]), (b["x"], b["y"]))
    assert recta <= macro[tintal][tv86]["weight"] <= 2 * recta  # por el trazado, sin rodeos


def test_portal_americas_llega_por_troncal_a_banderas(macro):
    camino = nx.shortest_path(macro, _nodo(macro, "Portal Américas"), _nodo(macro, "Banderas"), weight="weight")
    nombres = [macro.nodes[n]["nombre"] for n in camino]
    assert "Biblioteca Tintal" in nombres and "Transversal 86" in nombres


@pytest.mark.parametrize("a, b", [
    ("Polo - FINCOMERCIO", "Héroes - Colmena Seguros"),      # Calle 80 con Autopista Norte
    ("Héroes - Colmena Seguros", "Calle 76 - San Felipe"),   # Autopista Norte con Caracas
    ("Ricaurte - NQS", "Comuneros"),                          # NQS Central con NQS Sur
])
def test_cruces_con_transbordo_quedan_conectados(macro, a, b):
    assert _conectadas(macro, a, b)
