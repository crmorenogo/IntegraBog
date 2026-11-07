"""
Métricas de la red troncal: excentricidad de cada estación, diámetro,
radio, centro y periferia, por tiempo de viaje, distancia y número de
tramos (routing/metricas.py).

Uso:
    python -m integrabog.scripts.metricas_red
    python -m integrabog.scripts.metricas_red --transbordo 5 --salida resultados/metricas

Imprime el resumen y deja en la carpeta de salida:
  - metricas_red.geojson: el camino del diámetro de cada criterio, dibujado
    por el trazado oficial, y cada estación con su excentricidad (en rojo la
    periferia y en verde el centro, por tiempo). Se abre en geojson.io o en
    QGIS.
  - excentricidades.csv: una fila por estación, con su excentricidad y su
    estación más lejana en cada criterio.
  - metricas_red.md: las mismas cifras en tablas, con coma decimal.
"""
import argparse
import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path

import networkx as nx

from integrabog.config import RAIZ_PROYECTO, TRANSBORDO_MIN
from integrabog.graph.macro import construir_grafo_macro
from integrabog.routing.metricas import (
    CRITERIOS,
    MetricasRed,
    geometria_camino_lonlat,
    metricas_red,
    punto_lonlat,
    resumen_camino,
)
from integrabog.routing.network_design import VELOCIDAD_BRT_KMH

NOMBRE_CRITERIO = {"tiempo": "Tiempo de viaje", "distancia": "Distancia", "tramos": "Número de tramos"}
DECIMALES = {"tiempo": 1, "distancia": 2, "tramos": 0}
COLOR_RUTA = {"tiempo": "#dc2626", "distancia": "#2563eb", "tramos": "#16a34a"}
COLOR_ROL = {"periferia": "#dc2626", "centro": "#16a34a", "": "#6b7280"}


def _valor(m: MetricasRed, x: float, coma: bool = False) -> str:
    texto = "∞" if x == float("inf") else f"{x:.{DECIMALES[m.criterio]}f}"
    return (texto.replace(".", ",") if coma else texto) + f" {m.unidad}"


def _plural(n: int, palabra: str) -> str:
    return f"{n} {palabra}" + ("" if n == 1 else "s")


def _pares(G: nx.DiGraph, m: MetricasRed, flecha: str) -> list[str]:
    """Todos los pares que alcanzan el diámetro; en un grafo simétrico, cada viaje una vez."""
    nombre = lambda v: G.nodes[v].get("etiqueta") or G.nodes[v].get("nombre") or str(v)  # noqa: E731
    pares = m.pares_diametro_sin_orden() if _simetrico(G) else list(m.pares_diametro)
    return [f"{nombre(u)} {flecha} {nombre(v)}" for u, v in pares]


def _rol(m: MetricasRed, v) -> str:
    """'centro', 'periferia', los dos (si D = r) o ''."""
    roles = [r for r, conjunto in (("centro", m.centro), ("periferia", m.periferia)) if v in conjunto]
    return " y ".join(roles)


def _simetrico(G: nx.DiGraph) -> bool:
    return all(G.has_edge(v, u) for u, v in G.edges())


def imprimir(G: nx.DiGraph, metricas: dict, top: int) -> None:
    nombre = lambda v: G.nodes[v].get("etiqueta") or G.nodes[v].get("nombre") or str(v)  # noqa: E731
    for criterio, m in metricas.items():
        print(f"\n=== {NOMBRE_CRITERIO[criterio].upper()} ({m.unidad}) ===")
        if m.pares_sin_camino:
            print(f"  [!] {m.pares_sin_camino} pares de estaciones sin camino: la red no es fuertemente conexa "
                  f"y el diámetro es infinito.")
        origen, destino = m.par_diametro
        pares = _pares(G, m, "<->")
        print(f"Diámetro D = {_valor(m, m.diametro)}: {nombre(origen)} -> {nombre(destino)}")
        if len(pares) > 1:
            print(f"  lo alcanzan {len(pares)} pares: {'; '.join(pares)}")
        if m.camino_diametro:
            r = resumen_camino(G, m.camino_diametro, m.transbordo_min)
            print(f"  camino: {_plural(r['tramos'], 'tramo')} | {r['km']:.1f} km | {r['minutos']:.1f} min | "
                  f"{_plural(r['transbordos'], 'transbordo')} | {r['estaciones']} estaciones | "
                  f"troncales: {' -> '.join(r['troncales'])}")
        print(f"Radio r = {_valor(m, m.radio)}")
        print(f"Centro (e = r): {', '.join(nombre(v) for v in m.centro)}")
        print(f"Periferia (e = D): {', '.join(nombre(v) for v in m.periferia)}")
        orden = sorted(m.excentricidad, key=lambda v: (-m.excentricidad[v], str(v)))
        print(f"Las {top} más excéntricas: " + "; ".join(f"{nombre(v)} {_valor(m, m.excentricidad[v])}" for v in orden[:top]))
        print(f"Las {top} menos excéntricas: " + "; ".join(f"{nombre(v)} {_valor(m, m.excentricidad[v])}"
                                                           for v in orden[::-1][:top]))

    print("\n=== RESUMEN ===")
    print(f"  {'criterio':<18} {'diámetro':>14} {'radio':>14}  {'D/r':>5}  {'centro':>6}  {'periferia':>9}  par del diámetro")
    for criterio, m in metricas.items():
        razon = m.diametro / m.radio if m.radio else float("inf")
        print(f"  {NOMBRE_CRITERIO[criterio]:<18} {_valor(m, m.diametro):>14} {_valor(m, m.radio):>14}  {razon:>5.2f}  "
              f"{len(m.centro):>6}  {len(m.periferia):>9}  {nombre(m.par_diametro[0])} <-> {nombre(m.par_diametro[1])}")
    if _simetrico(G):
        """en un grafo no dirigido (o dirigido simétrico) con pesos no negativos, r <= D <= 2r:
         d(u, w) <= d(u, c) + d(c, w) <= 2r para c en el centro"""
        cumple = all(m.radio <= m.diametro <= 2 * m.radio for m in metricas.values())
        print(f"  Comprobación r <= D <= 2r (grafo simétrico): {'se cumple en los tres criterios' if cumple else 'NO SE CUMPLE'}")


def geojson(G: nx.DiGraph, metricas: dict) -> dict:
    nombre = lambda v: G.nodes[v].get("etiqueta") or G.nodes[v].get("nombre") or str(v)  # noqa: E731
    features = []
    for criterio, m in metricas.items():
        if not m.camino_diametro:
            continue
        r = resumen_camino(G, m.camino_diametro, m.transbordo_min)
        features.append({"type": "Feature",
                         "geometry": {"type": "LineString", "coordinates": geometria_camino_lonlat(G, m.camino_diametro)},
                         "properties": {"elemento": f"diámetro por {criterio}", "criterio": criterio,
                                        "diametro": round(m.diametro, 4), "unidad": m.unidad,
                                        "origen": nombre(m.par_diametro[0]), "destino": nombre(m.par_diametro[1]),
                                        "tramos": r["tramos"], "km": round(r["km"], 3), "minutos": round(r["minutos"], 2),
                                        "transbordos": r["transbordos"], "troncales": " -> ".join(r["troncales"]),
                                        "stroke": COLOR_RUTA[criterio], "stroke-width": 4, "stroke-opacity": 0.85}})
    tiempo = metricas.get("tiempo") or next(iter(metricas.values()))
    for v, d in G.nodes(data=True):
        lon, lat = punto_lonlat(G, v)
        rol = _rol(tiempo, v)
        propiedades = {"elemento": "estación", "cod_nodo": v, "estacion": nombre(v), "troncal": d.get("troncal")}
        for criterio, m in metricas.items():
            propiedades[f"e_{criterio}"] = round(m.excentricidad[v], 4)
            propiedades[f"mas_lejana_{criterio}"] = nombre(m.mas_lejana[v]) if m.mas_lejana[v] is not None else None
            propiedades[f"rol_{criterio}"] = _rol(m, v)
        propiedades.update({"marker-color": COLOR_ROL["periferia" if "periferia" in rol else rol],
                            "marker-size": "large" if rol else "small"})
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                         "properties": propiedades})
    return {"type": "FeatureCollection", "features": features}


def escribir_csv(G: nx.DiGraph, metricas: dict, ruta: Path) -> None:
    nombre = lambda v: G.nodes[v].get("etiqueta") or G.nodes[v].get("nombre") or str(v)  # noqa: E731
    primero = next(iter(metricas.values()))
    with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:  # utf-8-sig: Excel lee bien las tildes
        escritor = csv.writer(archivo)
        encabezado = ["cod_nodo", "estacion", "troncal"]
        for criterio, m in metricas.items():
            encabezado += [f"e_{criterio}_{m.unidad}", f"mas_lejana_{criterio}", f"rol_{criterio}"]
        escritor.writerow(encabezado)
        for v in sorted(G.nodes, key=lambda n: (primero.excentricidad[n], str(n))):
            fila = [v, nombre(v), G.nodes[v].get("troncal") or ""]
            for m in metricas.values():
                fila += [round(m.excentricidad[v], 4), nombre(m.mas_lejana[v]) if m.mas_lejana[v] is not None else "",
                         _rol(m, v)]
            escritor.writerow(fila)


def markdown(G: nx.DiGraph, metricas: dict, transbordo_min: float) -> str:
    nombre = lambda v: G.nodes[v].get("etiqueta") or G.nodes[v].get("nombre") or str(v)  # noqa: E731
    tipos = Counter(d.get("tipo") or "tramo" for *_, d in G.edges(data=True))
    coma = lambda x, n=1: f"{x:.{n}f}".replace(".", ",")  # noqa: E731
    lineas = [
        "# Métricas de la red troncal de TransMilenio", "",
        f"Grafo: {G.number_of_nodes()} estaciones y {G.number_of_edges()} aristas dirigidas "
        f"({tipos['tramo']} de tramo, {tipos['costura']} de costura y {tipos['cruce']} de cruce entre troncales); "
        f"{'simétrico' if _simetrico(G) else 'no simétrico'}, "
        f"{'fuertemente conexo' if nx.is_strongly_connected(G) else 'NO fuertemente conexo'}.",
        f"Parámetros: velocidad BRT {coma(VELOCIDAD_BRT_KMH)} km/h; transbordo {coma(transbordo_min)} min por arista de cruce.",
        f"Generado el {dt.date.today().isoformat()} con `python -m integrabog.scripts.metricas_red`.", "",
        "## Definiciones", "",
        "Para el grafo dirigido G = (V, E) y d(u, v), el largo del camino más corto de u a v según el criterio:", "",
        "- excentricidad: e(v) = máx { d(v, u) : u ∈ V }",
        "- diámetro: D = máx { e(v) : v ∈ V }",
        "- radio: r = mín { e(v) : v ∈ V }",
        "- centro: { v ∈ V : e(v) = r }",
        "- periferia: { v ∈ V : e(v) = D }", "",
        "Criterios para d(u, v): tiempo de viaje (largo por el trazado a la velocidad BRT, más el transbordo en cada "
        "cruce), distancia por el trazado oficial y número de tramos (cada arista cuenta 1).", "",
        "## Resumen", "",
        "| Criterio | Diámetro D | Pares que lo alcanzan | Radio r | D / r | Centro | Periferia |",
        "|---|---|---|---|---|---|---|",
    ]
    for criterio, m in metricas.items():
        lineas.append(f"| {NOMBRE_CRITERIO[criterio]} | {_valor(m, m.diametro, coma=True)} | "
                      f"{'; '.join(_pares(G, m, '↔'))} | {_valor(m, m.radio, coma=True)} | "
                      f"{coma(m.diametro / m.radio if m.radio else float('inf'), 2)} | "
                      f"{', '.join(nombre(v) for v in m.centro)} | {', '.join(nombre(v) for v in m.periferia)} |")
    for criterio, m in metricas.items():
        if not m.camino_diametro:
            continue
        r = resumen_camino(G, m.camino_diametro, m.transbordo_min)
        empate = (f" Es uno de los {len(_pares(G, m, '↔'))} pares que alcanzan el diámetro."
                  if len(_pares(G, m, "↔")) > 1 else "")
        lineas += ["", f"## Camino del diámetro: {NOMBRE_CRITERIO[criterio].lower()}", "",
                   f"{nombre(m.par_diametro[0])} → {nombre(m.par_diametro[1])}: {_plural(r['tramos'], 'tramo')}, "
                   f"{coma(r['km'], 2)} km, {coma(r['minutos'])} min, {_plural(r['transbordos'], 'transbordo')}, "
                   f"{r['estaciones']} estaciones. Troncales: {' → '.join(r['troncales'])}.{empate}", "",
                   " → ".join(nombre(v) for v in m.camino_diametro)]
    lineas += ["", "## Excentricidad por estación", "",
               "Ordenadas de la más central a la más periférica por tiempo de viaje.", "",
               "| Estación | Troncal | " + " | ".join(f"e por {c} ({metricas[c].unidad})" for c in metricas) + " |",
               "|---|---|" + "---|" * len(metricas)]
    primero = next(iter(metricas.values()))
    for v in sorted(G.nodes, key=lambda n: (primero.excentricidad[n], str(n))):
        valores = " | ".join(_valor(m, m.excentricidad[v], coma=True).rsplit(" ", 1)[0] for m in metricas.values())
        lineas.append(f"| {nombre(v)} | {G.nodes[v].get('troncal') or ''} | {valores} |")
    return "\n".join(lineas) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Excentricidad, diámetro, radio, centro y periferia de la red troncal.")
    parser.add_argument("--transbordo", type=float, default=TRANSBORDO_MIN,
                        help=f"minutos por transbordo en cada arista de cruce (config: {TRANSBORDO_MIN})")
    parser.add_argument("--salida", type=Path, default=RAIZ_PROYECTO / "resultados" / "metricas",
                        help="carpeta donde se escriben el GeoJSON, el CSV y el resumen")
    parser.add_argument("--top", type=int, default=5, help="cuántas estaciones listar en cada extremo")
    args = parser.parse_args()

    G = construir_grafo_macro()
    tipos = Counter(d.get("tipo") or "tramo" for *_, d in G.edges(data=True))
    print(f"\nRed troncal: {G.number_of_nodes()} estaciones, {G.number_of_edges()} aristas dirigidas "
          f"({tipos['tramo']} de tramo, {tipos['costura']} de costura, {tipos['cruce']} de cruce) | "
          f"velocidad BRT {VELOCIDAD_BRT_KMH} km/h | transbordo {args.transbordo} min por cruce")
    metricas = {criterio: metricas_red(G, criterio, args.transbordo) for criterio in CRITERIOS}
    imprimir(G, metricas, args.top)

    args.salida.mkdir(parents=True, exist_ok=True)
    rutas = {"geojson": args.salida / "metricas_red.geojson", "csv": args.salida / "excentricidades.csv",
             "md": args.salida / "metricas_red.md"}
    rutas["geojson"].write_text(json.dumps(geojson(G, metricas), ensure_ascii=False), encoding="utf-8")
    escribir_csv(G, metricas, rutas["csv"])
    rutas["md"].write_text(markdown(G, metricas, args.transbordo), encoding="utf-8")
    print("\nArchivos:\n" + "\n".join(f"  {ruta}" for ruta in rutas.values()))
    print("  (el GeoJSON se abre en https://geojson.io o en QGIS: en rojo la periferia y el diámetro por tiempo, "
          "en verde el centro)")


if __name__ == "__main__":
    main()
