"""
Construye el grafo macro de estaciones troncales de TransMilenio y corre
un diagnóstico de validación.
"""

from integrabog.graph.diagnostico import diagnosticar_grafo
from integrabog.graph.macro import construir_grafo_macro


def main():
    G = construir_grafo_macro()
    diagnosticar_grafo(G)
    return G


if __name__ == "__main__":
    grafo = main()
