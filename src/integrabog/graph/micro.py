"""
Módulo para la extracción y procesamiento del Grafo Micro (Malla Vial)
utilizando OpenStreetMap (OSMnx).

La razón de separar esto en dos funciones (_obtener_grafo_base y
obtener_malla_vial) y dos cachés distintas es de tiempo, no de estilo:
descargar y proyectar la malla vial es lo lento (~15 minutos la primera
vez), y NO depende de qué tolerancia de consolidación se use. Si todo
quedara en una sola función con una sola caché, cada vez que se quisiera
probar un valor de tolerancia distinto habría que volver a descargar
todo desde OpenStreetMap. Separado así, la descarga se cachea una sola
vez en RUTA_GRAFO_BASE, y cada tolerancia que se pruebe cachea su propio
resultado aparte -- probar una tolerancia nueva es rápido, y volver a
una que ya se probó es instantáneo.
"""

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
    """Descarga la malla vial cruda y la proyecta a un CRS métrico. No
    depende de la tolerancia de consolidación, por eso se cachea aparte
    (ver docstring del módulo).

    Args:
        lugar: nombre de lugar o lista de nombres para ox.graph_from_place.
            Tiene que ser una lista con Bogotá Y Soacha explícitos -- la
            extensión troncal a Soacha queda fuera del límite
            administrativo de Bogotá, y una consulta solo por "Bogotá,
            Colombia" deja esa zona sin ninguna calle descargada.
        forzar_descarga: si es True, ignora la caché y vuelve a bajar
            todo, incluso si ya existe RUTA_GRAFO_BASE.

    Returns:
        Grafo vial crudo, ya proyectado a CRS_METRICO, sin consolidar.
    """
    if RUTA_GRAFO_BASE.exists() and not forzar_descarga:
        print(f"Cargando grafo base desde caché: {RUTA_GRAFO_BASE}")
        return ox.load_graphml(RUTA_GRAFO_BASE)

    print(f"Descargando red vial de '{lugar}' desde OpenStreetMap...")
    ox.settings.use_cache = True
    ox.settings.log_console = True
    """ "drive" y no un filtro custom a trunk/primary/secondary: restringir solo a vías
     principales arriesga fragmentar la red en varios pedazos (le falta lo que conecta
     una avenida con otra); "drive" trae la jerarquía completa manejable sin arrastrar
     andenes, ciclorrutas ni vías de servicio que "all" sí incluiría"""
    G_crudo = ox.graph_from_place(lugar, network_type="drive", simplify=True)

    print(f"Proyectando al CRS {CRS_METRICO}...")
    """ tiene que pasar por acá ANTES de consolidar -- consolidate_intersections mide su
     tolerancia en las unidades del CRS, y en CRS84 (grados) esa tolerancia no significa nada"""
    G_proyectado = ox.project_graph(G_crudo, to_crs=CRS_METRICO)

    RUTA_GRAFO_BASE.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G_proyectado, filepath=RUTA_GRAFO_BASE)
    return G_proyectado


def _ruta_cache_micro(tolerancia: float):
    """Un archivo de caché distinto por cada tolerancia probada, para que
    repetir la misma tolerancia sea instantáneo y probar una nueva no
    pise el resultado de la anterior.

    Args:
        tolerancia: valor de tolerancia de consolidación, se usa tal
            cual en el nombre del archivo.

    Returns:
        Path al archivo de caché correspondiente a esa tolerancia.
    """
    return RUTA_GRAFO_MICRO.parent / f"malla_vial_micro_tol{tolerancia:g}.graphml"


def obtener_malla_vial(
    lugar: str | list[str] | None = None,
    forzar_descarga: bool = False,
    tolerancia: float = TOLERANCIA_CONSOLIDACION_M,
) -> nx.MultiDiGraph:
    """Entrega la malla vial lista para usar: descargada, proyectada,
    con intersecciones consolidadas y reducida a su componente
    fuertemente conexo más grande.

    Args:
        lugar: ver _obtener_grafo_base.
        forzar_descarga: si es True, ignora ambas cachés (base y de esta
            tolerancia) y reconstruye todo desde cero.
        tolerancia: radio en metros para ox.consolidate_intersections.
            Es un RADIO por nodo, no una distancia máxima directa: dos
            nodos se fusionan si están a menos de 2x este valor entre
            sí. El valor por defecto (ver config.py) se eligió
            comparando 2.0/5.0/10.0 m e inspeccionando el tamaño de los
            clústeres resultantes, no dejando el default de la librería.

    Returns:
        Grafo vial consolidado, con nodos e intersecciones reales de
        Bogotá y Soacha, restringido a su componente fuertemente conexo
        más grande.
    """
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

    """ medir ANTES de quedarse solo con la componente más grande -- si se descartara a
     ciegas y resultara que el segundo componente también es grande, se estaría
     perdiendo una porción real de la ciudad sin enterarse"""
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
