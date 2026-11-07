"""
Costura de tramos: repara las adyacencias que builder.py no puede ver
porque quedan del otro lado de una brecha de digitalización o de una
cadena de tramos sin ninguna estación acoplada.

El problema que resuelve: construir_aristas() en builder.py solo conecta
estaciones que caen dentro del MISMO tramo. Pero un tramo real de
TransMilenio a veces queda partido en varias piezas geométricas
separadas (por errores de digitalización, o porque hay un tramo sin
ninguna estación cerca -- un lazo de retorno, un conector corto), y ahí
dos estaciones que en la realidad son vecinas terminan sin arista entre
ellas porque cada una quedó acoplada a una pieza distinta.

La solución no compara estaciones directo contra estaciones -- compara
los EXTREMOS de cada tramo entre sí, con una tolerancia eps, y separado
usa componentes conexas para agrupar. Eso resuelve en un solo mecanismo
tanto el caso simple (dos tramos que deberían tocarse y no comparten
vértice exacto) como el caso de una cadena larga de tramos vacíos
intermedios y el caso de tres o más tramos confluyendo en el mismo
punto -- sin necesitar un caso especial para cada situación.
"""
import math
from collections import defaultdict

import geopandas as gpd
import networkx as nx
import pandas as pd


def construir_grafo_conectores(tramos: gpd.GeoDataFrame, acoples: pd.DataFrame, eps: float) -> nx.Graph:
    """Grafo auxiliar formado solo por los extremos de cada tramo (no
    por estaciones). Dos tipos de arista:
      - 'paso': un tramo sin ninguna estación acoplada se puede cruzar
        directo de un extremo al otro (peso = su longitud completa).
      - 'brecha': dos extremos de tramos DISTINTOS que quedan a menos
        de eps metros entre sí (peso = esa distancia real).

    Args:
        tramos: GeoDataFrame de tramos ya explotados (una fila por
            pieza geométrica simple, no por troncal completa).
        acoples: DataFrame de estaciones ya acopladas a un tramo_id,
            usado acá solo para saber qué tramos NO tienen ninguna
            estación (para agregarles la arista 'paso').
        eps: tolerancia en metros para considerar que dos extremos de
            tramos distintos representan el mismo punto físico.

    Returns:
        Grafo no dirigido cuyos nodos son (tramo_id, 'inicio'|'fin').
    """
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
            """ tramo vacío (sin ninguna estación acoplada) -- sin esta arista, cualquier
             par de estaciones que solo se conecta a través de este tramo queda sin ruta"""
            H.add_edge(n_ini, n_fin, weight=t.geometry.length, tipo="paso")

    nodos = list(H.nodes)
    for i in range(len(nodos)):
        for j in range(i + 1, len(nodos)):
            a, b = nodos[i], nodos[j]
            if a[0] == b[0]:
                continue # los dos extremos del mismo tramo no cuentan como "brecha" entre sí
            d = math.dist(coords_extremo[a], coords_extremo[b])
            if d < eps:
                H.add_edge(a, b, weight=d, tipo="brecha")
    return H

def hallar_estaciones_expuestas(tramos: gpd.GeoDataFrame, acoples: pd.DataFrame) -> list[tuple]:
    """La primera y la última estación (por 's') de cada tramo son sus
    'lados expuestos': el punto por donde ese tramo podría seguir
    conectándose con otro. No se limita a tramos con una sola estación
    -- cualquier tramo con 2+ estaciones también tiene dos lados
    expuestos en sus extremos, aunque ya esté conectado por dentro.

    Args:
        tramos: GeoDataFrame de tramos explotados.
        acoples: DataFrame de estaciones acopladas, con su tramo_id y
            posición de arco 's'.

    Returns:
        Lista de (cod_nodo, (tramo_id, 'inicio'|'fin'), distancia al
        extremo correspondiente) -- dos entradas por tramo con al menos
        una estación acoplada.
    """
    expuestas = []
    for tramo_id, grupo in acoples.groupby("tramo_id"):
        grupo = grupo.sort_values("s").reset_index(drop=True)
        largo = tramos.loc[tramos["tramo_id"] == tramo_id, "geometry"].iloc[0].length
        primera, ultima = grupo.iloc[0], grupo.iloc[-1]
        expuestas.append((primera["cod_nodo"], (tramo_id, "inicio"), primera["s"]))
        expuestas.append((ultima["cod_nodo"], (tramo_id, "fin"), largo - ultima["s"]))
    return expuestas

def calcular_aristas_costura(G: nx.DiGraph, tramos: gpd.GeoDataFrame,
                               acoples: pd.DataFrame, eps: float = 5.0) -> int:
    """Agrega al grafo las aristas que faltan entre estaciones separadas
    por una brecha de digitalización o por una cadena de tramos vacíos.

    Agrupar por componente conexa de construir_grafo_conectores() es lo
    que evita tener que distinguir "brecha simple entre dos tramos" de
    "tres tramos confluyendo en el mismo punto": si dos o más lados
    expuestos terminan en la misma componente, se conectan todos entre
    sí -- funciona igual sin importar cuántos tramos participan.

    Args:
        G: grafo al que se agregan las aristas de costura. Se modifica
            en el lugar; se asume que ya tiene los nodos y las aristas
            de builder.py.
        tramos: GeoDataFrame de tramos explotados.
        acoples: DataFrame de estaciones acopladas.
        eps: tolerancia en metros para construir_grafo_conectores. 5.0 m
            se eligió mirando la distribución real de distancias entre
            extremos de tramo distintos: las brechas reales de
            digitalización caen todas por debajo de ~1.5 m, y el
            siguiente caso más cercano ya está a más de 28 m -- hay un
            salto grande en el medio, así que el valor exacto dentro de
            ese rango no cambia el resultado.

    Returns:
        Cuántos pares de estaciones nuevos se conectaron.
    """
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
                    continue # misma estación expuesta por los dos lados del mismo tramo -- no conectarla consigo misma
                try:
                    dist_conector = nx.shortest_path_length(H, e1, e2, weight="weight")
                except nx.NetworkXNoPath:
                    continue
                """ misma lógica de acumulación de arco que en builder.py: distancia de la
                 estación a su extremo + lo que hay que recorrer por H + la otra estación a su extremo"""
                peso = round(d1 + dist_conector + d2, 2)
                G.add_edge(c1, c2, weight=peso, tipo="costura")
                G.add_edge(c2, c1, weight=peso, tipo="costura")
                n_agregadas += 1
    return n_agregadas