"""
Escenarios de la red troncal: la red de hoy más las troncales propuestas,
para medir el antes y el después con las mismas métricas
(routing/metricas.py y routing/robustez.py) y sobre las mismas estaciones.

Cómo entra una troncal propuesta al grafo macro, y por qué así:

  - Como una arista nueva entre sus dos estaciones, en los dos sentidos, de
    tipo 'propuesta' (network_design.TIPO_ARISTA_PROPUESTA). Sus paradas
    intermedias no se agregan como estaciones: dentro de la propuesta
    tendrían grado 2, así que no cambiarían ninguna distancia entre las
    estaciones existentes ni los puntos de corte ni los puentes. Con eso el
    conjunto de estaciones V es el mismo antes y después, y cada métrica
    compara lo mismo.
  - Largo ('weight'): el de la ruta por la malla vial, de estación a
    estación (largo_nueva_ruta_m de sugerir_nueva_troncal).
  - Tiempo ('tiempo_min'): el de la ruta nueva que muestra la app
    (tiempo_nueva_ruta_min), con la caminata de acceso en cada punta.
  - Transbordo: la propuesta une dos troncales, igual que un cruce, así que
    por defecto cobra el mismo TRANSBORDO_MIN (network_design.
    TIPOS_CON_TRANSBORDO). Es la conexión física: se construye el enlace y el
    pasajero cambia de servicio, como en un cruce. Por eso, en el después, ir
    de una punta a la otra cuesta el tiempo de la app más un transbordo. Con
    agregar_troncales(..., transbordo_min=0), la propuesta se opera en cambio
    como ruta continua: un servicio que sigue de una troncal a la otra sin
    transbordo. Es la cota superior de lo que puede aportar; los cruces de la
    red de hoy siguen cobrando el suyo en las dos variantes, así que el antes
    es el mismo.
  - Tramos ('tramos'): los de la ruta entre sus paradas sugeridas (separadas
    500 m como mínimo), para que el criterio 'tramos' la cuente como una
    línea con estaciones y no como un salto.
  - Forma ('geometry'): la de la ruta por las calles, para que los caminos
    del después se dibujen por donde van.

Agregar aristas no puede alargar ningún camino: en el después ninguna
distancia crece, y el diámetro, el radio, la media y cada excentricidad
bajan o se quedan igual. Tampoco puede aparecer un punto de corte o un
puente nuevo, ni subir el número de pares que dependen de una sola estación
o de un solo enlace. Que una métrica no cambie también dice algo: una
propuesta puede acortar muchos viajes sin tocar el par más alejado de la red.

Las propuestas se guardan en un GeoJSON (resultados/escenarios/
propuestas.geojson): calcularlas exige la malla vial completa (minutos) y
compararlas, solo el grafo macro (segundos). El archivo se puede editar a
mano o armar con otra herramienta, siempre que cada línea traiga las
propiedades de PROPIEDADES.
"""
import json
import numbers
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
from pyproj import Transformer
from shapely.geometry import LineString

from integrabog.config import CRS_METRICO, TRANSBORDO_MIN
from integrabog.routing.metricas import CRITERIOS, metricas_red
from integrabog.routing.network_design import (
    ATRIBUTO_TRANSBORDO_PROPIO,
    TIPO_ARISTA_PROPUESTA,
)
from integrabog.routing.robustez import RobustezRed, robustez_red

PROPIEDADES = ("origen", "destino", "largo_m", "tiempo_min", "tramos")
COLOR_PROPUESTA = "#16a34a"

_A_METRICO = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)


@dataclass(frozen=True)
class TroncalPropuesta:
    """Una troncal nueva entre dos estaciones de la red."""
    origen: Hashable                         # cod_nodo de la estación de origen
    destino: Hashable                        # cod_nodo de la estación de destino
    largo_m: float                           # por la malla vial, de estación a estación
    tiempo_min: float                        # el de la ruta nueva en la app, sin transbordo
    tramos: int                              # tramos entre las paradas sugeridas
    geometria_lonlat: tuple                  # ((lon, lat), ...) de origen a destino
    paradas_lonlat: tuple = ()               # paradas sugeridas, incluidas las dos estaciones
    nombre: str = ""
    tiempo_actual_min: float | None = None   # lo que calculó la app por la red de hoy (referencia)
    ahorro_min: float | None = None
    factor_rodeo: float | None = None        # si salió de los pares críticos: red troncal / línea recta


def codigo_estacion(identificador: Hashable) -> Hashable:
    """El cod_nodo de una estación del grafo multicapa ('macro_4107' -> 4107),
    que es su id en el grafo macro. Cualquier otro id queda igual."""
    if isinstance(identificador, str) and identificador.startswith("macro_") and identificador[6:].isdigit():
        return int(identificador[6:])
    return identificador


def propuesta_desde_sugerencia(resultado: dict, nombre: str = "") -> TroncalPropuesta:
    """La troncal que propone sugerir_nueva_troncal() (o cada resultado de
    identificar_pares_criticos), lista para agregar al grafo macro."""
    paradas = tuple(tuple(p) for p in resultado.get("estaciones_intermedias_lonlat") or ())
    return TroncalPropuesta(
        origen=codigo_estacion(resultado["estacion_origen"]),
        destino=codigo_estacion(resultado["estacion_destino"]),
        largo_m=float(resultado["largo_nueva_ruta_m"]),
        tiempo_min=float(resultado["tiempo_nueva_ruta_min"]),
        tramos=max(len(paradas) - 1, 1),
        geometria_lonlat=tuple(tuple(c) for c in resultado["geometria_lonlat"]),
        paradas_lonlat=paradas, nombre=nombre,
        tiempo_actual_min=resultado.get("tiempo_actual_min"), ahorro_min=resultado.get("ahorro_min"),
        factor_rodeo=resultado.get("factor_rodeo"))


def agregar_troncales(G: nx.DiGraph, propuestas: Iterable[TroncalPropuesta],
                      transbordo_min: float | None = None) -> nx.DiGraph:
    """Una copia del grafo macro con cada propuesta como arista nueva, en los
    dos sentidos (ver el docstring del módulo). G no se modifica.

    transbordo_min: el transbordo que cobra entrar a una propuesta. Con None
    (por defecto), el mismo de los cruces, el que se pase a las métricas. Con
    un número, ese, solo en las propuestas: 0 es la ruta continua.

    Raises:
        ValueError: si una estación de la propuesta no está en la red, o si
            las dos estaciones ya están unidas por una arista: en ese caso la
            propuesta no agrega una conexión nueva, y un DiGraph no admite
            dos aristas entre el mismo par. También si transbordo_min es
            negativo: un transbordo que restara tiempo haría que dar vueltas
            por la propuesta acortara los viajes.
    """
    if transbordo_min is not None and transbordo_min < 0:
        raise ValueError(f"El transbordo de las propuestas no puede ser negativo: {transbordo_min}.")
    propio = {} if transbordo_min is None else {ATRIBUTO_TRANSBORDO_PROPIO: float(transbordo_min)}
    H = G.copy()
    for p in propuestas:
        etiqueta = p.nombre or f"{p.origen} - {p.destino}"
        faltan = [n for n in (p.origen, p.destino) if n not in H]
        if faltan:
            raise ValueError(f"Propuesta '{etiqueta}': la estación {faltan[0]} no está en la red.")
        if H.has_edge(p.origen, p.destino) or H.has_edge(p.destino, p.origen):
            tipo = (H.get_edge_data(p.origen, p.destino) or H.get_edge_data(p.destino, p.origen)).get("tipo") or "tramo"
            raise ValueError(f"Propuesta '{etiqueta}': las dos estaciones ya están unidas por una arista de "
                             f"{tipo}, así que no agrega una conexión nueva.")
        forma = _linea_metrica(H, p)
        for a, b, linea in ((p.origen, p.destino, forma), (p.destino, p.origen, forma.reverse())):
            H.add_edge(a, b, weight=float(p.largo_m), tiempo_min=float(p.tiempo_min), tramos=int(p.tramos),
                       tipo=TIPO_ARISTA_PROPUESTA, geometry=linea, nom_tronc=f"Propuesta: {etiqueta}",
                       propuesta=etiqueta, **propio)
    return H


def _linea_metrica(G: nx.DiGraph, p: TroncalPropuesta) -> LineString:
    """La forma de la propuesta en el CRS métrico, con las puntas exactamente
    en las dos estaciones: así un camino que pasa por ella se dibuja sin
    saltos (metricas.geometria_camino_lonlat empalma por el punto común)."""
    lon, lat = zip(*p.geometria_lonlat)
    x, y = _A_METRICO.transform(lon, lat)
    puntos = list(zip(x, y))
    for i, estacion in ((0, p.origen), (-1, p.destino)):
        if "x" in G.nodes[estacion]:
            puntos[i] = (G.nodes[estacion]["x"], G.nodes[estacion]["y"])
    return LineString(puntos)


# --- GeoJSON de propuestas -----------------------------------------------------------------

def _a_json(valor):
    """numpy.int64 y compañía no se pueden escribir en JSON."""
    if isinstance(valor, numbers.Integral):
        return int(valor)
    if isinstance(valor, numbers.Real):
        return float(valor)
    return valor


def a_geojson(propuestas: Iterable[TroncalPropuesta]) -> dict:
    features = []
    for p in propuestas:
        propiedades = {"nombre": p.nombre, "origen": _a_json(p.origen), "destino": _a_json(p.destino),
                       "largo_m": round(float(p.largo_m), 1), "tiempo_min": round(float(p.tiempo_min), 2),
                       "tramos": int(p.tramos), "paradas": [list(c) for c in p.paradas_lonlat],
                       "tiempo_actual_min": _a_json(p.tiempo_actual_min), "ahorro_min": _a_json(p.ahorro_min),
                       "factor_rodeo": _a_json(p.factor_rodeo),
                       "stroke": COLOR_PROPUESTA, "stroke-width": 5}
        features.append({"type": "Feature", "properties": propiedades,
                         "geometry": {"type": "LineString", "coordinates": [list(c) for c in p.geometria_lonlat]}})
    return {"type": "FeatureCollection", "features": features}


def guardar_propuestas(propuestas: Iterable[TroncalPropuesta], ruta: Path) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(a_geojson(propuestas), ensure_ascii=False, indent=1), encoding="utf-8")


def leer_propuestas(ruta: Path) -> list[TroncalPropuesta]:
    """Las propuestas de un GeoJSON escrito por guardar_propuestas() o a mano.

    Raises:
        ValueError: si a alguna línea le falta una propiedad de PROPIEDADES o
            trae valores imposibles (largo, tiempo o tramos no positivos).
    """
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    propuestas = []
    for i, feature in enumerate(datos.get("features", []), start=1):
        p, geometria = feature.get("properties") or {}, feature.get("geometry") or {}
        donde = f"{ruta}, línea {i} ({p.get('nombre') or 'sin nombre'})"
        if geometria.get("type") != "LineString" or len(geometria.get("coordinates", [])) < 2:
            raise ValueError(f"{donde}: la geometría debe ser una LineString de al menos dos puntos.")
        faltan = [k for k in PROPIEDADES if p.get(k) is None]
        if faltan:
            raise ValueError(f"{donde}: faltan las propiedades {', '.join(faltan)}.")
        try:
            largo, tiempo, tramos = float(p["largo_m"]), float(p["tiempo_min"]), int(p["tramos"])
        except (TypeError, ValueError):
            raise ValueError(f"{donde}: largo_m, tiempo_min y tramos deben ser números.") from None
        if largo <= 0 or tiempo <= 0 or tramos < 1:
            raise ValueError(f"{donde}: largo_m y tiempo_min deben ser positivos y tramos, al menos 1.")
        propuestas.append(TroncalPropuesta(
            origen=p["origen"], destino=p["destino"], largo_m=largo, tiempo_min=tiempo,
            tramos=tramos, geometria_lonlat=tuple(tuple(c[:2]) for c in geometria["coordinates"]),
            paradas_lonlat=tuple(tuple(c[:2]) for c in p.get("paradas") or ()), nombre=p.get("nombre") or "",
            tiempo_actual_min=p.get("tiempo_actual_min"), ahorro_min=p.get("ahorro_min"),
            factor_rodeo=p.get("factor_rodeo")))
    return propuestas


# --- Evaluar y comparar ----------------------------------------------------------------------

@dataclass(frozen=True)
class EvaluacionRed:
    """Todo lo que se compara entre dos escenarios: las métricas de distancia
    en los tres criterios y la robustez por tiempo de viaje (el criterio
    principal del proyecto)."""
    metricas: dict                   # criterio -> MetricasRed
    robustez: RobustezRed


def evaluar(G: nx.DiGraph, transbordo_min: float = TRANSBORDO_MIN) -> EvaluacionRed:
    return EvaluacionRed(metricas={c: metricas_red(G, c, transbordo_min) for c in CRITERIOS},
                         robustez=robustez_red(G, "tiempo", transbordo_min))


def _porcentaje(parte: int, total: int) -> float:
    return 100 * parte / total if total else 0.0


def _peor(cierres: tuple) -> float:
    return 100 * cierres[0].perdida_eficiencia if cierres else 0.0


@dataclass(frozen=True)
class Indicador:
    clave: str
    nombre: str
    unidad: str
    decimales: int
    valor: Callable[[EvaluacionRed], float]
    mejor_si_sube: bool = False      # en casi todos, menos es mejor


"""Los indicadores de la tabla antes/después, en el orden en que se reportan."""
INDICADORES = (
    Indicador("diametro_tiempo", "Diámetro por tiempo", "min", 1, lambda ev: ev.metricas["tiempo"].diametro),
    Indicador("radio_tiempo", "Radio por tiempo", "min", 1, lambda ev: ev.metricas["tiempo"].radio),
    Indicador("media_tiempo", "Tiempo medio de viaje", "min", 1, lambda ev: ev.metricas["tiempo"].media),
    Indicador("diametro_distancia", "Diámetro por distancia", "km", 2, lambda ev: ev.metricas["distancia"].diametro),
    Indicador("media_distancia", "Distancia media", "km", 2, lambda ev: ev.metricas["distancia"].media),
    Indicador("diametro_tramos", "Diámetro por tramos", "tramos", 0, lambda ev: ev.metricas["tramos"].diametro),
    Indicador("media_tramos", "Tramos en promedio", "tramos", 1, lambda ev: ev.metricas["tramos"].media),
    Indicador("enlaces", "Enlaces", "", 0, lambda ev: ev.robustez.estructura.enlaces, mejor_si_sube=True),
    Indicador("ciclomatico", "Ciclos independientes (μ)", "", 0, lambda ev: ev.robustez.estructura.ciclomatico,
              mejor_si_sube=True),
    Indicador("puntos_de_corte", "Puntos de corte", "", 0, lambda ev: len(ev.robustez.estructura.puntos_de_corte)),
    Indicador("puentes", "Puentes", "", 0, lambda ev: len(ev.robustez.estructura.puentes)),
    Indicador("bloque_mayor", "Estaciones del bloque biconexo mayor", "", 0,
              lambda ev: ev.robustez.estructura.bloque_mayor, mejor_si_sube=True),
    Indicador("dependen_estacion", "Pares que dependen de una sola estación", "%", 1,
              lambda ev: _porcentaje(ev.robustez.estructura.pares_dependen_estacion,
                                     ev.robustez.estructura.pares_conectados)),
    Indicador("dependen_enlace", "Pares que dependen de un solo enlace", "%", 1,
              lambda ev: _porcentaje(ev.robustez.estructura.pares_dependen_enlace,
                                     ev.robustez.estructura.pares_conectados)),
    Indicador("eficiencia", "Eficiencia global", "1/min", 4, lambda ev: ev.robustez.eficiencia, mejor_si_sube=True),
    Indicador("intermediacion_max", "Intermediación máxima", "%", 1,
              lambda ev: 100 * max(ev.robustez.intermediacion.values(), default=0.0)),
    Indicador("peor_cierre_estacion", "Pérdida de eficiencia por el peor cierre de una estación", "%", 1,
              lambda ev: _peor(ev.robustez.cierres_estaciones)),
    Indicador("peor_cierre_enlace", "Pérdida de eficiencia por el peor cierre de un enlace", "%", 1,
              lambda ev: _peor(ev.robustez.cierres_enlaces)),
)


def comparar(antes: EvaluacionRed, despues: EvaluacionRed) -> list[dict]:
    """Una fila por indicador: valor antes, después, cambio absoluto y
    relativo (None si el valor de antes es 0), y 'mejora': True, False o
    None si no cambió (diferencias de punto flotante por debajo de 1e-9)."""
    filas = []
    for ind in INDICADORES:
        a, d = float(ind.valor(antes)), float(ind.valor(despues))
        cambio = d - a
        sin_cambio = abs(cambio) <= 1e-9 * max(1.0, abs(a))
        filas.append({"clave": ind.clave, "nombre": ind.nombre, "unidad": ind.unidad, "decimales": ind.decimales,
                      "antes": a, "despues": d, "cambio": 0.0 if sin_cambio else cambio,
                      "cambio_pct": None if sin_cambio or not a else 100 * cambio / a,
                      "mejora": None if sin_cambio else (cambio > 0) == ind.mejor_si_sube})
    return filas
