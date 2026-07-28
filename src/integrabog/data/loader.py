import geopandas as gpd

from integrabog.config import CRS_METRICO, RUTA_ESTACIONES, RUTA_TRAZADO


def cargar_estaciones() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(RUTA_ESTACIONES)
    return gdf.to_crs(CRS_METRICO)


def cargar_trazado() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(RUTA_TRAZADO)
    return gdf.to_crs(CRS_METRICO)
