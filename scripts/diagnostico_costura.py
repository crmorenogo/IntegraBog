"""
Lista las conexiones que agregan la costura y los cruces entre troncales
al grafo macro (graph/costura.py y graph/cruces.py), para revisarlas
a mano contra el sistema real cada vez que cambian los datos de trazado o
de estaciones (data/raw/).

Por qué hace falta: las dos se infieren de la geometría. La costura une
extremos de piezas del trazado que quedan a menos de TOLERANCIA_COSTURA_M, y
los cruces unen las estaciones vecinas de cada punto donde dos troncales se
tocan (config.py). Eso cierra los empalmes y transbordos reales, pero si unos
datos nuevos traen dos troncales que se tocan sin conectarse -- un puente
sin rampa, por ejemplo --, quedarían unidas igual. No hay forma de
distinguir los dos casos solo con la geometría; este listado es la forma de
verlo.

Marca con "REVISAR" las conexiones cuya distancia por el trazado es más
del doble de la distancia en línea recta: una costura sana sigue el
trazado de cerca, y un rodeo grande suele ser señal de una unión que no
existe en la realidad. Una vez revisada a mano, cada una se anota en
config.py: CONEXIONES_BLOQUEADAS si no existe (se quita del grafo) o
CONEXIONES_VERIFICADAS si sí (deja de marcarse).

    python -m integrabog.scripts.diagnostico_costura
"""
import math

import networkx as nx

from integrabog.config import (
    CONEXIONES_BLOQUEADAS,
    CONEXIONES_VERIFICADAS,
    DISTANCIA_MAX_CRUCE_M,
    TOLERANCIA_COSTURA_M,
)
from integrabog.graph.correcciones import es_verificada
from integrabog.graph.macro import construir_grafo_macro


def main():
    G = construir_grafo_macro()

    titulos = {
        "costura": f"COSTURA (extremos de pieza a menos de {TOLERANCIA_COSTURA_M:.0f} m)",
        "cruce": f"CRUCES ENTRE TRONCALES (estaciones a <= {DISTANCIA_MAX_CRUCE_M:.0f} m del cruce)",
    }
    for tipo_arista, titulo in titulos.items():
        print(f"\n--- CONEXIONES DE {titulo} ---")
        vistas = set()
        filas = []
        for u, v, d in G.edges(data=True):
            if d.get("tipo") != tipo_arista or frozenset((u, v)) in vistas:
                continue
            vistas.add(frozenset((u, v)))
            nu, nv = G.nodes[u], G.nodes[v]
            recta = math.dist((nu["x"], nu["y"]), (nv["x"], nv["y"]))
            verificada = es_verificada(u, v, CONEXIONES_VERIFICADAS)
            filas.append((nu["id_trazado"], nu["nombre"], nv["id_trazado"], nv["nombre"], d["weight"], recta,
                          verificada))

        for tz_u, nom_u, tz_v, nom_v, peso, recta, verificada in sorted(filas):
            tipo = "misma troncal" if tz_u == tz_v else "transbordo"
            if verificada:
                aviso = "  <- verificada a mano (config.py)"
            else:
                aviso = "  <- REVISAR" if peso > 2 * recta else ""
            print(f"  {nom_u} ({tz_u}) <-> {nom_v} ({tz_v}): {peso:.0f} m por trazado, "
                  f"{recta:.0f} m en recta [{tipo}]{aviso}")
        print(f"Total: {len(filas)} pares")

    print("\n--- BLOQUEADAS A MANO (config.py, no están en el grafo) ---")
    for a, b, motivo in CONEXIONES_BLOQUEADAS:
        print(f"  {motivo}")

    componentes = sorted(nx.weakly_connected_components(G), key=len, reverse=True)
    print(f"\nComponentes de la red troncal: {len(componentes)}"
          f"{' (toda la red conectada)' if len(componentes) == 1 else ''}")
    for comp in componentes[1:]:
        nombres = sorted(G.nodes[n]["nombre"] for n in comp)
        print(f"  aislada ({len(comp)}): {', '.join(nombres[:8])}{' ...' if len(nombres) > 8 else ''}")


if __name__ == "__main__":
    main()