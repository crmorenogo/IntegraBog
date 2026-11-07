"""
Orquesta la construcción del grafo multicapa: recalcula el macro (rápido,
es solo procesar 150 estaciones locales) y carga el micro desde caché,
los combina, y reporta estadísticas de validación.

El bloque de comparación de Soacha que aparece al final se coloco porque
es la prueba de que el fix de incluir Soacha en la descarga de OSMnx (micro.py)
sigue funcionando. Si algún día alguien cambia el 'lugar' de vuelta a
"Bogotá, Colombia" a secas, o revierte el fix por accidente, este
bloque lo va a volver a mostrar con los mismos números malos que
tuvierón antes de arreglarlo (San Mateo a 1.616 m, etc.).
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

    """solo aristas 'macro_' del lado origen -- cada estación tiene su transferencia
     contada una vez desde su propio nodo, no hace falta mirar las del lado micro también"""
    pesos = [d["weight"] for u, v, d in G_multicapa.edges(data=True)
             if d.get("layer") == "transferencia" and str(u).startswith("macro_")]
    arr = np.array(pesos)
    print(f"n={len(arr)} | min={arr.min():.1f} m | mediana={np.median(arr):.1f} m | "
          f"p90={np.percentile(arr, 90):.1f} m | max={arr.max():.1f} m")

    """ estos numeros son los que dio la corrida ANTES de agregar Soacha a la descarga --
     quedan fijos acá a propósito, como punto de referencia, no se recalculan"""
    antes = {"San Mateo - CC Unisur": 1616.3, "Terreros - Hospital Cardio Vascular": 1182.6,
             "León XIII": 699.3, "La Despensa": 316.2, "Portal Américas": 188.4}

    print("\nLas 5 que estaban mal antes de incluir Soacha, antes vs ahora:")
    for u, v, d in G_multicapa.edges(data=True):
        if d.get("layer") != "transferencia" or not str(u).startswith("macro_"):
            continue
        nombre = G_multicapa.nodes[u].get("nombre", "")
        if nombre in antes:
            print(f"  {nombre}: {antes[nombre]:.1f} m -> {d['weight']:.1f} m")

    peores = sorted(
        ((d["weight"], u) for u, v, d in G_multicapa.edges(data=True)
         if d.get("layer") == "transferencia" and str(u).startswith("macro_")),
        reverse=True
    )[:5]
    print("\nLas 5 estaciones más lejos AHORA:")
    for peso, nodo in peores:
        nombre = G_multicapa.nodes[nodo]['nombre']
        """tipo_estacion viene en el print para poder confirmar a ojo si las peores
         siguen siendo portales (tipo 1) -- si empieza a aparecer una estación
         sencilla acá, es señal de un problema real de cobertura, no del patrón
         ya conocido de que los portales quedan más lejos por ser complejos grandes"""
        tipo = G_multicapa.nodes[nodo].get('tipo_estacion', 'Desconocido')
        print(f"  {nombre}: {peso:.1f} m (tipo_estacion={tipo})")

    return G_multicapa


if __name__ == "__main__":
    main()