"""
Robustez de la red troncal: puntos de corte, puentes, bloques, número
ciclomático, conectividad, intermediación, eficiencia global y el efecto de
cerrar cada estación y cada enlace (routing/robustez.py).

Uso:
    python -m integrabog.scripts.robustez_red
    python -m integrabog.scripts.robustez_red --criterio tiempo --transbordo 5 --top 10 --salida resultados/robustez

Imprime el resumen y deja en la carpeta de salida:
  - robustez_red.md: las cifras en tablas, con coma decimal, para el informe;
  - estaciones.csv: una fila por estación (grado, punto de corte,
    intermediación y efecto de su cierre), de la más a la menos crítica;
  - enlaces.csv: una fila por enlace (puente y efecto de su cierre), ídem;
  - robustez_red.geojson: los enlaces dibujados por el trazado (en rojo los
    puentes) y las estaciones (en rojo los puntos de corte, en ámbar las de
    mayor intermediación). Se abre en geojson.io o en QGIS.
"""
import argparse
import csv
import datetime as dt
import json
import numbers
from pathlib import Path

import networkx as nx

from integrabog.config import RAIZ_PROYECTO, TRANSBORDO_MIN
from integrabog.graph.macro import construir_grafo_macro
from integrabog.routing.metricas import CRITERIOS, geometria_camino_lonlat, punto_lonlat
from integrabog.routing.robustez import RobustezRed, grafo_de_enlaces, robustez_red

NOMBRE_CRITERIO = {"tiempo": "tiempo de viaje", "distancia": "distancia", "tramos": "número de tramos"}
COLOR = {"corte": "#dc2626", "intermediacion": "#f59e0b", "otra": "#6b7280", "puente": "#dc2626", "enlace": "#64748b"}


def _nombre(G: nx.DiGraph, v) -> str:
    return G.nodes[v].get("etiqueta") or G.nodes[v].get("nombre") or str(v)


def _codigo(v):
    return int(v) if isinstance(v, numbers.Integral) else v


def _coma(x: float, decimales: int = 1) -> str:
    return f"{x:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _entero(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _enlace(G: nx.DiGraph, e: tuple, flecha: str = "–") -> str:
    return f"{_nombre(G, e[0])} {flecha} {_nombre(G, e[1])}"


def _tipo_enlace(G: nx.DiGraph, u, v) -> str:
    return G[u][v].get("tipo") or "tramo"


def _top_intermediacion(r: RobustezRed, n: int) -> list:
    return sorted(r.intermediacion, key=lambda v: -r.intermediacion[v])[:n]


def _sin_desconexion(cierres: tuple, n: int) -> list:
    """Los cierres que no dejan a nadie sin camino pero alargan viajes: los del
    núcleo con ciclos, donde la red tiene alternativa pero más larga."""
    return [c for c in cierres if not c.pares_desconectados and c.pares_alargados][:n]


def imprimir(G: nx.DiGraph, r: RobustezRed, top: int) -> None:
    e = r.estructura
    print("\n=== ESTRUCTURA ===")
    print(f"Estaciones n = {e.estaciones} | enlaces m = {e.enlaces} | componentes c = {e.componentes} | "
          f"número ciclomático μ = m - n + c = {e.ciclomatico}")
    print(f"Grado: mínimo δ = {e.grado_minimo}, máximo Δ = {e.grado_maximo}, medio {e.grado_medio:.2f}")
    cumple = e.conectividad_vertices <= e.conectividad_aristas <= e.grado_minimo
    print(f"Conectividad: κ = {e.conectividad_vertices} (estaciones), λ = {e.conectividad_aristas} (enlaces); "
          f"Whitney κ <= λ <= δ: {e.conectividad_vertices} <= {e.conectividad_aristas} <= {e.grado_minimo} "
          f"({'se cumple' if cumple else 'NO SE CUMPLE'})")
    print(f"Puntos de corte: {len(e.puntos_de_corte)} de {e.estaciones} estaciones | "
          f"puentes: {len(e.puentes)} de {e.enlaces} enlaces")
    print(f"Bloques (componentes biconexas): {e.bloques}; el mayor tiene {e.bloque_mayor} estaciones")
    for texto, n in (("una sola estación", e.pares_dependen_estacion), ("un solo enlace", e.pares_dependen_enlace)):
        print(f"Pares que dependen de {texto}: {n} de {e.pares_conectados} "
              f"({100 * n / e.pares_conectados if e.pares_conectados else 0:.1f} %)")

    print(f"\n=== INTERMEDIACIÓN ({NOMBRE_CRITERIO[r.criterio]}) ===")
    for v in _top_intermediacion(r, top):
        print(f"  {_nombre(G, v)} ({G.nodes[v].get('troncal') or ''}): {100 * r.intermediacion[v]:.1f} %")

    print(f"\n=== EFICIENCIA Y CIERRES ({NOMBRE_CRITERIO[r.criterio]}) ===")
    armonica = f" (media armónica de los viajes: {1 / r.eficiencia:.1f} {r.unidad})" if r.eficiencia else ""
    print(f"Eficiencia global E = {r.eficiencia:.4f} 1/{r.unidad}{armonica}")
    print(f"Las {top} estaciones cuyo cierre más daña la red:")
    for c in r.cierres_estaciones[:top]:
        print(f"  {_nombre(G, c.elemento)}: -{100 * c.perdida_eficiencia:.1f} % de eficiencia | "
              f"{c.pares_desconectados} pares sin camino | {c.pares_alargados} alargados")
    print(f"Los {top} enlaces cuyo cierre más daña la red:")
    for c in r.cierres_enlaces[:top]:
        puente = " (puente)" if c.elemento in r.estructura.puentes else ""
        print(f"  {_enlace(G, c.elemento)}{puente}: -{100 * c.perdida_eficiencia:.1f} % | "
              f"{c.pares_desconectados} pares sin camino | {c.pares_alargados} alargados")
    print("Cierres que no desconectan a nadie pero más alargan los viajes:")
    for c in _sin_desconexion(r.cierres_estaciones, top):
        print(f"  {_nombre(G, c.elemento)}: -{100 * c.perdida_eficiencia:.1f} % | {c.pares_alargados} pares alargados, "
              f"+{c.aumento_medio:.1f} {r.unidad} en promedio")


def markdown(G: nx.DiGraph, r: RobustezRed, top: int) -> str:
    e = r.estructura

    def pct(n: int) -> str:
        return _coma(100 * n / e.pares_conectados if e.pares_conectados else 0.0)

    lineas = [
        "# Robustez de la red troncal de TransMilenio", "",
        f"Grafo: {e.estaciones} estaciones y {e.enlaces} enlaces (grafo no dirigido de la red troncal). "
        f"Pesos por {NOMBRE_CRITERIO[r.criterio]}"
        + (f", con {_coma(r.transbordo_min)} min por transbordo" if r.criterio == "tiempo" else "") + ".",
        f"Generado el {dt.date.today().isoformat()} con `python -m integrabog.scripts.robustez_red`.", "",
        "## Definiciones", "",
        "- Punto de corte: estación cuyo cierre desconecta la red. Puente: enlace cuyo cierre desconecta la red.",
        "- Bloque: componente biconexa, un pedazo de la red que el cierre de una sola estación no parte.",
        "- Número ciclomático μ = m − n + c: cuántos ciclos independientes tiene la red (con μ = 0 sería un árbol).",
        ("- κ y λ: estaciones y enlaces que hay que cerrar, como mínimo, para desconectar la red. "
         "Desigualdad de Whitney: κ ≤ λ ≤ δ, con δ el grado mínimo."),
        ("- Pares que dependen de una sola estación: los que se separan al cerrar alguna estación distinta de ellos. "
         "Pares que dependen de un solo enlace: los que se separan al cerrar algún enlace."),
        "- Intermediación: fracción de los caminos más cortos entre otros pares que pasa por la estación.",
        ("- Eficiencia global: E = promedio de 1 / d(a, b) sobre los pares ordenados de estaciones distintas "
         "(1 / ∞ = 0). Su inverso es la media armónica de los viajes."),
        ("- Cierre: efecto de cerrar una estación o un enlace sobre los demás viajes: pares sin camino, pares "
         "alargados y pérdida de eficiencia (1 − E después / E antes)."), "",
        "## Estructura", "",
        "| Indicador | Valor |", "|---|---|",
        f"| Estaciones n | {e.estaciones} |",
        f"| Enlaces m | {e.enlaces} |",
        f"| Componentes c | {e.componentes} |",
        f"| Número ciclomático μ = m − n + c | {e.ciclomatico} |",
        f"| Grado mínimo δ, máximo Δ, medio | {e.grado_minimo}, {e.grado_maximo}, {_coma(e.grado_medio, 2)} |",
        f"| Conectividad de vértices κ | {e.conectividad_vertices} |",
        f"| Conectividad de aristas λ | {e.conectividad_aristas} |",
        f"| Puntos de corte | {len(e.puntos_de_corte)} de {e.estaciones} estaciones |",
        f"| Puentes | {len(e.puentes)} de {e.enlaces} enlaces |",
        f"| Bloques (el mayor) | {e.bloques} ({e.bloque_mayor} estaciones) |",
        (f"| Pares que dependen de una sola estación | {_entero(e.pares_dependen_estacion)} de "
         f"{_entero(e.pares_conectados)} ({pct(e.pares_dependen_estacion)} %) |"),
        (f"| Pares que dependen de un solo enlace | {_entero(e.pares_dependen_enlace)} de "
         f"{_entero(e.pares_conectados)} ({pct(e.pares_dependen_enlace)} %) |"),
        f"| Eficiencia global E | {_coma(r.eficiencia, 4)} 1/{r.unidad} |",
        "", f"## Intermediación: las {top} estaciones más usadas por los caminos más cortos", "",
        "| Estación | Troncal | Intermediación | Punto de corte |", "|---|---|---|---|",
    ]
    for v in _top_intermediacion(r, top):
        lineas.append(f"| {_nombre(G, v)} | {G.nodes[v].get('troncal') or ''} | {_coma(100 * r.intermediacion[v])} % | "
                      f"{'sí' if v in e.puntos_de_corte else 'no'} |")
    encabezado = ["| {} | Pérdida de eficiencia | Pares sin camino | Pares alargados | Aumento medio |",
                  "|---|---|---|---|---|"]
    lineas += ["", f"## Las {top} estaciones cuyo cierre más daña la red", "",
               encabezado[0].format("Estación"), encabezado[1]]
    lineas += [_fila(_nombre(G, c.elemento), c, r) for c in r.cierres_estaciones[:top]]
    lineas += ["", f"## Los {top} enlaces cuyo cierre más daña la red", "",
               encabezado[0].format("Enlace"), encabezado[1]]
    lineas += [_fila(_enlace(G, c.elemento, "↔") + (" (puente)" if c.elemento in e.puentes else ""), c, r)
               for c in r.cierres_enlaces[:top]]
    sin = _sin_desconexion(r.cierres_estaciones, top)
    if sin:
        lineas += ["", "## Estaciones cuyo cierre no desconecta a nadie pero más alarga los viajes", "",
                   "Están en el núcleo con ciclos: la red tiene una alternativa, pero más larga.", "",
                   encabezado[0].format("Estación"), encabezado[1]]
        lineas += [_fila(_nombre(G, c.elemento), c, r) for c in sin]
    return "\n".join(lineas) + "\n"


def _fila(nombre: str, c, r: RobustezRed) -> str:
    aumento = f"{_coma(c.aumento_medio)} {r.unidad}" if c.pares_alargados else "—"
    return (f"| {nombre} | {_coma(100 * c.perdida_eficiencia)} % | {_entero(c.pares_desconectados)} | "
            f"{_entero(c.pares_alargados)} | {aumento} |")


def escribir_csv(G: nx.DiGraph, r: RobustezRed, ruta_estaciones: Path, ruta_enlaces: Path) -> None:
    grado = dict(grafo_de_enlaces(G).degree())
    with open(ruta_estaciones, "w", newline="", encoding="utf-8-sig") as archivo:  # utf-8-sig: Excel lee las tildes
        escritor = csv.writer(archivo)
        escritor.writerow(["cod_nodo", "estacion", "troncal", "grado", "punto_de_corte", "intermediacion_pct",
                           "pares_desconectados", "pares_alargados", f"aumento_medio_{r.unidad}",
                           "perdida_eficiencia_pct"])
        for c in r.cierres_estaciones:
            v = c.elemento
            escritor.writerow([_codigo(v), _nombre(G, v), G.nodes[v].get("troncal") or "", grado[v],
                               "sí" if v in r.estructura.puntos_de_corte else "no",
                               round(100 * r.intermediacion[v], 3), c.pares_desconectados, c.pares_alargados,
                               round(c.aumento_medio, 3), round(100 * c.perdida_eficiencia, 3)])
    with open(ruta_enlaces, "w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["cod_origen", "origen", "cod_destino", "destino", "tipo", "largo_km", "puente",
                           "pares_desconectados", "pares_alargados", f"aumento_medio_{r.unidad}",
                           "perdida_eficiencia_pct"])
        for c in r.cierres_enlaces:
            u, v = c.elemento
            escritor.writerow([_codigo(u), _nombre(G, u), _codigo(v), _nombre(G, v), _tipo_enlace(G, u, v),
                               round(G[u][v]["weight"] / 1000, 3), "sí" if c.elemento in r.estructura.puentes else "no",
                               c.pares_desconectados, c.pares_alargados, round(c.aumento_medio, 3),
                               round(100 * c.perdida_eficiencia, 3)])


def geojson(G: nx.DiGraph, r: RobustezRed, top: int) -> dict:
    features = []
    for c in r.cierres_enlaces:
        u, v = c.elemento
        puente = c.elemento in r.estructura.puentes
        features.append({"type": "Feature",
                         "geometry": {"type": "LineString", "coordinates": geometria_camino_lonlat(G, (u, v))},
                         "properties": {"elemento": "enlace", "enlace": _enlace(G, c.elemento), "tipo": _tipo_enlace(G, u, v),
                                        "puente": puente, "pares_desconectados": c.pares_desconectados,
                                        "pares_alargados": c.pares_alargados,
                                        "perdida_eficiencia_pct": round(100 * c.perdida_eficiencia, 3),
                                        "stroke": COLOR["puente" if puente else "enlace"],
                                        "stroke-width": 4 if puente else 2, "stroke-opacity": 0.85}})
    mas_usadas = set(_top_intermediacion(r, top))
    for c in r.cierres_estaciones:
        v = c.elemento
        corte = v in r.estructura.puntos_de_corte
        lon, lat = punto_lonlat(G, v)
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                         "properties": {"elemento": "estación", "cod_nodo": _codigo(v), "estacion": _nombre(G, v),
                                        "troncal": G.nodes[v].get("troncal"), "punto_de_corte": corte,
                                        "intermediacion_pct": round(100 * r.intermediacion[v], 3),
                                        "pares_desconectados": c.pares_desconectados,
                                        "pares_alargados": c.pares_alargados,
                                        "perdida_eficiencia_pct": round(100 * c.perdida_eficiencia, 3),
                                        "marker-color": COLOR["corte" if corte else
                                                              "intermediacion" if v in mas_usadas else "otra"],
                                        "marker-size": "large" if v in mas_usadas else "small"}})
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    parser = argparse.ArgumentParser(description="Robustez de la red troncal: puntos de corte, puentes, "
                                                 "intermediación, eficiencia y cierres.")
    parser.add_argument("--criterio", choices=CRITERIOS, default="tiempo",
                        help="pesos para la intermediación, la eficiencia y los cierres (tiempo)")
    parser.add_argument("--transbordo", type=float, default=TRANSBORDO_MIN,
                        help=f"minutos por transbordo en cada arista de cruce (config: {TRANSBORDO_MIN})")
    parser.add_argument("--top", type=int, default=10, help="cuántas estaciones y enlaces listar en cada tabla")
    parser.add_argument("--salida", type=Path, default=RAIZ_PROYECTO / "resultados" / "robustez",
                        help="carpeta donde se escriben el resumen, los CSV y el GeoJSON")
    args = parser.parse_args()

    G = construir_grafo_macro()
    r = robustez_red(G, args.criterio, args.transbordo)
    print(f"\nRed troncal: {r.estructura.estaciones} estaciones, {r.estructura.enlaces} enlaces | pesos por "
          f"{NOMBRE_CRITERIO[args.criterio]}" + (f", transbordo {args.transbordo} min" if args.criterio == "tiempo" else ""))
    imprimir(G, r, args.top)

    args.salida.mkdir(parents=True, exist_ok=True)
    rutas = {"md": args.salida / "robustez_red.md", "estaciones": args.salida / "estaciones.csv",
             "enlaces": args.salida / "enlaces.csv", "geojson": args.salida / "robustez_red.geojson"}
    rutas["md"].write_text(markdown(G, r, args.top), encoding="utf-8")
    escribir_csv(G, r, rutas["estaciones"], rutas["enlaces"])
    rutas["geojson"].write_text(json.dumps(geojson(G, r, args.top), ensure_ascii=False), encoding="utf-8")
    print("\nArchivos:\n" + "\n".join(f"  {ruta}" for ruta in rutas.values()))


if __name__ == "__main__":
    main()
