"""
Factibilidad de una troncal nueva sobre la malla vial: restricciones de
Overture para el bus de referencia, superficie, la lista manual de config.py
y la selección de aristas de la ruta (routing.network_design.aristas_ruta_nueva).
"""
import networkx as nx
import pytest
from shapely.geometry import LineString

from integrabog.graph.correcciones import aplicar_vias_no_aptas
from integrabog.graph.micro import _atributos_de_sentido, evaluar_para_bus, superficie_de
from integrabog.routing.network_design import (
    _peso_tiempo,
    aristas_ruta_nueva,
    calcular_costo_brt,
    identificar_pares_criticos,
)

BIARTICULADO = {"length": 27.2, "width": 2.6, "height": 3.5, "weight": 40.0, "axle_count": 4}


def _regla(acceso="denied", **cuando):
    return {"access_type": acceso, "when": {"during": None, "heading": None, "using": None, "recognized": None,
                                            "mode": None, "vehicle": None, **cuando}, "between": None}


def _vehiculo(dimension, comparacion, valor, unidad=None):
    return {"dimension": dimension, "comparison": comparacion, "value": valor, "unit": unidad}


# --- Restricciones para el bus --------------------------------------------------------

@pytest.mark.parametrize("reglas, negado", [
    ([_regla(vehicle=[_vehiculo("height", "greater_than", 4.5, "m")])], False),     # el ejemplo real de Bogotá
    ([_regla(vehicle=[_vehiculo("weight", "greater_than", 10, "t")])], True),
    ([_regla(vehicle=[_vehiculo("weight", "greater_than", 20000, "lb")])], True),   # 9,07 t
    ([_regla(vehicle=[_vehiculo("length", "greater_than", 12, "m")])], True),
    ([_regla(vehicle=[_vehiculo("length", "greater_than", 100, "ft")])], False),    # 30,5 m
    ([_regla(vehicle=[_vehiculo("axle_count", "greater_than_equal", 3)])], True),
    ([_regla(vehicle=[_vehiculo("weight", "greater_than", 10, "quintales")])], False),  # unidad desconocida
    ([_regla(vehicle=[_vehiculo("height", "greater_than", 4, "m"),                  # las dos condiciones
                      _vehiculo("weight", "greater_than", 30, "t")])], False),      # a la vez: no por altura
    ([_regla(mode=["hgv"])], False),                                                # camiones, no buses
    ([_regla(mode=["bus"])], True),
    ([_regla(during="Mo-Fr 06:00-09:00", vehicle=[_vehiculo("weight", "greater_than", 3.5, "t")])], False),
])
def test_restricciones_de_overture_para_el_biarticulado(reglas, negado):
    regla = evaluar_para_bus(reglas, "forward", perfil=BIARTICULADO)
    assert (regla is not None and regla["access_type"] == "denied") == negado


def test_la_ultima_regla_que_aplica_decide_tambien_para_el_bus():
    """"Prohibido a más de 3,5 t, salvo buses": la segunda regla le aplica al bus y decide."""
    reglas = [_regla(vehicle=[_vehiculo("weight", "greater_than", 3.5, "t")]), _regla("allowed", mode=["bus"])]
    assert evaluar_para_bus(reglas, "forward", perfil=BIARTICULADO)["access_type"] == "allowed"


def test_restriccion_por_sentido():
    reglas = [_regla(heading="backward", mode=["bus"])]
    assert evaluar_para_bus(reglas, "forward", perfil=BIARTICULADO) is None
    assert evaluar_para_bus(reglas, "backward", perfil=BIARTICULADO)["access_type"] == "denied"


# --- Superficie y atributos de cada sentido -------------------------------------------

def test_superficie_por_tramo_y_en_forma_global():
    reglas = [{"value": "paved", "between": None}, {"value": "unpaved", "between": [0.6, 1.0]}]
    assert superficie_de(reglas, (0.0, 0.5)) == "paved"
    assert superficie_de(reglas, (0.6, 1.0)) == "unpaved"
    assert superficie_de("gravel") == "gravel"
    assert superficie_de(None) is None


def test_atributos_de_sentido_marcan_el_motivo():
    destapada = _atributos_de_sentido(None, None, "unpaved", "forward", (0.0, 1.0))
    assert not destapada["apta_troncal"] and destapada["motivo_no_apta"] == "superficie: unpaved"
    puente = _atributos_de_sentido([_regla(vehicle=[_vehiculo("weight", "greater_than", 10, "t")])],
                                   None, "paved", "forward", (0.0, 1.0))
    assert not puente["apta_troncal"] and puente["motivo_no_apta"].startswith("restricción para el bus: weight > 10")
    normal = _atributos_de_sentido(None, None, "paved", "forward", (0.0, 1.0))
    assert normal["apta_troncal"] and normal["motivo_no_apta"] is None


# --- Lista manual ---------------------------------------------------------------------

def _malla_con_nombres():
    G = nx.MultiDiGraph()
    for i, (nombre, x) in enumerate([("Avenida Calle 153", 0), ("Avenida Calle 153", 5000), ("Avenida Boyacá", 0)]):
        G.add_edge(f"a{i}", f"b{i}", overture_id=f"seg{i}_{i}", name=nombre, apta_troncal=True,
                   geometry=LineString([(1_000_000 + x, 1_000_000), (1_000_100 + x, 1_000_000)]))
    return G


def test_lista_manual_por_nombre_sin_distinguir_tildes(capsys):
    G = _malla_con_nombres()
    marcadas = aplicar_vias_no_aptas(G, [{"nombre": "avenida calle 153", "motivo": "angosta"},
                                         {"nombre": "Avenida Boyaca", "motivo": "prueba"}])
    assert marcadas == 3
    datos = [d for _, _, d in G.edges(data=True)]
    assert all(not d["apta_troncal"] for d in datos)
    assert datos[0]["motivo_no_apta"] == "lista manual: angosta"


def test_lista_manual_por_id_y_por_zona(capsys):
    G = _malla_con_nombres()
    assert aplicar_vias_no_aptas(G, [{"overture_id": "seg2", "motivo": "x"}]) == 1  # id base, sin el '_2'
    """la zona deja por fuera el tramo de la Calle 153 que está 5 km más allá"""
    from integrabog.graph.correcciones import _A_METRICO
    lon, lat = _A_METRICO.transform(1_000_050, 1_000_000, direction="INVERSE")
    assert aplicar_vias_no_aptas(G, [{"nombre": "Avenida Calle 153", "cerca_de": (lat, lon), "radio_m": 300,
                                      "motivo": "x"}]) == 1


def test_lista_manual_sin_coincidencias_avisa(capsys):
    assert aplicar_vias_no_aptas(_malla_con_nombres(), [{"nombre": "Calle Inventada", "motivo": "x"}]) == 0
    assert "ninguna arista coincide" in capsys.readouterr().out


# --- Selección de aristas de la ruta --------------------------------------------------
#
#   o --- A ===== B ===== C --- d        === avenida 'primary' (apta)
#          \                 /
#           R1 ----- R2 ----             --- calle 'residential': más corta, pero solo
#                                            sirve de acceso cerca de las estaciones

def _red_de_prueba(residencial_apta=True):
    G = nx.MultiDiGraph()
    pos = {"A": (0, 0), "B": (1500, 0), "C": (3000, 0), "R1": (200, -100), "R2": (2800, -100)}
    for n, (x, y) in pos.items():
        G.add_node(n, x=float(x), y=float(y), layer="micro")
    G.add_node("o", x=-50.0, y=0.0, layer="macro", etiqueta="Origen")
    G.add_node("d", x=3050.0, y=0.0, layer="macro", etiqueta="Destino")

    def via(u, v, clase, apta=True):
        for a, b in ((u, v), (v, u)):
            geom = LineString([pos[a], pos[b]])
            G.add_edge(a, b, layer="micro", **{"class": clase}, length=geom.length, weight=geom.length,
                       geometry=geom, apta_troncal=apta)

    via("A", "B", "primary")
    via("B", "C", "primary")
    via("A", "R1", "residential")
    via("R1", "R2", "residential", apta=residencial_apta)  # a más de 300 m de las dos estaciones en su mayoría
    via("R2", "C", "residential")
    for est, nodo in (("o", "A"), ("d", "C")):
        G.add_edge(est, nodo, layer="transferencia", weight=50.0)
        G.add_edge(nodo, est, layer="transferencia", weight=50.0)
    calcular_costo_brt(G)
    return G


def test_la_ruta_de_la_troncal_no_sale_de_las_vias_aptas_salvo_para_llegar():
    G = _red_de_prueba()
    claves = {(u, v) for u, v, _ in aristas_ruta_nueva(G, "o", "d")}
    assert ("A", "B") in claves and ("B", "C") in claves
    assert ("A", "R1") in claves and ("R2", "C") in claves     # tocan el radio de acceso de una estación
    assert ("R1", "R2") not in claves                           # residencial lejos de las dos: no
    camino = nx.shortest_path(G.edge_subgraph(aristas_ruta_nueva(G, "o", "d")), "o", "d", weight=_peso_tiempo)
    assert camino == ["o", "A", "B", "C", "d"]


def test_una_via_marcada_no_apta_no_sirve_ni_de_acceso():
    G = _red_de_prueba()
    G["A"]["B"][0]["apta_troncal"] = False
    G["A"]["B"][0]["motivo_no_apta"] = "lista manual: prueba"
    with pytest.raises(nx.NetworkXNoPath):
        nx.shortest_path(G.edge_subgraph(aristas_ruta_nueva(G, "o", "d")), "o", "d", weight=_peso_tiempo)


def test_pares_criticos_salta_los_pares_sin_ruta_apta():
    """Dos estaciones cercanas sin troncal entre ellas, pero sin ninguna vía apta para unirlas:
     no hay corredor que proponer, y la lista no se cae por eso."""
    G = _red_de_prueba()
    for u, v in (("A", "B"), ("B", "A")):
        G[u][v][0]["apta_troncal"] = False
    G.nodes["o"].update(id_trazado="T1")
    G.nodes["d"].update(id_trazado="T2")
    assert identificar_pares_criticos(G, top_n=5, radio_m=5000) == []
