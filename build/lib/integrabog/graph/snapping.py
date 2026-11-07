"""
Lógica de acople (snapping) espacial: para cada estación, encuentra el
tramo de trazado geométricamente más cercano y su posición de arco.

Este módulo es la proyección ortogonal de un
punto sobre un segmento: dado el punto de una estación y un segmento
del trazado, hay una fórmula cerrada para hallar tanto el punto más
cercano sobre ese segmento como la distancia a él, sin tener que probar
puntos al azar. Shapely ya la implementa (.distance() y .project()), así
que este módulo no reimplementa esa parte -- solo decide CONTRA CUÁL
tramo aplicarla (el de menor distancia entre todos los candidatos) y
qué hacer con el resultado (posición de arco 's', usada después en
builder.py para ordenar estaciones dentro de un mismo tramo).
"""
import geopandas as gpd
import pandas as pd
from integrabog.config import TOLERANCIA_ACOPLE_M


def explotar_tramos(trazado: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Descompone cada MultiLineString en LineStrings individuales,
    conservando los atributos originales (id_trazado, nom_tronc, ...)
    en cada pieza resultante.

    Hace falta porque .project() (posición de arco) solo tiene sentido
    geométrico sobre una curva simple y continua. Un MultiLineString
    puede traer piezas físicamente separadas bajo el mismo id_trazado
    (un lazo de retorno en un portal, por ejemplo) -- tratarlo como una
    sola curva daría una posición de arco que salta de una pieza a otra
    sin que exista ningún camino físico real entre ellas.

    Args:
        trazado: GeoDataFrame de trazado troncal, tal como viene del
            GeoJSON oficial (LineString o MultiLineString por fila).

    Returns:
        GeoDataFrame con una fila por pieza geométrica simple, con una
        columna nueva 'tramo_id' (índice secuencial, usado como
        identificador en el resto del pipeline).
    """
    tramos = trazado.explode(index_parts=False).reset_index(drop=True)
    tramos["tramo_id"] = tramos.index
    return tramos

def acoplar_estaciones(
    estaciones: gpd.GeoDataFrame,
    tramos: gpd.GeoDataFrame,
    tolerancia_m: float = TOLERANCIA_ACOPLE_M,
) -> pd.DataFrame:
    """Para cada estación, busca el tramo más cercano (mínimo de
    L.distance(P) sobre todos los tramos candidatos) y calcula su
    posición de arco 's' sobre ese tramo.

    Args:
        estaciones: GeoDataFrame de estaciones (Point), ya reproyectado
            al mismo CRS que 'tramos'.
        tramos: GeoDataFrame de tramos ya explotados (ver
            explotar_tramos).
        tolerancia_m: distancia máxima aceptable entre una estación y su
            tramo más cercano. Por defecto viene de la distribución real
            de distancias medida sobre los datos: la mayoría de
            estaciones caen a centímetros del tramo, y el único grupo
            que se aleja son los portales (hasta ~256 m, por ser
            complejos físicamente más grandes que una estación sencilla)
            -- el valor por defecto cubre ese caso real sin ser tan
            flojo como para aceptar un error de otro tipo.

    Returns:
        DataFrame con una fila por estación acoplada (cod_nodo, tramo_id,
        id_trazado, nom_tronc, posición de arco 's', distancia de
        acople). Las estaciones que superan la tolerancia quedan fuera,
        con una advertencia impresa -- no se fuerza un acople dudoso.
    """
    filas = []
    for _, est in estaciones.iterrows():
        punto = est.geometry
        distancias = tramos.geometry.distance(punto)
        idx_cercano = distancias.idxmin()
        dist_min = distancias.loc[idx_cercano]

        if dist_min > tolerancia_m:
            print(f"[ADVERTENCIA] '{est['nom_est']}' no se acopló "
                  f"({dist_min:.1f} m > tolerancia)")
            continue

        tramo = tramos.loc[idx_cercano]
        s = tramo.geometry.project(punto) # posición de arco: distancia acumulada desde el inicio del tramo hasta el punto más cercano a la estación
        filas.append({
            "cod_nodo": int(est["cod_nodo"]),
            "tramo_id": int(tramo["tramo_id"]),
            "id_trazado": tramo["id_trazado"],
            "nom_tronc": tramo["nom_tronc"],
            "s": float(s),
            "dist_acople": float(dist_min),
        })
    return pd.DataFrame(filas)