from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.routing.network_design import calcular_costo_brt, identificar_pares_criticos


def main():
    G_macro = construir_grafo_macro()
    G_micro = obtener_malla_vial()
    g_multicapa = construir_grafo_multicapa(G_macro, G_micro)
    calcular_costo_brt(g_multicapa)

    for r in identificar_pares_criticos(g_multicapa, top_n=5):
        print(
            f"{r['estacion_origen']} <-> {r['estacion_destino']}: "
            f"dist_geo={r['distancia_geometrica_m']} m | tiempo_nuevo={r['tiempo_nueva_ruta_min']} min | "
            f"paradas={len(r['estaciones_intermedias_lonlat'])}"
        )


if __name__ == "__main__":
    main()
