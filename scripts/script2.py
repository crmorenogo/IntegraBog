import networkx as nx
from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa
from integrabog.routing.network_design import _TRANSFORMADOR

G = construir_grafo_multicapa(construir_grafo_macro(), obtener_malla_vial())
o, d = "macro_4107", "macro_3014"
aristas = [(u, v, k) for u, v, k, a in G.edges(keys=True, data=True)
           if a["layer"] == "micro" or (a["layer"] == "transferencia" and {u, v} & {o, d})]
H = G.edge_subgraph(aristas)

dirigido = nx.shortest_path_length(H, o, d, weight="weight")
sin_sentidos = nx.shortest_path_length(H.to_undirected(as_view=True), o, d, weight="weight")
print(f"Respetando sentidos: {dirigido:.0f} m | ignorando sentidos: {sin_sentidos:.0f} m")

camino = nx.shortest_path(H, o, d, weight="weight")
print("\nPegar en https://geojson.io (como LineString):")
coords = [list(_TRANSFORMADOR.transform(G.nodes[n]["x"], G.nodes[n]["y"])) for n in camino]
print({"type": "LineString", "coordinates": [[round(x, 6), round(y, 6)] for x, y in coords]})

print("\nTramos de un solo sentido usados en la ruta:")
for u, v in zip(camino[:-1], camino[1:]):
    a = min(G.get_edge_data(u, v).values(), key=lambda e: e["weight"])
    if a.get("oneway"):
        print(f"  {a.get('name') or 'sin nombre'} ({a.get('class')}) {a['weight']:.0f} m")