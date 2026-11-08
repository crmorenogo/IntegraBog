"""
Robustez de la red troncal (routing/robustez.py).

Primero, redes con respuesta conocida: una línea, un anillo, dos triángulos
unidos por un puente y dos grafos completos unidos por una estación, que
cumplen la desigualdad de Whitney de forma estricta. Después, los conteos de
pares que dependen de una sola estación o de un solo enlace (que salen de los
bloques, sin cerrar nada) contra la fuerza bruta: cerrar cada estación y cada
enlace y mirar qué pares se separan, en grafos al azar. Al final, la red real.
"""
import itertools
import json
import math
import random
import sys

import networkx as nx
import pytest

from integrabog.graph.macro import construir_grafo_macro
from integrabog.routing.metricas import en_orden, peso
from integrabog.routing.robustez import (
    _aristas,
    _distancias,
    cierres,
    eficiencia_global,
    enlaces,
    estructura,
    grafo_de_enlaces,
    intermediacion,
    robustez_red,
)


def _red(conexiones, metros=1000.0):
    """Grafo dirigido simétrico como el macro. Cada conexión es (u, v) o (u, v, metros[, tipo])."""
    G = nx.DiGraph()
    for u, v, *resto in conexiones:
        datos = {"weight": float(resto[0]) if resto else metros}
        if len(resto) > 1:
            datos["tipo"] = resto[1]
        G.add_edge(u, v, **datos)
        G.add_edge(v, u, **datos)
    return G


# --- Estructura: redes con respuesta conocida ------------------------------------------

def test_en_una_linea_todo_es_critico():
    """1 - 2 - 3 - 4 - 5: un árbol (μ = 0). Las estaciones del medio son puntos de corte y
     todos los enlaces son puentes. De los 10 pares, solo los 4 de estaciones vecinas no
     dependen de una tercera estación; de un solo enlace dependen todos."""
    e = estructura(_red([(1, 2), (2, 3), (3, 4), (4, 5)]))
    assert (e.estaciones, e.enlaces, e.componentes, e.ciclomatico) == (5, 4, 1, 0)
    assert e.puntos_de_corte == (2, 3, 4)
    assert e.puentes == ((1, 2), (2, 3), (3, 4), (4, 5))
    assert (e.bloques, e.bloque_mayor) == (4, 2)
    assert (e.conectividad_vertices, e.conectividad_aristas, e.grado_minimo) == (1, 1, 1)
    assert (e.pares_conectados, e.pares_dependen_estacion, e.pares_dependen_enlace) == (10, 6, 10)


def test_un_anillo_no_tiene_puntos_debiles():
    e = estructura(_red([(k, k % 6 + 1) for k in range(1, 7)]))
    assert e.ciclomatico == 1 and e.puntos_de_corte == () and e.puentes == ()
    assert (e.bloques, e.bloque_mayor) == (1, 6)
    assert (e.conectividad_vertices, e.conectividad_aristas, e.grado_minimo) == (2, 2, 2)
    assert e.pares_dependen_estacion == e.pares_dependen_enlace == 0


#   1 - 2       5 - 6
#    \ /         \ /
#     3 --------- 4
def test_dos_triangulos_unidos_por_un_puente():
    e = estructura(_red([(1, 2), (2, 3), (3, 1), (3, 4), (4, 5), (5, 6), (6, 4)]))
    assert e.puntos_de_corte == (3, 4) and e.puentes == ((3, 4),)
    assert (e.bloques, e.bloque_mayor, e.ciclomatico) == (3, 3, 2)
    assert (e.conectividad_vertices, e.conectividad_aristas, e.grado_minimo) == (1, 1, 2)
    """cerrar 3 separa {1, 2} de {4, 5, 6} y cerrar 4 separa {1, 2, 3} de {5, 6}: son los 9 pares
     de un triángulo con el otro, menos 3-4, que no depende de ninguna otra estación"""
    assert e.pares_dependen_estacion == 8
    assert e.pares_dependen_enlace == 9


def test_whitney_con_igualdad_en_un_grafo_completo():
    e = estructura(_red([(a, b) for a, b in itertools.combinations(range(1, 6), 2)]))
    assert (e.conectividad_vertices, e.conectividad_aristas, e.grado_minimo) == (4, 4, 4)
    assert e.ciclomatico == 10 - 5 + 1


def test_whitney_puede_ser_estricta():
    """Dos K4 unidos por dos enlaces que salen de la misma estación (1): cerrar 1 los separa
     (κ = 1), pero hacen falta dos enlaces (λ = 2), y toda estación tiene al menos 3 (δ = 3)."""
    k4_a, k4_b = itertools.combinations(range(1, 5), 2), itertools.combinations(range(5, 9), 2)
    e = estructura(_red([*k4_a, *k4_b, (1, 5), (1, 6)]))
    assert (e.conectividad_vertices, e.conectividad_aristas, e.grado_minimo) == (1, 2, 3)
    assert e.puntos_de_corte == (1,) and e.puentes == ()


def test_una_red_con_un_sentido_unico_no_se_analiza():
    G = _red([(1, 2), (2, 3)])
    G.remove_edge(3, 2)
    with pytest.raises(ValueError, match="dos sentidos"):
        estructura(G)
    with pytest.raises(ValueError, match="dos sentidos"):
        cierres(G)


# --- Los conteos de pares contra la fuerza bruta -------------------------------------------

def _fuerza_bruta(H: nx.Graph):
    """Cierra cada estación y cada enlace, y mira qué pares pierden su camino."""
    conectados = {p for p in itertools.combinations(H.nodes, 2) if nx.has_path(H, *p)}
    por_estacion, por_enlace, corte, puentes = set(), set(), set(), set()
    for x in H.nodes:
        K = H.subgraph(n for n in H if n != x)
        separados = {p for p in conectados if x not in p and not nx.has_path(K, *p)}
        por_estacion |= separados
        if separados:
            corte.add(x)
    for a, b in H.edges:
        K = H.copy()
        K.remove_edge(a, b)
        separados = {p for p in conectados if not nx.has_path(K, *p)}
        por_enlace |= separados
        if separados:
            puentes.add(frozenset((a, b)))
    return len(conectados), len(por_estacion), len(por_enlace), corte, puentes


@pytest.mark.parametrize("semilla", range(30))
def test_los_pares_que_dependen_de_un_elemento_salen_de_los_bloques(semilla):
    rng = random.Random(semilla)
    n = rng.randint(4, 12)
    H = nx.gnm_random_graph(n, rng.randint(n - 2, 2 * n), seed=semilla)
    G = _red(list(H.edges()))
    G.add_nodes_from(H.nodes)  # también estaciones aisladas: sus pares no cuentan como conectados
    e = estructura(G)
    conectados, por_estacion, por_enlace, corte, puentes = _fuerza_bruta(H)
    assert (e.pares_conectados, e.pares_dependen_estacion, e.pares_dependen_enlace) == (
        conectados, por_estacion, por_enlace)
    assert set(e.puntos_de_corte) == corte
    assert {frozenset(p) for p in e.puentes} == puentes
    assert e.ciclomatico == e.enlaces - e.estaciones + e.componentes
    assert e.conectividad_vertices <= e.conectividad_aristas <= e.grado_minimo


# --- Desempeño: intermediación, eficiencia y cierres ---------------------------------------

def test_cerrar_una_estacion_de_una_linea():
    """1 - 2 - 3 - 4, por tramos. Cerrar 2 deja a 1 sola: se pierden {1, 3} y {1, 4}, y queda
     solo 3-4. Eficiencia de {1, 3, 4} antes: 2 (1/2 + 1/3 + 1) / 6 = 11/18; después: 2/6.
     Cerrar la punta (1) no le hace nada al resto."""
    estaciones, _ = cierres(_red([(1, 2), (2, 3), (3, 4)]), "tramos")
    por = {c.elemento: c for c in estaciones}
    assert (por[2].pares_desconectados, por[2].pares_alargados) == (2, 0)
    assert por[2].perdida_eficiencia == pytest.approx(1 - (2 / 6) / (11 / 18))
    assert (por[1].pares_desconectados, por[1].perdida_eficiencia) == (0, pytest.approx(0))


def test_cerrar_un_enlace_de_una_linea_separa_los_dos_lados():
    _, de_enlaces = cierres(_red([(1, 2), (2, 3), (3, 4)]), "tramos")
    por = {c.elemento: c for c in de_enlaces}
    assert por[(2, 3)].pares_desconectados == 2 * 2
    assert por[(1, 2)].pares_desconectados == 1 * 3


def test_cerrar_un_enlace_de_un_anillo_alarga_un_solo_viaje():
    """Anillo 1-2-3-4, por tramos. Cerrar 1-2 obliga a ir de 1 a 2 por la otra mitad (de 1 a 3
     tramos); los demás pares tienen otro camino igual de corto. Eficiencia antes: cada estación
     ve dos a 1 tramo y una a 2, 4 (1 + 1 + 1/2) / 12 = 10/12; después, 2 (1/3 + 1/2 + 1 + 1 +
     1/2 + 1) / 12 = (26/3) / 12."""
    _, de_enlaces = cierres(_red([(1, 2), (2, 3), (3, 4), (4, 1)]), "tramos")
    c = {c.elemento: c for c in de_enlaces}[(1, 2)]
    assert (c.pares_desconectados, c.pares_alargados, c.aumento_medio) == (0, 1, 2)
    assert c.perdida_eficiencia == pytest.approx(1 - (26 / 3) / 10)


def test_los_cierres_salen_del_mas_al_menos_danino():
    estaciones, de_enlaces = cierres(_red([(1, 2), (2, 3), (3, 4), (4, 5), (5, 3)]), "tramos")
    for lista in (estaciones, de_enlaces):
        perdidas = [c.perdida_eficiencia for c in lista]
        assert perdidas == sorted(perdidas, reverse=True)
    assert estaciones[0].elemento == 3  # el punto de corte que deja a 1 y 2 sin el anillo


#   a ---1 km (cruce)--- x ---1 km--- b
#    \                               /
#     -1,5 km--- y ---1,5 km--------
def test_la_intermediacion_sigue_los_pesos_del_criterio():
    """Por distancia, de a a b conviene ir por x (2 km contra 3); por tiempo, el transbordo del
     cruce a-x (5 min) hace que convenga y."""
    G = _red([("a", "x", 1000, "cruce"), ("x", "b", 1000), ("a", "y", 1500), ("y", "b", 1500)])
    por_distancia, por_tiempo = intermediacion(G, "distancia"), intermediacion(G, "tiempo", 5.0)
    assert por_distancia["x"] > por_distancia["y"]
    assert por_tiempo["y"] > por_tiempo["x"]


def test_la_eficiencia_es_el_promedio_de_los_inversos():
    G = _red([(1, 2, 1000), (2, 3, 2500), (3, 4, 700), (4, 1, 4000), (2, 4, 3100, "cruce")])
    for criterio in ("tiempo", "distancia", "tramos"):
        largos = dict(nx.all_pairs_dijkstra_path_length(G, weight=peso(criterio)))
        esperada = sum(1 / largos[u][v] for u in G for v in G if u != v) / (4 * 3)
        assert eficiencia_global(G, criterio) == pytest.approx(esperada)


def test_los_enlaces_se_cuentan_una_vez_en_orden_de_codigo():
    assert enlaces(_red([(3, 1), (2, 3), (1, 2)])) == [(1, 2), (1, 3), (2, 3)]


# --- La red real ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def macro():
    return construir_grafo_macro()


@pytest.fixture(scope="module")
def robustez(macro):
    return robustez_red(macro)


def test_la_red_real_cumple_whitney_y_la_formula_ciclomatica(robustez):
    e = robustez.estructura
    assert e.ciclomatico == e.enlaces - e.estaciones + e.componentes
    assert e.conectividad_vertices <= e.conectividad_aristas <= e.grado_minimo
    assert e.componentes == 1 and e.pares_conectados == math.comb(e.estaciones, 2)
    assert e.ciclomatico > 0 and e.bloque_mayor > 2  # hay un núcleo con ciclos


def test_un_cierre_desconecta_pares_si_y_solo_si_es_punto_de_corte_o_puente(robustez):
    e = robustez.estructura
    assert {c.elemento for c in robustez.cierres_estaciones if c.pares_desconectados} == set(e.puntos_de_corte)
    assert {c.elemento for c in robustez.cierres_enlaces if c.pares_desconectados} == set(e.puentes)
    assert len(robustez.cierres_estaciones) == e.estaciones and len(robustez.cierres_enlaces) == e.enlaces


def test_un_puente_separa_el_producto_de_sus_dos_lados(macro, robustez):
    H = grafo_de_enlaces(macro)
    for c in robustez.cierres_enlaces:
        if c.pares_desconectados:
            K = H.copy()
            K.remove_edge(*c.elemento)
            lado = len(nx.node_connected_component(K, c.elemento[0]))
            assert c.pares_desconectados == lado * (H.number_of_nodes() - lado)


def test_las_distancias_de_scipy_son_las_de_networkx(macro):
    nodos = en_orden(macro)
    D = _distancias(len(nodos), *_aristas(macro, nodos, "tiempo", 5.0))
    largos = dict(nx.all_pairs_dijkstra_path_length(macro, weight=peso("tiempo", 5.0)))
    assert all(D[i, j] == pytest.approx(largos[u][v]) for i, u in enumerate(nodos) for j, v in enumerate(nodos))


def test_los_codigos_quedan_como_las_claves_de_la_red(macro, robustez):
    """Algunos códigos llegan como numpy.int64 por las aristas; lo que se reporta es siempre la
     clave del nodo (para que se pueda escribir en JSON)."""
    claves = {v: type(v) for v in macro.nodes}
    e = robustez.estructura
    assert all(type(v) is claves[v] for v in e.puntos_de_corte)
    assert all(type(u) is claves[u] and type(v) is claves[v] for u, v in e.puentes)


def test_el_script_deja_los_cuatro_archivos(macro, robustez, tmp_path, monkeypatch):
    from integrabog.scripts import robustez_red as script
    monkeypatch.setattr(sys, "argv", ["robustez_red", "--salida", str(tmp_path), "--top", "3"])
    script.main()
    e = robustez.estructura
    datos = json.loads((tmp_path / "robustez_red.geojson").read_text(encoding="utf-8"))
    tipos = [f["geometry"]["type"] for f in datos["features"]]
    assert tipos.count("Point") == e.estaciones and tipos.count("LineString") == e.enlaces
    assert sum(f["properties"].get("puente") is True for f in datos["features"]) == len(e.puentes)
    assert len((tmp_path / "estaciones.csv").read_text(encoding="utf-8-sig").splitlines()) == e.estaciones + 1
    assert len((tmp_path / "enlaces.csv").read_text(encoding="utf-8-sig").splitlines()) == e.enlaces + 1
    resumen = (tmp_path / "robustez_red.md").read_text(encoding="utf-8")
    assert "## Estructura" in resumen and "cuyo cierre más daña la red" in resumen
