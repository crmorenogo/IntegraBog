"""
Construcción de nodos y aristas del grafo de estaciones troncales.
"""
import networkx as nx
import pandas as pd
import geopandas as gpd


def construir_nodos(G: nx.DiGraph, estaciones: gpd.GeoDataFrame) -> None:
    """Agrega una estación por nodo."""
    for _, est in estaciones.iterrows():
        G.add_node(
            int(est["cod_nodo"]),
            nombre=est["nom_est"],
            num_est=est["num_est"],
            tipo_estacion=int(est["tipo_esta"]),
            id_trazado=est["id_trazado"],
            x=est.geometry.x,
            y=est.geometry.y,
        )

def construir_aristas(G: nx.DiGraph, acoples: pd.DataFrame) -> None:
    """Ordena las estaciones acopladas a cada tramo por su posición de
    arco 's' y conecta cada par de estaciones consecutivas.

    Al estar ordenadas por 's', dos estaciones consecutivas no tienen
    ninguna otra estación acoplada entre ellas sobre ese mismo tramo
    físico: son, por construcción, adyacentes en el grafo.
    """
    for _, grupo in acoples.groupby("tramo_id"):
        grupo = grupo.sort_values("s").reset_index(drop=True)
        for i in range(len(grupo) - 1):
            a, b = grupo.loc[i], grupo.loc[i + 1]
            peso = round(b["s"] - a["s"], 2)
            G.add_edge(a["cod_nodo"], b["cod_nodo"], weight=peso,
                       id_trazado=a["id_trazado"], nom_tronc=a["nom_tronc"])
            G.add_edge(b["cod_nodo"], a["cod_nodo"], weight=peso,
                       id_trazado=a["id_trazado"], nom_tronc=a["nom_tronc"])