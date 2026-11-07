"""
Orquesta la construcción del grafo multicapa: recalcula el macro (rápido,
es solo procesar 150 estaciones locales) y carga el micro desde caché,
los combina, y reporta estadísticas de validación.

El bloque de comparación de Soacha que aparece al final se coloco porque
es la prueba de que la malla vial cubre Soacha. Con OSMnx eso dependía de
pedir "Soacha, Colombia" además de Bogotá en la descarga; con Overture
depende de que AREA_ESTUDIO_BBOX (config.py) la incluya. Si algún día
alguien recorta el área por accidente, este bloque lo va a volver a
mostrar con números malos como los que hubo antes del arreglo (San Mateo
a 1.616 m, etc.). Esos valores "antes" se quedan fijos como referencia:
salieron de la malla OSM.

Desde que cada estación se engancha a varios conectores (uno por calzada,
ver multilayer.py), una estación tiene más de una arista de transferencia.
Las estadísticas de este bloque miran solo la MÁS CERCANA de cada una --
la distancia que de verdad dice si la estación tiene calle cerca --, para
que los números sigan siendo comparables con los de antes del cambio. El
número de enganches se reporta aparte.
"""
from collections import Counter

from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.graph.diagnostico import diagnosticar_grafo


def main():
    print("Construyendo grafo macro (TransMilenio)...")
    G_macro = construir_grafo_macro()

    print("\nCargando grafo micro (malla vial) desde caché...")
    G_micro = obtener_malla_vial()

    print("\nFusionando en grafo multicapa...")
    G_multicapa = construir_grafo_multicapa(G_macro, G_micro)

    print("\n--- RESUMEN DEL GRAFO MULTICAPA ---")
    diagnosticar_grafo(G_multicapa)

    conteo_capas = Counter(d.get("layer") for _, _, d in G_multicapa.edges(data=True))
    print(f"Aristas por capa: {dict(conteo_capas)}")

    print("\n--- DIAGNÓSTICO COMPARATIVO SOACHA (ANTES VS AHORA) ---")
    import numpy as np

    """solo aristas 'macro_' del lado origen (la de vuelta tiene el mismo peso), y de cada
     estación solo su enganche más cercano: los adicionales existen para alcanzar la otra
     calzada, no dicen nada sobre si la estación tiene calle cerca"""
    enganches = {}
    for u, v, d in G_multicapa.edges(data=True):
        if d.get("layer") == "transferencia" and str(u).startswith("macro_"):
            enganches.setdefault(u, []).append(d["weight"])
    mas_cercano = {u: min(pesos) for u, pesos in enganches.items()}

    arr = np.array(list(mas_cercano.values()))
    print(f"Enganche más cercano por estación: n={len(arr)} | min={arr.min():.1f} m | "
          f"mediana={np.median(arr):.1f} m | p90={np.percentile(arr, 90):.1f} m | max={arr.max():.1f} m")
    por_estacion = Counter(len(p) for p in enganches.values())
    print(f"Enganches por estación: {dict(sorted(por_estacion.items()))} "
          f"(total {sum(len(p) for p in enganches.values())} aristas de ida)")

    """ estos numeros son los que dio la corrida ANTES de agregar Soacha a la descarga --
     quedan fijos acá a propósito, como punto de referencia, no se recalculan"""
    antes = {"San Mateo - CC Unisur": 1616.3, "Terreros - Hospital Cardio Vascular": 1182.6,
             "León XIII": 699.3, "La Despensa": 316.2, "Portal Américas": 188.4}

    print("\nLas 5 que estaban mal antes de incluir Soacha, antes vs ahora:")
    for nodo, peso in mas_cercano.items():
        nombre = G_multicapa.nodes[nodo].get("nombre", "")
        if nombre in antes:
            print(f"  {nombre}: {antes[nombre]:.1f} m -> {peso:.1f} m")

    peores = sorted(((peso, nodo) for nodo, peso in mas_cercano.items()), reverse=True)[:5]
    print("\nLas 5 estaciones más lejos AHORA:")
    for peso, nodo in peores:
        nombre = G_multicapa.nodes[nodo]['nombre']
        """tipo_estacion viene en el print para poder confirmar a ojo si las peores
         siguen siendo portales (tipo 1) -- si empieza a aparecer una estación
         sencilla acá, es señal de un problema real de cobertura, no del patrón
         ya conocido de que los portales quedan más lejos por ser complejos grandes"""
        tipo = G_multicapa.nodes[nodo].get('tipo_estacion', 'Desconocido')
        print(f"  {nombre}: {peso:.1f} m (tipo_estacion={tipo}, {len(enganches[nodo])} enganches)")

    return G_multicapa


if __name__ == "__main__":
    main()