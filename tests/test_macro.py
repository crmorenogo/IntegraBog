"""Tests para el módulo graph.macro — construcción del grafo macro."""

import networkx as nx
import pytest


class TestConstruirGrafoMacro:
    """Prueba el pipeline completo desde datos crudos hasta grafo macro."""

    @pytest.mark.slow
    def test_devuelve_digrafo(self):
        from integrabog.graph.macro import construir_grafo_macro

        G = construir_grafo_macro()
        assert isinstance(G, nx.DiGraph)

    @pytest.mark.slow
    def test_tiene_nodos_y_aristas(self):
        from integrabog.graph.macro import construir_grafo_macro

        G = construir_grafo_macro()
        assert G.number_of_nodes() > 0
        assert G.number_of_edges() > 0

    @pytest.mark.slow
    def test_nodos_tienen_atributos_esperados(self):
        from integrabog.graph.macro import construir_grafo_macro

        G = construir_grafo_macro()
        nodo = next(iter(G.nodes))
        attrs = G.nodes[nodo]
        assert "x" in attrs
        assert "y" in attrs
        assert "nombre" in attrs
