"""
Diagnóstico de sentido de circulación y de factibilidad de corredores en
la malla vial (Overture), con los datos reales y sin tocar el modelo.

Caso que lo motivó: la ruta propuesta Toberín -> San Mateo, al llegar por la
Av. Calle 153 a la Av. Boyacá (Av. Carrera 72), gira directo hacia la
calzada contraria en vez de dar la vuelta a la rotonda, y además usa una
calle y una rotonda donde un articulado no cabe. La primera corrida (release
2026-09-23.1) mostró que la causa eran 3 km de la Av. Carrera 72 que
Overture trae sin regla de sentido; desde entonces graph/sentido.py completa
ese sentido y la ruta solo usa vías aptas para una troncal. Este script
sirve para verificar ese arreglo y para encontrar los casos que queden.

La malla es un grafo dirigido: micro.py solo deja recorrer una pieza en el
sentido que permiten las reglas de acceso de Overture, más lo que completa
graph/sentido.py. Una contravía, entonces, solo puede venir de una de estas
causas, y cada sección mira una:

  1. Rotondas con piezas de doble sentido (las que graph/sentido.py no
     completó porque no son mayoritariamente de un sentido: muchas son
     manzanas o parques redondos, no rotondas).
  2. Calzadas separadas sin sentido: una avenida con separador son dos
     líneas paralelas con el mismo nombre, cada una de un solo sentido. Si
     una de las dos viene sin la regla y graph/sentido.py no la pudo deducir
     (las dos calzadas sin regla, o la vecina del lado equivocado), el
     modelo deja ir en contravía. Lo que salga aquí se corrige a mano con
     config.SENTIDOS_FORZADOS.
  3. Giros prohibidos: Overture los trae en 'prohibited_transitions'. Desde
     nov-2026 la ruta del modelo los respeta (graph/giros.py); aquí se
     cuentan los que hay en los datos y los que quedaron en la malla.
  4. La ruta tramo por tramo: cada pieza con sus reglas crudas, marcando
     lo que no cuadra (ver AVISOS abajo).
  5. Perfil vial: qué trae Overture (ancho, superficie, restricciones por
     dimensión del vehículo) y cuántas aristas quedan no aptas para una
     troncal y por qué.
  6. Efecto del filtro de factibilidad y de las reglas de giro: la misma
     ruta como se calculaba antes (sin filtro, sin giros prohibidos ni tope
     de giro), sin filtro pero con las reglas de giro, y la del modelo. Si la
     de antes hacía algún giro prohibido o en U, se dice dónde.

    python -m integrabog.scripts.diagnostico_sentido
    python -m integrabog.scripts.diagnostico_sentido --origen "Toberín" --destino "San Mateo"

Escribe diagnostico_sentido_ruta.geojson (la ruta tramo por tramo, con las
reglas crudas de cada segmento y su 'overture_id' para SENTIDOS_FORZADOS o
VIAS_NO_APTAS_TRONCAL, y la ruta sin filtro) para abrir en https://geojson.io.

AVISOS en la ruta:
  CONTRAVIA_SEGUN_OVERTURE  el modelo recorre la pieza en un sentido que las reglas de Overture
                            niegan para toda la pieza: sería un error del modelo, no de los datos.
  CONTRAVIA_PARCIAL         una regla de Overture niega ese sentido en PARTE de la pieza (menos de la
                            mitad, por eso el modelo la dejó pasar).
  ROTONDA_AL_REVES          la pieza bordea una rotonda (borde mayoritariamente de un sentido y
                            antihorario) y se recorre en sentido horario: en contravía.
  ROTONDA_SIN_SENTIDO       la pieza bordea una rotonda y el modelo la tiene de doble sentido.
  CARA_REDONDA_SIN_SENTIDO  la pieza es de doble sentido, bordea una cara redonda que no parece rotonda
                            y se recorre en sentido horario: si esa cara es una rotonda, es contravía.
  CALZADA_SIN_SENTIDO       la pieza es una calzada de doble sentido con otra calzada paralela del mismo
                            nombre al lado (las dos sin regla, o la otra del lado equivocado): si es una
                            avenida con separador, va en contravía (ver AVENIDAS_CON_SEPARADOR).
  SENTIDO_DEDUCIDO          el sentido de la pieza lo completó graph/sentido.py (no venía en Overture).
  GIRO_EN_U                 cambio de rumbo de más de config.GIRO_MAXIMO_BUS_GRADOS (150°) entre dos piezas
                            seguidas: una vuelta en U en un cruce. Las rutas que respetan los giros no
                            los hacen; en la de antes, marca dónde estaba.
  GIRO_PROHIBIDO_EN_DATOS   se entra a la pieza por un giro que Overture prohíbe para el bus
                            (prohibited_transitions). En las rutas que respetan los giros no puede
                            salir; en la de antes, marca dónde estaba el giro.
"""
import argparse
import json
import math
import re
from collections import Counter

import geopandas as gpd
import networkx as nx
import numpy as np
import shapely
from shapely.geometry import Point
from shapely.strtree import STRtree

from integrabog.config import CLASES_APTAS_TRONCAL, CRS_METRICO
from integrabog.graph import micro
from integrabog.graph.correcciones import _A_METRICO
from integrabog.graph.giros import (
    ATRIBUTO_GIROS,
    angulo_de_giro,
    camino_respetando_giros,
    continuaciones,
    giros_en_u,
    giros_prohibidos_en,
    rumbos,
)
from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.graph.sentido import (
    AREA_ROTONDA_M2,
    COMPACIDAD_MIN_ROTONDA,
    FRACCION_MIN_ANTIHORARIO,
    FRACCION_MIN_UN_SENTIDO,
    motivos_calzadas,
    sentido_alrededor,
)
from integrabog.routing.network_design import (
    _TRANSFORMADOR,
    _arista_del_camino,
    _geometria_ruta_lonlat,
    _peso_tiempo,
    _resolver_estacion,
    _tiempo_arista,
    calcular_costo_brt,
    peso_arista,
    ruta_nueva,
)




# --- Datos ----------------------------------------------------------------------------

def _segmentos_crudos() -> dict:
    """Segmentos crudos de Overture por id, en el CRS métrico, con las reglas
    ya normalizadas (mismo _a_python de micro.py). Vacío si no hay caché cruda."""
    crudos = micro._leer_crudo("segment")
    if crudos is None:
        print("[AVISO] No hay descarga cruda en data/raw/overture/: se omiten las reglas crudas.")
        return {}
    anidadas = ("names", "access_restrictions", "prohibited_transitions", "width_rules", "road_surface")
    columnas = [c for c in ("id", "class", "subclass", *anidadas) if c in crudos.columns]
    crudos = crudos[columnas + ["geometry"]].to_crs(CRS_METRICO)
    for c in anidadas:
        if c in crudos:
            crudos[c] = crudos[c].map(micro._a_python)
    return {fila["id"]: fila for fila in crudos.to_dict("records")}


def _id_crudo(overture_id: str, crudos: dict) -> str:
    """Las piezas que deja City2Graph llevan el id del segmento con un sufijo
    '_<n>' (una por tramo entre conectores)."""
    if overture_id in crudos:
        return overture_id
    return re.sub(r"_\d+$", "", str(overture_id))


def _piezas(G_micro: nx.MultiDiGraph) -> dict:
    """Una entrada por pieza de calle (no por sentido): geometría en el
    sentido de dibujo, nombre, clase y los sentidos en que existe."""
    piezas = {}
    for u, v, d in G_micro.edges(data=True):
        p = piezas.setdefault(d["overture_id"], {"geometry": d["geometry"] if not d.get("reversed") else None,
                                                 "name": d.get("name"), "class": d.get("class"),
                                                 "sentidos": set(), "u": u, "v": v})
        if p["geometry"] is None and not d.get("reversed"):
            p["geometry"] = d["geometry"]
        p["sentidos"].add("forward" if not d.get("reversed") else "backward")
    for p in piezas.values():
        if p["geometry"] is None:  # solo existe en sentido inverso: se guarda en el sentido de dibujo
            d = next(iter(G_micro.get_edge_data(p["u"], p["v"]).values()))
            p["geometry"] = d["geometry"].reverse()
    return piezas


def _lonlat(x: float, y: float) -> str:
    lon, lat = _TRANSFORMADOR.transform(x, y)
    return f"{lat:.5f}, {lon:.5f}"


# --- Geometría auxiliar ---------------------------------------------------------------

def tramo_de_pieza(pieza, segmento) -> tuple[float, float]:
    """Posición [desde, hasta] de una pieza dentro de su segmento crudo, como
    fracción del largo: la misma referencia lineal que usa 'between'."""
    largo = segmento.length
    if not largo:
        return 0.0, 1.0
    a = segmento.project(Point(pieza.coords[0])) / largo
    b = segmento.project(Point(pieza.coords[-1])) / largo
    return (a, b) if a <= b else (b, a)


def negado_en_parte(reglas, sentido: str, tramo: tuple[float, float]) -> bool:
    """¿Alguna regla de Overture niega este sentido, para un carro, en
    alguna parte de la pieza, aunque no cubra la mitad que exige micro.py?"""
    for regla in reglas or []:
        if not isinstance(regla, dict) or regla.get("access_type") != "denied":
            continue
        if not micro.regla_aplica({**regla, "between": None}, sentido, tramo):
            continue  # no es para carros, es condicional, o es del otro sentido
        entre = regla.get("between")
        if not entre or min(tramo[1], entre[1]) - max(tramo[0], entre[0]) > 1e-6:
            return True
    return False


# --- 1. Rotondas ----------------------------------------------------------------------

def revisar_rotondas(piezas: dict) -> dict:
    """Caras de la malla pequeñas y casi circulares, separadas en dos grupos
    con el mismo criterio de graph/sentido.py:

      - rotondas: su borde ya es mayoritariamente de un sentido y antihorario.
        El modelo les completa las piezas que falten, así que aquí no deberían
        quedar piezas de doble sentido.
      - otras caras redondas: manzanas, parques o intercambiadores grandes con
        calles de varios sentidos. El modelo no las toca. Si alguna es en
        realidad una rotonda sin reglas, se corrige con SENTIDOS_FORZADOS.

    Returns:
        {overture_id de cada pieza del borde: (centro de la cara, es_rotonda)}
    """
    print("\n--- 1. ROTONDAS ---")
    ids = list(piezas)
    lineas = [piezas[i]["geometry"] for i in ids]
    caras = [c for c in shapely.get_parts(shapely.polygonize(lineas))
             if AREA_ROTONDA_M2[0] <= c.area <= AREA_ROTONDA_M2[1]
             and 4 * math.pi * c.area / c.length ** 2 >= COMPACIDAD_MIN_ROTONDA]
    arbol = STRtree(lineas)
    borde_de, conteo, detalle = {}, Counter(), []
    for cara in caras:
        en_borde = [ids[j] for j in arbol.query(cara.exterior.buffer(1.0), predicate="contains")]
        if not en_borde:
            continue
        centro = cara.centroid
        largo = {i: piezas[i]["geometry"].length for i in en_borde}
        un_sentido = [i for i in en_borde if len(piezas[i]["sentidos"]) == 1]
        largo_un_sentido = sum(largo[i] for i in un_sentido)
        antihorario = sum(largo[i] for i in un_sentido if sentido_alrededor(_recorrido(piezas[i]), centro) == "antihorario")
        es_rotonda = (largo_un_sentido / sum(largo.values()) >= FRACCION_MIN_UN_SENTIDO
                      and antihorario / largo_un_sentido >= FRACCION_MIN_ANTIHORARIO) if largo_un_sentido else False
        for i in en_borde:
            borde_de[i] = (centro, es_rotonda)
        dobles = len(en_borde) - len(un_sentido)
        clave = "rotonda" if es_rotonda else "cara"
        conteo[clave] += 1
        conteo[clave + "_con_dobles"] += bool(dobles)
        if dobles and not es_rotonda:
            nombres = sorted({piezas[i]["name"] or "sin nombre" for i in en_borde})
            detalle.append((cara.area, _lonlat(centro.x, centro.y), dobles, len(en_borde), nombres))
    print(f"Caras casi circulares: {len(caras)} | rotondas (borde mayoritariamente de un sentido y antihorario): "
          f"{conteo['rotonda']}, con piezas de doble sentido: {conteo['rotonda_con_dobles']} "
          f"(el modelo las completa: debería ser 0)")
    print(f"Otras caras redondas (manzanas, parques, intercambiadores; el modelo no las toca): {conteo['cara']}, "
          f"con piezas de doble sentido: {conteo['cara_con_dobles']}. Las más grandes, por si alguna es una "
          f"rotonda real sin reglas (se corrige con SENTIDOS_FORZADOS):")
    for area, punto, n_dobles, n, nombres in sorted(detalle, reverse=True)[:10]:
        print(f"  {punto}  ({area:,.0f} m²): {n_dobles}/{n} piezas de doble sentido -- {', '.join(nombres[:3])}")
    return borde_de


def _recorrido(pieza: dict):
    """Geometría de una pieza en su sentido de circulación (para las de un solo sentido)."""
    return pieza["geometry"] if "forward" in pieza["sentidos"] else pieza["geometry"].reverse()


# --- 2. Calzadas separadas ------------------------------------------------------------

def revisar_calzadas(G_micro: nx.MultiDiGraph, zona: tuple[float, float, float] | None = None) -> dict:
    """Calzadas arteriales que siguen de doble sentido aunque tienen al lado
    otra calzada paralela con el mismo nombre, con el motivo por el que
    graph/sentido.py no les dedujo el sentido (el mismo cálculo, sobre la
    malla ya construida).

    Args:
        zona: (lat, lon, radio_m) para listar pieza por pieza lo que haya en
            esa zona, con su overture_id (para SENTIDOS_FORZADOS).

    Returns:
        {overture_id: motivo} de las piezas revisadas.
    """
    print("\n--- 2. CALZADAS SEPARADAS QUE SIGUEN DE DOBLE SENTIDO ---")
    filas = [{"u": u, "v": v, "overture_id": d["overture_id"], "class": d.get("class"), "name": d.get("name"),
              "reversed": bool(d.get("reversed")), "geometry": d["geometry"]}
             for u, v, d in G_micro.edges(data=True)]
    aristas = gpd.GeoDataFrame(filas, geometry="geometry", crs=CRS_METRICO)
    motivos = motivos_calzadas(aristas)
    piezas = {f["overture_id"]: f for f in filas if not f["reversed"]}
    conteo = Counter(motivos.values())
    print(f"Piezas arteriales de doble sentido revisadas: {len(motivos)} | de doble sentido de verdad (sin otra "
          f"calzada al lado): {conteo['sin vecina']} | con la otra calzada también sin regla: "
          f"{conteo['vecina de doble sentido']} | con la otra calzada del lado equivocado: {conteo['contradictoria']}")
    completables = conteo["completada"] + conteo["completada (avenida confirmada)"]
    if completables:
        """la caché no puede estar vieja respecto de config.py (micro.py la regenera si cambia un
         parámetro); lo normal es que unas pocas piezas cambien de vecina después de la pasada de
         graph/sentido.py, porque su vecina de entonces se completó en esa misma pasada o se quitó
         al podar la malla. La primera corrida con avenidas confirmadas dio 5 de 2.327"""
        print(f"  ({completables} se completarían si la regla se corriera otra vez sobre la malla final: su "
              f"calzada vecina cambió después de la primera pasada. Si fueran cientos, revisar que la caché "
              f"esté al día con build_micro.)")
    dobles = Counter(piezas[p]["name"] for p, m in motivos.items() if m == "vecina de doble sentido" and p in piezas)
    if dobles:
        print("Avenidas con las dos calzadas sin regla, por piezas (si es de calzadas separadas, agregarla a "
              "AVENIDAS_CON_SEPARADOR en config.py):")
        for nombre, n in dobles.most_common(15):
            print(f"  {nombre}: {n}")
    if zona:
        lat, lon, radio = zona
        centro = Point(*_A_METRICO.transform(lon, lat))
        cerca = sorted(((piezas[p]["geometry"].distance(centro), p, m) for p, m in motivos.items()
                        if p in piezas and piezas[p]["geometry"].distance(centro) <= radio))
        dudosas = [c for c in cerca if c[2] != "sin vecina"]
        print(f"\nEn la zona ({lat}, {lon}, {radio:.0f} m): {len(cerca)} piezas arteriales de doble sentido; "
              f"{len(cerca) - len(dudosas)} sin otra calzada al lado (de doble sentido de verdad, no se listan) y "
              f"{len(dudosas)} que podrían ser una calzada en contravía:")
        for distancia, p, m in dudosas[:60]:
            f = piezas[p]
            print(f"  {distancia:>5.0f} m  {f['class']:<9} {f['geometry'].length:>5.0f} m  "
                  f"{_lonlat(*f['geometry'].interpolate(0.5, normalized=True).coords[0][:2])}  {m:<26} "
                  f"{f['name'] or 'sin nombre'}  {p}")
    return motivos


# --- 3. Giros prohibidos --------------------------------------------------------------

def revisar_giros_prohibidos(crudos: dict, G_micro: nx.MultiDiGraph) -> None:
    print("\n--- 3. GIROS PROHIBIDOS (prohibited_transitions; la ruta del modelo los respeta) ---")
    con_reglas = [s for s in crudos.values() if isinstance(s.get("prohibited_transitions"), list)
                  and s["prohibited_transitions"]]
    print(f"Segmentos con prohibited_transitions: {len(con_reglas)} de {len(crudos)}")
    llegadas = [d for _, _, d in G_micro.edges(data=True) if d.get(ATRIBUTO_GIROS)]
    print(f"En la malla, para el bus: {sum(len(continuaciones(d)) for d in llegadas)} giros prohibidos desde "
          f"{len(llegadas)} aristas de llegada (build_micro dice cuántos no le aplican al bus y por qué)")
    if con_reglas:
        print("  ejemplo:", json.dumps(con_reglas[0]["prohibited_transitions"], ensure_ascii=False, default=str)[:400])


# --- 4. La ruta -----------------------------------------------------------------------

def _aristas_sin_filtro(G: nx.MultiDiGraph, o: str, d: str) -> list[tuple]:
    """Toda la malla vial (con su sentido, sin el filtro de factibilidad) más las
    transferencias de origen y destino: la ruta como se calculaba antes del filtro."""
    return [(u, v, k) for u, v, k, a in G.edges(keys=True, data=True)
            if a.get("layer") == "micro" or (a.get("layer") == "transferencia" and {u, v} & {o, d})]


def revisar_ruta(G: nx.MultiDiGraph, crudos: dict, rotondas: dict, motivos: dict, o: str, d: str) -> tuple[list, list]:
    print(f"\n--- 4. RUTA PROPUESTA: {G.nodes[o].get('etiqueta', o)} -> {G.nodes[d].get('etiqueta', d)} ---")
    """la misma ruta que calcula el modelo (sugerir_nueva_troncal): solo vías aptas, sin giros prohibidos"""
    camino, claves, _ = ruta_nueva(G, o, d)
    filas, features = filas_de_camino(G, camino, crudos, rotondas, motivos, "modelo (tramo por tramo)", claves)
    _imprimir_ruta(filas, detalle=True)
    return camino, features


def filas_de_camino(G, camino, crudos: dict, rotondas: dict, motivos: dict, etiqueta: str,
                    claves: list | None = None, color: str = "#2563eb") -> tuple[list, list]:
    """Cada tramo de malla del camino con sus avisos (ver AVISOS en el docstring).
    'claves': las de la ruta, si se conocen (si no, la mejor de las aristas paralelas).
    'color': el de los tramos sin aviso en el GeoJSON (rojo = aviso, morado = sentido deducido)."""
    aristas = [_arista_del_camino(G, camino, claves, i) for i in range(len(camino) - 1)]
    """el giro prohibido se busca en la secuencia entera (con las transferencias, que cortan
     cualquier giro en curso), con las mismas reglas que respeta la ruta del modelo"""
    por_giro_prohibido, en_u = set(giros_prohibidos_en(aristas)), set(giros_en_u(aristas))
    features, filas, anterior = [], [], None
    for orden, a in enumerate(aristas):
        if a.get("layer") != "micro":
            anterior = None
            continue
        sentido = "backward" if a.get("reversed") else "forward"
        id_crudo = _id_crudo(a["overture_id"], crudos)
        crudo = crudos.get(id_crudo, {})
        reglas = crudo.get("access_restrictions")
        marcas = []
        if crudo:
            dibujo = a["geometry"].reverse() if a.get("reversed") else a["geometry"]
            tramo = tramo_de_pieza(dibujo, crudo["geometry"])
            if not micro.es_circulable(reglas, sentido, tramo):
                marcas.append("CONTRAVIA_SEGUN_OVERTURE")
            elif negado_en_parte(reglas, sentido, tramo):
                marcas.append("CONTRAVIA_PARCIAL")
        if a.get("sentido_inferido"):
            marcas.append("SENTIDO_DEDUCIDO")
        if not a.get("oneway") and motivos.get(a["overture_id"]) in ("vecina de doble sentido", "contradictoria"):
            marcas.append("CALZADA_SIN_SENTIDO")
        if a["overture_id"] in rotondas:
            centro, es_rotonda = rotondas[a["overture_id"]]
            horario = sentido_alrededor(a["geometry"], centro) == "horario"
            if es_rotonda and horario:
                marcas.append("ROTONDA_AL_REVES")
            elif es_rotonda and not a.get("oneway"):
                marcas.append("ROTONDA_SIN_SENTIDO")
            elif not es_rotonda and horario and not a.get("oneway"):
                """una pieza de UN sentido de una cara que no es rotonda va por donde dicen los datos
                 (en la primera corrida, un tramo de la NQS en el borde de una manzana de 3,7 ha se
                 marcaba como rotonda al revés sin serlo); solo se avisa si es de doble sentido"""
                marcas.append("CARA_REDONDA_SIN_SENTIDO")
        """el mismo rumbo y el mismo tope de giro que usa la búsqueda de la ruta (graph/giros.py)"""
        giro = angulo_de_giro(rumbos(anterior)[1], rumbos(a)[0]) if anterior is not None else None
        if orden in en_u:
            marcas.append("GIRO_EN_U")
        if orden in por_giro_prohibido:
            marcas.append("GIRO_PROHIBIDO_EN_DATOS")
        filas.append({"orden": orden, "nombre": a.get("name") or "sin nombre", "clase": a.get("class") or "",
                      "largo": a.get("length", 0.0), "un_solo_sentido": bool(a.get("oneway")),
                      "giro": None if giro is None else round(giro), "avisos": marcas,
                      "punto": _lonlat(*a["geometry"].coords[0][:2]), "overture_id": a["overture_id"],
                      "viene_de": (anterior.get("name") or "sin nombre") if anterior is not None else None,
                      "viene_de_id": anterior["overture_id"] if anterior is not None else None})
        features.append({
            "type": "Feature",
            "geometry": shapely.geometry.mapping(shapely.transform(a["geometry"], _a_lonlat)),
            "properties": {
                "ruta": etiqueta, "orden": orden, "nombre": a.get("name"),
                "clase": a.get("class"), "subclase": a.get("subclass"),
                "un_solo_sentido": bool(a.get("oneway")), "recorrido_al_reves_del_dibujo": bool(a.get("reversed")),
                "giro_grados": None if giro is None else round(giro), "avisos": marcas,
                "overture_id": a["overture_id"],
                "access_restrictions": json.dumps(reglas, ensure_ascii=False, default=str),
                "stroke": ("#dc2626" if set(marcas) - {"SENTIDO_DEDUCIDO"}
                           else "#9333ea" if marcas else color), "stroke-width": 4,
            },
        })
        anterior = a
    return filas, features


def _imprimir_ruta(filas: list, detalle: bool) -> None:
    avisos = Counter(m for f in filas for m in f["avisos"])
    print(f"Tramos de malla en la ruta: {len(filas)} | {sum(f['largo'] for f in filas) / 1000:.1f} km")
    print(f"Avisos: {dict(avisos) if avisos else 'ninguno'}")
    print("\nCalles de la ruta, en orden (tramos seguidos con el mismo nombre y clase, agrupados):")
    for nombre, clase, metros, unico, marcas in _agrupar_por_calle(filas):
        print(f"  {metros:>6.0f} m  {clase:<12} {'1 sentido ' if unico else '2 sentidos'}  {nombre}"
              f"{'   <- ' + ', '.join(sorted(marcas)) if marcas else ''}")
    marcadas = [i for i, f in enumerate(filas) if set(f["avisos"]) - {"SENTIDO_DEDUCIDO"}]
    if detalle and marcadas:
        print("\nTramos con aviso (y los 2 de antes y después), con su overture_id:")
        print("  #     giro  1-sent  clase        punto (lat, lon)     nombre")
        mostrar = sorted({j for i in marcadas for j in range(max(0, i - 2), min(len(filas), i + 3))})
        for j in mostrar:
            f = filas[j]
            print(f"  {f['orden']:<5}{'' if f['giro'] is None else f['giro']:>5}  {'sí' if f['un_solo_sentido'] else 'no':<6}  "
                  f"{f['clase']:<12} {f['punto']:<20} {f['nombre']}  {f['overture_id']}  {' '.join(f['avisos'])}")


def _agrupar_por_calle(filas: list) -> list:
    grupos = []
    for f in filas:
        if grupos and grupos[-1][0] == f["nombre"] and grupos[-1][1] == f["clase"]:
            g = grupos[-1]
            grupos[-1] = (g[0], g[1], g[2] + f["largo"], g[3] and f["un_solo_sentido"], g[4] | set(f["avisos"]))
        else:
            grupos.append((f["nombre"], f["clase"], f["largo"], f["un_solo_sentido"], set(f["avisos"])))
    return grupos


def _a_lonlat(coords: np.ndarray) -> np.ndarray:
    lons, lats = _TRANSFORMADOR.transform(coords[:, 0], coords[:, 1])
    return np.column_stack([lons, lats])


# --- 5. Perfil vial en los datos ------------------------------------------------------

def revisar_perfil_vial(crudos: dict) -> None:
    """¿Trae Overture lo necesario para decidir si un articulado cabe en una
    vía? El esquema tiene 'width_rules' (ancho en metros) y 'road_surface';
    lo que importa es cuántas vías de Bogotá lo traen de verdad."""
    print("\n--- 5. PERFIL VIAL EN LOS DATOS (para un filtro de vía apta) ---")
    vehiculares = [s for s in crudos.values() if s.get("class") in micro.CLASES_VIALES_VEHICULARES]
    if not vehiculares:
        print("  Sin segmentos crudos vehiculares.")
        return
    total = len(vehiculares)
    con_ancho = [s for s in vehiculares if isinstance(s.get("width_rules"), list) and s["width_rules"]]
    superficies = Counter(json.dumps(s.get("road_surface"), default=str)[:40] for s in vehiculares
                          if isinstance(s.get("road_surface"), list) and s["road_surface"])
    print(f"Segmentos vehiculares: {total} | con ancho (width_rules): {len(con_ancho)} "
          f"({100 * len(con_ancho) / total:.1f} %)")
    por_clase = Counter(s["class"] for s in con_ancho)
    if por_clase:
        print(f"  con ancho, por clase: {dict(por_clase.most_common())}")
        print(f"  ejemplo: {json.dumps(con_ancho[0]['width_rules'], default=str)[:200]}")
    print(f"Con superficie declarada: {sum(superficies.values())} | valores más comunes: "
          f"{dict(superficies.most_common(5)) if superficies else 'ninguno'}")
    """límites de altura, peso o largo: Overture los expresa como reglas de acceso para vehículos
     que superan una dimensión (when.vehicle). micro.py hoy los ignora porque evalúa un carro;
     para un articulado (18 m) o un biarticulado (27 m) serían justo los que importan"""
    con_dimension = [s for s in vehiculares
                     if any(isinstance(r, dict) and (r.get("when") or {}).get("vehicle")
                            for r in (s.get("access_restrictions") or []))]
    print(f"Con límites por dimensión o peso del vehículo (when.vehicle): {len(con_dimension)} "
          f"({100 * len(con_dimension) / total:.1f} %)")
    if con_dimension:
        ejemplo = next(r for r in con_dimension[0]["access_restrictions"]
                       if isinstance(r, dict) and (r.get("when") or {}).get("vehicle"))
        print(f"  ejemplo: {json.dumps(ejemplo, ensure_ascii=False, default=str)[:250]}")
    print("Radio de giro y número o ancho de carriles: no existen en el esquema de Overture.")


def revisar_aptitud(G: nx.MultiDiGraph) -> None:
    """Cuántas aristas de la malla no puede usar una troncal nueva, y por qué."""
    micro_aristas = [d for _, _, d in G.edges(data=True) if d.get("layer") == "micro"]
    total = len(micro_aristas)
    motivos = Counter(str(d.get("motivo_no_apta")).split(":")[0] for d in micro_aristas if not d.get("apta_troncal", True))
    por_clase = sum(1 for d in micro_aristas if d.get("apta_troncal", True) and d.get("class") not in CLASES_APTAS_TRONCAL)
    partes = [f"por clase vial menor {por_clase} ({100 * por_clase / max(total, 1):.0f} %; solo usables como acceso)"]
    partes += [f"{m} {n}" for m, n in motivos.most_common()]
    print(f"\nAristas de la malla: {total} | no aptas para troncal: " + ", ".join(partes))
    deducidas = Counter(d.get("sentido_inferido") for d in micro_aristas if d.get("sentido_inferido"))
    print(f"Aristas con sentido completado por graph/sentido.py: {dict(deducidas) if deducidas else 'ninguna'}")


# --- 6. Escenarios --------------------------------------------------------------------

ANTES, SIN_FILTRO, MODELO = ("antes: sin filtro, sin reglas de giro", "sin filtro (sentido y giros)",
                              "modelo: vías aptas, sentido y giros")
_COLOR_RUTA = {ANTES: "#6b7280", SIN_FILTRO: "#f59e0b", MODELO: "#16a34a"}


def _ruta_escenario(G: nx.MultiDiGraph, o: str, d: str, nombre: str) -> tuple[list, list | None]:
    """(nodos, claves) de la ruta de cada escenario; las claves son None en la de antes, que
    se calculaba con nx.shortest_path (la mejor de las aristas paralelas), sin giros
    prohibidos ni tope de giro. Las otras dos respetan ambos."""
    if nombre == MODELO:
        camino, claves, _ = ruta_nueva(G, o, d)
        return camino, claves
    aristas = _aristas_sin_filtro(G, o, d)
    if nombre == ANTES:
        return nx.shortest_path(G.edge_subgraph(aristas), o, d, weight=_peso_tiempo), None
    camino, claves, _ = camino_respetando_giros(G, o, d, peso_arista, aristas=aristas)
    return camino, claves


def revisar_filtro(G: nx.MultiDiGraph, crudos: dict, rotondas: dict, motivos: dict, o: str, d: str) -> list:
    """La misma ruta como se calculaba antes (sin filtro de factibilidad ni reglas de giro),
    sin filtro pero respetando los giros prohibidos y el tope de giro, y la del modelo, para
    ver qué cambia: distancia, tiempo, tipo de vía, giros y si sigue usando las vías marcadas
    a mano."""
    print("\n--- 6. EFECTO DEL FILTRO DE FACTIBILIDAD Y DE LAS REGLAS DE GIRO EN LA RUTA ---")
    print(f"\n  {'ruta':<38} {'km':>6} {'min':>6}  {'arterias':>9}  {'otras':>6}  {'no aptas':>9}  "
          f"{'giros prohib.':>13}  {'giros en U':>10}  usa 'Calle 153'")
    features, caminos = [], {}
    for nombre in (ANTES, SIN_FILTRO, MODELO):
        try:
            camino, claves = _ruta_escenario(G, o, d, nombre)
        except nx.NetworkXNoPath:
            print(f"  {nombre:<38}   sin ruta posible")
            continue
        aristas = [_arista_del_camino(G, camino, claves, i) for i in range(len(camino) - 1)]
        metros, minutos, arterias, no_aptas, calle_153 = 0.0, 0.0, 0.0, 0.0, False
        for a in aristas:
            minutos += _tiempo_arista(a)
            if a.get("layer") != "micro":
                continue
            largo = a.get("length", 0.0)
            metros += largo
            arterias += largo if a.get("class") in CLASES_APTAS_TRONCAL else 0.0
            no_aptas += largo if not a.get("apta_troncal", True) else 0.0
            calle_153 |= "153" in str(a.get("name") or "")
        giros, vueltas = len(giros_prohibidos_en(aristas)), len(giros_en_u(aristas))
        caminos[nombre] = (camino, claves)
        print(f"  {nombre:<38} {metros / 1000:>6.1f} {minutos:>6.1f}  {100 * arterias / max(metros, 1):>8.0f}%  "
              f"{100 * (metros - arterias) / max(metros, 1):>5.0f}%  {no_aptas:>7.0f} m  {giros:>13}  {vueltas:>10}  "
              f"{'sí' if calle_153 else 'no'}")
        features.append({"type": "Feature",
                         "geometry": {"type": "LineString", "coordinates": _geometria_ruta_lonlat(G, camino, claves)},
                         "properties": {"ruta": nombre, "km": round(metros / 1000, 2), "min": round(minutos, 1),
                                        "giros_prohibidos": giros, "giros_en_u": vueltas, "stroke": _COLOR_RUTA[nombre],
                                        "stroke-width": 3, "stroke-opacity": 0.8}})
    print(f"\n  (arterias = {', '.join(sorted(CLASES_APTAS_TRONCAL))}; no aptas = superficie, restricción para el bus "
          "o lista manual de config.py; giros prohib. = giros que Overture prohíbe para el bus; giros en U = "
          "de más de config.GIRO_MAXIMO_BUS_GRADOS en un cruce)")

    if ANTES in caminos:
        camino_antes, claves_antes = caminos[ANTES]
        filas, _ = filas_de_camino(G, camino_antes, crudos, rotondas, motivos, ANTES, claves_antes)
        giros = [f for f in filas if {"GIRO_PROHIBIDO_EN_DATOS", "GIRO_EN_U"} & set(f["avisos"])]
        if giros:
            print("\nGiros que hacía la ruta de antes y que el modelo ya no hace:")
            for f in giros:
                tipo = "prohibido en los datos" if "GIRO_PROHIBIDO_EN_DATOS" in f["avisos"] else f"en U ({f['giro']}°)"
                print(f"  {f['punto']}  {tipo}: de {f['viene_de']} ({f['viene_de_id']}) a {f['nombre']} "
                      f"({f['overture_id']})")
    if SIN_FILTRO in caminos and caminos[SIN_FILTRO][0] != caminos.get(MODELO, (None,))[0]:
        """la ruta sin filtro también se muestra calle por calle (y tramo por tramo en el GeoJSON):
         ahí se ve si al modelo le queda alguna contravía (CALZADA_SIN_SENTIDO) o una maniobra rara
         que hoy solo esquiva porque el filtro lo desvía"""
        print(f"\nRuta {SIN_FILTRO}, calle por calle:")
        filas, tramos = filas_de_camino(G, caminos[SIN_FILTRO][0], crudos, rotondas, motivos, SIN_FILTRO,
                                        caminos[SIN_FILTRO][1], color=_COLOR_RUTA[SIN_FILTRO])
        _imprimir_ruta(filas, detalle=True)
        features += tramos
    return features


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--origen", default="Toberín")
    parser.add_argument("--destino", default="San Mateo")
    parser.add_argument("--salida", default="diagnostico_sentido_ruta.geojson")
    parser.add_argument("--zona", help="lat,lon: lista pieza por pieza las calzadas de doble sentido de esa zona, "
                                       "con su overture_id y el motivo")
    parser.add_argument("--radio", type=float, default=1500.0, help="radio de --zona en metros (1500)")
    args = parser.parse_args()
    zona = (*map(float, args.zona.split(",")), args.radio) if args.zona else None

    G_micro = micro.obtener_malla_vial()
    crudos = _segmentos_crudos()
    piezas = _piezas(G_micro)
    sentidos = Counter(len(p["sentidos"]) for p in piezas.values())
    print(f"\nPiezas de calle: {len(piezas)} | un solo sentido: {sentidos[1]} | doble sentido: {sentidos[2]}")

    rotondas = revisar_rotondas(piezas)
    motivos = revisar_calzadas(G_micro, zona)
    revisar_giros_prohibidos(crudos, G_micro)

    G = construir_grafo_multicapa(construir_grafo_macro(), G_micro)
    calcular_costo_brt(G)
    o, d = _resolver_estacion(G, args.origen), _resolver_estacion(G, args.destino)
    _, features = revisar_ruta(G, crudos, rotondas, motivos, o, d)
    revisar_perfil_vial(crudos)
    revisar_aptitud(G)
    features += revisar_filtro(G, crudos, rotondas, motivos, o, d)

    with open(args.salida, "w", encoding="utf-8") as archivo:
        json.dump({"type": "FeatureCollection", "features": features}, archivo, ensure_ascii=False)
    print(f"\nRutas guardadas en {args.salida} (abrir en https://geojson.io): la del modelo tramo por tramo "
          f"(en rojo los tramos con aviso, en morado los de sentido deducido; cada uno con su overture_id), "
          f"y las de la sección 6: la del modelo (verde), sin filtro (naranja, también tramo por tramo si "
          f"difiere de la del modelo) y la de antes (gris).")


if __name__ == "__main__":
    main()
