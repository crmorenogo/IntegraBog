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
from integrabog.routing.network_design import VELOCIDAD_BRT_KMH, calcular_costo_brt

# Mismo transformador de coordenadas que usa network_design.py, pero
# expuesto aqui porque la API tambien necesita convertir coordenadas de
# estaciones (metros, EPSG:3116) a lon/lat (EPSG:4326) para el mapa.
TRANSFORMADOR_A_LONLAT = Transformer.from_crs(CRS_METRICO, "EPSG:4326", always_xy=True)


class EstadoGrafo:
    """Contenedor para el grafo multicapa, con soporte para simulación
    'what‑if' de nuevas conexiones (pares críticos activables)."""

    def __init__(self, grafo: nx.MultiDiGraph, segundos_construccion: float):
        self.grafo = grafo
        self.segundos_construccion = segundos_construccion
        # --- estado de simulación what‑if ---
        self.conexion_activa: dict | None = None
        self._aristas_virtuales: list[tuple] = []  # (u, v, key) de aristas inyectadas

    # ------------------------------------------------------------------
    # mutación del grafo para simulación de pares críticos
    # ------------------------------------------------------------------

    def activar_conexion(self, origen: str, destino: str, tiempo_min: float) -> dict:
        """Añade aristas macro virtuales entre *origen* y *destino* para
        simular que existe una troncal nueva con el tiempo de viaje dado.

        Si ya hay una simulación activa, la reemplaza automáticamente."""
        if self.conexion_activa is not None:
            self.desactivar_conexion()

        # peso en metros tal que Dijkstra en capa macro devuelva
        # exactamente *tiempo_min* minutos (ver _peso_tiempo en
        # network_design.py: tiempo = (weight / 1000) / 25.2 * 60)
        peso_m = tiempo_min * VELOCIDAD_BRT_KMH * 1000.0 / 60.0

        atributos = {
            "layer": "macro",
            "nom_tronc": "SIMULACIÓN",
            "weight": peso_m,
            "length": peso_m,
            "virtual": True,
        }

        k_ida = self.grafo.add_edge(origen, destino, **atributos)
        k_vuelta = self.grafo.add_edge(destino, origen, **atributos)

        self._aristas_virtuales = [
            (origen, destino, k_ida),
            (destino, origen, k_vuelta),
        ]

        self.conexion_activa = {
            "estacion_origen": origen,
            "estacion_destino": destino,
            "tiempo_nueva_ruta_min": tiempo_min,
        }
        return self.conexion_activa

    def desactivar_conexion(self) -> None:
        """Elimina las aristas virtuales inyectadas y restaura el grafo
        a su estado original."""
        for u, v, k in self._aristas_virtuales:
            if self.grafo.has_edge(u, v, k):
                self.grafo.remove_edge(u, v, k)
        self._aristas_virtuales.clear()
        self.conexion_activa = None


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
