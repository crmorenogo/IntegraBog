import networkx as nx
from integrabog.graph.macro import construir_grafo_macro
from integrabog.graph.micro import obtener_malla_vial
from integrabog.graph.multilayer import construir_grafo_multicapa

G = construir_grafo_multicapa(construir_grafo_macro(), obtener_malla_vial())
o, d = "macro_4107", "macro_3014"
aristas = [(u, v, k) for u, v, k, a in G.edges(keys=True, data=True)
           if a["layer"] == "micro" or (a["layer"] == "transferencia" and {u, v} & {o, d})]
H = G.edge_subgraph(aristas)
print(f"{nx.shortest_path_length(H, o, d, weight='weight'):.0f} m")