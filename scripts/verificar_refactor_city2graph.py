"""
Verificación de no-regresión del refactor de la capa de construcción a
City2Graph.

Construye el grafo multicapa DOS veces sobre exactamente las mismas
entradas (macro recién construido + micro desde la caché .graphml): una con
la implementación anterior (copia congelada abajo, _fusion_anterior) y otra
con la actual (construir_grafo_multicapa). Y compara:

  1. nodos: mismo conjunto de IDs, mismos atributos (valor Y tipo -- un
     np.int64 donde antes había un int ya es una diferencia);
  2. aristas: mismas (u, v, key), mismos atributos;
  3. orden de vecinos de cada nodo, que es lo que usa Dijkstra para
     desempatar caminos de igual costo -- si cambiara, dos rutas de igual
     tiempo podrían salir distintas aunque el grafo "sea el mismo";
  4. atributos a nivel de grafo;
  5. identificar_pares_criticos(top_n=5) y el caso límite Escuela Militar
     <-> San Martín, campo por campo.

Existe porque el refactor se validó en un entorno sin acceso a
OpenStreetMap, sobre una malla sintética de escala parecida: hace falta
correrlo UNA vez en la máquina que tiene la caché real. Cuando salga
"IDÉNTICOS", este script (y con él la copia congelada) se puede borrar.

    python -m integrabog.scripts.verificar_refactor_city2graph
"""
import sys
import time
from collections import Counter

import networkx as nx
import numpy as np
import osmnx as ox
from shapely.geometry.base import BaseGeometry

from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.routing.network_design import (
    _mejor_arista,
    _peso_tiempo,
    calcular_costo_brt,
    identificar_pares_criticos,
    sugerir_nueva_troncal,
)

MAX_EJEMPLOS = 5


def _fusion_anterior(G_macro: nx.DiGraph, G_micro: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Copia literal de multilayer.py antes del refactor (prefijo a mano +
    nx.compose + ox.distance.nearest_nodes). Solo sirve como referencia
    para esta comparación; no la usa nadie más."""
    def _namespacear(G, prefijo, capa):
        G_renombrado = nx.relabel_nodes(G, {n: f"{prefijo}_{n}" for n in G.nodes})
        nx.set_node_attributes(G_renombrado, capa, "layer")
        nx.set_edge_attributes(G_renombrado, capa, "layer")
        if isinstance(G_renombrado, nx.MultiDiGraph):
            return G_renombrado
        return nx.MultiDiGraph(G_renombrado)

    G_macro_capa = _namespacear(G_macro, "macro", "macro")
    G_micro_capa = _namespacear(G_micro, "micro", "micro")
    G_multicapa = nx.compose(G_macro_capa, G_micro_capa)
    estaciones = [(n, d["x"], d["y"]) for n, d in G_macro_capa.nodes(data=True)]
    ids_estacion, xs, ys = zip(*estaciones)
    nodos_viales, distancias = ox.distance.nearest_nodes(G_micro_capa, X=list(xs), Y=list(ys), return_dist=True)
    for id_estacion, id_vial, dist in zip(ids_estacion, nodos_viales, distancias):
        peso = round(float(dist), 2)
        G_multicapa.add_edge(id_estacion, id_vial, weight=peso, layer="transferencia")
        G_multicapa.add_edge(id_vial, id_estacion, weight=peso, layer="transferencia")
    return G_multicapa


def _iguales(a: object, b: object) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, BaseGeometry):
        return a.equals_exact(b, tolerance=0)
    return a == b


def _solo_cambia_a_nativo(a: object, b: object) -> bool:
    """np.float64(638.38) -> 638.38: la vuelta por tabla convierte escalares de
    numpy (los que dejan los cálculos con pandas en builder.py/costura.py) en
    su tipo nativo equivalente. Mismo valor, y np.float64 ya era subclase de
    float: no cambia ningún cálculo, pero se reporta aparte para que quede
    a la vista."""
    return isinstance(a, np.generic) and type(a.item()) is type(b) and a.item() == b


def _diferencias_atributos(da: dict, db: dict, normalizados: Counter | None = None) -> list[str]:
    difs = [f"falta '{k}'" for k in da.keys() - db.keys()]
    difs += [f"sobra '{k}'" for k in db.keys() - da.keys()]
    for k in da.keys() & db.keys():
        if _iguales(da[k], db[k]):
            continue
        if normalizados is not None and _solo_cambia_a_nativo(da[k], db[k]):
            normalizados[(k, type(da[k]).__name__, type(db[k]).__name__)] += 1
            continue
        difs.append(f"'{k}': {da[k]!r} ({type(da[k]).__name__}) != {db[k]!r} ({type(db[k]).__name__})")
    return difs


def comparar_grafos(G_ant: nx.MultiDiGraph, G_nue: nx.MultiDiGraph) -> tuple[list[str], Counter]:
    """Devuelve (diferencias legibles, conteo de normalizaciones numpy -> nativo).
    La lista vacía significa idénticos."""
    problemas = []
    normalizados = Counter()
    if type(G_nue) is not nx.MultiDiGraph:
        problemas.append(f"tipo de grafo: {type(G_nue).__name__} (se esperaba MultiDiGraph)")

    solo_ant, solo_nue = set(G_ant) - set(G_nue), set(G_nue) - set(G_ant)
    if solo_ant or solo_nue:
        problemas.append(f"nodos: {len(solo_ant)} solo antes {sorted(solo_ant)[:MAX_EJEMPLOS]}, "
                         f"{len(solo_nue)} solo ahora {sorted(solo_nue)[:MAX_EJEMPLOS]}")
    difs_nodo = [(n, d) for n in set(G_ant) & set(G_nue)
                 if (d := _diferencias_atributos(G_ant.nodes[n], G_nue.nodes[n], normalizados))]
    if difs_nodo:
        problemas.append(f"atributos de nodo distintos en {len(difs_nodo)} nodos, p. ej. {difs_nodo[:MAX_EJEMPLOS]}")

    aristas_ant = {(u, v, k): d for u, v, k, d in G_ant.edges(keys=True, data=True)}
    aristas_nue = {(u, v, k): d for u, v, k, d in G_nue.edges(keys=True, data=True)}
    solo_ant_e, solo_nue_e = aristas_ant.keys() - aristas_nue.keys(), aristas_nue.keys() - aristas_ant.keys()
    if solo_ant_e or solo_nue_e:
        problemas.append(f"aristas: {len(solo_ant_e)} solo antes {list(solo_ant_e)[:MAX_EJEMPLOS]}, "
                         f"{len(solo_nue_e)} solo ahora {list(solo_nue_e)[:MAX_EJEMPLOS]}")
    difs_arista = [(e, d) for e in aristas_ant.keys() & aristas_nue.keys()
                   if (d := _diferencias_atributos(aristas_ant[e], aristas_nue[e], normalizados))]
    if difs_arista:
        problemas.append(f"atributos de arista distintos en {len(difs_arista)} aristas, p. ej. {difs_arista[:MAX_EJEMPLOS]}")

    orden_distinto = [n for n in set(G_ant) & set(G_nue)
                      if [(v, list(ks)) for v, ks in G_ant.succ[n].items()] != [(v, list(ks)) for v, ks in G_nue.succ[n].items()]
                      or list(G_ant.pred[n]) != list(G_nue.pred[n])]
    if orden_distinto:
        problemas.append(f"orden de vecinos distinto en {len(orden_distinto)} nodos, p. ej. {orden_distinto[:MAX_EJEMPLOS]}")

    if difs := _diferencias_atributos(G_ant.graph, G_nue.graph):
        problemas.append(f"atributos de grafo: {difs}")
    return problemas, normalizados


def _ruta_en_metros(G: nx.MultiDiGraph, origen: str, destino: str) -> float:
    """Largo en metros de la ruta propuesta, sumando la arista que eligió el
    ruteo entre cada par de nodos -- mismo criterio y mismo subgrafo que
    diagnostico_caso_limite.py (el que reportó ~3.311 m)."""
    aristas = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True)
               if d.get("layer") == "micro"
               or (d.get("layer") == "transferencia" and (u in (origen, destino) or v in (origen, destino)))]
    camino = nx.shortest_path(G.edge_subgraph(aristas), origen, destino, weight=_peso_tiempo)
    total = 0.0
    for u, v in zip(camino, camino[1:]):
        arista = _mejor_arista(G.get_edge_data(u, v))
        total += arista.get("length", arista.get("weight", 0.0))
    return total


def main() -> int:
    G_macro = construir_grafo_macro()
    G_micro = obtener_malla_vial()

    t0 = time.perf_counter()
    G_ant = _fusion_anterior(G_macro, G_micro)
    t_ant = time.perf_counter() - t0
    t0 = time.perf_counter()
    G_nue = construir_grafo_multicapa(G_macro, G_micro)
    t_nue = time.perf_counter() - t0
    print(f"\nFusión anterior: {t_ant:.1f} s | City2Graph: {t_nue:.1f} s")
    print(f"Antes : {G_ant.number_of_nodes()} nodos, {G_ant.number_of_edges()} aristas")
    print(f"Ahora : {G_nue.number_of_nodes()} nodos, {G_nue.number_of_edges()} aristas")

    problemas, normalizados = comparar_grafos(G_ant, G_nue)

    calcular_costo_brt(G_ant)
    calcular_costo_brt(G_nue)
    pares_ant = identificar_pares_criticos(G_ant, top_n=5)
    pares_nue = identificar_pares_criticos(G_nue, top_n=5)
    if pares_ant != pares_nue:
        problemas.append("identificar_pares_criticos(top_n=5) devuelve resultados distintos")
    caso_ant = sugerir_nueva_troncal(G_ant, "macro_4107", "macro_3014")
    caso_nue = sugerir_nueva_troncal(G_nue, "macro_4107", "macro_3014")
    if caso_ant != caso_nue:
        problemas.append("sugerir_nueva_troncal(Escuela Militar, San Martín) devuelve resultados distintos")

    print("\nPares críticos (versión City2Graph):")
    for r in pares_nue:
        print(f"  {G_nue.nodes[r['estacion_origen']]['nombre']} <-> {G_nue.nodes[r['estacion_destino']]['nombre']}: "
              f"dist_geo={r['distancia_geometrica_m']} m | tiempo_nuevo={r['tiempo_nueva_ruta_min']} min")
    print(f"Caso límite Escuela Militar <-> San Martín: ruta de "
          f"{_ruta_en_metros(G_nue, 'macro_4107', 'macro_3014'):.0f} m "
          f"({caso_nue['tiempo_nueva_ruta_min']} min) | antes: "
          f"{_ruta_en_metros(G_ant, 'macro_4107', 'macro_3014'):.0f} m ({caso_ant['tiempo_nueva_ruta_min']} min)")

    if normalizados:
        print("\nNormalizaciones de tipo (mismo valor; no cambian ningún cálculo):")
        for (atributo, antes, ahora), n in normalizados.items():
            print(f"  - '{atributo}': {antes} -> {ahora} en {n} elementos")

    if problemas:
        print("\nDIFERENCIAS:")
        for p in problemas:
            print(f"  - {p}")
        return 1
    salvedad = " salvo las normalizaciones de arriba" if normalizados else ""
    print(f"\nIDÉNTICOS: mismos nodos, aristas, claves, atributos (valor y tipo{salvedad}), orden de "
          f"vecinos, atributos de grafo, pares críticos y caso límite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
