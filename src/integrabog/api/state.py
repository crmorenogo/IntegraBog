"""
Estado de la API: construye el grafo multicapa UNA sola vez cuando el
servidor arranca, y lo mantiene en memoria para todas las peticiones.

Por que no se reconstruye en cada request:
    Construir el grafo micro desde OSMnx o incluso solo cargarlo desde
    el .graphml de cache toma varios segundos (son ~94 MB). Si se
    hiciera en cada llamada, cada endpoint tardaria eso mismo en
    responder. La solucion estandar en FastAPI es un "lifespan": un
    bloque de codigo que corre una vez al iniciar el proceso y deja
    el resultado disponible en app.state.
"""

import time

import networkx as nx
from pyproj import Transformer

from integrabog.config import CRS_METRICO
from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.routing.network_design import calcular_costo_brt

# Mismo transformador de coordenadas que usa network_design.py, pero
# expuesto aqui porque la API tambien necesita convertir coordenadas de
# estaciones (metros, EPSG:3116) a lon/lat (EPSG:4326) para el mapa.
TRANSFORMADOR_A_LONLAT = Transformer.from_crs(CRS_METRICO, "EPSG:4326", always_xy=True)


class EstadoGrafo:
    """Contenedor simple para el grafo multicapa ya listo para consultar."""

    def __init__(self, grafo: nx.MultiDiGraph, segundos_construccion: float):
        self.grafo = grafo
        self.segundos_construccion = segundos_construccion


def construir_estado() -> EstadoGrafo:
    """Arma el grafo multicapa completo (macro + micro + fusion) y le
    calcula el costo BRT, dejando todo listo para las rutas de la API.

    El grafo macro se reconstruye siempre (es barato: 150 estaciones
    locales). El grafo micro se carga desde el .graphml en cache
    (data/processed/malla_vial_micro_tol2.graphml); si ese archivo no
    existe, OSMnx lo descarga la primera vez y esto puede tardar varios
    minutos -- correr antes 'python -m integrabog.scripts.build_micro'
    para que la API arranque rapido.
    """
    inicio = time.perf_counter()

    print("[API] Construyendo grafo macro (TransMilenio)...")
    G_macro = construir_grafo_macro()

    print("[API] Cargando grafo micro (malla vial) desde cache...")
    G_micro = obtener_malla_vial()

    print("[API] Fusionando en grafo multicapa...")
    G_multicapa = construir_grafo_multicapa(G_macro, G_micro)

    print("[API] Calculando costo BRT sobre la malla vial...")
    calcular_costo_brt(G_multicapa)

    duracion = time.perf_counter() - inicio
    print(
        f"[API] Grafo multicapa listo en {duracion:.1f} s "
        f"({G_multicapa.number_of_nodes()} nodos, {G_multicapa.number_of_edges()} aristas)."
    )

    return EstadoGrafo(grafo=G_multicapa, segundos_construccion=duracion)
