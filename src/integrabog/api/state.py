import time

import networkx as nx
from pyproj import Transformer

from integrabog.config import CRS_METRICO
from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.routing.network_design import calcular_costo_brt

TRANSFORMADOR_A_LONLAT = Transformer.from_crs(CRS_METRICO, "EPSG:4326", always_xy=True)


class EstadoGrafo:
    def __init__(self, grafo: nx.MultiDiGraph, segundos_construccion: float):
        self.grafo = grafo
        self.segundos_construccion = segundos_construccion


def construir_estado() -> EstadoGrafo:
    inicio = time.perf_counter()

    print("[API] Construyendo grafo macro (TransMilenio)...")
    G_macro = construir_grafo_macro()

    print("[API] Cargando grafo micro (malla vial) desde cache...")
    G_micro = obtener_malla_vial()

    print("[API] Fusionando en grafo multicapa...")
    g_multicapa = construir_grafo_multicapa(G_macro, G_micro)

    print("[API] Calculando costo BRT sobre la malla vial...")
    calcular_costo_brt(g_multicapa)

    duracion = time.perf_counter() - inicio
    print(
        f"[API] Grafo multicapa listo en {duracion:.1f} s "
        f"({g_multicapa.number_of_nodes()} nodos, {g_multicapa.number_of_edges()} aristas)."
    )

    return EstadoGrafo(grafo=g_multicapa, segundos_construccion=duracion)
