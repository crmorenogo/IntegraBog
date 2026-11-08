"""
Robustez de la red troncal: cuánto depende su conectividad de una sola
estación o de un solo enlace, y cuánto se alargan los viajes cuando uno de
ellos se cierra (por obras, un bloqueo o una emergencia).

Se mide sobre el mismo grafo macro de routing/metricas.py, en dos niveles.

1. Estructura: solo importa qué estaciones están unidas. Se trabaja sobre el
   grafo no dirigido H que tiene un enlace {u, v} donde el grafo macro tiene
   una arista entre u y v. El grafo macro es simétrico (cada conexión va en
   los dos sentidos; se verifica al empezar), así que H no pierde nada. Con
   n estaciones, m enlaces y c componentes conexas:

     - número ciclomático μ = m − n + c: los enlaces que sobran respecto a un
       bosque generador, o sea, cuántos ciclos independientes tiene la red.
       Cada ciclo es una alternativa de recorrido; con μ = 0 la red sería un
       árbol y cada enlace sería imprescindible;
     - puntos de corte: estaciones cuyo cierre desconecta la red;
     - puentes: enlaces cuyo cierre desconecta la red;
     - bloques: las componentes biconexas, los pedazos de la red que el
       cierre de una sola estación no alcanza a partir;
     - conectividad de vértices κ y de aristas λ: cuántas estaciones o
       enlaces hay que cerrar, como mínimo, para desconectar la red. Se
       cumple la desigualdad de Whitney, κ ≤ λ ≤ δ, con δ el grado mínimo.

   Dos conteos resumen todo lo anterior en una cifra que se puede comparar
   entre dos redes con las mismas estaciones:

     - pares que dependen de una sola estación: los pares {a, b} conectados
       que se separan al cerrar alguna estación distinta de a y b. Son los
       que no comparten ningún bloque. Como dos bloques comparten a lo sumo
       una estación, cada par está a lo sumo en un bloque común, y los pares
       protegidos son exactamente Σ C(|B|, 2) sobre los bloques B;
     - pares que dependen de un solo enlace: los que quedan en componentes
       distintas al quitar todos los puentes (las componentes 2-conexas por
       aristas).

2. Desempeño: con los pesos de un criterio de routing/metricas.py (por
   defecto el tiempo de viaje, que cobra el transbordo):

     - intermediación de cada estación (betweenness): la fracción de los
       caminos más cortos entre otros pares de estaciones que pasa por
       ella. Las más altas son los cuellos de botella de la red: su cierre
       es el que más viajes desvía;
     - eficiencia global E: el promedio de 1 / d(a, b) sobre los pares
       ordenados de estaciones distintas (Latora y Marchiori, 2001). A
       diferencia del tiempo medio, sigue definida cuando un cierre deja
       pares sin camino (1 / ∞ = 0), así que mide en una sola escala los
       desvíos y las desconexiones;
     - cierres: para cada estación y cada enlace, qué les pasa a los demás
       viajes si se cierra: cuántos pares quedan sin camino, cuántos siguen
       conectados pero con un viaje más largo (y cuánto más, en promedio) y
       cuánta eficiencia se pierde. El cierre de una estación se mide sobre
       los pares que no la incluyen: sus propios viajes se pierden siempre.

Las distancias de todos los pares se calculan con scipy
(sparse.csgraph.dijkstra) y no con NetworkX: el análisis de cierres necesita
un cálculo de todos los pares por cada estación y por cada enlace (unos 330
en la red troncal), lo que con NetworkX toma varios segundos y con scipy,
menos de uno. Las distancias son las mismas (tests/test_robustez.py).
"""
from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from integrabog.config import TRANSBORDO_MIN
from integrabog.routing.metricas import TOLERANCIA, UNIDAD, en_orden, peso


@dataclass(frozen=True)
class EstructuraRed:
    """Lo que no depende de los pesos, solo de qué estaciones están unidas."""
    estaciones: int                  # n
    enlaces: int                     # m
    componentes: int                 # c
    ciclomatico: int                 # μ = m − n + c
    grado_minimo: int                # δ
    grado_maximo: int                # Δ
    grado_medio: float               # 2m / n
    conectividad_vertices: int       # κ
    conectividad_aristas: int        # λ
    puntos_de_corte: tuple           # estaciones, en orden de código
    puentes: tuple                   # enlaces (u, v), u antes que v en orden de código
    bloques: int                     # componentes biconexas
    bloque_mayor: int                # estaciones del bloque más grande
    pares_conectados: int            # pares {a, b} con camino entre ellos
    pares_dependen_estacion: int     # se separan al cerrar una sola estación (distinta de a y b)
    pares_dependen_enlace: int       # se separan al cerrar un solo enlace


@dataclass(frozen=True)
class Cierre:
    """Efecto de cerrar una estación o un enlace sobre los demás viajes."""
    elemento: Any                    # la estación, o el enlace (u, v)
    pares_desconectados: int         # pares que tenían camino y lo pierden
    pares_alargados: int             # pares que siguen conectados, pero con un viaje más largo
    aumento_medio: float             # cuánto más, en promedio, en esos pares (unidad del criterio; 0 si ninguno)
    perdida_eficiencia: float        # 1 − E después / E antes, entre 0 y 1


@dataclass(frozen=True)
class RobustezRed:
    """Resultado de robustez_red() para un criterio de peso."""
    criterio: str
    unidad: str
    transbordo_min: float
    estructura: EstructuraRed
    intermediacion: dict             # estación -> fracción de los caminos más cortos que pasa por ella
    eficiencia: float                # E de la red completa, en 1 / unidad
    cierres_estaciones: tuple        # un Cierre por estación, del más dañino al menos dañino
    cierres_enlaces: tuple           # un Cierre por enlace, ídem


def grafo_de_enlaces(G: nx.DiGraph) -> nx.Graph:
    """El grafo no dirigido H: un enlace {u, v} donde G tiene una arista entre u y v."""
    H = nx.Graph()
    H.add_nodes_from(G.nodes)
    H.add_edges_from((u, v) for u, v in G.edges() if u != v)
    return H


def _canonicos(G: nx.Graph) -> dict:
    """Cada estación apunta a su propia clave en G.nodes. Los códigos llegan
    unos como int y otros como numpy.int64: son iguales para un dict, pero
    las aristas pueden devolver el otro objeto, y numpy.int64 no se puede
    escribir en JSON. Pasar todo por aquí deja siempre la clave del nodo."""
    return {v: v for v in G.nodes}


def enlaces(G: nx.DiGraph) -> list[tuple]:
    """Los enlaces de G, cada uno una sola vez como (u, v), con u antes que v
    en orden de código. Es el orden en que se reportan en todo el módulo."""
    canonico = _canonicos(G)
    posicion = {v: i for i, v in enumerate(en_orden(G))}
    unicos = {tuple(sorted((canonico[u], canonico[v]), key=posicion.__getitem__)) for u, v in G.edges() if u != v}
    return sorted(unicos, key=lambda e: (posicion[e[0]], posicion[e[1]]))


def es_simetrico(G: nx.DiGraph) -> bool:
    return all(G.has_edge(v, u) for u, v in G.edges())


def _exigir_simetrico(G: nx.DiGraph) -> None:
    if not es_simetrico(G):
        raise ValueError("La robustez se mide sobre el grafo no dirigido de los enlaces, lo que supone que "
                         "cada conexión va en los dos sentidos, como hoy en el grafo macro. Esta red tiene "
                         "aristas de un solo sentido.")


def _pares(k: int) -> int:
    return k * (k - 1) // 2


def estructura(G: nx.DiGraph) -> EstructuraRed:
    """Puntos de corte, puentes, bloques, número ciclomático, κ, λ y los
    pares que dependen de una sola estación o de un solo enlace."""
    _exigir_simetrico(G)
    H = grafo_de_enlaces(G)
    posicion = {v: i for i, v in enumerate(en_orden(G))}
    n, m = H.number_of_nodes(), H.number_of_edges()
    componentes = [len(c) for c in nx.connected_components(H)]
    canonico = _canonicos(G)
    corte = tuple(sorted((canonico[v] for v in nx.articulation_points(H)), key=posicion.__getitem__))
    de_nx = {tuple(sorted((canonico[u], canonico[v]), key=posicion.__getitem__)) for u, v in nx.bridges(H)}
    puentes = tuple(e for e in enlaces(G) if e in de_nx)
    bloques = [len(b) for b in nx.biconnected_components(H)]
    # las componentes 2-conexas por aristas son las que quedan al quitar todos los puentes
    sin_puentes = H.copy()
    sin_puentes.remove_edges_from(puentes)
    dos_conexas = [len(k) for k in nx.connected_components(sin_puentes)]
    conectados = sum(_pares(k) for k in componentes)
    grados = [d for _, d in H.degree()]
    return EstructuraRed(
        estaciones=n, enlaces=m, componentes=len(componentes), ciclomatico=m - n + len(componentes),
        grado_minimo=min(grados, default=0), grado_maximo=max(grados, default=0),
        grado_medio=2 * m / n if n else 0.0,
        conectividad_vertices=_conectividad(H, len(componentes), bool(corte), nx.node_connectivity),
        conectividad_aristas=_conectividad(H, len(componentes), bool(puentes), nx.edge_connectivity),
        puntos_de_corte=corte, puentes=puentes,
        bloques=len(bloques), bloque_mayor=max(bloques, default=0),
        pares_conectados=conectados,
        pares_dependen_estacion=conectados - sum(_pares(k) for k in bloques),
        pares_dependen_enlace=conectados - sum(_pares(k) for k in dos_conexas))


def _conectividad(H: nx.Graph, componentes: int, hay_corte: bool, calcular) -> int:
    """κ o λ. Si la red ya tiene un punto de corte (o un puente), vale 1 sin
    calcular nada más: es el caso de la red troncal, donde el algoritmo
    general, por flujos máximos, sobra."""
    if H.number_of_nodes() <= 1 or componentes > 1:
        return 0
    return 1 if hay_corte else calcular(H)


def intermediacion(G: nx.DiGraph, criterio: str = "tiempo", transbordo_min: float = TRANSBORDO_MIN) -> dict:
    """Intermediación (betweenness) normalizada de cada estación, con los
    pesos del criterio. En un grafo dirigido simétrico, NetworkX cuenta cada
    par en los dos sentidos y divide por (n − 1)(n − 2): da lo mismo que en
    el grafo no dirigido, la fracción de los pares {s, t} (s, t distintos de
    la estación) cuyos caminos más cortos pasan por ella."""
    return nx.betweenness_centrality(G, weight=peso(criterio, transbordo_min), normalized=True)


def _aristas(G: nx.DiGraph, nodos: list, criterio: str, transbordo_min: float):
    """Las aristas como tres arreglos (fila, columna, peso), en el orden de 'nodos'."""
    posicion = {v: i for i, v in enumerate(nodos)}
    w = peso(criterio, transbordo_min)
    datos = [(posicion[u], posicion[v], float(w(u, v, d))) for u, v, d in G.edges(data=True)]
    if not datos:
        return np.array([], dtype=int), np.array([], dtype=int), np.array([], dtype=float)
    filas, columnas, pesos = zip(*datos)
    return np.array(filas), np.array(columnas), np.array(pesos, dtype=float)


def _distancias(n: int, filas, columnas, pesos, quitar=None) -> np.ndarray:
    """Distancias de todos los pares (n x n; ∞ si no hay camino), sin las
    aristas marcadas en 'quitar'. Un DiGraph no tiene aristas paralelas, así
    que la matriz no suma dos pesos en la misma celda."""
    if quitar is not None:
        filas, columnas, pesos = filas[~quitar], columnas[~quitar], pesos[~quitar]
    return dijkstra(csr_matrix((pesos, (filas, columnas)), shape=(n, n)), directed=True)


def _eficiencia(D: np.ndarray) -> float:
    """Promedio de 1 / d sobre los pares ordenados de estaciones distintas
    de la matriz D (1 / ∞ = 0)."""
    k = D.shape[0]
    if k < 2:
        return 0.0
    with np.errstate(divide="ignore"):
        inversa = np.where(np.isfinite(D) & (D > 0), 1.0 / D, 0.0)
    np.fill_diagonal(inversa, 0.0)
    return float(inversa.sum() / (k * (k - 1)))


def eficiencia_global(G: nx.DiGraph, criterio: str = "tiempo", transbordo_min: float = TRANSBORDO_MIN) -> float:
    nodos = en_orden(G)
    return _eficiencia(_distancias(len(nodos), *_aristas(G, nodos, criterio, transbordo_min)))


def _cierre(elemento, antes: np.ndarray, despues: np.ndarray, tolerancia: float) -> Cierre:
    """Compara dos matrices de distancias de las mismas estaciones. Cada par
    se cuenta una vez (triángulo superior): el grafo es simétrico."""
    sup = np.triu_indices(antes.shape[0], k=1)
    a, d = antes[sup], despues[sup]
    conectados = np.isfinite(a)
    siguen = conectados & np.isfinite(d)
    alargados = siguen & (d > a + tolerancia)
    e_antes = _eficiencia(antes)
    return Cierre(
        elemento=elemento,
        pares_desconectados=int((conectados & ~siguen).sum()),
        pares_alargados=int(alargados.sum()),
        aumento_medio=float((d[alargados] - a[alargados]).mean()) if alargados.any() else 0.0,
        perdida_eficiencia=1 - _eficiencia(despues) / e_antes if e_antes > 0 else 0.0)


def cierres(G: nx.DiGraph, criterio: str = "tiempo", transbordo_min: float = TRANSBORDO_MIN) -> tuple[tuple, tuple]:
    """El efecto de cerrar, uno a la vez, cada estación y cada enlace.

    Returns:
        (cierres de estaciones, cierres de enlaces), cada uno ordenado del
        más dañino al menos dañino: por pérdida de eficiencia, luego por
        pares desconectados y luego por orden de código.
    """
    _exigir_simetrico(G)
    nodos = en_orden(G)
    n, posicion = len(nodos), {v: i for i, v in enumerate(nodos)}
    filas, columnas, pesos = _aristas(G, nodos, criterio, transbordo_min)
    D0 = _distancias(n, filas, columnas, pesos)
    tolerancia = TOLERANCIA[criterio]

    por_estacion = []
    for i, v in enumerate(nodos):
        D1 = _distancias(n, filas, columnas, pesos, quitar=(filas == i) | (columnas == i))
        resto = np.delete(np.arange(n), i)
        por_estacion.append(_cierre(v, D0[np.ix_(resto, resto)], D1[np.ix_(resto, resto)], tolerancia))

    por_enlace = []
    for u, v in enlaces(G):
        i, j = posicion[u], posicion[v]
        quitar = ((filas == i) & (columnas == j)) | ((filas == j) & (columnas == i))
        por_enlace.append(_cierre((u, v), D0, _distancias(n, filas, columnas, pesos, quitar), tolerancia))

    por_estacion.sort(key=lambda c: (-c.perdida_eficiencia, -c.pares_desconectados, posicion[c.elemento]))
    por_enlace.sort(key=lambda c: (-c.perdida_eficiencia, -c.pares_desconectados,
                                   posicion[c.elemento[0]], posicion[c.elemento[1]]))
    return tuple(por_estacion), tuple(por_enlace)


def robustez_red(G: nx.DiGraph, criterio: str = "tiempo", transbordo_min: float = TRANSBORDO_MIN) -> RobustezRed:
    """Estructura, intermediación, eficiencia global y cierres de la red,
    con los pesos del criterio (ver el docstring del módulo)."""
    por_estacion, por_enlace = cierres(G, criterio, transbordo_min)
    return RobustezRed(
        criterio=criterio, unidad=UNIDAD[criterio], transbordo_min=transbordo_min,
        estructura=estructura(G),
        intermediacion=intermediacion(G, criterio, transbordo_min),
        eficiencia=eficiencia_global(G, criterio, transbordo_min),
        cierres_estaciones=por_estacion, cierres_enlaces=por_enlace)
