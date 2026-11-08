"""
Antes y después: las métricas de la red troncal de hoy contra las de la red
con las troncales propuestas (routing/escenarios.py), sobre las mismas
estaciones, y el aporte de cada propuesta por separado.

Uso:
    python -m integrabog.scripts.comparar_escenarios
    python -m integrabog.scripts.comparar_escenarios --propuestas resultados/escenarios/propuestas.geojson --transbordo 5
    python -m integrabog.scripts.comparar_escenarios --transbordo-propuestas 5 0 --salida resultados/escenarios/final

Las propuestas salen de proponer_troncales, o de un GeoJSON armado a mano
con las mismas propiedades (escenarios.PROPIEDADES). Solo necesita el grafo
macro, así que corre en segundos. Deja en la carpeta de salida:
  - antes_despues.md: el escenario, la tabla antes/después, el aporte de cada
    propuesta y los puentes y puntos de corte que desaparecen, con coma
    decimal, para el informe;
  - antes_despues.csv: una fila por estación, con su excentricidad, su
    tiempo medio de viaje y su intermediación, antes y después;
  - antes_despues.geojson: las troncales propuestas (verde), los enlaces que
    dejan de ser puentes (azul) y las estaciones, coloreadas según cuánto
    baja su tiempo medio de viaje. Se abre en geojson.io o en QGIS.

--transbordo-propuestas fija lo que cobra entrar a una propuesta, sin tocar
los cruces de la red de hoy (--transbordo), así que el antes no cambia. Por
defecto es el mismo de los cruces: la conexión física, en la que el pasajero
cambia de servicio. Con 0, la propuesta se opera como ruta continua, sin
transbordo: la cota superior de lo que puede aportar. Con varios valores
(por ejemplo, 5 0), evalúa cada variante y deja, además de su informe
completo en una subcarpeta (conexion_fisica/, ruta_continua/), la
comparación lado a lado:
  - comparacion_transbordo.md: los indicadores antes y en cada variante, el
    viaje entre las dos puntas de cada propuesta y las estaciones que más
    acortan su tiempo medio de viaje;
  - comparacion_transbordo.csv: una fila por estación, con su tiempo medio de
    viaje y su intermediación antes y en cada variante.
"""
import argparse
import csv
import datetime as dt
import json
import math
import numbers
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from integrabog.config import RAIZ_PROYECTO, TRANSBORDO_MIN
from integrabog.graph.macro import construir_grafo_macro
from integrabog.routing.escenarios import (
    EvaluacionRed,
    TroncalPropuesta,
    a_geojson,
    agregar_troncales,
    comparar,
    evaluar,
    leer_propuestas,
)
from integrabog.routing.metricas import geometria_camino_lonlat, peso, punto_lonlat
from integrabog.routing.robustez import enlaces

CARPETA = RAIZ_PROYECTO / "resultados" / "escenarios"
"""columnas de la tabla de aportes: (clave del indicador, encabezado en el informe, en la consola)"""
APORTES = (("media_tiempo", "Tiempo medio", "tiempo medio"), ("diametro_tiempo", "Diámetro por tiempo", "diámetro"),
           ("puentes", "Puentes", "puentes"), ("puntos_de_corte", "Puntos de corte", "p. de corte"),
           ("dependen_enlace", "Pares que dependen de un enlace", "dep. enlace"),
           ("eficiencia", "Eficiencia global", "eficiencia"))
COLOR = {"puente": "#2563eb", "mucho": "#15803d", "algo": "#86efac", "nada": "#9ca3af"}


def _nombre(G: nx.DiGraph, v) -> str:
    return G.nodes[v].get("etiqueta") or G.nodes[v].get("nombre") or str(v)


def _codigo(v):
    return int(v) if isinstance(v, numbers.Integral) else v


def _hoy() -> str:
    """La fecha de hoy en la zona horaria del equipo (la del informe)."""
    return dt.datetime.now().astimezone().date().isoformat()


def _numero(x: float, decimales: int, coma: bool) -> str:
    if math.isinf(x):
        return "∞"
    texto = f"{x:,.{decimales}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".") if coma else texto.replace(",", "")


def _con_signo(x: float, decimales: int, coma: bool) -> str:
    return ("−" if x < 0 else "+") + _numero(abs(x), decimales, coma)


def _valor(f: dict, x: float, coma: bool) -> str:
    unidad = f" {f['unidad']}" if f["unidad"] else ""
    return _numero(x, f["decimales"], coma) + unidad


def _cambio(f: dict, coma: bool) -> str:
    """'=' si no cambió. Si cambió: en puntos si el indicador ya es un porcentaje; en porcentaje
    para la eficiencia (su valor en 1/min no se lee fácil); si no, con su unidad y el cambio
    relativo entre paréntesis. '≈ 0' si cambió menos de lo que se alcanza a mostrar."""
    if f["mejora"] is None:
        return "="
    signo = "+" if f["cambio"] > 0 else "−"
    if f["clave"] == "eficiencia" and f["cambio_pct"] is not None:
        relativo = _numero(abs(f["cambio_pct"]), 1, coma)
        return f"{signo}{relativo} %" if float(relativo.replace(",", ".")) else "≈ 0"
    absoluto = _numero(abs(f["cambio"]), f["decimales"], coma)
    if not float(absoluto.replace(".", "").replace(",", ".") if coma else absoluto):
        return "≈ 0"
    if f["unidad"] == "%":
        return f"{signo}{absoluto} pts"
    unidad = f" {f['unidad']}" if f["unidad"] else ""
    relativo = f" ({signo}{_numero(abs(f['cambio_pct']), 1, coma)} %)" if f["cambio_pct"] is not None else ""
    return f"{signo}{absoluto}{unidad}{relativo}"


def _validas(G: nx.DiGraph, propuestas: list[TroncalPropuesta]) -> tuple[list, list]:
    """Las propuestas que se pueden agregar, una tras otra (así también se
    detectan las repetidas), y el motivo de cada una que no."""
    validas: list[TroncalPropuesta] = []
    avisos: list[str] = []
    for p in propuestas:
        try:
            agregar_troncales(G, validas + [p])
            validas.append(p)
        except ValueError as err:
            avisos.append(str(err))
    return validas, avisos


def _desaparecen(antes: tuple, despues: tuple) -> list:
    quedan = set(despues)
    return [x for x in antes if x not in quedan]


# --- Variantes: el mismo después, con distinto transbordo al entrar a las propuestas -------

@dataclass(frozen=True)
class Variante:
    """El después con 'transbordo_propuestas' minutos de transbordo al entrar a
    una propuesta. Los cruces de la red de hoy cobran lo mismo en todas."""
    transbordo_propuestas: float
    clave: str                       # subcarpeta de salida cuando hay varias variantes
    titulo: str                      # para el informe
    corto: str                       # para las columnas de la consola
    grafo: nx.DiGraph
    despues: EvaluacionRed
    filas: list                      # comparar(antes, despues)
    aportes: list                    # [(propuesta, filas de esa propuesta agregada sola)]


def _nombres_variante(minutos: float, transbordo: float) -> tuple[str, str, str]:
    """(clave, título, nombre corto) de la variante con 'minutos' de transbordo en las propuestas."""
    texto = f"{minutos:g}".replace(".", ",")
    if minutos == 0:
        return "ruta_continua", "Ruta continua (sin transbordo)", "ruta continua"
    if minutos == transbordo:
        return "conexion_fisica", f"Conexión física ({texto} min de transbordo)", "conexión física"
    return (f"transbordo_{minutos:g}_min".replace(".", "_"), f"Propuestas con {texto} min de transbordo",
            f"transbordo {texto} min")


def evaluar_variante(G: nx.DiGraph, validas: list, antes: EvaluacionRed, minutos: float,
                     transbordo: float) -> Variante:
    clave, titulo, corto = _nombres_variante(minutos, transbordo)
    H = agregar_troncales(G, validas, minutos)
    despues = evaluar(H, transbordo)
    """el aporte de cada una, agregada sola: con varias, la suma de los aportes no tiene por qué dar
     el total (dos propuestas pueden acortar los mismos viajes)"""
    aportes = [(p, {f["clave"]: f for f in comparar(antes, evaluar(agregar_troncales(G, [p], minutos), transbordo))})
               for p in validas] if len(validas) > 1 else []
    return Variante(minutos, clave, titulo, corto, H, despues, comparar(antes, despues), aportes)


def _cobro(minutos: float, transbordo: float, coma: bool) -> str:
    """Qué cobra entrar a una propuesta, para el texto del informe."""
    if minutos == 0:
        return ("se opera como ruta continua: entrar a ella no cobra transbordo (los cruces de la red de hoy "
                f"cobran {_numero(transbordo, 1, coma)} min)")
    if minutos == transbordo:
        return f"cobra {_numero(minutos, 1, coma)} min de transbordo, como un cruce entre troncales"
    return (f"cobra {_numero(minutos, 1, coma)} min de transbordo (los cruces de la red de hoy, "
            f"{_numero(transbordo, 1, coma)} min)")

def _estaciones(G: nx.DiGraph, antes: EvaluacionRed, despues: EvaluacionRed) -> list[dict]:
    """Una fila por estación, de la que más acorta su tiempo medio de viaje a la que menos."""
    ta, td = antes.metricas["tiempo"], despues.metricas["tiempo"]
    corte_a, corte_d = set(antes.robustez.estructura.puntos_de_corte), set(despues.robustez.estructura.puntos_de_corte)
    filas = [{"v": v, "media_antes": ta.media_desde[v], "media_despues": td.media_desde[v],
              "delta_media": td.media_desde[v] - ta.media_desde[v],
              "e_antes": ta.excentricidad[v], "e_despues": td.excentricidad[v],
              "delta_e": td.excentricidad[v] - ta.excentricidad[v],
              "int_antes": 100 * antes.robustez.intermediacion[v], "int_despues": 100 * despues.robustez.intermediacion[v],
              "corte_antes": v in corte_a, "corte_despues": v in corte_d} for v in G.nodes]
    return sorted(filas, key=lambda f: (f["delta_media"], str(f["v"])))


def _imprimir_estructura(G, e_a, e_d) -> None:
    for titulo, lista, formato in (("Puentes que dejan de serlo", _desaparecen(e_a.puentes, e_d.puentes),
                                    lambda e: f"{_nombre(G, e[0])} - {_nombre(G, e[1])}"),
                                   ("Puntos de corte que dejan de serlo",
                                    _desaparecen(e_a.puntos_de_corte, e_d.puntos_de_corte), lambda v: _nombre(G, v))):
        print(f"\n{titulo} ({len(lista)}): " + ("; ".join(formato(x) for x in lista) if lista else "ninguno"))


def imprimir(G, validas, avisos, antes, variante: Variante, top) -> None:
    filas, aportes, despues = variante.filas, variante.aportes, variante.despues
    print(f"\nRed de hoy: {G.number_of_nodes()} estaciones, {antes.robustez.estructura.enlaces} enlaces | "
          f"propuestas: {len(validas)}")
    entrada = ("ruta continua, sin transbordo" if variante.transbordo_propuestas == 0
               else f"+ {variante.transbordo_propuestas:g} min de transbordo")
    for p in validas:
        print(f"  {p.nombre}: {p.largo_m / 1000:.2f} km, {p.tiempo_min:.1f} min ({entrada}), {p.tramos} tramos")
    for aviso in avisos:
        print(f"  [!] se omite: {aviso}")

    print("\n=== ANTES Y DESPUÉS ===")
    print(f"  {'indicador':<58} {'antes':>14} {'después':>14}  cambio")
    for f in filas:
        print(f"  {f['nombre']:<58} {_valor(f, f['antes'], False):>14} {_valor(f, f['despues'], False):>14}  "
              f"{_cambio(f, False)}")
    for criterio in ("tiempo", "distancia"):
        a, d = antes.metricas[criterio], despues.metricas[criterio]
        if a.par_diametro != d.par_diametro:
            print(f"  El par más alejado por {criterio} cambia: {' <-> '.join(_nombre(G, v) for v in a.par_diametro)} "
                  f"-> {' <-> '.join(_nombre(G, v) for v in d.par_diametro)}")

    if len(aportes) > 1:
        print("\n=== APORTE DE CADA PROPUESTA (AGREGADA SOLA) ===")
        print(f"  {'propuesta':<46} " + " ".join(f"{corto:>18}" for *_, corto in APORTES))
        for p, fila in aportes:
            print(f"  {p.nombre[:46]:<46} " + " ".join(f"{_cambio(fila[clave], False):>18}" for clave, *_ in APORTES))

    _imprimir_estructura(G, antes.robustez.estructura, despues.robustez.estructura)

    por_estacion = _estaciones(G, antes, despues)
    print(f"\nLas {top} estaciones que más acortan su tiempo medio de viaje:")
    for f in por_estacion[:top]:
        print(f"  {_nombre(G, f['v'])}: {f['media_antes']:.1f} -> {f['media_despues']:.1f} min ({f['delta_media']:+.1f})")


def markdown(G, validas, avisos, antes, variante: Variante, transbordo_min, top) -> str:
    def coma(x: float, n: int = 1) -> str:
        return _numero(x, n, True)

    filas, aportes, despues = variante.filas, variante.aportes, variante.despues
    propio = variante.transbordo_propuestas
    if propio == 0:
        nota_transbordo = ("El ahorro según la app es el del viaje de una punta a la otra, sin transbordo. En este "
                           "escenario la propuesta se opera como ruta continua y tampoco cobra transbordo, así que ese "
                           "ahorro llega completo al viaje entre sus dos estaciones: es la cota superior de lo que "
                           "puede aportar.")
    else:
        como_cruce = ", como un cruce entre troncales" if propio == transbordo_min else ""
        nota_transbordo = ("El ahorro según la app es el del viaje de una punta a la otra, sin transbordo. En el "
                           f"escenario, cruzar por la propuesta cobra además {coma(propio)} min{como_cruce}: una "
                           "propuesta que ahorra menos que eso no acorta ni siquiera el viaje entre sus dos estaciones.")
    lineas = [
        "# Antes y después: la red troncal con las troncales propuestas", "",
        (f"Red de hoy: {G.number_of_nodes()} estaciones y {antes.robustez.estructura.enlaces} enlaces. "
         f"Mismas estaciones antes y después: cada propuesta entra como una conexión nueva entre sus dos estaciones, "
         f"con el largo y el tiempo de su ruta por la malla vial, y {_cobro(propio, transbordo_min, True)}."),
        f"Generado el {_hoy()} con `python -m integrabog.scripts.comparar_escenarios`.", "",
        "## Escenario", "",
        "| Propuesta | Largo | Tiempo de la ruta nueva | Tramos | Hoy por la red | Ahorro según la app | Rodeo de hoy |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in validas:
        hoy = f"{coma(p.tiempo_actual_min)} min" if p.tiempo_actual_min is not None else "—"
        ahorro = f"{coma(p.ahorro_min)} min" if p.ahorro_min is not None else "—"
        rodeo = f"{coma(p.factor_rodeo)}×" if p.factor_rodeo is not None else "—"
        lineas.append(f"| {p.nombre} | {coma(p.largo_m / 1000, 2)} km | {coma(p.tiempo_min)} min | {p.tramos} | "
                      f"{hoy} | {ahorro} | {rodeo} |")
    lineas += ["", nota_transbordo]
    if avisos:
        lineas += ["", "Propuestas omitidas:", ""] + [f"- {a}" for a in avisos]
    lineas += ["", "## Antes y después", "", "| Indicador | Antes | Después | Cambio |", "|---|---|---|---|"]
    lineas += [f"| {f['nombre']} | {_valor(f, f['antes'], True)} | {_valor(f, f['despues'], True)} | "
               f"{_cambio(f, True)} |" for f in filas]
    for criterio in ("tiempo", "distancia"):
        a, d = antes.metricas[criterio], despues.metricas[criterio]
        if a.par_diametro != d.par_diametro:
            lineas += ["", (f"El par más alejado por {criterio} cambia de "
                            f"{' ↔ '.join(_nombre(G, v) for v in a.par_diametro)} a "
                            f"{' ↔ '.join(_nombre(G, v) for v in d.par_diametro)}.")]
    if len(aportes) > 1:
        lineas += ["", "## Aporte de cada propuesta, agregada sola", "",
                   "| Propuesta | " + " | ".join(titulo for _, titulo, _ in APORTES) + " |",
                   "|---|" + "---|" * len(APORTES)]
        lineas += [f"| {p.nombre} | " + " | ".join(_cambio(fila[clave], True) for clave, *_ in APORTES) + " |"
                   for p, fila in aportes]
    e_a, e_d = antes.robustez.estructura, despues.robustez.estructura
    puentes, cortes = _desaparecen(e_a.puentes, e_d.puentes), _desaparecen(e_a.puntos_de_corte, e_d.puntos_de_corte)
    lineas += ["", "## Estructura que cambia", "",
               f"- Puentes que dejan de serlo ({len(puentes)}): "
               + ("; ".join(f"{_nombre(G, u)} ↔ {_nombre(G, v)}" for u, v in puentes) or "ninguno") + ".",
               f"- Puntos de corte que dejan de serlo ({len(cortes)}): "
               + (", ".join(_nombre(G, v) for v in cortes) or "ninguno") + "."]
    por_estacion = _estaciones(G, antes, despues)
    lineas += ["", f"## Las {top} estaciones que más acortan su tiempo medio de viaje", "",
               "| Estación | Troncal | Antes | Después | Cambio |", "|---|---|---|---|---|"]
    lineas += [f"| {_nombre(G, f['v'])} | {G.nodes[f['v']].get('troncal') or ''} | {coma(f['media_antes'])} min | "
               f"{coma(f['media_despues'])} min | {_con_signo(f['delta_media'], 1, True)} min |"
               for f in por_estacion[:top]]
    ia, idp = antes.robustez.intermediacion, despues.robustez.intermediacion
    lineas += ["", "## Intermediación de las estaciones más usadas", "",
               "| Estación | Antes | Después |", "|---|---|---|"]
    mas_usadas = sorted(G.nodes, key=lambda v: -max(ia[v], idp[v]))[:top]
    lineas += [f"| {_nombre(G, v)} | {coma(100 * ia[v])} % | {coma(100 * idp[v])} % |" for v in mas_usadas]
    return "\n".join(lineas) + "\n"


def escribir_csv(G, antes, despues, ruta: Path) -> None:
    with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:  # utf-8-sig: Excel lee las tildes
        escritor = csv.writer(archivo)
        escritor.writerow(["cod_nodo", "estacion", "troncal", "media_tiempo_antes_min", "media_tiempo_despues_min",
                           "cambio_media_min", "e_tiempo_antes_min", "e_tiempo_despues_min", "cambio_e_min",
                           "intermediacion_antes_pct", "intermediacion_despues_pct", "punto_de_corte_antes",
                           "punto_de_corte_despues"])
        for f in _estaciones(G, antes, despues):
            v = f["v"]
            escritor.writerow([_codigo(v), _nombre(G, v), G.nodes[v].get("troncal") or "",
                               round(f["media_antes"], 3), round(f["media_despues"], 3), round(f["delta_media"], 3),
                               round(f["e_antes"], 3), round(f["e_despues"], 3), round(f["delta_e"], 3),
                               round(f["int_antes"], 3), round(f["int_despues"], 3),
                               "sí" if f["corte_antes"] else "no", "sí" if f["corte_despues"] else "no"])


def geojson(G, validas, antes, despues) -> dict:
    """De abajo hacia arriba: la red de hoy (gris), los enlaces que dejan de ser puentes (azul), las
    propuestas (verde) y las estaciones."""
    features = [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": geometria_camino_lonlat(G, e)},
                 "properties": {"elemento": "enlace de hoy", "enlace": f"{_nombre(G, e[0])} - {_nombre(G, e[1])}",
                                "stroke": COLOR["nada"], "stroke-width": 2, "stroke-opacity": 0.7}}
                for e in enlaces(G)]
    propuestas = a_geojson(validas)["features"]
    for f in propuestas:
        f["properties"]["elemento"] = "troncal propuesta"
    for u, v in _desaparecen(antes.robustez.estructura.puentes, despues.robustez.estructura.puentes):
        features.append({"type": "Feature",
                         "geometry": {"type": "LineString", "coordinates": geometria_camino_lonlat(G, (u, v))},
                         "properties": {"elemento": "deja de ser puente", "enlace": f"{_nombre(G, u)} - {_nombre(G, v)}",
                                        "stroke": COLOR["puente"], "stroke-width": 4, "stroke-opacity": 0.85}})
    features += propuestas
    puntas = {x for p in validas for x in (p.origen, p.destino)}
    for f in _estaciones(G, antes, despues):
        v = f["v"]
        lon, lat = punto_lonlat(G, v)
        color = "mucho" if f["delta_media"] <= -1 else "algo" if f["delta_media"] < -1e-9 else "nada"
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                         "properties": {"elemento": "estación", "cod_nodo": _codigo(v), "estacion": _nombre(G, v),
                                        "troncal": G.nodes[v].get("troncal"),
                                        "media_tiempo_antes_min": round(f["media_antes"], 3),
                                        "media_tiempo_despues_min": round(f["media_despues"], 3),
                                        "cambio_media_min": round(f["delta_media"], 3),
                                        "punto_de_corte_antes": f["corte_antes"],
                                        "punto_de_corte_despues": f["corte_despues"],
                                        "marker-color": COLOR[color], "marker-size": "large" if v in puntas else "small"}})
    return {"type": "FeatureCollection", "features": features}


# --- Comparación lado a lado de las variantes ------------------------------------------------

NOTA_INVARIANTE = ("La estructura de la red (enlaces, μ, puntos de corte, puentes, bloques y pares que dependen de un "
                   "solo elemento) y las distancias por largo y por tramos no dependen del transbordo: son las mismas "
                   "en todas las variantes.")


def tiempo_entre(H: nx.DiGraph, a, b, transbordo: float) -> float | None:
    """Minutos del viaje más rápido de a a b, o None si no hay camino."""
    try:
        return nx.dijkstra_path_length(H, a, b, weight=peso("tiempo", transbordo))
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def viajes_entre_puntas(G: nx.DiGraph, validas: list, variantes: list, transbordo: float) -> list[tuple]:
    """Por propuesta: (propuesta, minutos hoy, [minutos en cada variante]) del viaje entre sus dos
    estaciones. Es la cifra que mejor se entiende: lo que tarda hoy ese viaje y lo que tardaría."""
    return [(p, tiempo_entre(G, p.origen, p.destino, transbordo),
             [tiempo_entre(v.grafo, p.origen, p.destino, transbordo) for v in variantes]) for p in validas]


def _minutos(x: float | None, coma: bool, hoy: float | None = None) -> str:
    """'13,8 min (−3,1)': los minutos de un viaje y, si se da 'hoy', cuánto cambian; '—' si no hay camino."""
    if x is None:
        return "—"
    texto = f"{_numero(x, 1, coma)} min"
    if hoy is None:
        return texto
    cambio = x - hoy
    return texto + (" (=)" if abs(cambio) < 0.05 else f" ({_con_signo(cambio, 1, coma)})")


def _estaciones_variantes(G: nx.DiGraph, antes: EvaluacionRed, variantes: list) -> list[dict]:
    """Una fila por estación con su tiempo medio de viaje y su intermediación, antes y en cada
    variante; primero las que más acortan su tiempo medio en alguna de ellas."""
    ta = antes.metricas["tiempo"].media_desde
    filas = []
    for s in G.nodes:
        medias = [v.despues.metricas["tiempo"].media_desde[s] for v in variantes]
        filas.append({"v": s, "media_antes": ta[s], "medias": medias, "mejor": min(m - ta[s] for m in medias),
                      "int_antes": 100 * antes.robustez.intermediacion[s],
                      "intermediaciones": [100 * v.despues.robustez.intermediacion[s] for v in variantes]})
    return sorted(filas, key=lambda f: (f["mejor"], str(f["v"])))


def imprimir_variantes(G, validas, avisos, antes, variantes, transbordo, top) -> None:
    print(f"\nRed de hoy: {G.number_of_nodes()} estaciones, {antes.robustez.estructura.enlaces} enlaces | "
          f"propuestas: {len(validas)}")
    for p in validas:
        print(f"  {p.nombre}: {p.largo_m / 1000:.2f} km, {p.tiempo_min:.1f} min de ruta, {p.tramos} tramos")
    for aviso in avisos:
        print(f"  [!] se omite: {aviso}")
    print(f"Los cruces de hoy cobran {transbordo:g} min de transbordo en todas las variantes. Entrar a una propuesta: "
          + " | ".join(v.titulo for v in variantes))

    print("\n=== ANTES Y DESPUÉS, POR VARIANTE ===")
    print(f"  {'indicador':<56} {'antes':>14} " + " ".join(f"{v.corto:>18}" for v in variantes))
    for filas in zip(*(v.filas for v in variantes)):
        f = filas[0]
        print(f"  {f['nombre']:<56} {_valor(f, f['antes'], False):>14} "
              + " ".join(f"{_valor(g, g['despues'], False):>18}" for g in filas))
    print(f"  {NOTA_INVARIANTE}")

    print("\n=== VIAJE ENTRE LAS DOS PUNTAS DE CADA PROPUESTA ===")
    print(f"  {'propuesta':<46} {'hoy':>10} " + " ".join(f"{v.corto:>18}" for v in variantes))
    for p, hoy, tiempos in viajes_entre_puntas(G, validas, variantes, transbordo):
        print(f"  {p.nombre[:46]:<46} {_minutos(hoy, False):>10} "
              + " ".join(f"{_minutos(x, False, hoy):>18}" for x in tiempos))

    _imprimir_estructura(G, antes.robustez.estructura, variantes[0].despues.robustez.estructura)

    print(f"\nLas {top} estaciones que más acortan su tiempo medio de viaje:")
    print(f"  {'estación':<44} {'antes':>10} " + " ".join(f"{v.corto:>18}" for v in variantes))
    for f in _estaciones_variantes(G, antes, variantes)[:top]:
        print(f"  {_nombre(G, f['v'])[:44]:<44} {_minutos(f['media_antes'], False):>10} "
              + " ".join(f"{_minutos(m, False, f['media_antes']):>18}" for m in f["medias"]))


def markdown_variantes(G, validas, avisos, antes, variantes, transbordo, top) -> str:
    def coma(x: float, n: int = 1) -> str:
        return _numero(x, n, True)

    lineas = [
        "# Conexión física y ruta continua: el después según el transbordo de las propuestas", "",
        (f"Red de hoy: {G.number_of_nodes()} estaciones y {antes.robustez.estructura.enlaces} enlaces. En todas las "
         f"variantes los cruces entre troncales de hoy cobran {format(transbordo, 'g').replace('.', ',')} min de "
         "transbordo, así que el antes es el mismo. Lo único que cambia es lo que cobra entrar a una propuesta:"), "",
    ]
    for v in variantes:
        if v.transbordo_propuestas == 0:
            texto = ("un servicio sigue de una troncal a la otra por la propuesta, sin que el pasajero cambie de bus. "
                     "Es la cota superior de lo que pueden aportar las propuestas.")
        elif v.transbordo_propuestas == transbordo:
            texto = "se construye el enlace y el pasajero cambia de servicio para usarlo, como en un cruce entre troncales."
        else:
            texto = f"entrar a la propuesta cobra {coma(v.transbordo_propuestas)} min."
        lineas.append(f"- **{v.titulo}:** {texto}")
    lineas += ["", f"Generado el {_hoy()} con `python -m integrabog.scripts.comparar_escenarios`.",
               "", "## Propuestas", "", "| Propuesta | Largo | Tiempo de la ruta nueva | Tramos |", "|---|---|---|---|"]
    lineas += [f"| {p.nombre} | {coma(p.largo_m / 1000, 2)} km | {coma(p.tiempo_min)} min | {p.tramos} |" for p in validas]
    if avisos:
        lineas += ["", "Propuestas omitidas:", ""] + [f"- {a}" for a in avisos]

    lineas += ["", "## Viaje entre las dos puntas de cada propuesta", "",
               "| Propuesta | Hoy | " + " | ".join(v.titulo for v in variantes) + " |",
               "|---|---|" + "---|" * len(variantes)]
    for p, hoy, tiempos in viajes_entre_puntas(G, validas, variantes, transbordo):
        lineas.append(f"| {p.nombre} | {_minutos(hoy, True)} | "
                      + " | ".join(_minutos(x, True, hoy) for x in tiempos) + " |")
    lineas += ["", ("Hoy es el viaje por la red troncal, con sus transbordos. Las variantes dan el viaje más rápido con "
                    "todas las propuestas a la vez: una propuesta acorta este viaje solo si su ruta, más lo que cobre "
                    "entrar a ella, gana al de hoy, y el viaje puede salir más corto que la ruta de su propia propuesta "
                    "si otra ofrece un camino mejor.")]

    lineas += ["", "## Indicadores de la red", "",
               "| Indicador | Antes | " + " | ".join(f"{v.titulo} | Cambio" for v in variantes) + " |",
               "|---|---|" + "---|---|" * len(variantes)]
    for filas in zip(*(v.filas for v in variantes)):
        f = filas[0]
        lineas.append(f"| {f['nombre']} | {_valor(f, f['antes'], True)} | "
                      + " | ".join(f"{_valor(g, g['despues'], True)} | {_cambio(g, True)}" for g in filas) + " |")
    lineas += ["", (NOTA_INVARIANTE + " Lo que cambia son los indicadores de tiempo: diámetro, radio y media por tiempo, "
                    "eficiencia global, intermediación y pérdidas por cierres.")]

    e_a, e_d = antes.robustez.estructura, variantes[0].despues.robustez.estructura
    puentes, cortes = _desaparecen(e_a.puentes, e_d.puentes), _desaparecen(e_a.puntos_de_corte, e_d.puntos_de_corte)
    lineas += ["", "## Estructura que cambia (igual en todas las variantes)", "",
               f"- Puentes que dejan de serlo ({len(puentes)}): "
               + ("; ".join(f"{_nombre(G, u)} ↔ {_nombre(G, v)}" for u, v in puentes) or "ninguno") + ".",
               f"- Puntos de corte que dejan de serlo ({len(cortes)}): "
               + (", ".join(_nombre(G, v) for v in cortes) or "ninguno") + "."]

    lineas += ["", f"## Las {top} estaciones que más acortan su tiempo medio de viaje", "",
               "| Estación | Troncal | Antes | " + " | ".join(v.titulo for v in variantes) + " |",
               "|---|---|---|" + "---|" * len(variantes)]
    for f in _estaciones_variantes(G, antes, variantes)[:top]:
        lineas.append(f"| {_nombre(G, f['v'])} | {G.nodes[f['v']].get('troncal') or ''} | "
                      f"{_minutos(f['media_antes'], True)} | "
                      + " | ".join(_minutos(m, True, f["media_antes"]) for m in f["medias"]) + " |")

    carpetas = ", ".join(f"`{v.clave}/`" for v in variantes)
    lineas += ["", (f"El informe completo de cada variante (aporte de cada propuesta, intermediación, CSV por estación y "
                    f"GeoJSON para el mapa) está en su carpeta: {carpetas}.")]
    return "\n".join(lineas) + "\n"


def escribir_csv_variantes(G, antes, variantes, ruta: Path) -> None:
    with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:  # utf-8-sig: Excel lee las tildes
        escritor = csv.writer(archivo)
        escritor.writerow(["cod_nodo", "estacion", "troncal", "media_tiempo_antes_min"]
                          + [c for v in variantes for c in (f"media_tiempo_{v.clave}_min", f"cambio_media_{v.clave}_min")]
                          + ["intermediacion_antes_pct"] + [f"intermediacion_{v.clave}_pct" for v in variantes])
        for f in _estaciones_variantes(G, antes, variantes):
            s = f["v"]
            escritor.writerow([_codigo(s), _nombre(G, s), G.nodes[s].get("troncal") or "", round(f["media_antes"], 3)]
                              + [x for m in f["medias"] for x in (round(m, 3), round(m - f["media_antes"], 3))]
                              + [round(f["int_antes"], 3)] + [round(i, 3) for i in f["intermediaciones"]])


def escribir_informe(carpeta: Path, G, validas, avisos, antes, variante: Variante, transbordo, top) -> list[Path]:
    """Los tres archivos del antes y después de una variante."""
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = [carpeta / "antes_despues.md", carpeta / "antes_despues.csv", carpeta / "antes_despues.geojson"]
    rutas[0].write_text(markdown(G, validas, avisos, antes, variante, transbordo, top), encoding="utf-8")
    escribir_csv(G, antes, variante.despues, rutas[1])
    rutas[2].write_text(json.dumps(geojson(G, validas, antes, variante.despues), ensure_ascii=False), encoding="utf-8")
    return rutas


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara la red troncal de hoy con la red con las troncales propuestas.")
    parser.add_argument("--propuestas", type=Path, default=CARPETA / "propuestas.geojson",
                        help="GeoJSON de proponer_troncales (resultados/escenarios/propuestas.geojson)")
    parser.add_argument("--transbordo", type=float, default=TRANSBORDO_MIN,
                        help=f"minutos por transbordo en los cruces entre troncales (config: {TRANSBORDO_MIN}); "
                             "también en las propuestas, salvo que se dé --transbordo-propuestas")
    parser.add_argument("--transbordo-propuestas", type=float, nargs="+", metavar="MIN",
                        help="minutos de transbordo al entrar a una propuesta, sin tocar los cruces de hoy. Por "
                             "defecto, los de --transbordo (conexión física); 0 = ruta continua, la cota superior. "
                             "Con varios valores (por ejemplo, 5 0) compara las variantes lado a lado")
    parser.add_argument("--top", type=int, default=10, help="cuántas estaciones listar en cada tabla")
    parser.add_argument("--salida", type=Path, default=CARPETA, help="carpeta de salida")
    args = parser.parse_args()
    minutos = list(dict.fromkeys(args.transbordo_propuestas or [args.transbordo]))
    if args.transbordo < 0 or any(m < 0 for m in minutos):
        parser.error("los transbordos no pueden ser negativos")

    if not args.propuestas.exists():
        raise SystemExit(f"No existe {args.propuestas}. Primero: python -m integrabog.scripts.proponer_troncales")
    G = construir_grafo_macro()
    validas, avisos = _validas(G, leer_propuestas(args.propuestas))
    if not validas:
        raise SystemExit("Ninguna propuesta se puede agregar a la red:\n  " + "\n  ".join(avisos))

    antes = evaluar(G, args.transbordo)
    variantes = [evaluar_variante(G, validas, antes, m, args.transbordo) for m in minutos]
    if len(variantes) == 1:
        imprimir(G, validas, avisos, antes, variantes[0], args.top)
        rutas = escribir_informe(args.salida, G, validas, avisos, antes, variantes[0], args.transbordo, args.top)
    else:
        imprimir_variantes(G, validas, avisos, antes, variantes, args.transbordo, args.top)
        args.salida.mkdir(parents=True, exist_ok=True)
        rutas = [args.salida / "comparacion_transbordo.md", args.salida / "comparacion_transbordo.csv"]
        rutas[0].write_text(markdown_variantes(G, validas, avisos, antes, variantes, args.transbordo, args.top),
                            encoding="utf-8")
        escribir_csv_variantes(G, antes, variantes, rutas[1])
        for v in variantes:
            rutas += escribir_informe(args.salida / v.clave, G, validas, avisos, antes, v, args.transbordo, args.top)
    print("\nArchivos:\n" + "\n".join(f"  {ruta}" for ruta in rutas))


if __name__ == "__main__":
    main()
