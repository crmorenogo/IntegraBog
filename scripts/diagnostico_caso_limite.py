"""
Diagnóstico: ¿por qué Escuela Militar <-> San Martín da 17.5 min para
apenas 306 m en línea recta? Mide la ruta real, tramo por tramo, para
descartar un error de código antes de aceptarlo como limitación.
"""
import networkx as nx

from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.routing.network_design import (
    _TRANSFORMADOR,
    _mejor_arista,
    _peso_tiempo,
    calcular_costo_brt,
)


def main():
    print("Reconstruyendo el grafo multicapa (usa la caché, no descarga nada nuevo)...")
    G_macro = construir_grafo_macro()
    G_micro = obtener_malla_vial()
    G_multicapa = construir_grafo_multicapa(G_macro, G_micro)
    calcular_costo_brt(G_multicapa)

    origen, destino = "macro_4107", "macro_3014"  # Escuela Militar, San Martin

    aristas_ruta = [
        (u, v, k) for u, v, k, d in G_multicapa.edges(keys=True, data=True)
        if d.get("layer") == "micro"
        or (d.get("layer") == "transferencia" and (u in (origen, destino) or v in (origen, destino)))
    ]
    G_ruta = G_multicapa.edge_subgraph(aristas_ruta)
    camino = nx.shortest_path(G_ruta, origen, destino, weight=_peso_tiempo)

    distancia_real_m = 0.0
    por_tipo = {}
    for i in range(len(camino) - 1):
        arista = _mejor_arista(G_multicapa.get_edge_data(camino[i], camino[i + 1]))
        largo = arista.get("length", arista.get("weight", 0.0))
        distancia_real_m += largo
        if arista.get("layer") == "micro":
            tipo = arista.get("highway", "sin_tag")
            tipo = tipo[0] if isinstance(tipo, list) else tipo
        else:
            tipo = arista.get("layer")
        por_tipo[tipo] = por_tipo.get(tipo, 0.0) + largo

    print(f"\nDistancia real de la ruta: {distancia_real_m:.0f} m  (vs 306 m en línea recta -> {distancia_real_m/306:.1f}x)")
    print(f"Nodos en el camino: {len(camino)}")
    print("Distancia por tipo de vía:")
    for tipo, m in sorted(por_tipo.items(), key=lambda x: -x[1]):
        print(f"  {tipo}: {m:.0f} m ({m/distancia_real_m*100:.0f}%)")

    for nodo, nombre in [(origen, "Escuela Militar"), (destino, "San Martín")]:
        d = G_multicapa.nodes[nodo]
        lon, lat = _TRANSFORMADOR.transform(d["x"], d["y"])
        print(f"{nombre}: {lat:.5f}, {lon:.5f}  (pégalo en Google Maps)")


if __name__ == "__main__":
    main()
