"""
Lógica de acople (snapping) espacial: para cada estación, encuentra el
tramo de trazado geométricamente más cercano y su posición de arco.
"""

import geopandas as gpd
import pandas as pd

from integrabog.config import TOLERANCIA_ACOPLE_M


def explotar_tramos(trazado: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Descompone cada MultiLineString en LineStrings individuales,
    conservando los atributos originales (id_trazado, nom_tronc, ...)
    en cada pieza resultante."""
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
    posición de arco 's' sobre ese tramo."""
    filas = []
    for _, est in estaciones.iterrows():
        punto = est.geometry
        distancias = tramos.geometry.distance(punto)
        idx_cercano = distancias.idxmin()
        dist_min = distancias.loc[idx_cercano]

        if dist_min > tolerancia_m:
            print(f"[ADVERTENCIA] '{est['nom_est']}' no se acopló ({dist_min:.1f} m > tolerancia)")
            continue

        tramo = tramos.loc[idx_cercano]
        s = tramo.geometry.project(punto)
        filas.append(
            {
                "cod_nodo": int(est["cod_nodo"]),
                "tramo_id": int(tramo["tramo_id"]),
                "id_trazado": tramo["id_trazado"],
                "nom_tronc": tramo["nom_tronc"],
                "s": float(s),
                "dist_acople": float(dist_min),
            }
        )
    return pd.DataFrame(filas)
