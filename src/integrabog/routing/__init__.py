"""
Algoritmos de diseño de rutas sobre la red multicapa de TransMilenio.

Incluye la sugerencia de nuevas troncales y la identificación de pares
críticos (estaciones que más se beneficiarían de una conexión directa).
"""

from integrabog.routing.network_design import (
    EstacionNoEncontradaError,
    identificar_pares_criticos,
    sugerir_nueva_troncal,
)

__all__ = [
    "EstacionNoEncontradaError",
    "sugerir_nueva_troncal",
    "identificar_pares_criticos",
]
