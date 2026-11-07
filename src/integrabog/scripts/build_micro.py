"""
Script para descargar, construir y validar el grafo de la malla vial
(Grafo Micro) desde Overture Maps.

Aparte del proyecto: sirve para probar Fase 2 sola, sin tener que armar
el grafo macro ni el multicapa encima. Si esto falla o da un número
raro, el problema está en la descarga de Overture o en su lectura
(micro.py), no en nada de lo que se construye después.

La primera corrida descarga con City2Graph (necesita salida a internet
hacia stac.overturemaps.org y S3); las siguientes usan la caché.
"""
from collections import Counter

from integrabog.graph.micro import obtener_malla_vial


def main():
    """sin argumentos posicionales: la versión OSMnx recibía aquí "Bogotá, Colombia", lo que
     sin caché bajaba solo Bogotá -- sin Soacha -- y la guardaba encima de la buena"""
    G_micro = obtener_malla_vial()

    print("\n--- RESUMEN DEL GRAFO MICRO (MALLA VIAL, OVERTURE MAPS) ---")
    print(f"Release de Overture: {G_micro.graph.get('overture_release', 'no registrado')}")
    print(f"Nodos (conectores): {G_micro.number_of_nodes()}")
    print(f"Aristas (tramos de calle, por sentido): {G_micro.number_of_edges()}")

    if G_micro.number_of_edges() > 0:
        aristas = [d for _, _, d in G_micro.edges(data=True)]
        print(f"Aristas por clase vial: {dict(Counter(d['class'] for d in aristas).most_common())}")
        print(f"De un solo sentido: {sum(d['oneway'] for d in aristas) / len(aristas) * 100:.1f}% | "
              f"rampas (subclass=link): {sum(d.get('subclass') == 'link' for d in aristas)} | "
              f"con límite de velocidad: {sum('velocidad_max_kmh' in d for d in aristas)}")

        """una arista cualquiera, no una en particular -- esto es solo para confirmar
         a ojo que los atributos vienen poblados (class, length, name), no para
         inspeccionar un tramo específico"""
        origen, destino, key, datos_arista = next(iter(G_micro.edges(keys=True, data=True)))
        print("\nEjemplo de atributos de una calle (arista):")
        print(f"  - Longitud física: {datos_arista.get('length', float('nan')):.2f} metros")
        print(f"  - Clase vial (class): {datos_arista.get('class', 'N/A')}"
              f"{' / ' + datos_arista['subclass'] if 'subclass' in datos_arista else ''}")
        print(f"  - Nombre: {datos_arista.get('name', 'Sin nombre')}")
        print(f"  - Un solo sentido: {datos_arista.get('oneway')}")
        print(f"  - Segmento Overture: {datos_arista.get('overture_id')}")

    return G_micro


if __name__ == "__main__":
    main()
