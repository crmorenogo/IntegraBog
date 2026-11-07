"""
Giros prohibidos de Overture (graph/giros.py): cómo se leen las reglas,
cómo se pegan a la malla al construirla (micro.py), y que la ruta de una
troncal nueva (network_design.ruta_nueva) no los tome.

Malla de prueba, en el formato de Overture y por City2Graph de verdad
(una cuadrícula de 3 x 3 con el cruce del caso real en el centro):

    NW ---- N1 ---- NE         y = 400      Calle norte
    |       |       |
    W1 ---- J ----- E1         y = 0        Av. Calle 153 (dibujada de E1 a W1)
    |       |       |
    SW ---- S1 ---- SE         y = -400     Calle sur
  x=-400   x=0    x=400

    Av. Carrera 72: de S1 a N1 por J (dibujada hacia el norte); bordes
    oeste y este: carreras secundarias. Todo de doble sentido.

Regla principal: llegando por la Calle 153 hacia el occidente (sentido de
dibujo), en J no se puede girar a la Av. Carrera 72 hacia el sur (en contra
del dibujo). Es el giro a la izquierda del caso Toberín -> San Mateo.
"""
import json
import math

import geopandas as gpd
import networkx as nx
import pytest
from shapely.geometry import LineString, Point

from integrabog.graph.giros import (
    ATRIBUTO_GIROS,
    angulo_de_giro,
    camino_respetando_giros,
    continuaciones,
    giros_en_u,
    giros_prohibidos_en,
    rumbos,
    segmento_de,
)
from integrabog.graph.micro import construir_malla_desde_overture
from integrabog.routing.network_design import (
    _geometria_ruta_lonlat,
    calcular_costo_brt,
    ruta_nueva,
    sugerir_nueva_troncal,
)

# --- La búsqueda, sobre grafos armados a mano -------------------------------------------

def _peso(u, v, d):
    return d["w"]


def _grafo(*aristas):
    """aristas: (u, v, overture_id, peso[, reversed])."""
    G = nx.MultiDiGraph()
    for u, v, pieza, w, *rev in aristas:
        G.add_edge(u, v, overture_id=pieza, reversed=bool(rev and rev[0]), w=w)
    return G


def _prohibir(G, u, v, *continuaciones_prohibidas, clave=0):
    G[u][v][clave][ATRIBUTO_GIROS] = json.dumps([[list(paso) for paso in c] for c in continuaciones_prohibidas])


#   S -> C, y en C: izquierda a W (corta), recto a N, derecha a E; de N se llega a W por NW
def _cruz():
    return _grafo(("S", "C", "sc", 1), ("C", "W", "cw", 1), ("C", "N", "cn", 1), ("N", "NW", "nnw", 1),
                  ("NW", "W", "nww", 1), ("C", "E", "ce", 1))


def test_sin_reglas_es_el_dijkstra_de_siempre():
    G = _cruz()
    assert camino_respetando_giros(G, "S", "W", _peso) == (["S", "C", "W"], [0, 0], 2.0)
    assert camino_respetando_giros(G, "S", "W", _peso)[0] == nx.shortest_path(G, "S", "W", weight="w")


def test_un_giro_prohibido_obliga_a_dar_la_vuelta():
    G = _cruz()
    _prohibir(G, "S", "C", [("cw", False)])
    assert camino_respetando_giros(G, "S", "W", _peso) == (["S", "C", "N", "NW", "W"], [0, 0, 0, 0], 4.0)
    """la regla es solo para quien llega por S -> C: quien ya está en C puede tomar C -> W"""
    assert camino_respetando_giros(G, "C", "W", _peso)[0] == ["C", "W"]


def test_la_regla_mira_el_sentido_de_la_pieza():
    """(pieza, reversed): la misma pieza recorrida al revés es otra arista, y la regla no la toca."""
    G = _cruz()
    G.add_edge("W", "C", overture_id="cw", reversed=True, w=1)
    G.add_edge("W", "X", overture_id="wx", reversed=False, w=1)
    _prohibir(G, "S", "C", [("cw", True)])  # prohíbe C -> W solo si fuera "cw" al revés: no existe así
    assert camino_respetando_giros(G, "S", "X", _peso)[0] == ["S", "C", "W", "X"]


def test_una_secuencia_de_varios_pasos_solo_prohibe_el_recorrido_completo():
    """Como un giro en U por un cruce del separador: S -> C -> N -> NW prohibido entero; cada
     tramo suelto sí se puede."""
    G = _cruz()
    _prohibir(G, "S", "C", [("cn", False), ("nnw", False)])
    assert camino_respetando_giros(G, "S", "N", _peso)[0] == ["S", "C", "N"]
    with pytest.raises(nx.NetworkXNoPath):
        camino_respetando_giros(G, "S", "NW", _peso)
    assert camino_respetando_giros(G, "C", "NW", _peso)[0] == ["C", "N", "NW"]


def test_si_la_unica_salida_es_prohibida_no_hay_ruta():
    G = _cruz()
    _prohibir(G, "S", "C", [("cw", False)], [("cn", False)])
    with pytest.raises(nx.NetworkXNoPath):
        camino_respetando_giros(G, "S", "W", _peso)
    with pytest.raises(nx.NodeNotFound):
        camino_respetando_giros(G, "S", "no-existe", _peso)


def test_entre_piezas_paralelas_toma_la_permitida_y_devuelve_su_clave():
    """Dos piezas distintas entre los mismos dos conectores (una calzada y su carril de giro):
     la ruta tiene que decir cuál usó, porque la más barata es justo la prohibida."""
    G = _grafo(("A", "B", "ab", 1), ("B", "C", "directa", 1), ("B", "C", "carril", 3))
    _prohibir(G, "A", "B", [("directa", False)])
    assert camino_respetando_giros(G, "A", "C", _peso) == (["A", "B", "C"], [0, 1], 4.0)


def test_revisar_un_camino_dice_en_que_arista_esta_el_giro():
    G = _cruz()
    _prohibir(G, "S", "C", [("cn", False), ("nnw", False)])
    camino = [G["S"]["C"][0], G["C"]["N"][0], G["N"]["NW"][0], G["NW"]["W"][0]]
    assert giros_prohibidos_en(camino) == [2]
    assert giros_prohibidos_en(camino[1:]) == []  # sin la arista de llegada no hay giro
    assert giros_prohibidos_en([G["S"]["C"][0], {"layer": "transferencia"}, G["N"]["NW"][0]]) == []


# --- Giros en U: el caso de la corrida real, en miniatura ----------------------------------
#
#            N
#          /   \        anillo de radio 20 m partido en 4 arcos, de doble sentido (como en los
#   X     W     A ---- E0  datos); X: tramo de 10 m al norte de A, de doble sentido
#   |      \   /   calle (de E0 a A, hacia el occidente)
#            B
#            |  salida (de B al sur)
#            S0
#
# Regla: llegando por la calle, no se puede ir de A a B por el anillo y salir al sur (es
# cortar la rotonda al revés). Sin tope de giro, la ruta sube de A a X, da la vuelta en U y
# vuelve a A: ya no "llega por la calle", y la regla no le aplica.

_ANGULO = {"E": 0.0, "N": 90.0, "W": 180.0, "S": 270.0}


def _arco(desde, hasta, radio=20.0, n=16):
    a0, a1 = _ANGULO[desde], _ANGULO[hasta] if _ANGULO[hasta] > _ANGULO[desde] else _ANGULO[hasta] + 360.0
    puntos = [(radio * math.cos(math.radians(a0 + (a1 - a0) * t / n)),
               radio * math.sin(math.radians(a0 + (a1 - a0) * t / n))) for t in range(n + 1)]
    exacto = {"E": (radio, 0.0), "N": (0.0, radio), "W": (-radio, 0.0), "S": (0.0, -radio)}
    puntos[0], puntos[-1] = exacto[desde], exacto[hasta]
    return LineString(puntos)


def _rotonda_con_tramo_corto():
    G = nx.MultiDiGraph()

    def pieza(u, v, pid, geom, doble=True, nombre="Avenida Carrera 72"):
        for a, b, g, rev in ((u, v, geom, False), (v, u, geom.reverse(), True))[:2 if doble else 1]:
            G.add_edge(a, b, overture_id=pid, reversed=rev, geometry=g, length=g.length, name=nombre, layer="micro",
                       **{"class": "trunk"})

    pieza("A", "N", "an", _arco("E", "N"))
    pieza("N", "W", "nw", _arco("N", "W"))
    pieza("W", "B", "wb", _arco("W", "S"))
    pieza("B", "A", "ba", _arco("S", "E"))
    pieza("A", "X", "stub", LineString([(20, 0), (20, 10)]))
    pieza("E0", "A", "calle", LineString([(200, 0), (20, 0)]), doble=False, nombre="Avenida Calle 153")
    pieza("B", "S0", "salida", LineString([(0, -20), (0, -200)]), doble=False)
    _prohibir(G, "E0", "A", [("ba", True), ("salida", False)])  # A -> B (al revés del dibujo) -> sur
    calcular_costo_brt(G)
    return G


def _largo(u, v, d):
    return d["length"]


def test_sin_tope_de_giro_la_ruta_sortea_el_giro_prohibido_con_una_vuelta_en_u():
    G = _rotonda_con_tramo_corto()
    camino, _, _ = camino_respetando_giros(G, "E0", "S0", _largo, giro_maximo_grados=None)
    assert camino == ["E0", "A", "X", "A", "B", "S0"]


def test_con_tope_de_giro_da_la_vuelta_a_la_rotonda():
    G = _rotonda_con_tramo_corto()
    camino, claves, costo = camino_respetando_giros(G, "E0", "S0", _largo)  # tope por defecto: 150°
    assert camino == ["E0", "A", "N", "W", "B", "S0"]  # antihorario, como se recorre una rotonda
    aristas = [G.edges[u, v, k] for u, v, k in zip(camino[:-1], camino[1:], claves)]
    assert giros_en_u(aristas) == [] and giros_prohibidos_en(aristas) == []


def test_angulo_de_giro():
    assert angulo_de_giro(0, 0) == 0
    assert angulo_de_giro(180, -180) == 0
    assert angulo_de_giro(90, 0) == 90
    assert angulo_de_giro(10, -170) == 180
    assert angulo_de_giro(170, -170) == 20  # cruza los ±180°


def test_un_giro_en_v_entre_piezas_distintas_tampoco():
    """No solo devolverse por la misma pieza: pasar a otra que sale casi de vuelta (160°) es
     igual de imposible para un biarticulado; un giro de 120° sí se permite."""
    G = nx.MultiDiGraph()
    for u, v, pid, coords in (("P", "Q", "pq", [(0, 0), (100, 0)]),
                              ("Q", "R", "qr", [(100, 0), (100 - 94.0, 34.2)]),   # sale a 160°
                              ("Q", "T", "qt", [(100, 0), (150, 80)]),
                              ("T", "R", "tr", [(150, 80), (6.0, 34.2)])):
        G.add_edge(u, v, overture_id=pid, reversed=False, geometry=LineString(coords))
    peso = lambda u, v, d: d["geometry"].length  # noqa: E731
    assert camino_respetando_giros(G, "P", "R", peso, giro_maximo_grados=None)[0] == ["P", "Q", "R"]
    assert camino_respetando_giros(G, "P", "R", peso)[0] == ["P", "Q", "T", "R"]
    assert camino_respetando_giros(G, "P", "R", peso, giro_maximo_grados=170)[0] == ["P", "Q", "R"]


def test_el_diagnostico_marca_la_vuelta_en_u_con_el_mismo_tope():
    from integrabog.scripts.diagnostico_sentido import filas_de_camino
    G = _rotonda_con_tramo_corto()
    filas, _ = filas_de_camino(G, ["E0", "A", "X", "A", "B", "S0"], {}, {}, {}, "antes")
    assert [f["nombre"] for f in filas if "GIRO_EN_U" in f["avisos"]] == ["Avenida Carrera 72"]
    assert [f["orden"] for f in filas if "GIRO_PROHIBIDO_EN_DATOS" in f["avisos"]] == []  # la vuelta lo "borra"


def test_segmento_de_cada_pieza():
    ids = {"cra72", "calle_7"}
    assert segmento_de("cra72_2", ids) == "cra72"
    assert segmento_de("cra72", ids) == "cra72"
    assert segmento_de("calle_7", ids) == "calle_7"  # un id de Overture con sufijo propio y sin partir


# --- Las reglas de Overture, por la construcción completa de la malla ---------------------

BASE = (1_000_000.0, 1_000_000.0)
POS = {"J": (0, 0), "N1": (0, 400), "S1": (0, -400), "E1": (400, 0), "W1": (-400, 0),
       "NW": (-400, 400), "NE": (400, 400), "SW": (-400, -400), "SE": (400, -400)}


def _xy(n):
    return BASE[0] + POS[n][0], BASE[1] + POS[n][1]


def _segmento(sid, nodos, clase, nombre, giros=None):
    linea = LineString([_xy(n) for n in nodos])
    ats = [linea.project(Point(_xy(n)), normalized=True) for n in nodos]
    return {"id": sid, "theme": "transportation", "type": "segment", "version": 0, "subtype": "road",
            "class": clase, "subclass": None, "names": {"primary": nombre, "common": None, "rules": None},
            "connectors": [{"connector_id": n, "at": round(at, 9)} for n, at in zip(nodos, ats)],
            "access_restrictions": None, "speed_limits": None, "road_flags": None, "road_surface": None,
            "prohibited_transitions": giros, "geometry": linea}


def _regla(pasos, final, **cuando):
    regla = {"sequence": [{"connector_id": c, "segment_id": s} for c, s in pasos], "final_heading": final}
    if cuando:
        regla["when"] = cuando
    return regla


REGLAS_CALLE = [
    _regla([("J", "ave")], "backward", heading="forward"),                # la del caso: prohibida para el bus
    _regla([("J", "ave")], "forward", heading="forward", mode=["car"]),   # solo carros: al bus no le aplica
    _regla([("J", "ave")], "forward", heading="forward", during="Mo-Fr 07:00-09:00"),  # por horario: tampoco
    _regla([("N1", "borde_este")], "forward"),                            # N1 no está en la calle: inconsistente
    _regla([("E1", "borde_este")], "forward", heading="forward"),         # a E1 (at=0) no se llega hacia adelante
    _regla([("J", "peatonal")], "forward"),                               # segmento fuera de la malla
    {**_regla([("J", "ave")], "forward"), "between": [0.0, 0.25]},        # J está en 0.5: fuera del tramo
]
REGLAS_AVENIDA = [
    _regla([("J", "calle")], "forward", heading="backward",              # bajando por la avenida, a la calle al
           vehicle=[{"dimension": "weight", "comparison": "greater_than", "value": 10, "unit": "t"}]),  # occidente
]
REGLAS_BORDE_OESTE = [
    # por la Calle 153 de W1 a E1, PASANDO por J sin girar, y al llegar a E1, al norte: prohibido entero
    _regla([("W1", "calle"), ("E1", "borde_este")], "forward", heading="forward"),
]


@pytest.fixture(scope="module")
def malla():
    segmentos = [
        _segmento("ave", ["S1", "J", "N1"], "trunk", "Avenida Carrera 72", REGLAS_AVENIDA),
        _segmento("calle", ["E1", "J", "W1"], "primary", "Avenida Calle 153", REGLAS_CALLE),
        _segmento("borde_sur", ["SW", "S1", "SE"], "secondary", "Calle sur"),
        _segmento("borde_norte", ["NW", "N1", "NE"], "secondary", "Calle norte"),
        _segmento("borde_oeste", ["SW", "W1", "NW"], "secondary", "Carrera oeste", REGLAS_BORDE_OESTE),
        _segmento("borde_este", ["SE", "E1", "NE"], "secondary", "Carrera este"),
    ]
    seg = gpd.GeoDataFrame(segmentos, geometry="geometry", crs="EPSG:3116")
    con = gpd.GeoDataFrame({"id": list(POS)}, geometry=[Point(_xy(n)) for n in POS], crs="EPSG:3116")
    return construir_malla_desde_overture(seg, con)


def _arista(G, pieza, al_reves=False):
    encontradas = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True)
                   if d["overture_id"] == pieza and bool(d["reversed"]) == al_reves]
    assert len(encontradas) == 1, (pieza, al_reves, encontradas)
    return encontradas[0]


def _giros(G, pieza, al_reves=False):
    return continuaciones(G.edges[_arista(G, pieza, al_reves)])


def test_la_regla_del_caso_queda_en_la_arista_por_la_que_se_llega(malla):
    """calle_1 es la pieza de E1 a J (la Calle 153 hacia el occidente); ave_1 la de S1 a J,
     que hacia el sur se recorre al revés del dibujo."""
    assert _giros(malla, "calle_1") == ((("ave_1", True),),)


def test_reglas_que_no_le_aplican_al_bus_no_se_pegan(malla):
    """La de solo carros, la de horario y la de otro tramo salen de la misma arista de llegada
     que la del caso: si se pegaran, saldría también ave_2 (hacia el norte) como prohibida."""
    assert ("ave_2", False) not in {paso for c in _giros(malla, "calle_1") for paso in c}
    assert _giros(malla, "ave_1") == ()  # nada sale de la avenida subiendo


def test_una_regla_por_peso_si_le_aplica_al_biarticulado(malla):
    """Bajando por la avenida (ave_2 al revés: de N1 a J), prohibido girar a la calle hacia el
     occidente a más de 10 t. El bus de referencia pesa 40 t."""
    assert _giros(malla, "ave_2", al_reves=True) == ((("calle_2", False),),)


def test_una_secuencia_que_pasa_por_un_cruce_sin_girar(malla):
    """De W1 a E1 por la Calle 153 son dos piezas (pasa por J): la continuación tiene las dos,
     y después la del giro prohibido al norte en E1."""
    assert _giros(malla, "borde_oeste_1") == ((("calle_2", True), ("calle_1", True), ("borde_este_2", False)),)


def test_el_informe_de_la_construccion(malla, capsys):
    """Se reconstruye para capturar lo que imprime la construcción."""
    segmentos = [_segmento("calle", ["E1", "J", "W1"], "primary", "Avenida Calle 153", REGLAS_CALLE),
                 _segmento("ave", ["S1", "J", "N1"], "trunk", "Avenida Carrera 72"),
                 _segmento("borde_sur", ["SW", "S1", "SE"], "secondary", "Calle sur"),
                 _segmento("borde_norte", ["NW", "N1", "NE"], "secondary", "Calle norte"),
                 _segmento("borde_oeste", ["SW", "W1", "NW"], "secondary", "Carrera oeste"),
                 _segmento("borde_este", ["SE", "E1", "NE"], "secondary", "Carrera este")]
    construir_malla_desde_overture(
        gpd.GeoDataFrame(segmentos, geometry="geometry", crs="EPSG:3116"),
        gpd.GeoDataFrame({"id": list(POS)}, geometry=[Point(_xy(n)) for n in POS], crs="EPSG:3116"))
    salida = capsys.readouterr().out
    assert ("Giros prohibidos de Overture: 7 reglas | aplicadas al bus: 1 (desde 1 aristas de llegada) | "
            "fuera de la malla podada: 1 | no le aplican al bus: 3") in salida
    assert "fuera del tramo ('between')" in salida and "inconsistentes: 2" in salida


def _metros_secundarias_al_doble(u, v, d):
    return d["length"] * (2.0 if d["class"] == "secondary" else 1.0)


def test_la_ruta_no_toma_el_giro_prohibido(malla):
    sin_reglas = malla.copy()
    for *_, d in sin_reglas.edges(data=True):
        d.pop(ATRIBUTO_GIROS, None)
    assert camino_respetando_giros(sin_reglas, "E1", "S1", _metros_secundarias_al_doble)[0] == ["E1", "J", "S1"]

    camino, claves, costo = camino_respetando_giros(malla, "E1", "S1", _metros_secundarias_al_doble)
    assert camino == ["E1", "SE", "S1"] and costo == pytest.approx(1600.0)
    assert giros_prohibidos_en([malla.edges[u, v, k] for u, v, k in zip(camino[:-1], camino[1:], claves)]) == []
    """quien llega a J por el otro lado (de W1, hacia el oriente) sí puede bajar: es giro a la derecha"""
    assert camino_respetando_giros(malla, "W1", "S1", _metros_secundarias_al_doble)[0] == ["W1", "J", "S1"]


def test_los_giros_sobreviven_a_la_cache(malla, tmp_path, monkeypatch):
    """La malla se guarda en GeoParquet y se recarga en cada arranque: si el atributo se
     perdiera ahí, la API volvería a tomar giros prohibidos sin ningún error."""
    import integrabog.graph.micro as micro
    monkeypatch.setattr(micro, "RUTA_MALLA_PROCESADA", tmp_path / "malla")
    micro._guardar_malla_procesada(malla, {"prueba": True}, {"release": "prueba"})
    recargada = micro._cargar_malla_procesada({"prueba": True})
    antes = {(d["overture_id"], d["reversed"]): (d.get(ATRIBUTO_GIROS), rumbos(d)) for *_, d in malla.edges(data=True)}
    despues = {(d["overture_id"], bool(d["reversed"])): (d.get(ATRIBUTO_GIROS), rumbos(d))
               for *_, d in recargada.edges(data=True)}
    assert despues == antes
    assert sum(1 for t, _ in despues.values() if t) == 3
    assert all(d.get("rumbo_inicial") is not None for *_, d in recargada.edges(data=True))  # guardados, no recalculados


def test_cada_arista_de_la_malla_trae_su_rumbo(malla):
    """calle_1 va de E1 a J: hacia el occidente (180°); ave_1 al revés, de J a S1: al sur (-90°)."""
    datos = malla.edges[_arista(malla, "calle_1")]
    assert abs(abs(datos["rumbo_inicial"]) - 180) < 1e-6 and abs(abs(datos["rumbo_final"]) - 180) < 1e-6
    assert malla.edges[_arista(malla, "ave_1", al_reves=True)]["rumbo_inicial"] == pytest.approx(-90.0)


# --- La ruta de una troncal nueva (network_design) ----------------------------------------

@pytest.fixture()
def multicapa(malla):
    """La malla con dos estaciones: origen junto a E1 y destino junto a S1. Los bordes pasan de
     'secondary' a 'primary': desde nov-2026 una troncal nueva no puede ir por secundarias
     (config.CLASES_APTAS_TRONCAL), y aquí el rodeo legal va por ellos. Sigue siendo más caro
     que el giro prohibido (primary x1,15 en los dos tramos contra primary + trunk)."""
    G = nx.MultiDiGraph(crs="EPSG:3116")
    G.add_nodes_from((n, {**d, "layer": "micro"}) for n, d in malla.nodes(data=True))
    G.add_edges_from((u, v, k, {**d, "layer": "micro", "class": "primary" if d["class"] == "secondary" else d["class"]})
                     for u, v, k, d in malla.edges(keys=True, data=True))
    for estacion, cruce in (("o", "E1"), ("d", "S1")):
        x, y = malla.nodes[cruce]["x"] + 30, malla.nodes[cruce]["y"]
        G.add_node(estacion, x=x, y=y, layer="macro", etiqueta=estacion)
        G.add_edge(estacion, cruce, layer="transferencia", weight=30.0)
        G.add_edge(cruce, estacion, layer="transferencia", weight=30.0)
    calcular_costo_brt(G)
    return G


def test_la_troncal_nueva_rodea_el_giro_prohibido(multicapa):
    """Por costo BRT, Calle 153 + avenida (primary + trunk) es lo más barato, pero ese giro está
     prohibido: la ruta baja por la Carrera este y la Calle sur."""
    camino, claves, minutos = ruta_nueva(multicapa, "o", "d")
    assert camino == ["o", "E1", "SE", "S1", "d"]
    assert len(claves) == len(camino) - 1
    sin_giros = nx.shortest_path(multicapa, "o", "d", weight=lambda u, v, d: min(
        a.get("tiempo_brt_min", a.get("weight", 0) / 1000 / 4.5 * 60) for a in d.values()))
    assert sin_giros == ["o", "E1", "J", "S1", "d"]  # lo que hacía el modelo antes

    resultado = sugerir_nueva_troncal(multicapa, "o", "d")
    assert resultado["tiempo_nueva_ruta_min"] == pytest.approx(round(minutos, 2))
    assert resultado["geometria_lonlat"] == _geometria_ruta_lonlat(multicapa, camino, claves)


def test_el_diagnostico_marca_el_giro_exacto(multicapa):
    from integrabog.scripts.diagnostico_sentido import filas_de_camino
    filas, _ = filas_de_camino(multicapa, ["o", "E1", "J", "S1", "d"], {}, {}, {}, "antes")
    marcadas = [(f["viene_de"], f["nombre"]) for f in filas if "GIRO_PROHIBIDO_EN_DATOS" in f["avisos"]]
    assert marcadas == [("Avenida Calle 153", "Avenida Carrera 72")]
    filas, _ = filas_de_camino(multicapa, ["o", "E1", "SE", "S1", "d"], {}, {}, {}, "modelo")
    assert not any("GIRO_PROHIBIDO_EN_DATOS" in f["avisos"] for f in filas)
