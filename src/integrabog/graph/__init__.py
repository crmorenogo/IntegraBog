# pylint: disable=missing-function-docstring,invalid-name
"""
Construcción y análisis de la red de TransMilenio en tres capas:

- Macro: estaciones troncales y conexiones existentes.
- Micro: malla vial de Bogotá (desde OSMnx / OpenStreetMap).
- Multicapa: fusión de ambas capas con acople de estaciones.
"""

from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.graph.snapping import acoplar_estaciones, explotar_tramos

__all__ = [
    "construir_grafo_macro",
    "obtener_malla_vial",
    "construir_grafo_multicapa",
    "explotar_tramos",
    "acoplar_estaciones",
]
