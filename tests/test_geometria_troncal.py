"""
Forma de las aristas del grafo macro (graph/geometria_troncal.py) y su
dibujo en las rutas (network_design._geometria_ruta_lonlat).

Lo que protegen: que el mapa nunca vuelva a unir dos estaciones con una
recta que pase por encima de manzanas. Cada arista de la red troncal tiene
que traer su recorrido por el trazado, orientado y del mismo largo que su
peso, y la ruta dibujada tiene que medir lo mismo que la ruta calculada.
"""
import math

import networkx as nx
import pytest
from shapely.geometry import LineString

from integrabog.graph.geometria_troncal import a_linea, tramo_entre, unir_tramos
from integrabog.graph.macro import construir_grafo_macro
from integrabog.routing.network_design import _TRANSFORMADOR, _geometria_ruta_lonlat

# --- Utilidades ----------------------------------------------------------------------

L_EN_L = LineString([(0, 0), (100, 0), (100, 100)])  # una "L" de 200 m


def test_tramo_entre_sigue_la_curva_en_los_dos_sentidos():
    ida = tramo_entre(L_EN_L, 50, 150)
    assert ida == [(50, 0), (100, 0), (100, 50)]
    assert tramo_entre(L_EN_L, 150, 50) == ida[::-1]


def test_unir_tramos_quita_el_punto_repetido_y_deja_el_salto_como_recta():
    assert unir_tramos([(0, 0), (1, 0)], [(1, 0), (2, 0)], [(2, 5)]) == [(0, 0), (1, 0), (2, 0), (2, 5)]


def test_a_linea_con_un_solo_punto_usa_la_recta_de_respaldo():
    linea = a_linea([(3, 3)], ((0, 0), (1, 1)))
    assert linea.is_valid and list(linea.coords) == [(0, 0), (1, 1)]


# --- Datos oficiales -----------------------------------------------------------------

@pytest.fixture(scope="module")
def macro():
    return construir_grafo_macro()


def _nodo(G, nombre):
    encontrados = [n for n, d in G.nodes(data=True) if d["nombre"] == nombre]
    if not encontrados:
        pytest.skip(f"'{nombre}' no está en los datos de estaciones")
    return encontrados[0]


def _posicion(G, n):
    return G.nodes[n]["x"], G.nodes[n]["y"]


def test_toda_arista_macro_trae_su_forma_del_mismo_largo_que_su_peso(macro):
    for u, v, d in macro.edges(data=True):
        geom = d.get("geometry")
        assert isinstance(geom, LineString) and geom.is_valid, (u, v, d.get("tipo"))
        assert geom.length == pytest.approx(d["weight"], abs=0.01), (u, v, d.get("tipo"))


def test_la_forma_va_de_u_a_v_y_la_inversa_es_la_misma_al_reves(macro):
    for u, v, d in macro.edges(data=True):
        inicio = d["geometry"].coords[0]
        assert math.dist(inicio, _posicion(macro, u)) <= math.dist(inicio, _posicion(macro, v))
        assert list(macro[v][u]["geometry"].coords) == list(d["geometry"].coords)[::-1]


def test_la_costura_de_tintal_sigue_el_giro_y_no_corta_en_diagonal(macro):
    tintal, tv86 = _nodo(macro, "Biblioteca Tintal"), _nodo(macro, "Transversal 86")
    geom = macro[tintal][tv86]["geometry"]
    recta = math.dist(_posicion(macro, tintal), _posicion(macro, tv86))
    assert geom.length > 1.2 * recta  # 1.223 m por el trazado contra ~890 m en recta
    assert len(geom.coords) > 2


def test_las_estaciones_con_nombre_repetido_tienen_etiqueta_distinta(macro):
    etiquetas = [d["etiqueta"] for _, d in macro.nodes(data=True)]
    assert len(set(etiquetas)) == len(etiquetas)
    jimenez = sorted(d["etiqueta"] for _, d in macro.nodes(data=True)
                     if d["nombre"] == "Temporal AV. Jiménez - Inter Eléctricas")
    if len(jimenez) == 2:
        assert jimenez[0] != jimenez[1] and all("(" in e for e in jimenez)


# --- Dibujo de la ruta ---------------------------------------------------------------

def test_ruta_dibujada_mide_lo_mismo_que_la_calculada(macro):
    """Portal Américas -> Banderas por la troncal (pasa por la costura de Tintal). El largo
     dibujado = suma de pesos + los dos tramos cortos de cada estación extrema al trazado.
     Si se intercalara el punto de cada estación intermedia, saldría más largo (picos)."""
    G = nx.MultiDiGraph()
    G.add_nodes_from(macro.nodes(data=True))
    for u, v, d in macro.edges(data=True):
        G.add_edge(u, v, **d, layer="macro")
    origen, destino = _nodo(macro, "Portal Américas"), _nodo(macro, "Banderas")
    camino = nx.shortest_path(macro, origen, destino, weight="weight")
    peso_total = sum(macro[a][b]["weight"] for a, b in zip(camino[:-1], camino[1:]))

    coords_lonlat = _geometria_ruta_lonlat(G, camino)
    xs, ys = _TRANSFORMADOR.transform(*zip(*coords_lonlat), direction="INVERSE")
    dibujada = LineString(list(zip(xs, ys))).length

    primera = macro[camino[0]][camino[1]]["geometry"].coords[0]
    ultima = macro[camino[-2]][camino[-1]]["geometry"].coords[-1]
    accesos = math.dist(_posicion(macro, origen), primera) + math.dist(_posicion(macro, destino), ultima)
    assert dibujada == pytest.approx(peso_total + accesos, abs=2.0)  # 2 m: redondeo de lon/lat a 6 decimales
