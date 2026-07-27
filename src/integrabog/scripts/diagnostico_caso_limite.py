"""
Diagnóstico: La razón por lo que Escuela Militar <-> San Martín da 17.5 min
para apenas 306 m en línea recta. Mide la ruta real, tramo por tramo,
para descartar un error de código antes de aceptarlo como limitación.

El origen y el destino están fijos ("macro_4107", "macro_3014")
porque su único objetivo es reproducir un caso puntual ya identificado
en identificar_pares_criticos(), no servir de herramienta general para cualquier par.
Si mañana aparece otro par sospechoso, se copia y se cambian esas dos líneas, no se
generaliza de más para un caso que hasta ahora solo se ha necesitado una
vez.
"""
import networkx as nx

from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.routing.network_design import calcular_costo_brt, _peso_tiempo, _mejor_arista, _TRANSFORMADOR


def main():
    print("Reconstruyendo el grafo multicapa (usa la caché, no descarga nada nuevo)...")
    G_macro = construir_grafo_macro()
    G_micro = obtener_malla_vial()
    G_multicapa = construir_grafo_multicapa(G_macro, G_micro)
    calcular_costo_brt(G_multicapa)

    origen, destino = "macro_4107", "macro_3014"  # Escuela Militar, San Martin

    """mismo filtro de subgrafo que usa sugerir_nueva_troncal() para la ruta propuesta --
     tiene que ser exactamente ese, si no se estaría midiendo un camino distinto al que
     de verdad reportó el 17.5"""
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
        """_mejor_arista y no leer 'weight'/'length' directo del edge_data -- entre dos
         nodos puede haber más de una arista paralela, y hay que medir la misma que
         _peso_tiempo usó para armar 'camino', no una cualquiera de las paralelas"""
        arista = _mejor_arista(G_multicapa.get_edge_data(camino[i], camino[i + 1]))
        largo = arista.get("length", arista.get("weight", 0.0))
        distancia_real_m += largo
        if arista.get("layer") == "micro":
            tipo = arista.get("highway", "sin_tag")
            tipo = tipo[0] if isinstance(tipo, list) else tipo # highway fusionado por OSMnx puede llegar como lista
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
        print(f"{nombre}: {lat:.5f}, {lon:.5f}  (pégarlo en Google Maps)") # a mano en un mapa, no hay forma de confirmar la barrera física desde acá


if __name__ == "__main__":
    main()