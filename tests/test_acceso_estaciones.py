"""
Enganche de estaciones a la malla vial (multilayer._aristas_transferencia).

Reproduce en miniatura el caso Escuela Militar <-> San Martín: dos
estaciones en el separador de una avenida de doble calzada, donde cada
calzada es de un solo sentido. Con un único enganche la estación de origen
queda amarrada a la calzada que va en sentido contrario y la ruta tiene que
llegar hasta el retorno y volver; con el enganche múltiple sale directo por
la calzada correcta.

Geometría (EPSG:3116, metros), avenida en sentido oeste-este:

    calzada norte (solo hacia el oeste)   N0 <- N1 <- N2 <- N3        y = 1030
    estaciones en el separador            A (x=1000)    B (x=1300)   y = 1015
    calzada sur   (solo hacia el este)    S0 -> S1 -> S2 -> S3        y = 1000

A está 1 m más cerca de la calzada norte, así que su conector más cercano
es N1, que solo lleva hacia el oeste -- alejándose de B. El retorno está
2 km al oeste.
"""
import networkx as nx
import pytest
from shapely.geometry import LineString

from integrabog.config import MARGEN_ACCESO_M, RADIO_ACCESO_MAX_M
from integrabog.graph.multilayer import construir_grafo_multicapa


def _malla_doble_calzada() -> nx.MultiDiGraph:
    G = nx.MultiDiGraph(crs="EPSG:3116")
    xs = {0: -1000.0, 1: 1000.0, 2: 1300.0, 3: 3000.0}
    for i, x in xs.items():
        G.add_node(f"N{i}", x=x, y=1030.0)
        G.add_node(f"S{i}", x=x, y=1000.0)

    def via(u, v):
        a, b = G.nodes[u], G.nodes[v]
        geom = LineString([(a["x"], a["y"]), (b["x"], b["y"])])
        G.add_edge(u, v, length=geom.length, weight=geom.length, geometry=geom,
                   **{"class": "trunk"}, oneway=True)

    for i in (3, 2, 1):
        via(f"N{i}", f"N{i - 1}")  # calzada norte: hacia el oeste
    for i in (0, 1, 2):
        via(f"S{i}", f"S{i + 1}")  # calzada sur: hacia el este
    via("N0", "S0")  # retornos en los extremos
    via("S3", "N3")
    return G


def _macro() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node(1, x=1000.0, y=1016.0, nombre="A", num_est="1", tipo_estacion=4, id_trazado="T")
    G.add_node(2, x=1300.0, y=1014.0, nombre="B", num_est="2", tipo_estacion=4, id_trazado="T")
    G.add_edge(1, 2, weight=300.0, layer="macro")
    G.add_edge(2, 1, weight=300.0, layer="macro")
    return G


def _distancia_por_malla(G, origen, destino) -> float:
    aristas = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True)
               if d["layer"] == "micro" or (d["layer"] == "transferencia" and {u, v} & {origen, destino})]
    return nx.shortest_path_length(G.edge_subgraph(aristas), origen, destino, weight="weight")


@pytest.fixture(scope="module")
def multicapa():
    return construir_grafo_multicapa(_macro(), _malla_doble_calzada())


def test_estacion_en_separador_queda_enganchada_a_las_dos_calzadas(multicapa):
    destinos = {v for _, v, d in multicapa.out_edges("macro_1", data=True) if d["layer"] == "transferencia"}
    assert {"micro_N1", "micro_S1"} <= destinos


def test_el_mas_cercano_va_primero_y_cada_enganche_tiene_su_inverso(multicapa):
    vecinos = [v for _, v, d in multicapa.out_edges("macro_1", data=True) if d["layer"] == "transferencia"]
    assert vecinos[0] == "micro_N1"
    for v in vecinos:
        ida = multicapa["macro_1"][v][0]["weight"]
        assert multicapa[v]["macro_1"][0]["weight"] == ida


def test_ruta_entre_estaciones_del_separador_no_da_la_vuelta(multicapa):
    """Con k=1 serían ~4.600 m (hasta el retorno oeste y de vuelta); con el
    enganche múltiple: 15 m de caminata + 300 m de calzada + 14 m."""
    assert _distancia_por_malla(multicapa, "macro_1", "macro_2") < 400


def test_calles_lejanas_no_se_enganchan():
    """Un conector a más de MARGEN_ACCESO_M por encima del más cercano no se usa,
    aunque esté dentro de RADIO_ACCESO_MAX_M."""
    micro = _malla_doble_calzada()
    lejos = 1016.0 + 14.0 + MARGEN_ACCESO_M + 20.0
    assert lejos - 1016.0 < RADIO_ACCESO_MAX_M
    micro.add_node("L", x=1000.0, y=lejos)
    G = construir_grafo_multicapa(_macro(), micro)
    assert "micro_L" not in G["macro_1"]
