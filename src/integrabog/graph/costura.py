"""
Costura de tramos: repara las adyacencias que Paso 8 no puede ver
porque quedan del otro lado de una brecha de digitalización o de una
cadena de tramos sin ninguna estación.
"""

import math
from collections import defaultdict

import geopandas as gpd
import networkx as nx
import pandas as pd


def construir_grafo_conectores(
    tramos: gpd.GeoDataFrame, acoples: pd.DataFrame, eps: float
) -> nx.Graph:
    """Grafo auxiliar formado solo por los extremos de cada tramo.
    'paso': un tramo sin estaciones se cruza directo (peso = su longitud).
    'brecha': dos extremos de tramos distintos a menos de eps metros."""
    H = nx.Graph()
    coords_extremo = {}
    for _, t in tramos.iterrows():
        coords = list(t.geometry.coords)
        n_ini, n_fin = (t["tramo_id"], "inicio"), (t["tramo_id"], "fin")
        H.add_node(n_ini)
        H.add_node(n_fin)
        coords_extremo[n_ini] = coords[0]
        coords_extremo[n_fin] = coords[-1]
        if not (acoples["tramo_id"] == t["tramo_id"]).any():
            H.add_edge(n_ini, n_fin, weight=t.geometry.length, tipo="paso")

    nodos = list(H.nodes)
    for i in range(len(nodos)):
        for j in range(i + 1, len(nodos)):
            a, b = nodos[i], nodos[j]
            if a[0] == b[0]:
                continue
            d = math.dist(coords_extremo[a], coords_extremo[b])
            if d < eps:
                H.add_edge(a, b, weight=d, tipo="brecha")
    return H


def hallar_estaciones_expuestas(tramos: gpd.GeoDataFrame, acoples: pd.DataFrame) -> list[tuple]:
    """La primera y la última estación (por 's') de cada tramo son sus
    'lados expuestos': el punto por donde ese tramo podría seguir
    conectándose con otro. No se limita a tramos con una sola estación
    — cualquier tramo con 2+ estaciones también tiene dos lados
    expuestos en sus extremos, aunque ya esté conectado por dentro."""
    expuestas = []
    for tramo_id, grupo in acoples.groupby("tramo_id"):
        grupo = grupo.sort_values("s").reset_index(drop=True)
        largo = tramos.loc[tramos["tramo_id"] == tramo_id, "geometry"].iloc[0].length
        primera, ultima = grupo.iloc[0], grupo.iloc[-1]
        expuestas.append((primera["cod_nodo"], (tramo_id, "inicio"), primera["s"]))
        expuestas.append((ultima["cod_nodo"], (tramo_id, "fin"), largo - ultima["s"]))
    return expuestas


def calcular_aristas_costura(
    G: nx.DiGraph, tramos: gpd.GeoDataFrame, acoples: pd.DataFrame, eps: float = 5.0
) -> int:
    """Agrega al grafo las aristas que faltan entre estaciones separadas
    por una brecha de digitalización o por una cadena de tramos vacíos.
    Devuelve cuántos pares nuevos se agregaron."""
    H = construir_grafo_conectores(tramos, acoples, eps)
    expuestas = hallar_estaciones_expuestas(tramos, acoples)

    componente_de = {nodo: i for i, comp in enumerate(nx.connected_components(H)) for nodo in comp}
    grupos = defaultdict(list)
    for cod_nodo, extremo, dist in expuestas:
        if extremo in componente_de:
            grupos[componente_de[extremo]].append((cod_nodo, extremo, dist))

    n_agregadas = 0
    for miembros in grupos.values():
        for i in range(len(miembros)):
            for j in range(i + 1, len(miembros)):
                c1, e1, d1 = miembros[i]
                c2, e2, d2 = miembros[j]
                if c1 == c2:
                    continue
                try:
                    dist_conector = nx.shortest_path_length(H, e1, e2, weight="weight")
                except nx.NetworkXNoPath:
                    continue
                peso = round(d1 + dist_conector + d2, 2)
                G.add_edge(c1, c2, weight=peso, tipo="costura")
                G.add_edge(c2, c1, weight=peso, tipo="costura")
                n_agregadas += 1
    return n_agregadas
