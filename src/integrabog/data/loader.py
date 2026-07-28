"""
Carga de las fuentes geoespaciales crudas y su reproyección a un
sistema de coordenadas métrico.

"""

import geopandas as gpd

from integrabog.config import CRS_METRICO, RUTA_ESTACIONES, RUTA_TRAZADO


def cargar_estaciones() -> gpd.GeoDataFrame:
    """Lee las estaciones (Point) y las reproyecta a un CRS métrico."""
    gdf = gpd.read_file(RUTA_ESTACIONES)
    return gdf.to_crs(CRS_METRICO)


def cargar_trazado() -> gpd.GeoDataFrame:
    """Lee las líneas de trazado y las reproyecta al mismo CRS."""
    gdf = gpd.read_file(RUTA_TRAZADO)
    return gdf.to_crs(CRS_METRICO)
