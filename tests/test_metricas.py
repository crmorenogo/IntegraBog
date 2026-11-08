"""
Métricas de la red troncal (routing/metricas.py): excentricidad, diámetro,
radio, centro y periferia.

Primero, redes armadas a mano donde la respuesta se sabe de antemano: una
línea, un anillo y dos troncales unidas por un cruce, en la que el costo del
transbordo cambia el par más alejado (como pasa en la red real: Terminal ↔
San Mateo por distancia, Portal Suba ↔ San Mateo por tiempo). Después, la red
real, comparada contra las funciones de networkx y contra la desigualdad
r <= D <= 2r de los grafos simétricos.
"""
import json
import math
import sys

import networkx as nx
import pytest
from shapely.geometry import LineString

from integrabog.graph.macro import construir_grafo_macro
from integrabog.routing.metricas import (
    CRITERIOS,
    geometria_camino_lonlat,
    metricas_red,
    peso,
    punto_lonlat,
    resumen_camino,
)
from integrabog.routing.network_design import VELOCIDAD_BRT_KMH

ORIGEN = (1_000_000.0, 1_000_000.0)  # metros, EPSG:3116


def _red(aristas, posiciones=None, troncal=None):
    """Grafo dirigido simétrico como el macro: aristas (u, v, metros[, tipo]); cada una con su
     forma (una recta entre las dos estaciones si se dan posiciones)."""
    G = nx.DiGraph()
    for u, v, metros, *tipo in aristas:
        for a, b in ((u, v), (v, u)):
            datos = {"weight": float(metros)}
            if tipo:
                datos["tipo"] = tipo[0]
            if posiciones:
                datos["geometry"] = LineString([posiciones[a], posiciones[b]])
            G.add_edge(a, b, **datos)
    for n in G.nodes:
        if posiciones:
            G.nodes[n].update(x=posiciones[n][0], y=posiciones[n][1])
        if troncal:
            G.nodes[n]["troncal"] = troncal(n)
    return G


def _minutos(km):
    return km / VELOCIDAD_BRT_KMH * 60


# --- Redes con respuesta conocida -----------------------------------------------------

def test_una_linea():
    """1 - 2 - 3 - 4 - 5: el centro es la del medio y la periferia, las puntas."""
    G = _red([(1, 2, 1000), (2, 3, 1000), (3, 4, 1000), (4, 5, 1000)])
    m = metricas_red(G, "tramos")
    assert m.excentricidad == {1: 4, 2: 3, 3: 2, 4: 3, 5: 4}
    assert (m.diametro, m.radio, m.centro, m.periferia) == (4, 2, (3,), (1, 5))
    assert m.par_diametro == (1, 5) and m.camino_diametro == (1, 2, 3, 4, 5)
    assert m.pares_diametro_sin_orden() == [(1, 5)]
    assert metricas_red(G, "distancia").diametro == pytest.approx(4.0)        # km
    assert metricas_red(G, "tiempo").diametro == pytest.approx(_minutos(4.0))  # min, sin cruces


def test_un_anillo_es_todo_centro_y_todo_periferia():
    """En un ciclo de 6 todas las estaciones tienen excentricidad 3: D = r, y el diámetro lo
     alcanzan los 3 pares de estaciones opuestas."""
    G = _red([(k, k % 6 + 1, 500) for k in range(1, 7)])
    m = metricas_red(G, "tramos")
    assert m.diametro == m.radio == 3
    assert m.centro == m.periferia == (1, 2, 3, 4, 5, 6)
    assert m.pares_diametro_sin_orden() == [(1, 4), (2, 5), (3, 6)]


#   troncal T: 1 ---10 km--- 2 ---10 km--- 3
#                            |
#                          1 km (cruce: transbordo)
#                            |
#   troncal S:     4 ---8 km--- 5
def _dos_troncales():
    return _red([(1, 2, 10_000), (2, 3, 10_000), (4, 5, 8_000), (5, 2, 1_000, "cruce")],
                troncal=lambda n: "T" if n in (1, 2, 3) else "S")


def test_sin_transbordo_el_tiempo_es_la_distancia():
    G = _dos_troncales()
    distancia, tiempo = metricas_red(G, "distancia"), metricas_red(G, "tiempo", transbordo_min=0)
    assert distancia.par_diametro == tiempo.par_diametro == (1, 3)
    assert distancia.diametro == pytest.approx(20.0)
    assert tiempo.diametro == pytest.approx(_minutos(20.0))


def test_el_transbordo_cambia_el_par_mas_alejado():
    """1 -> 3 son 20 km sin transbordo; 1 -> 4 son 19 km pero con un transbordo de 5 min. Por
     tiempo gana el segundo, igual que Portal Suba ↔ San Mateo en la red real."""
    m = metricas_red(_dos_troncales(), "tiempo", transbordo_min=5)
    assert m.diametro == pytest.approx(_minutos(19.0) + 5)
    assert m.par_diametro == (1, 4) and m.camino_diametro == (1, 2, 5, 4)
    assert m.pares_diametro_sin_orden() == [(1, 4), (3, 4)]
    assert m.periferia == (1, 3, 4)
    """el centro es el cruce de la troncal T: e(2) = máx(10 km, 9 km + transbordo)"""
    assert m.centro == (2,) and m.radio == pytest.approx(_minutos(9.0) + 5)


def test_resumen_de_un_camino():
    G = _dos_troncales()
    r = resumen_camino(G, (1, 2, 5, 4), transbordo_min=5)
    assert r == {"tramos": 3, "km": pytest.approx(19.0), "minutos": pytest.approx(_minutos(19.0) + 5),
                 "transbordos": 1, "estaciones": 4, "troncales": ["T", "S"]}


def test_en_un_grafo_dirigido_cuenta_el_sentido():
    """Un ciclo de un solo sentido a -> b -> c -> a: de a a c hay que dar la vuelta."""
    G = nx.DiGraph()
    G.add_edges_from([("a", "b"), ("b", "c"), ("c", "a")], weight=1000.0)
    m = metricas_red(G, "tramos")
    assert m.excentricidad == {"a": 2, "b": 2, "c": 2}
    assert m.pares_diametro_sin_orden() == [("a", "c"), ("b", "a"), ("c", "b")]


def test_si_una_estacion_no_llega_a_todas_el_diametro_es_infinito():
    G = nx.DiGraph()
    G.add_edge("a", "b", weight=1000.0)  # de b no se vuelve
    m = metricas_red(G, "tramos")
    assert m.excentricidad == {"a": 1, "b": math.inf}
    assert m.diametro == math.inf and m.pares_sin_camino == 1
    assert (m.radio, m.centro, m.periferia) == (1, ("a",), ("b",))


def _cuadricula():
    return _red([((i, j), (i + di, j + dj), 300 + 97 * ((3 * i + 5 * j + di) % 7), *(["cruce"] if (i + j) % 3 == 0 else []))
                 for i in range(5) for j in range(5) for di, dj in ((1, 0), (0, 1)) if i + di < 5 and j + dj < 5])


def test_igual_que_networkx_en_una_cuadricula_con_pesos_distintos():
    """Mismas excentricidades, diámetro y radio que networkx. Centro y periferia se comparan con
     la misma tolerancia que usa el módulo (ver la prueba siguiente)."""
    G = _cuadricula()
    for criterio in CRITERIOS:
        m, w = metricas_red(G, criterio), peso(criterio)
        excentricidad = nx.eccentricity(G, weight=w)
        assert all(m.excentricidad[v] == pytest.approx(excentricidad[v]) for v in G)
        assert m.diametro == pytest.approx(nx.diameter(G, weight=w))
        assert m.radio == pytest.approx(nx.radius(G, weight=w))
        assert set(m.centro) == {v for v in G if excentricidad[v] == pytest.approx(m.radio)}
        assert set(m.periferia) == {v for v in G if excentricidad[v] == pytest.approx(m.diametro)}


def test_la_media_es_el_viaje_tipico():
    """En la línea 1 - 2 - 3 - 4 - 5, por tramos: los 10 pares suman 1·4 + 2·3 + 3·2 + 4·1 = 20,
     así que la media es 2. Desde la punta, (1 + 2 + 3 + 4) / 4 = 2,5; desde el medio, 1,5."""
    G = _red([(1, 2, 1000), (2, 3, 1000), (3, 4, 1000), (4, 5, 1000)])
    m = metricas_red(G, "tramos")
    assert m.media == pytest.approx(2.0)
    assert (m.media_desde[1], m.media_desde[3]) == (pytest.approx(2.5), pytest.approx(1.5))


def test_la_media_es_la_de_networkx():
    G = _cuadricula()
    for criterio in CRITERIOS:
        w = peso(criterio)
        assert metricas_red(G, criterio).media == pytest.approx(nx.average_shortest_path_length(G, weight=w))


def test_los_empates_se_comparan_con_tolerancia():
    """Por distancia, (0, 0) y (0, 4) tienen la misma excentricidad: 3,661 km exactos (sumas de
     metros enteros). Pero sumando en otro orden, el punto flotante da 3,6610000000000005 y
     3,6609999999999996, y nx.periphery, que compara con igualdad exacta, deja por fuera a
     (0, 4) y (4, 0). El módulo los toma como iguales (metricas.TOLERANCIA)."""
    G = _cuadricula()
    m = metricas_red(G, "distancia")
    assert m.excentricidad[(0, 0)] != m.excentricidad[(0, 4)]  # el ruido del punto flotante
    assert m.excentricidad[(0, 0)] == pytest.approx(m.excentricidad[(0, 4)], abs=1e-12)
    assert m.periferia == ((0, 0), (0, 4), (4, 0), (4, 4))
    assert set(nx.periphery(G, weight=peso("distancia"))) == {(0, 0), (4, 4)}


def test_el_camino_se_dibuja_por_la_forma_de_cada_arista():
    posiciones = {1: ORIGEN, 2: (ORIGEN[0] + 1000, ORIGEN[1]), 3: (ORIGEN[0] + 1000, ORIGEN[1] + 500)}
    G = _red([(1, 2, 1000), (2, 3, 500)], posiciones)
    linea = geometria_camino_lonlat(G, (1, 2, 3))
    assert len(linea) == 3  # el punto compartido de dos aristas seguidas no se repite
    assert linea[0] == punto_lonlat(G, 1) and linea[-1] == punto_lonlat(G, 3)


# --- La red real -----------------------------------------------------------------------

@pytest.fixture(scope="module")
def macro():
    return construir_grafo_macro()


@pytest.fixture(scope="module")
def metricas(macro):
    return {criterio: metricas_red(macro, criterio) for criterio in CRITERIOS}


def test_la_red_real_es_fuertemente_conexa_y_cumple_r_d_2r(macro, metricas):
    assert nx.is_strongly_connected(macro)
    for m in metricas.values():
        assert m.pares_sin_camino == 0
        assert m.radio <= m.diametro <= 2 * m.radio


def test_la_red_real_coincide_con_networkx(macro, metricas):
    for criterio, m in metricas.items():
        excentricidad = nx.eccentricity(macro, weight=peso(criterio))
        assert all(m.excentricidad[v] == pytest.approx(excentricidad[v]) for v in macro)


def test_el_camino_del_diametro_mide_el_diametro(macro, metricas):
    for criterio, m in metricas.items():
        w = peso(criterio)
        largo = sum(w(u, v, macro[u][v]) for u, v in zip(m.camino_diametro[:-1], m.camino_diametro[1:]))
        assert largo == pytest.approx(m.diametro)
        assert all(u in m.periferia and v in m.periferia for u, v in m.pares_diametro)


def test_cobrar_el_transbordo_no_puede_acortar_el_diametro(macro):
    sin, con = metricas_red(macro, "tiempo", transbordo_min=0), metricas_red(macro, "tiempo", transbordo_min=5)
    assert con.diametro >= sin.diametro
    assert sin.par_diametro == metricas_red(macro, "distancia").par_diametro  # sin transbordo, tiempo = distancia


def test_el_script_deja_los_tres_archivos(macro, tmp_path, monkeypatch):
    from integrabog.scripts import metricas_red as script
    monkeypatch.setattr(sys, "argv", ["metricas_red", "--salida", str(tmp_path)])
    script.main()
    datos = json.loads((tmp_path / "metricas_red.geojson").read_text(encoding="utf-8"))
    tipos = [f["geometry"]["type"] for f in datos["features"]]
    assert tipos.count("LineString") == 3 and tipos.count("Point") == macro.number_of_nodes()
    filas = (tmp_path / "excentricidades.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(filas) == macro.number_of_nodes() + 1
    resumen = (tmp_path / "metricas_red.md").read_text(encoding="utf-8")
    assert "## Resumen" in resumen and "## Excentricidad por estación" in resumen


# --- La app cobra el mismo transbordo --------------------------------------------------
#
#              t1                 hoy, de o a d por la red troncal: por t1 (3 km, con un
#            /    \ (cruce)       transbordo en el cruce t1-d) o por t2 (4,5 km, sin
#   o ------+      +------ d      transbordo). Ruta nueva posible: una vía primaria de A a C.
#            \    /
#              t2

def _app(con_t2=True):
    from integrabog.routing.network_design import calcular_costo_brt
    pos = {"o": (0, 0), "d": (3000, 0), "t1": (1500, 300), "t2": (1500, -1200), "A": (50, 0), "C": (2950, 0)}
    G = nx.MultiDiGraph(crs="EPSG:3116")
    for n in ("o", "d", "t1", "t2"):
        G.add_node(n, x=pos[n][0] + ORIGEN[0], y=pos[n][1] + ORIGEN[1], layer="macro", etiqueta=n)
    for n in ("A", "C"):
        G.add_node(n, x=pos[n][0] + ORIGEN[0], y=pos[n][1] + ORIGEN[1], layer="micro")
    xy = {n: (pos[n][0] + ORIGEN[0], pos[n][1] + ORIGEN[1]) for n in pos}

    def arista(u, v, capa, metros, **extra):
        for a, b in ((u, v), (v, u)):
            G.add_edge(a, b, layer=capa, weight=float(metros), geometry=LineString([xy[a], xy[b]]), **extra)

    arista("o", "t1", "macro", 2000)
    arista("t1", "d", "macro", 1000, tipo="cruce")
    if con_t2:
        arista("o", "t2", "macro", 2250)
        arista("t2", "d", "macro", 2250)
    arista("A", "C", "micro", 2900, length=2900.0, **{"class": "primary"}, apta_troncal=True)
    arista("o", "A", "transferencia", 50)
    arista("d", "C", "transferencia", 50)
    calcular_costo_brt(G)
    return G


def test_la_ruta_actual_de_la_app_cobra_el_transbordo():
    from integrabog.routing.network_design import sugerir_nueva_troncal
    r = sugerir_nueva_troncal(_app(con_t2=False), "o", "d")
    assert r["tiempo_actual_min"] == pytest.approx(round(_minutos(3.0) + 5, 2))
    assert (r["transbordos_actuales"], r["transbordo_min"]) == (1, 5.0)


def test_el_transbordo_puede_cambiar_la_ruta_actual():
    """Sin cobrarlo, el camino corto (por t1, 3 km) ganaba; cobrando 5 min, el de 4,5 km sin
     transbordo sale más rápido (10,7 min contra 12,1)."""
    from integrabog.routing.network_design import _geometria_ruta_lonlat, sugerir_nueva_troncal
    G = _app()
    r = sugerir_nueva_troncal(G, "o", "d")
    assert r["tiempo_actual_min"] == pytest.approx(round(_minutos(4.5), 2)) and r["transbordos_actuales"] == 0
    assert r["geometria_actual_lonlat"] == _geometria_ruta_lonlat(G, ["o", "t2", "d"])


def test_la_app_y_las_metricas_miden_igual_cada_arista(macro):
    """Misma función para la ruta actual de la app y para las métricas: en todas las aristas
     de la red real, con y sin transbordo."""
    from integrabog.routing.network_design import _tiempo_arista
    w = peso("tiempo")
    assert all(w(u, v, d) == _tiempo_arista({**d, "layer": "macro"}) for u, v, d in macro.edges(data=True))
    assert any(d.get("tipo") == "cruce" for *_, d in macro.edges(data=True))
