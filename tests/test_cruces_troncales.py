"""
Aristas de cruce entre troncales (graph/cruces.py) y pares críticos sobre
una red troncal ya conectada (routing/network_design.py).

Las pruebas con datos reales buscan las estaciones por nombre, para que
sigan valiendo cuando se actualicen los archivos de Datos Abiertos.
"""
import geopandas as gpd
import networkx as nx
import pandas as pd
import pytest
from shapely.geometry import LineString

from integrabog.graph.cruces import TIPO_ARISTA_CRUCE, calcular_aristas_cruce
from integrabog.graph.macro import construir_grafo_macro


# --- Cruce en miniatura -------------------------------------------------------------
#
#            N2 (y=+500)
#             |
#   W1 -------+------- E1      troncal X (horizontal), estaciones a 200 m y 300 m del cruce
#  (x=-200)   |      (x=300)
#            S2 (y=-400)       troncal Y (vertical), estaciones a 500 m y 400 m
#
#   y una estación lejana L sobre X, a 2.000 m del cruce.

def _cruce_miniatura():
    tramos = gpd.GeoDataFrame({
        "tramo_id": [0, 1],
        "id_trazado": ["X", "Y"],
        "geometry": [LineString([(-3000, 0), (3000, 0)]), LineString([(0, -1000), (0, 1000)])],
    }, crs="EPSG:3116")
    """'s' es la posición de arco desde el inicio de cada pieza: X empieza en x=-3000, Y en y=-1000"""
    acoples = pd.DataFrame({
        "cod_nodo": [1, 2, 3, 4, 5],
        "tramo_id": [0, 0, 1, 1, 0],
        "s": [2800.0, 3300.0, 1500.0, 600.0, 5000.0],
    })
    G = nx.DiGraph()
    posiciones = {1: (-200, 0), 2: (300, 0), 3: (0, 500), 4: (0, -400), 5: (2000, 0)}
    for n, (x, y) in posiciones.items():
        G.add_node(n, x=float(x), y=float(y))
    return G, tramos, acoples


def test_une_las_vecinas_de_cada_lado_con_peso_por_el_trazado():
    G, tramos, acoples = _cruce_miniatura()
    n = calcular_aristas_cruce(G, tramos, acoples, tolerancia_m=50, distancia_max_m=1200)
    assert n == 4  # {W1, E1} x {N2, S2}
    assert G[1][3]["weight"] == pytest.approx(200 + 500)
    assert G[2][4]["weight"] == pytest.approx(300 + 400)
    assert G[4][2]["weight"] == G[2][4]["weight"]  # en los dos sentidos
    assert G[1][3]["tipo"] == TIPO_ARISTA_CRUCE
    """la forma gira en el cruce (W1 -> cruce -> N2), no va en diagonal de W1 a N2"""
    assert list(G[1][3]["geometry"].coords) == [(-200, 0), (0, 0), (0, 500)]
    assert list(G[3][1]["geometry"].coords) == [(0, 500), (0, 0), (-200, 0)]


def test_no_usa_estaciones_lejos_del_cruce():
    G, tramos, acoples = _cruce_miniatura()
    calcular_aristas_cruce(G, tramos, acoples, tolerancia_m=50, distancia_max_m=1200)
    assert G.degree(5) == 0  # L está a 2.000 m: no es "la estación del cruce"


def test_no_pisa_una_arista_existente():
    G, tramos, acoples = _cruce_miniatura()
    G.add_edge(1, 3, weight=123.0, tipo="costura")
    G.add_edge(3, 1, weight=123.0, tipo="costura")
    n = calcular_aristas_cruce(G, tramos, acoples, tolerancia_m=50, distancia_max_m=1200)
    assert n == 3
    assert G[1][3] == {"weight": 123.0, "tipo": "costura"}


def test_troncales_que_no_se_acercan_no_se_unen():
    G, tramos, acoples = _cruce_miniatura()
    tramos.loc[1, "geometry"] = LineString([(0, 100), (0, 1000)])  # Y ahora termina a 100 m de X
    assert calcular_aristas_cruce(G, tramos, acoples, tolerancia_m=50, distancia_max_m=1200) == 0


# --- Datos oficiales -----------------------------------------------------------------

@pytest.fixture(scope="module")
def macro():
    return construir_grafo_macro()


def _nodo(G, nombre):
    encontrados = [n for n, d in G.nodes(data=True) if d["nombre"] == nombre]
    if not encontrados:
        pytest.skip(f"'{nombre}' no está en los datos de estaciones")
    return encontrados[0]


def test_red_troncal_queda_en_una_sola_pieza(macro):
    assert nx.number_weakly_connected_components(macro) == 1


@pytest.mark.parametrize("a, b", [
    ("Concejo de Bogotá", "AV. ElDorado"),       # Calle 26 x NQS
    ("Centro Memoria", "Calle 26 - Atrio"),      # Calle 26 x Caracas
    ("Escuela Militar", "San Martín"),           # Suba termina contra la Calle 80
    ("Ricaurte - NQS", "Ricaurte - CL 13"),      # NQS x Américas
    ("Biblioteca", "Santa Lucía"),               # Tunal termina contra la Caracas Sur
])
def test_cruces_conocidos_tienen_arista_directa(macro, a, b):
    u, v = _nodo(macro, a), _nodo(macro, b)
    assert macro.has_edge(u, v) and macro.has_edge(v, u)


# --- Pares críticos con la red troncal conectada --------------------------------------

def test_pares_criticos_ordena_por_rodeo_y_pone_primero_los_sin_conexion():
    """Tres estaciones sobre una calle recta: A-B a 300 m en recta pero 3.000 m por la
     troncal (rodeo 10x), B-C a 400 m y conectadas directo (rodeo 1x), y D sin troncal."""
    from integrabog.graph.multilayer import construir_grafo_multicapa
    from integrabog.routing.network_design import calcular_costo_brt, identificar_pares_criticos

    micro = nx.MultiDiGraph(crs="EPSG:3116")
    xs = [0, 300, 700, 1000]
    for i, x in enumerate(xs):
        micro.add_node(f"m{i}", x=float(x), y=0.0)
    for i in range(len(xs) - 1):
        for u, v in ((f"m{i}", f"m{i + 1}"), (f"m{i + 1}", f"m{i}")):
            a, b = micro.nodes[u], micro.nodes[v]
            geom = LineString([(a["x"], 0), (b["x"], 0)])
            micro.add_edge(u, v, length=geom.length, weight=geom.length, geometry=geom, oneway=False,
                           **{"class": "trunk"})

    macro = nx.DiGraph()
    for cod, x, tz in [(1, 0, "T1"), (2, 300, "T2"), (3, 700, "T2"), (4, 1000, "T3")]:
        macro.add_node(cod, x=float(x), y=10.0, nombre=f"E{cod}", num_est=str(cod), tipo_estacion=4, id_trazado=tz)
    for u, v, w in [(1, 2, 3000.0), (2, 3, 400.0)]:
        macro.add_edge(u, v, weight=w)
        macro.add_edge(v, u, weight=w)

    G = construir_grafo_multicapa(macro, micro)
    calcular_costo_brt(G)
    pares = identificar_pares_criticos(G, top_n=5, radio_m=1000)
    claves = [(p["estacion_origen"], p["estacion_destino"], p["factor_rodeo"]) for p in pares]

    assert claves[0][2] is None and "macro_4" in claves[0][:2]  # sin conexión troncal: primero
    assert ("macro_1", "macro_2", 10.0) in claves
    assert all(c[2] is None or c[2] >= 1 for c in claves)


# --- Correcciones manuales (graph/correcciones.py) --------------------------------------

def test_virrey_la_castellana_bloqueada_y_la_castellana_sigue_saliendo_al_norte(macro):
    virrey, castellana = _nodo(macro, "Virrey"), _nodo(macro, "La Castellana")
    assert not macro.has_edge(virrey, castellana) and not macro.has_edge(castellana, virrey)
    calle_100 = _nodo(macro, "Calle 100 - Marketmedios")
    assert macro.has_edge(castellana, calle_100)  # el giro que sí existe sigue en el grafo


def test_ciudad_universitaria_eldorado_se_conserva(macro):
    cu, eldorado = _nodo(macro, "Ciudad Universitaria - Lotería de Bogotá"), _nodo(macro, "AV. ElDorado")
    assert macro.has_edge(cu, eldorado) and macro.has_edge(eldorado, cu)


def test_bloqueo_solo_quita_aristas_inferidas(capsys):
    from integrabog.graph.correcciones import aplicar_conexiones_bloqueadas
    G = nx.DiGraph()
    G.add_node(1, nombre="A")
    G.add_node(2, nombre="B")
    G.add_node(3, nombre="C")
    for u, v, tipo in [(1, 2, "cruce"), (2, 1, "cruce"), (2, 3, None), (3, 2, None)]:
        G.add_edge(u, v, weight=100.0, **({"tipo": tipo} if tipo else {}))

    quitadas = aplicar_conexiones_bloqueadas(G, [(1, 2, "x"), (2, 3, "y"), (2, 99, "z")])

    assert quitadas == ["A <-> B"]
    assert not G.has_edge(1, 2) and not G.has_edge(2, 1)
    assert G.has_edge(2, 3)  # arista del trazado oficial: no se toca
    salida = capsys.readouterr().out
    assert "trazado oficial" in salida and "cod_nodo" in salida  # los dos casos avisan, no fallan en silencio


def test_resolver_estacion_ignora_tildes_y_mayusculas():
    """El archivo oficial dice "Toberin - Foundever" (sin tilde); quien busca escribe "Toberín"."""
    from integrabog.routing.network_design import _resolver_estacion
    G = nx.MultiDiGraph()
    G.add_node("macro_1", layer="macro", nombre="Toberin - Foundever", etiqueta="Toberin - Foundever")
    G.add_node("macro_2", layer="macro", nombre="San Mateo - CC Unisur", etiqueta="San Mateo - CC Unisur")
    assert _resolver_estacion(G, "Toberín") == "macro_1"
    assert _resolver_estacion(G, "TOBERÍN - foundever") == "macro_1"
    assert _resolver_estacion(G, "san mateo") == "macro_2"
