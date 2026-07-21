import numpy as np

pesos = [d["weight"] for u, v, d in G_multicapa.edges(data=True)
         if d.get("layer") == "transferencia" and u.startswith("macro_")]
arr = np.array(pesos)
print(f"n={len(arr)} | min={arr.min():.1f} m | mediana={np.median(arr):.1f} m | "
      f"p90={np.percentile(arr, 90):.1f} m | max={arr.max():.1f} m")

antes = {"San Mateo - CC Unisur": 1616.3, "Terreros - Hospital Cardio Vascular": 1182.6,
         "León XIII": 699.3, "La Despensa": 316.2, "Portal Américas": 188.4}
print("\nLas 5 que estaban mal antes de incluir Soacha, antes vs ahora:")
for u, v, d in G_multicapa.edges(data=True):
    if d.get("layer") != "transferencia" or not u.startswith("macro_"):
        continue
    nombre = G_multicapa.nodes[u].get("nombre", "")
    if nombre in antes:
        print(f"  {nombre}: {antes[nombre]:.1f} m -> {d['weight']:.1f} m")

peores = sorted(
    ((d["weight"], u) for u, v, d in G_multicapa.edges(data=True)
     if d.get("layer") == "transferencia" and u.startswith("macro_")),
    reverse=True
)[:5]
print("\nLas 5 estaciones más lejos AHORA:")
for peso, nodo in peores:
    print(f"  {G_multicapa.nodes[nodo]['nombre']}: {peso:.1f} m")