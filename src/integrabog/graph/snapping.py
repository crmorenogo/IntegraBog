import geopandas as gpd
import pandas as pd

from integrabog.config import TOLERANCIA_ACOPLE_M


def explotar_tramos(trazado: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    tramos = trazado.explode(index_parts=False).reset_index(drop=True)
    tramos["tramo_id"] = tramos.index
    return tramos


def acoplar_estaciones(
    estaciones: gpd.GeoDataFrame,
    tramos: gpd.GeoDataFrame,
    tolerancia_m: float = TOLERANCIA_ACOPLE_M,
) -> pd.DataFrame:
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
