# pylint: disable=missing-function-docstring,invalid-name
"""
Carga y reproyección de datos geoespaciales.

Las funciones aquí aceptan rutas absolutas y devuelven GeoDataFrames
ya convertidos al CRS métrico del proyecto (EPSG:3116).
"""

from integrabog.data.loader import cargar_estaciones, cargar_trazado

__all__ = ["cargar_estaciones", "cargar_trazado"]
