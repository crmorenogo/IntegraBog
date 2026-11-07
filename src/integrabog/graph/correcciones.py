"""
Correcciones manuales: a la conectividad inferida del grafo macro
(CONEXIONES_BLOQUEADAS / CONEXIONES_VERIFICADAS) y a la aptitud de la malla
vial para una troncal (VIAS_NO_APTAS_TRONCAL, al final del archivo).

Por qué existen: costura.py y cruces.py deducen las conexiones entre
troncales solo de la geometría del trazado, y la geometría no sabe hacia
dónde dejan girar los puentes. Hay empalmes que en el plano parecen
permitir un movimiento que en la calle no existe -- el caso que abrió esta
lista: en el puente de la Calle 92 los buses pasan de la NQS a la
Autopista Norte solo hacia el norte (La Castellana -> Calle 100), y el giro
en "V" hacia el sur (Virrey) es físicamente imposible, aunque el trazado
deje las dos troncales tocándose ahí.

Esa información la aporta alguien que conoce la operación, así que vive
en config.py (CONEXIONES_BLOQUEADAS y CONEXIONES_VERIFICADAS) y no
enterrada en el código: cada entrada lleva su motivo, para que quien
revise el modelo sepa de dónde sale.

Las listas usan cod_nodo y no el nombre de la estación: los nombres
cambian con los patrocinios ("Calle 100 - Marketmedios") y hay uno
repetido entre las 150 estaciones ("Temporal AV. Jiménez - Inter
Eléctricas"). Si una actualización de Datos Abiertos cambia un cod_nodo, la
corrección no se aplica en silencio: se imprime una advertencia con el
par que ya no se encuentra.
"""
import re

import networkx as nx
from pyproj import Transformer
from shapely.geometry import Point

from integrabog.config import CRS_METRICO
from integrabog.graph.sentido import normalizar_nombre

TIPOS_INFERIDOS = ("costura", "cruce")  # las aristas de builder.py vienen del trazado mismo


def aplicar_conexiones_bloqueadas(G: nx.DiGraph, bloqueadas: list[tuple[int, int, str]]) -> list[str]:
    """Quita del grafo macro las conexiones marcadas como inexistentes en la
    operación real, en los dos sentidos.

    Solo quita aristas inferidas (costura o cruce): una arista entre dos
    estaciones consecutivas de la misma pieza del trazado (builder.py) es
    el dato oficial, y si estuviera mal habría que corregir el trazado, no
    taparlo aquí.

    Args:
        G: grafo macro ya armado. Se modifica en el lugar.
        bloqueadas: (cod_nodo_a, cod_nodo_b, motivo).

    Returns:
        Una línea por par efectivamente quitado ("A <-> B"), para el
        reporte de construir_grafo_macro().
    """
    quitadas = []
    for a, b, _motivo in bloqueadas:
        if a not in G or b not in G:
            faltan = [n for n in (a, b) if n not in G]
            print(f"[ADVERTENCIA] Conexión bloqueada {a} <-> {b}: no existe la estación {faltan} "
                  f"en los datos (¿cambió el cod_nodo?). Revisar CONEXIONES_BLOQUEADAS en config.py.")
            continue
        aristas = [(u, v) for u, v in ((a, b), (b, a)) if G.has_edge(u, v)]
        if not aristas:
            print(f"[ADVERTENCIA] Conexión bloqueada {G.nodes[a]['nombre']} <-> {G.nodes[b]['nombre']}: "
                  f"ya no la genera el modelo; se puede quitar de CONEXIONES_BLOQUEADAS.")
            continue
        no_inferidas = [(u, v) for u, v in aristas if G[u][v].get("tipo") not in TIPOS_INFERIDOS]
        if no_inferidas:
            print(f"[ADVERTENCIA] Conexión bloqueada {G.nodes[a]['nombre']} <-> {G.nodes[b]['nombre']}: "
                  f"viene del trazado oficial (no de la costura ni de un cruce); no se quita.")
            continue
        G.remove_edges_from(aristas)
        quitadas.append(f"{G.nodes[a]['nombre']} <-> {G.nodes[b]['nombre']}")
    return quitadas


def es_verificada(a: int, b: int, verificadas: list[tuple[int, int, str]]) -> str | None:
    """Motivo con el que se verificó a mano la conexión a <-> b, o None."""
    for x, y, motivo in verificadas:
        if {x, y} == {a, b}:
            return motivo
    return None


# --- Malla vial: vías no aptas para una troncal -----------------------------------------

_A_METRICO = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)


def aplicar_vias_no_aptas(G_micro: nx.MultiDiGraph, reglas: list[dict]) -> int:
    """Marca como no aptas para una troncal ('apta_troncal' = False, con el
    motivo) las aristas de la malla vial que nombra config.VIAS_NO_APTAS_TRONCAL.

    Por qué hace falta además del filtro por clase vial: la clase de Overture
    no sabe del ancho de la calzada ni de los radios de giro. La Av. Calle 153,
    por ejemplo, viene como 'primary' y el filtro por clase la deja pasar,
    aunque un articulado no quepa. Eso solo lo sabe quien conoce la ciudad,
    así que va en una lista, cada entrada con su motivo.

    No quita aristas: la malla sigue sirviendo para enganchar estaciones y
    para todo lo demás; solo la ruta de una troncal nueva las evita.

    Returns:
        Cuántas aristas se marcaron.
    """
    total = 0
    for regla in reglas:
        nombre = normalizar_nombre(regla.get("nombre"))
        overture_id = regla.get("overture_id")
        if not (nombre or overture_id):
            raise ValueError(f"VIAS_NO_APTAS_TRONCAL: la entrada {regla} no trae 'nombre' ni 'overture_id'.")
        zona = None
        if regla.get("cerca_de"):
            lat, lon = regla["cerca_de"]
            zona = (Point(*_A_METRICO.transform(lon, lat)), float(regla.get("radio_m", 200.0)))
        motivo = f"lista manual: {regla.get('motivo', 'sin motivo anotado')}"
        marcadas = 0
        for _, _, datos in G_micro.edges(data=True):
            if overture_id and overture_id not in (datos.get("overture_id"),
                                                   re.sub(r"_\d+$", "", str(datos.get("overture_id")))):
                continue
            if nombre and normalizar_nombre(datos.get("name")) != nombre:
                continue
            if zona and datos["geometry"].distance(zona[0]) > zona[1]:
                continue
            datos["apta_troncal"] = False
            datos["motivo_no_apta"] = motivo
            marcadas += 1
        etiqueta = regla.get("nombre") or overture_id
        if marcadas:
            print(f"Vías no aptas para troncal (config.py): {etiqueta} -> {marcadas} aristas")
        else:
            print(f"[ADVERTENCIA] VIAS_NO_APTAS_TRONCAL: ninguna arista coincide con '{etiqueta}'"
                  f"{' en la zona dada' if zona else ''}. Revisar el nombre tal como lo trae Overture "
                  f"(diagnostico_sentido_ruta.geojson lo muestra).")
        total += marcadas
    return total
