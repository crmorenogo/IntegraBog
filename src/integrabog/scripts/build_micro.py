"""
Script para descargar, construir y validar el grafo de la malla vial (Grafo Micro).
"""
from integrabog.graph.micro import obtener_malla_vial


def main():
    G_micro = obtener_malla_vial("Bogotá, Colombia", forzar_descarga=False)

    print("\n--- RESUMEN DEL GRAFO MICRO (MALLA VIAL) ---")
    print(f"Nodos (intersecciones): {G_micro.number_of_nodes()}")
    print(f"Aristas (tramos de calle): {G_micro.number_of_edges()}")

    if G_micro.number_of_edges() > 0:
        origen, destino, key, datos_arista = next(iter(G_micro.edges(keys=True, data=True)))
        print("\nEjemplo de atributos de una calle (arista):")
        print(f"  - Longitud física: {datos_arista.get('length', 'N/A'):.2f} metros")
        print(f"  - Tipo de vía (highway): {datos_arista.get('highway', 'N/A')}")
        print(f"  - Nombre: {datos_arista.get('name', 'Sin nombre')}")

    return G_micro


if __name__ == "__main__":
    main()