"""
Métricas de la red troncal sobre el grafo macro: excentricidad de cada
estación, diámetro, radio, centro y periferia.

Definiciones, para el grafo dirigido G = (V, E) y d(u, v) el largo del
camino más corto de u a v según el criterio:

    excentricidad   e(v) = máx { d(v, u) : u ∈ V }
    diámetro        D    = máx { e(v) : v ∈ V }   (= el mayor d(u, v) entre todos los pares)
    radio           r    = mín { e(v) : v ∈ V }
    centro          { v ∈ V : e(v) = r }
    periferia       { v ∈ V : e(v) = D }
    media           el promedio de d(u, v) sobre los pares ordenados (u, v), u ≠ v, con camino

El diámetro es el peor viaje de la red y la media, el viaje típico: para
comparar dos redes (antes y después de una troncal nueva, en
routing/escenarios.py) hacen falta las dos, porque una conexión puede acortar
muchos viajes sin tocar el par más alejado.

El grafo macro hoy es simétrico (cada arista va en los dos sentidos), así
que d(u, v) = d(v, u). Igual se calcula sobre el grafo dirigido, con la
excentricidad de salida: si algún día se bloquea una conexión en un solo
sentido, el resultado sigue siendo correcto. Si una estación no llega a
todas, su excentricidad es infinita, y también el diámetro.

Tres criterios para d(u, v):
  - 'tiempo' (min): el largo de cada arista por el trazado a la velocidad BRT
    del modelo, más TRANSBORDO_MIN en cada arista de cruce entre troncales.
    Es la medida principal: es lo que vive el usuario y lo que el modelo
    optimiza.
  - 'distancia' (km): el largo por el trazado oficial.
  - 'tramos': cada arista cuenta 1. Es el diámetro topológico clásico. Una
    troncal propuesta (routing/escenarios.py) cuenta los tramos entre sus
    paradas: es una línea con estaciones, no un salto.
Sin el costo del transbordo, 'tiempo' sería 'distancia' dividida por la
velocidad: el mismo par y el mismo camino. El transbordo es lo que separa
las dos medidas. Con las 150 estaciones de la primera versión, el par más
alejado por distancia era Terminal ↔ San Mateo, y por tiempo, San Mateo ↔
Portal Suba, que tiene un kilómetro menos pero dos transbordos.

Desempates: entre varias estaciones a la misma distancia máxima (con
TOLERANCIA en el criterio), gana la primera en orden de código. Así el
resultado no cambia de una corrida a otra.

Las métricas son de la infraestructura, no de los servicios: el grafo supone
que un bus puede ir por cualquier tramo y pasar por cualquier cruce, a una
sola velocidad. No modela las rutas (G11, B16...), sus frecuencias ni las
esperas, salvo lo que se le cobre al transbordo.
"""
import math
import numbers
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import networkx as nx
from pyproj import Transformer

from integrabog.config import CRS_METRICO, TRANSBORDO_MIN
from integrabog.routing.network_design import implica_transbordo, tiempo_troncal_min

CRITERIOS = ("tiempo", "distancia", "tramos")
UNIDAD = {"tiempo": "min", "distancia": "km", "tramos": "tramos"}
"""dos excentricidades que difieren en menos que esto se toman como iguales (centro,
 periferia y desempates): una milésima de segundo, un milímetro"""
TOLERANCIA = {"tiempo": 1e-5, "distancia": 1e-6, "tramos": 0.0}

_A_LONLAT = Transformer.from_crs(CRS_METRICO, "EPSG:4326", always_xy=True)


def peso(criterio: str, transbordo_min: float = TRANSBORDO_MIN) -> Callable[[object, object, dict], float]:
    """Función de peso de una arista del grafo macro según el criterio."""
    if criterio == "tiempo":
        """la misma cuenta que la ruta actual de la app (network_design.tiempo_troncal_min)"""
        return lambda u, v, d: tiempo_troncal_min(d, transbordo_min)
    if criterio == "distancia":
        return lambda u, v, d: d["weight"] / 1000
    if criterio == "tramos":
        return lambda u, v, d: d.get("tramos", 1)
    raise ValueError(f"Criterio desconocido: {criterio!r} (opciones: {', '.join(CRITERIOS)})")


@dataclass(frozen=True)
class MetricasRed:
    """Resultado de metricas_red() para un criterio. Los valores van en 'unidad'."""
    criterio: str
    unidad: str
    transbordo_min: float
    excentricidad: dict          # estación -> e(v)
    mas_lejana: dict             # estación -> la estación que le da su excentricidad
    diametro: float
    radio: float
    centro: tuple                # estaciones con e(v) = r, en orden de código
    periferia: tuple             # estaciones con e(v) = D, en orden de código
    par_diametro: tuple          # (origen, destino) del diámetro: el primero en orden de código
    camino_diametro: tuple       # estaciones del camino más corto entre ese par
    pares_diametro: tuple        # todos los pares (u, v) con d(u, v) = D (puede haber empates)
    pares_sin_camino: int        # pares (u, v) con u != v sin camino de u a v
    media: float                 # promedio de d(u, v) sobre los pares ordenados con camino
    media_desde: dict            # estación -> promedio de d(v, u) hasta las estaciones a las que llega

    def pares_diametro_sin_orden(self) -> list[tuple]:
        """Los pares del diámetro sin repetir (u, v) y (v, u): en un grafo simétrico son el
        mismo viaje en los dos sentidos."""
        vistos, pares = set(), []
        for u, v in self.pares_diametro:
            if frozenset((u, v)) not in vistos:
                vistos.add(frozenset((u, v)))
                pares.append((u, v))
        return pares


def en_orden(G: nx.DiGraph) -> list:
    """Las estaciones en orden de código (cod_nodo), para desempatar siempre igual. Los
    códigos son números (también los de numpy); cualquier otro id va después, como texto."""
    def clave(n):
        return (0, n, "") if isinstance(n, numbers.Real) else (1, 0, str(n))
    return sorted(G.nodes, key=clave)


def metricas_red(G: nx.DiGraph, criterio: str = "tiempo", transbordo_min: float = TRANSBORDO_MIN) -> MetricasRed:
    """Excentricidad de cada estación, diámetro, radio, centro y periferia
    del grafo macro según el criterio (ver el docstring del módulo).

    Corre un Dijkstra desde cada estación: con 153 estaciones y ~370
    aristas, todos los pares salen en milisegundos.
    """
    funcion = peso(criterio, transbordo_min)
    tolerancia = TOLERANCIA[criterio]
    estaciones = en_orden(G)
    excentricidad: dict[Any, float] = {}
    mas_lejana: dict[Any, Any] = {}
    lejanas: dict[Any, tuple] = {}
    caminos: dict[Any, tuple] = {}
    media_desde: dict[Any, float] = {}
    sin_camino, suma, pares = 0, 0.0, 0
    for v in estaciones:
        largos, rutas = nx.single_source_dijkstra(G, v, weight=funcion)
        alcanzadas = len(largos) - 1  # sin contar la estación misma (d(v, v) = 0 no suma)
        media_desde[v] = sum(largos.values()) / alcanzadas if alcanzadas else 0.0
        suma, pares = suma + sum(largos.values()), pares + alcanzadas
        faltan = len(G) - len(largos)
        if faltan:
            sin_camino += faltan
            excentricidad[v], mas_lejana[v], lejanas[v] = math.inf, None, ()
            continue
        maximo = max(largos.values())
        lejanas[v] = tuple(u for u in estaciones if largos[u] >= maximo - tolerancia)
        excentricidad[v], mas_lejana[v], caminos[v] = maximo, lejanas[v][0], tuple(rutas[lejanas[v][0]])

    diametro, radio = max(excentricidad.values()), min(excentricidad.values())
    periferia = tuple(v for v in estaciones if excentricidad[v] >= diametro - tolerancia)
    centro = tuple(v for v in estaciones if excentricidad[v] <= radio + tolerancia)
    origen = periferia[0]
    return MetricasRed(
        criterio=criterio, unidad=UNIDAD[criterio], transbordo_min=transbordo_min,
        excentricidad=excentricidad, mas_lejana=mas_lejana, diametro=diametro, radio=radio,
        centro=centro, periferia=periferia, par_diametro=(origen, mas_lejana[origen]),
        camino_diametro=caminos.get(origen, ()),
        pares_diametro=tuple((v, u) for v in periferia for u in lejanas[v]),
        pares_sin_camino=sin_camino, media=suma / pares if pares else 0.0, media_desde=media_desde)


def resumen_camino(G: nx.DiGraph, camino: Sequence, transbordo_min: float = TRANSBORDO_MIN) -> dict:
    """Las tres medidas de un mismo camino, más sus transbordos y las
    troncales por las que pasa (en orden, sin repetir seguidas). 'estaciones'
    son las de la red por las que pasa: las paradas de una troncal propuesta
    no son nodos del grafo, pero sus tramos sí cuentan en 'tramos'."""
    aristas = [G[u][v] for u, v in zip(camino[:-1], camino[1:])]
    troncales: list[str] = []
    for v in camino:
        troncal = G.nodes[v].get("troncal")
        if troncal and (not troncales or troncales[-1] != troncal):
            troncales.append(troncal)
    return {"tramos": sum(peso("tramos")(None, None, d) for d in aristas),
            "km": sum(d["weight"] for d in aristas) / 1000,
            "minutos": sum(peso("tiempo", transbordo_min)(None, None, d) for d in aristas),
            "transbordos": sum(1 for d in aristas if implica_transbordo(d)),
            "estaciones": len(camino),
            "troncales": troncales}


def punto_lonlat(G: nx.DiGraph, v) -> tuple[float, float]:
    """Posición de una estación en lon/lat."""
    lon, lat = _A_LONLAT.transform(G.nodes[v]["x"], G.nodes[v]["y"])
    return round(lon, 6), round(lat, 6)


def geometria_camino_lonlat(G: nx.DiGraph, camino: Sequence) -> list[tuple[float, float]]:
    """El camino dibujado por el trazado oficial: la forma de cada arista
    (graph/geometria_troncal.py, orientada de u a v), en lon/lat."""
    puntos: list[tuple] = []
    for u, v in zip(camino[:-1], camino[1:]):
        geometria = G[u][v].get("geometry")
        coords = list(geometria.coords) if geometria is not None else [
            (G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])]
        puntos.extend(coords[1:] if puntos and coords[0] == puntos[-1] else coords)
    if not puntos:
        return []
    lon, lat = _A_LONLAT.transform(*zip(*[p[:2] for p in puntos]))
    return [(round(x, 6), round(y, 6)) for x, y in zip(lon, lat)]
