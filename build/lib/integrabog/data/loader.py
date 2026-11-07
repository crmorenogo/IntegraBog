"""
Carga las dos fuentes crudas del proyecto (estaciones y trazado troncal)
y las deja ya en el CRS métrico que usa el resto del pipeline.

Los GeoJSON originales vienen en CRS84 (grados), que es lo que exporta
el portal de datos abiertos. Ningún cálculo de distancia real que hace
el resto del proyecto (acople estación-trazado, longitud de arco,
costura, snapping contra la malla vial) funciona bien en grados, así
que este módulo es el único lugar donde se toca el CRS de origen. Todo
lo que viene después (builder, snapping, costura, macro) asume que ya
recibe geometrías en EPSG:3116 y no vuelve a preocuparse por en qué
sistema de coordenadas está parado.

Están separadas en dos funciones en vez de una sola `cargar_geojson(ruta)`
genérica porque estaciones y trazado no son intercambiables: una es
puntos, la otra líneas, y cada una se usa distinto más adelante. Si el
día de mañana una necesita una validación o un preprocesamiento que la
otra no, no hay que tocar una función compartida para separarlas.
"""
import geopandas as gpd
from integrabog.config import RUTA_ESTACIONES, RUTA_TRAZADO, CRS_METRICO


def cargar_estaciones() -> gpd.GeoDataFrame:
    """Lee las estaciones (Point) y las reproyecta a un CRS métrico.

    Returns:
        GeoDataFrame con una fila por estación, geometría Point ya en
        CRS_METRICO, con todos los atributos originales del GeoJSON
        intactos (cod_nodo, nom_est, id_trazado, tipo_esta, etc.).
    """
    gdf = gpd.read_file(RUTA_ESTACIONES) # toma el CRS de origen (CRS84) directo del archivo, no hay que declararlo a mano
    return gdf.to_crs(CRS_METRICO) # reproyección centralizada: de aquí en adelante nadie más en el proyecto reproyecta nada


def cargar_trazado() -> gpd.GeoDataFrame:
    """Lee las líneas de trazado y las reproyecta al mismo CRS.

    Returns:
        GeoDataFrame con una fila por tramo de trazado, geometría
        LineString/MultiLineString ya en CRS_METRICO, con los atributos
        originales del GeoJSON intactos (id_trazado, nom_tronc, etc.).
    """
    gdf = gpd.read_file(RUTA_TRAZADO)
    return gdf.to_crs(CRS_METRICO) # mismo CRS que cargar_estaciones() -- si no coinciden, el acople espacial en builder.py da resultados sin sentido sin lanzar ningún error