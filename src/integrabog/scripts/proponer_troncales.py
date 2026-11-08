"""
Troncales propuestas para el escenario "después" (routing/escenarios.py):
calcula la ruta de cada una por la malla vial, con las mismas reglas de la
app (vías aptas para una troncal, sentidos de circulación, giros prohibidos y
sin vueltas en U), y las guarda en un GeoJSON que lee comparar_escenarios.

Uso:
    python -m integrabog.scripts.proponer_troncales                  # los 5 pares críticos
    python -m integrabog.scripts.proponer_troncales --top 3
    python -m integrabog.scripts.proponer_troncales --par "Escuela Militar" "San Martín" --par "Nariño" "Ciudad Jardín"

Sin --par toma los pares críticos de la app (identificar_pares_criticos):
estaciones cercanas en línea recta y lejanas por la red troncal. Con --par,
las estaciones se dan como en la app: código, etiqueta o nombre parcial, sin
distinguir tildes. Necesita la malla vial completa (la primera vez la
descarga de Overture); por eso se guarda el resultado, y la comparación,
que solo usa el grafo macro, se puede repetir sin volver a calcularlo.
"""
import argparse
from pathlib import Path

import networkx as nx

from integrabog.config import RAIZ_PROYECTO, TRANSBORDO_MIN
from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.routing.escenarios import (
    TroncalPropuesta,
    guardar_propuestas,
    propuesta_desde_sugerencia,
)
from integrabog.routing.network_design import (
    EstacionNoEncontradaError,
    calcular_costo_brt,
    identificar_pares_criticos,
    sugerir_nueva_troncal,
)

SALIDA = RAIZ_PROYECTO / "resultados" / "escenarios" / "propuestas.geojson"


def _etiqueta(G: nx.MultiDiGraph, nodo) -> str:
    return G.nodes[nodo].get("etiqueta") or G.nodes[nodo].get("nombre") or str(nodo)


def _unidas(G: nx.MultiDiGraph, a, b) -> bool:
    """Si la red troncal de hoy ya tiene una conexión directa entre a y b."""
    return any(d.get("layer") == "macro" for u, v in ((a, b), (b, a)) for d in (G.get_edge_data(u, v) or {}).values())


def proponer(G_multicapa: nx.MultiDiGraph, pares: list | None = None, top: int = 5) -> tuple[list, list]:
    """Las troncales propuestas para los pares dados, o para los 'top' pares
    críticos si no se da ninguno. Requiere calcular_costo_brt(G_multicapa).

    Returns:
        (propuestas, avisos): las TroncalPropuesta que se pueden agregar al
        grafo macro, y una línea por cada par que se dejó por fuera y por qué
        (estación inexistente o ambigua, sin ruta por vías aptas, ya unidas
        por la red de hoy o repetido).
    """
    avisos, resultados = [], []
    if pares:
        for origen, destino in pares:
            try:
                resultados.append(sugerir_nueva_troncal(G_multicapa, origen, destino))
            except EstacionNoEncontradaError as err:
                avisos.append(f"{origen} -> {destino}: {err}")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                avisos.append(f"{origen} -> {destino}: no hay ruta por vías aptas para una troncal")
    else:
        resultados = identificar_pares_criticos(G_multicapa, top_n=top)

    propuestas, vistos = [], set()
    for r in resultados:
        o, d = r["estacion_origen"], r["estacion_destino"]
        nombre = f"{_etiqueta(G_multicapa, o)} ↔ {_etiqueta(G_multicapa, d)}"
        if frozenset((o, d)) in vistos:
            avisos.append(f"{nombre}: repetida")
        elif _unidas(G_multicapa, o, d):
            avisos.append(f"{nombre}: la red troncal de hoy ya las une directamente; no agrega una conexión nueva")
        else:
            vistos.add(frozenset((o, d)))
            propuestas.append(propuesta_desde_sugerencia(r, nombre))
    return propuestas, avisos


def imprimir(propuestas: list[TroncalPropuesta], avisos: list[str]) -> None:
    print(f"\n{'propuesta':<52} {'largo':>8} {'tiempo':>8} {'hoy':>8} {'ahorro':>8} {'tramos':>6} {'rodeo':>6}")
    for p in propuestas:
        hoy = f"{p.tiempo_actual_min:.1f}" if p.tiempo_actual_min is not None else "—"
        ahorro = f"{p.ahorro_min:+.1f}" if p.ahorro_min is not None else "—"
        rodeo = f"{p.factor_rodeo:.1f}x" if p.factor_rodeo is not None else "—"
        print(f"{p.nombre:<52} {p.largo_m / 1000:>5.2f} km {p.tiempo_min:>4.1f} min {hoy:>8} {ahorro:>8} "
              f"{p.tramos:>6} {rodeo:>6}")
    print("  (tiempo: el de la ruta nueva en la app, sin transbordo; hoy: por la red troncal, con transbordos;\n"
          "   en el escenario, cruzar por la propuesta cobra además un transbordo, como un cruce, salvo que\n"
          "   comparar_escenarios la opere como ruta continua: --transbordo-propuestas 0)")
    for aviso in avisos:
        print(f"  [!] {aviso}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Calcula las troncales propuestas y las guarda para "
                                                 "comparar_escenarios.")
    parser.add_argument("--par", nargs=2, action="append", metavar=("ORIGEN", "DESTINO"),
                        help="un par de estaciones (se puede repetir); sin --par, los pares críticos")
    parser.add_argument("--top", type=int, default=5, help="cuántos pares críticos proponer si no se da --par (5)")
    parser.add_argument("--salida", type=Path, default=SALIDA, help="GeoJSON de salida")
    args = parser.parse_args()

    print("Construyendo el grafo multicapa (usa la caché de la malla vial)...")
    G = construir_grafo_multicapa(construir_grafo_macro(), obtener_malla_vial())
    calcular_costo_brt(G)
    propuestas, avisos = proponer(G, args.par, args.top)
    imprimir(propuestas, avisos)
    if not propuestas:
        raise SystemExit("\nNo quedó ninguna propuesta: no se escribió el archivo.")
    guardar_propuestas(propuestas, args.salida)
    print(f"\n{len(propuestas)} propuestas guardadas en {args.salida}\n"
          f"Siguiente paso: python -m integrabog.scripts.comparar_escenarios --propuestas {args.salida}\n"
          f"  (con --transbordo-propuestas {TRANSBORDO_MIN:g} 0 compara la conexión física con la ruta continua)")


if __name__ == "__main__":
    main()
