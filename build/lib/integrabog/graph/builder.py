"""
Construye los nodos y las aristas del grafo macro (capa troncal) a
partir de las estaciones ya cargadas y de los acoples estación-tramo ya
calculados en snapping.py.

Este módulo no calcula nada geométrico ni decide a qué tramo pertenece
cada estación -- eso ya viene resuelto en el DataFrame de acoples que
recibe construir_aristas. Aquí solo se traduce esa información a la
estructura de grafo: un nodo por estación, y una arista entre cada par
de estaciones consecutivas dentro de un mismo tramo.
"""
import networkx as nx
import pandas as pd
import geopandas as gpd


def construir_nodos(G: nx.DiGraph, estaciones: gpd.GeoDataFrame) -> None:
    """Agrega una estación por nodo, con sus atributos originales.

    Args:
        G: grafo al que se agregan los nodos. Se modifica en el lugar.
        estaciones: GeoDataFrame de estaciones ya reproyectado (ver
            loader.py), con geometría Point.
    """
    for _, est in estaciones.iterrows():
        G.add_node(
            int(est["cod_nodo"]), # cod_nodo como ID, no nom_est -- hay un nombre repetido en las 150 estaciones, y con ID duplicado NetworkX sobreescribe un nodo con otro sin avisar
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

    Args:
        G: grafo al que se agregan las aristas. Se modifica en el lugar;
            se asume que ya tiene los nodos de construir_nodos.
        acoples: DataFrame con, por estación, a qué tramo_id quedó
            acoplada y su posición de arco 's' sobre ese tramo.
    """
    for _, grupo in acoples.groupby("tramo_id"):
        """el orden dentro de cada tramo es lo único que importa acá --
         agrupar por tramo_id evita conectar estaciones de tramos
         distintos que por casualidad quedaron con 's' parecido"""
        grupo = grupo.sort_values("s").reset_index(drop=True)
        for i in range(len(grupo) - 1):
            a, b = grupo.loc[i], grupo.loc[i + 1]
            peso = round(b["s"] - a["s"], 2) # diferencia de arco, no distancia en línea recta -- sigue la curva real del tramo, no atraviesa manzanas
            G.add_edge(a["cod_nodo"], b["cod_nodo"], weight=peso,
                       id_trazado=a["id_trazado"], nom_tronc=a["nom_tronc"])
            G.add_edge(b["cod_nodo"], a["cod_nodo"], weight=peso,
                       id_trazado=a["id_trazado"], nom_tronc=a["nom_tronc"])
            """arista en ambos sentidos: no hay dato de sentido de circulación real todavía,
             así que por ahora se asume que se puede recorrer el tramo en cualquier dirección"""