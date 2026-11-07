"""
Detectores de scripts/diagnostico_sentido.py sobre casos construidos a mano:
una rotonda (bien cargada y sin sentido) y una avenida con separador
donde una calzada perdió su regla de sentido.
"""
import math

import networkx as nx
from shapely.geometry import LineString, Point

from integrabog.scripts.diagnostico_sentido import revisar_calzadas, revisar_rotondas


def _rotonda(sentidos):
    """Anillo de radio 40 m partido en 4 piezas, más 4 brazos de acceso."""
    piezas = {}
    centro = Point(1_000_000, 1_000_000)
    n = 64
    anillo = [(centro.x + 40 * math.cos(2 * math.pi * k / n), centro.y + 40 * math.sin(2 * math.pi * k / n))
              for k in range(n + 1)]
    for i in range(4):
        piezas[f"r{i}"] = {"geometry": LineString(anillo[i * 16:(i + 1) * 16 + 1]), "name": "Glorieta",
                           "class": "primary", "sentidos": set(sentidos)}
        x, y = anillo[i * 16]
        piezas[f"b{i}"] = {"geometry": LineString([(x, y), (centro.x + 3 * (x - centro.x), centro.y + 3 * (y - centro.y))]),
                           "name": f"Brazo {i}", "class": "primary", "sentidos": {"forward", "backward"}}
    return piezas


def test_un_anillo_de_doble_sentido_es_una_cara_redonda_no_una_rotonda(capsys):
    """Sin ninguna pieza de un sentido no hay cómo saber si es una rotonda: se reporta aparte,
     como cara redonda, para revisarla a mano (en Bogotá casi todas son manzanas o parques)."""
    revisar_rotondas(_rotonda({"forward", "backward"}))
    salida = capsys.readouterr().out
    assert "rotondas (borde mayoritariamente de un sentido y antihorario): 0" in salida
    assert "el modelo no las toca): 1, con piezas de doble sentido: 1" in salida


def test_un_anillo_antihorario_de_un_sentido_es_una_rotonda(capsys):
    bordes = revisar_rotondas(_rotonda({"forward"}))  # dibujado antihorario
    assert "antihorario): 1, con piezas de doble sentido: 0" in capsys.readouterr().out
    assert bordes["r0"][1] is True


def _malla_avenida(nombre, sentidos_sur):
    """Dos calzadas paralelas de 'nombre' a 20 m, la norte sin regla; la sur con 'sentidos_sur'.
    La sur se dibuja hacia el oriente: con tránsito por la derecha es la que va al oriente (el
    separador, al norte, le queda a la izquierda), y la norte tendría que ir al occidente."""
    G = nx.MultiDiGraph()
    for pieza, (a, b), sentidos in (("norte", ((0, 20), (300, 20)), ("forward", "backward")),
                                     ("sur", ((0, 0), (300, 0)), sentidos_sur)):
        linea = LineString([a, b])
        for sentido in sentidos:
            geom = linea if sentido == "forward" else linea.reverse()
            u, v = (f"{pieza}-a", f"{pieza}-b") if sentido == "forward" else (f"{pieza}-b", f"{pieza}-a")
            G.add_edge(u, v, overture_id=pieza, name=nombre, **{"class": "trunk"}, geometry=geom,
                       reversed=sentido == "backward", oneway=len(sentidos) == 1)
    return G


def test_avenida_con_las_dos_calzadas_sin_regla_se_reporta_para_confirmarla(capsys):
    motivos = revisar_calzadas(_malla_avenida("Avenida Calle 13", ("forward", "backward")))
    salida = capsys.readouterr().out
    assert motivos == {"norte": "vecina de doble sentido", "sur": "vecina de doble sentido"}
    assert "Avenida Calle 13: 2" in salida and "AVENIDAS_CON_SEPARADOR" in salida


def test_una_calzada_que_se_completaria_en_otra_pasada_se_cuenta_sin_alarma(capsys):
    """Una calzada que la regla completaría sobre la malla final pero que quedó de doble
     sentido. En la corrida real fueron 5 de 2.327 y la caché estaba al día (micro.py la
     regenera si cambia config.py): su vecina cambió después de la pasada de sentido.py. Antes
     el diagnóstico decía que la caché estaba vieja, y no lo estaba."""
    revisar_calzadas(_malla_avenida("Avenida Calle 13", ("forward",)))
    salida = capsys.readouterr().out
    assert "1 se completarían si la regla se corriera otra vez" in salida
    assert "[!]" not in salida


# --- El caso reportado, en miniatura: rotonda sin sentido "cortada" en contravía -------
#
#                N (0, 40)
#        W0 --- W        E --- E0          anillo de radio 40 m, partido en 4 arcos
#                S (0, -40)                 entrada por el sur (S0 -> S), salida al oeste (W -> W0)
#                |
#                S0 (0, -200)
#
# En Colombia la rotonda se recorre en sentido antihorario: S -> E -> N -> W (3/4 de vuelta).
# Sin la regla de sentido, la ruta más corta "corta" S -> W en sentido horario: la contravía.


from integrabog.routing.network_design import calcular_costo_brt  # noqa: E402
from integrabog.scripts.diagnostico_sentido import (  # noqa: E402
    _piezas,
    filas_de_camino,
    negado_en_parte,
    revisar_ruta,
    sentido_alrededor,
    tramo_de_pieza,
)

_ANGULO = {"E": 0, "N": 90, "W": 180, "S": 270}


def _arco(desde, hasta, radio=40.0, n=16):
    """Arco antihorario de 'desde' a 'hasta' (ángulos en grados)."""
    a0, a1 = _ANGULO[desde], _ANGULO[hasta] if _ANGULO[hasta] > _ANGULO[desde] else _ANGULO[hasta] + 360
    puntos = [(radio * math.cos(math.radians(a0 + (a1 - a0) * t / n)),
               radio * math.sin(math.radians(a0 + (a1 - a0) * t / n))) for t in range(n + 1)]
    """extremos exactos (cos/sin dejan -9.8e-15 en vez de 0): en los datos reales cada pieza
     termina justo en su conector, y sin eso el anillo no cierra"""
    exacto = {"E": (radio, 0.0), "N": (0.0, radio), "W": (-radio, 0.0), "S": (0.0, -radio)}
    puntos[0], puntos[-1] = exacto[desde], exacto[hasta]
    return LineString(puntos)


def _rotonda_sin_sentido():
    G = nx.MultiDiGraph(crs="EPSG:3116")
    pos = {"E": (40, 0), "N": (0, 40), "W": (-40, 0), "S": (0, -40), "S0": (0, -200), "W0": (-200, 0), "E0": (200, 0)}
    for n, (x, y) in pos.items():
        G.add_node(n, x=float(x), y=float(y), layer="micro")

    def calle(u, v, geom, nombre, ida_y_vuelta=True):
        base = {"layer": "micro", "class": "primary", "name": nombre, "overture_id": f"{u}-{v}",
                "length": geom.length, "weight": geom.length, "oneway": not ida_y_vuelta}
        G.add_edge(u, v, geometry=geom, reversed=False, **base)
        if ida_y_vuelta:
            G.add_edge(v, u, geometry=geom.reverse(), reversed=True, **base)

    for u, v in [("E", "N"), ("N", "W"), ("W", "S"), ("S", "E")]:
        calle(u, v, _arco(u, v), "Glorieta")  # dibujados antihorario, pero de DOBLE sentido: falta la regla
    calle("S0", "S", LineString([pos["S0"], pos["S"]]), "Calle 153")
    calle("W", "W0", LineString([pos["W"], pos["W0"]]), "Av. Boyacá")
    calle("E", "E0", LineString([pos["E"], pos["E0"]]), "Av. Boyacá")
    """estaciones de origen y destino, enganchadas a los extremos de las vías"""
    G.add_node("o", x=0.0, y=-210.0, layer="macro", etiqueta="Origen")
    G.add_node("d", x=-210.0, y=0.0, layer="macro", etiqueta="Destino")
    for est, cruce in (("o", "S0"), ("d", "W0")):
        G.add_edge(est, cruce, weight=10.0, layer="transferencia")
        G.add_edge(cruce, est, weight=10.0, layer="transferencia")
    calcular_costo_brt(G)
    return G


def _detectar_rotondas(G):
    from integrabog.scripts.diagnostico_sentido import revisar_rotondas
    malla = G.edge_subgraph([(u, v, k) for u, v, k, a in G.edges(keys=True, data=True) if a["layer"] == "micro"])
    return revisar_rotondas(_piezas(malla))


def test_sentido_alrededor_del_centro():
    assert sentido_alrededor(_arco("S", "E"), Point(0, 0)) == "antihorario"
    assert sentido_alrededor(_arco("S", "E").reverse(), Point(0, 0)) == "horario"


def test_la_ruta_corta_la_rotonda_en_contravia_y_el_diagnostico_lo_marca(capsys):
    G = _rotonda_sin_sentido()
    rotondas = _detectar_rotondas(G)
    assert set(rotondas) == {"E-N", "N-W", "W-S", "S-E"}

    camino, _ = revisar_ruta(G, {}, rotondas, {}, "o", "d")
    assert camino == ["o", "S0", "S", "W", "W0", "d"]  # S -> W: un cuarto de vuelta, en sentido horario
    """sin ninguna pieza de un sentido el anillo no se reconoce como rotonda (podría ser una
     manzana redonda): se avisa como cara redonda recorrida en sentido horario, para revisarla"""
    assert "CARA_REDONDA_SIN_SENTIDO" in capsys.readouterr().out


def test_un_tramo_de_un_sentido_por_el_borde_de_una_manzana_redonda_no_es_aviso(capsys):
    """El falso aviso de la primera corrida real: un tramo de la NQS, de un solo sentido y
     recorrido por donde dicen los datos, bordea una manzana de 3,7 ha casi circular. Va en
     sentido horario alrededor de ella, y eso no es una contravía."""
    G = _rotonda_sin_sentido()
    for u, v in (("N", "E"), ("W", "N"), ("S", "W"), ("E", "S")):  # anillo de un solo sentido, horario
        G.remove_edge(v, u)
        G[u][v][0].update(oneway=True)
    for _, _, d in G.edges(data=True):
        if d.get("name") == "Glorieta":
            d["oneway"] = True
    rotondas = _detectar_rotondas(G)
    assert not any(es_rotonda for _, es_rotonda in rotondas.values())  # horario: no es una rotonda colombiana
    revisar_ruta(G, {}, rotondas, {}, "o", "d")
    salida = capsys.readouterr().out
    assert "Avisos: ninguno" in salida


def test_la_ruta_avisa_cuando_va_por_una_calzada_sin_sentido():
    G = _rotonda_sin_sentido()
    G["S0"]["S"][0]["oneway"] = False
    filas, _ = filas_de_camino(G, ["o", "S0", "S", "W", "W0", "d"], {}, {}, {"S0-S": "vecina de doble sentido"}, "x")
    assert "CALZADA_SIN_SENTIDO" in filas[0]["avisos"]


def test_una_rotonda_entera_de_doble_sentido_no_la_completa_el_modelo_pero_el_diagnostico_la_ve(capsys):
    """graph/sentido.py solo completa rotondas que ya son mayoritariamente de un sentido (las
     de doble sentido completo suelen ser manzanas redondas). Esta queda como está, y por eso
     el diagnóstico tiene que seguir marcándola: es la que se corrige a mano."""
    from integrabog.graph.sentido import completar_sentidos
    import geopandas as gpd
    G = _rotonda_sin_sentido()
    filas = [{"u": u, "v": v, "key": k, **{c: a[c] for c in ("overture_id", "class", "name", "length",
                                                             "oneway", "reversed", "geometry")}}
             for u, v, k, a in G.edges(keys=True, data=True) if a["layer"] == "micro"]
    resultado = completar_sentidos(gpd.GeoDataFrame(filas, geometry="geometry", crs="EPSG:3116"), forzados=[])
    assert len(resultado) == len(filas)  # no se quitó ningún sentido
    assert "(1 caras redondas de doble sentido sin tocar)" in capsys.readouterr().out


def test_contravia_parcial_y_tramo_de_pieza():
    segmento = LineString([(0, 0), (100, 0)])
    assert tramo_de_pieza(LineString([(60, 0), (20, 0)]), segmento) == (0.2, 0.6)
    regla = [{"access_type": "denied", "when": {"heading": "backward"}, "between": [0.5, 1.0]}]
    """la pieza [0.2, 0.6] solo tiene 0.1 de 0.4 negado: micro.py la deja pasar (exige la mitad),
     el diagnóstico la marca como parcial"""
    assert negado_en_parte(regla, "backward", (0.2, 0.6))
    assert not negado_en_parte(regla, "forward", (0.2, 0.6))
    assert not negado_en_parte(regla, "backward", (0.0, 0.4))
