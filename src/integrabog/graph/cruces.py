"""
Aristas de cruce: conectan las troncales donde una atraviesa a otra, o
donde una termina contra el costado de otra.

El hueco que llena: builder.py solo une estaciones consecutivas de una
misma pieza del trazado, y costura.py solo une piezas por sus EXTREMOS.
Ninguno de los dos ve un cruce a mitad de pieza -- la Calle 26 pasando
por debajo de la Caracas y de la NQS, la NQS cruzando la Américas en
Ricaurte -- ni una troncal que muere contra el costado de otra (Suba
contra la Calle 80, Tunal contra la Caracas Sur). Con solo esos dos
mecanismos la red troncal quedaba partida en 6 pedazos y ningún viaje
que necesitara pasar de uno a otro tenía tiempo "actual".

Cómo se arma, y por qué así:

  - Un cruce es cualquier punto donde dos piezas del trazado de troncales
    DISTINTAS se tocan o quedan a menos de TOLERANCIA_CRUCE_M (el mismo
    margen de 50 m que la costura: en el trazado oficial las troncales
    rara vez comparten el vértice exacto). Piezas de una misma troncal no
    se miran aquí; eso ya es trabajo de costura.py.

  - En cada cruce se toma, sobre cada una de las dos piezas, la estación
    más cercana A CADA LADO del punto de cruce (hasta dos por troncal), y
    se une cada una de un lado con cada una del otro. No basta con la
    más cercana: si el cruce queda entre X1 (200 m antes) y X2 (300 m
    después), un viaje que venga de la otra troncal y siga hacia X2 tendría
    que llegar a X1 y devolverse, y el modelo sobreestimaría ese recorrido
    en 400 m.

  - El peso es la distancia por el trazado -- de la estación al punto de
    cruce sobre su troncal, más la brecha entre las dos líneas, más del
    cruce a la otra estación --, en metros, igual que las aristas de
    builder.py y de costura.py. La arista guarda ese mismo recorrido en
    'geometry' (ver geometria_troncal.py): en el mapa se ve el giro del bus
    en el cruce, no una diagonal entre las dos estaciones. Por eso se recorren a velocidad BRT y no
    caminando: modelan que el bus (o el usuario, en un transbordo dentro de
    la estación) sigue por el corredor, no una caminata por la calle.

  - Solo se usa una estación si queda a no más de DISTANCIA_MAX_CRUCE_M del
    cruce por el trazado: más allá de eso ya no es "la estación del cruce"
    sino una cualquiera de la troncal, y se crearían conexiones largas que
    no existen.

  - Nunca se pisa una arista que ya exista (de builder.py o de costura.py):
    esas vienen de un dato más directo que esta inferencia.

Las conexiones que resultan se pueden revisar con
    python -m integrabog.scripts.diagnostico_costura
"""
import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import Point
from shapely.ops import nearest_points

from integrabog.config import DISTANCIA_MAX_CRUCE_M, TOLERANCIA_CRUCE_M
from integrabog.graph.geometria_troncal import a_linea, invertir, tramo_entre, unir_tramos

TIPO_ARISTA_CRUCE = "cruce"

"""dos puntos de cruce entre las mismas dos piezas a menos de esto se toman como el mismo
 cruce: dos troncales que corren pegadas un tramo dan una cadena de puntos, no varios cruces"""
_SEPARACION_MIN_CRUCES_M = 150.0


def puntos_de_cruce(pieza_a, pieza_b, tolerancia_m: float) -> list[tuple[float, float, float]]:
    """Dónde se cruzan dos piezas del trazado.

    Args:
        pieza_a, pieza_b: LineString de dos piezas (CRS métrico).
        tolerancia_m: distancia máxima entre las líneas para considerar
            que se tocan aunque no compartan ningún punto.

    Returns:
        Lista de (s_a, s_b, brecha): posición de arco del cruce sobre cada
        pieza y la distancia entre las líneas en ese punto (0 si se
        intersecan). Vacía si las piezas no se acercan a menos de la
        tolerancia.
    """
    if pieza_a.distance(pieza_b) > tolerancia_m:
        return []
    interseccion = pieza_a.intersection(pieza_b)
    if interseccion.is_empty:
        p_a, p_b = nearest_points(pieza_a, pieza_b)
        return [(pieza_a.project(p_a), pieza_b.project(p_b), p_a.distance(p_b))]

    """una intersección puede ser un punto, varios, o un tramo compartido si las dos
     líneas corren encima una de otra; de un tramo basta con sus dos extremos"""
    puntos = []
    for g in getattr(interseccion, "geoms", [interseccion]):
        puntos.extend([Point(c) for c in g.coords] if g.geom_type == "Point" else
                      [Point(g.coords[0]), Point(g.coords[-1])])
    cruces = []
    for p in puntos:
        s_a = pieza_a.project(p)
        if all(abs(s_a - otro[0]) >= _SEPARACION_MIN_CRUCES_M for otro in cruces):
            cruces.append((s_a, pieza_b.project(p), 0.0))
    return cruces


def _vecinas_del_cruce(estaciones_pieza: pd.DataFrame, s_cruce: float, distancia_max_m: float) -> list[tuple]:
    """La estación más cercana a cada lado del cruce sobre una pieza.

    Returns:
        Lista de (cod_nodo, distancia por el trazado hasta el cruce,
        posición de arco de la estación); de 0 a 2 elementos.
    """
    vecinas = []
    antes = estaciones_pieza[estaciones_pieza["s"] <= s_cruce]
    despues = estaciones_pieza[estaciones_pieza["s"] > s_cruce]
    if not antes.empty:
        fila = antes.loc[antes["s"].idxmax()]
        vecinas.append((int(fila["cod_nodo"]), s_cruce - fila["s"], float(fila["s"])))
    if not despues.empty:
        fila = despues.loc[despues["s"].idxmin()]
        vecinas.append((int(fila["cod_nodo"]), fila["s"] - s_cruce, float(fila["s"])))
    return [v for v in vecinas if v[1] <= distancia_max_m]


def calcular_aristas_cruce(G: nx.DiGraph, tramos: gpd.GeoDataFrame, acoples: pd.DataFrame,
                           tolerancia_m: float = TOLERANCIA_CRUCE_M,
                           distancia_max_m: float = DISTANCIA_MAX_CRUCE_M) -> int:
    """Agrega al grafo macro las aristas de cruce entre troncales (ver el
    docstring del módulo).

    Args:
        G: grafo macro con los nodos de builder.py y las aristas de
            builder.py y costura.py. Se modifica en el lugar.
        tramos: piezas del trazado (snapping.explotar_tramos).
        acoples: estaciones acopladas a cada pieza, con su posición de
            arco 's' (snapping.acoplar_estaciones).
        tolerancia_m: ver TOLERANCIA_CRUCE_M en config.py.
        distancia_max_m: ver DISTANCIA_MAX_CRUCE_M en config.py.

    Returns:
        Cuántos pares de estaciones nuevos se conectaron.
    """
    por_pieza = {tramo_id: grupo for tramo_id, grupo in acoples.groupby("tramo_id")}
    piezas = [fila for _, fila in tramos.iterrows() if fila["tramo_id"] in por_pieza]
    candidatas = {}  # (u, v) con u < v -> (menor peso encontrado, estación de inicio de la forma, forma)

    for i, a in enumerate(piezas):
        for b in piezas[i + 1:]:
            if a["id_trazado"] == b["id_trazado"]:
                continue
            for s_a, s_b, brecha in puntos_de_cruce(a.geometry, b.geometry, tolerancia_m):
                lado_a = _vecinas_del_cruce(por_pieza[a["tramo_id"]], s_a, distancia_max_m)
                lado_b = _vecinas_del_cruce(por_pieza[b["tramo_id"]], s_b, distancia_max_m)
                for est_a, d_a, s_est_a in lado_a:
                    for est_b, d_b, s_est_b in lado_b:
                        par = (min(est_a, est_b), max(est_a, est_b))
                        peso = round(d_a + brecha + d_b, 2)
                        if par in candidatas and peso >= candidatas[par][0]:
                            continue
                        """de la estación al cruce por su troncal, el salto entre las dos líneas
                         (si no se tocan) y del cruce a la otra estación por la otra troncal"""
                        coords = unir_tramos(tramo_entre(a.geometry, s_est_a, s_a),
                                             tramo_entre(b.geometry, s_b, s_est_b))
                        na, nb = G.nodes[est_a], G.nodes[est_b]
                        candidatas[par] = (peso, est_a,
                                           a_linea(coords, ((na["x"], na["y"]), (nb["x"], nb["y"]))))

    n_agregadas = 0
    for (u, v), (peso, inicio, linea) in sorted(candidatas.items()):
        if G.has_edge(u, v) or G.has_edge(v, u):
            continue  # ya conectadas por builder.py o costura.py: ese dato manda
        ida = linea if inicio == u else invertir(linea)
        G.add_edge(u, v, weight=peso, tipo=TIPO_ARISTA_CRUCE, geometry=ida)
        G.add_edge(v, u, weight=peso, tipo=TIPO_ARISTA_CRUCE, geometry=invertir(ida))
        n_agregadas += 1
    return n_agregadas
