import networkx as nx
import osmnx as ox

from integrabog.config import (
    CONSERVAR_VIAS_SIN_SALIDA,
    CRS_METRICO,
    RUTA_GRAFO_BASE,
    RUTA_GRAFO_MICRO,
    TOLERANCIA_CONSOLIDACION_M,
)


def _obtener_grafo_base(lugar: str | list[str], forzar_descarga: bool = False) -> nx.MultiDiGraph:
    if RUTA_GRAFO_BASE.exists() and not forzar_descarga:
        print(f"Cargando grafo base desde caché: {RUTA_GRAFO_BASE}")
        return ox.load_graphml(RUTA_GRAFO_BASE)

    print(f"Descargando red vial de '{lugar}' desde OpenStreetMap...")
    ox.settings.use_cache = True
    ox.settings.log_console = True
    G_crudo = ox.graph_from_place(lugar, network_type="drive", simplify=True)  # type: ignore[arg-type]

    print(f"Proyectando al CRS {CRS_METRICO}...")
    G_proyectado = ox.project_graph(G_crudo, to_crs=CRS_METRICO)

    RUTA_GRAFO_BASE.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G_proyectado, filepath=RUTA_GRAFO_BASE)
    return G_proyectado


def _ruta_cache_micro(tolerancia: float):
    return RUTA_GRAFO_MICRO.parent / f"malla_vial_micro_tol{tolerancia:g}.graphml"


def obtener_malla_vial(
    lugar: str | list[str] | None = None,
    forzar_descarga: bool = False,
    tolerancia: float = TOLERANCIA_CONSOLIDACION_M,
) -> nx.MultiDiGraph:
    ruta_cache = _ruta_cache_micro(tolerancia)
    if ruta_cache.exists() and not forzar_descarga:
        print(f"Cargando grafo micro (tolerancia={tolerancia}) desde caché: {ruta_cache}")
        return ox.load_graphml(ruta_cache)

    if lugar is None:
        lugar = ["Bogotá, Colombia", "Soacha, Colombia"]
    G_proyectado = _obtener_grafo_base(lugar, forzar_descarga)
    nodos_antes = G_proyectado.number_of_nodes()

    print(f"Consolidando intersecciones (radio {tolerancia} m)...")
    G_consolidado = ox.consolidate_intersections(
        G_proyectado,
        tolerance=tolerancia,
        rebuild_graph=True,
        dead_ends=CONSERVAR_VIAS_SIN_SALIDA,  # política explícita -- ver config.py
        reconnect_edges=True,
    )
    nodos_despues = G_consolidado.number_of_nodes()
    print(
        f"Nodos: {nodos_antes} -> {nodos_despues} "
        f"({(1 - nodos_despues / nodos_antes) * 100:.1f}% fusionado)"
    )

    # medir ANTES de quedarse solo con la componente más grande -- si se descartara a
    # ciegas y resultara que el segundo componente también es grande, se estaría
    # perdiendo una porción real de la ciudad sin enterarse
    componentes = sorted(nx.strongly_connected_components(G_consolidado), key=len, reverse=True)
    print(f"Componentes fuertemente conexas: {len(componentes)}")
    print(f"Tamaños (top 10): {[len(c) for c in componentes[:10]]}")
    print(
        f"El componente más grande retiene {len(componentes[0])}/{nodos_despues} nodos "
        f"({len(componentes[0]) / nodos_despues * 100:.1f}%)"
    )

    G_final = G_consolidado.subgraph(componentes[0]).copy()

    ruta_cache.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G_final, filepath=ruta_cache)
    return G_final
