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
from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.routing.network_design import (
    _TRANSFORMADOR,
    _arista_del_camino,
    calcular_costo_brt,
    ruta_nueva,
)


def main():
    print("Reconstruyendo el grafo multicapa (usa la caché, no descarga nada nuevo)...")
    G_macro = construir_grafo_macro()
    G_micro = obtener_malla_vial()
    G_multicapa = construir_grafo_multicapa(G_macro, G_micro)
    calcular_costo_brt(G_multicapa)

    origen, destino = "macro_4107", "macro_3014"  # Escuela Militar, San Martin

    """la misma ruta que usa sugerir_nueva_troncal() (ruta_nueva: solo vías aptas para una
     troncal, sin giros prohibidos ni vueltas en U) -- si no, se estaría midiendo un camino distinto al que
     reporta el modelo"""
    camino, claves, _ = ruta_nueva(G_multicapa, origen, destino)

    distancia_real_m = 0.0
    por_tipo = {}
    for i in range(len(camino) - 1):
        """con la clave que usó la ruta y no leer 'weight'/'length' directo del edge_data --
         entre dos nodos puede haber más de una arista paralela, y hay que medir la misma que
         tomó la ruta, no una cualquiera de las paralelas"""
        arista = _arista_del_camino(G_multicapa, camino, claves, i)
        largo = arista.get("length", arista.get("weight", 0.0))
        distancia_real_m += largo
        if arista.get("layer") == "micro":
            tipo = arista.get("class", "sin_clase")  # jerarquía vial de Overture (antes 'highway' de OSM)
            if arista.get("subclass") == "link":
                tipo += " (rampa)"
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
