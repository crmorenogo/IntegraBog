# pylint: disable=missing-function-docstring,invalid-name
"""
Diseño de rutas sobre la red multicapa de TransMilenio y análisis de la red
troncal:

- network_design: sugerencia de nuevas troncales e identificación de pares
  críticos (estaciones que más se beneficiarían de una conexión directa).
- metricas: excentricidad, diámetro, radio, centro, periferia y distancia media.
- robustez: puntos de corte, puentes, intermediación, eficiencia y cierres.
- escenarios: troncales propuestas y comparación antes/después.
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
