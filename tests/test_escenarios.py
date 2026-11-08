"""
Escenarios antes/después (routing/escenarios.py): cómo entra una troncal
propuesta al grafo macro, el GeoJSON de propuestas y la comparación.

Primero, una línea de cinco estaciones a la que una propuesta le cierra un
ciclo: todo cambia de forma predecible (desaparecen los puntos de corte y los
puentes, sube μ, bajan las distancias). Después, la propuesta que arma la app
sobre una red mínima con malla vial, y la red real con una propuesta de
prueba entre las dos estaciones cercanas con más rodeo.
"""
import json
import sys
from collections import Counter

import networkx as nx
import pytest
from pyproj import Transformer
from shapely.geometry import LineString

from integrabog.graph.macro import construir_grafo_macro
from integrabog.routing.escenarios import (
    TroncalPropuesta,
    agregar_troncales,
    codigo_estacion,
    comparar,
    evaluar,
    guardar_propuestas,
    leer_propuestas,
    propuesta_desde_sugerencia,
)
from integrabog.routing.metricas import (
    geometria_camino_lonlat,
    metricas_red,
    peso,
    punto_lonlat,
    resumen_camino,
)
from integrabog.routing.network_design import (
    ATRIBUTO_TRANSBORDO_PROPIO,
    VELOCIDAD_BRT_KMH,
    implica_transbordo,
    tiempo_troncal_min,
)
from integrabog.routing.robustez import estructura

_A_LONLAT = Transformer.from_crs("EPSG:3116", "EPSG:4326", always_xy=True)
ORIGEN = (1_000_000.0, 1_000_000.0)


def _linea():
    """1 - 2 - 3 - 4 - 5, a 1 km, en línea recta hacia el oriente."""
    G = nx.DiGraph()
    pos = {k: (ORIGEN[0] + 1000 * (k - 1), ORIGEN[1]) for k in range(1, 6)}
    for k in range(1, 5):
        for a, b in ((k, k + 1), (k + 1, k)):
            G.add_edge(a, b, weight=1000.0, geometry=LineString([pos[a], pos[b]]))
    for k, (x, y) in pos.items():
        G.nodes[k].update(x=x, y=y, etiqueta=f"E{k}", troncal="T")
    return G


def _propuesta(G, a, b, largo_m, tiempo_min, tramos=2, nombre=""):
    """Una propuesta de prueba en línea recta (con un quiebre, para que la forma no sea trivial)."""
    xa, ya, xb, yb = G.nodes[a]["x"], G.nodes[a]["y"], G.nodes[b]["x"], G.nodes[b]["y"]
    puntos = [(xa, ya), ((xa + xb) / 2, (ya + yb) / 2 + 400), (xb, yb)]
    lonlat = tuple(tuple(round(c, 6) for c in _A_LONLAT.transform(x, y)) for x, y in puntos)
    return TroncalPropuesta(a, b, largo_m, tiempo_min, tramos, lonlat, (lonlat[0], lonlat[-1]), nombre)


# --- Cómo entra la propuesta ---------------------------------------------------------------

def test_la_propuesta_entra_como_arista_en_los_dos_sentidos():
    G = _linea()
    H = agregar_troncales(G, [_propuesta(G, 1, 5, 4500, 12.0, tramos=3, nombre="E1 ↔ E5")])
    assert not G.has_edge(1, 5)  # la red de hoy no se toca
    for a, b in ((1, 5), (5, 1)):
        d = H[a][b]
        assert (d["tipo"], d["weight"], d["tiempo_min"], d["tramos"]) == ("propuesta", 4500.0, 12.0, 3)
        assert d["propuesta"] == "E1 ↔ E5"
    """la forma va de a a b y sus puntas quedan exactamente en las estaciones"""
    assert H[1][5]["geometry"].coords[0] == (G.nodes[1]["x"], G.nodes[1]["y"])
    assert H[5][1]["geometry"].coords[0] == (G.nodes[5]["x"], G.nodes[5]["y"])
    assert list(H[5][1]["geometry"].coords) == list(H[1][5]["geometry"].coords)[::-1]


def test_la_propuesta_cobra_el_transbordo_como_un_cruce():
    G = _linea()
    H = agregar_troncales(G, [_propuesta(G, 1, 5, 4500, 12.0, tramos=3)])
    d = H[1][5]
    assert peso("tiempo", 5.0)(1, 5, d) == pytest.approx(12.0 + 5.0)
    assert peso("tiempo", 0.0)(1, 5, d) == pytest.approx(12.0)
    assert peso("distancia")(1, 5, d) == pytest.approx(4.5)
    assert peso("tramos")(1, 5, d) == 3
    r = resumen_camino(H, (2, 1, 5), transbordo_min=5.0)
    assert (r["tramos"], r["transbordos"], r["estaciones"]) == (1 + 3, 1, 3)
    assert r["minutos"] == pytest.approx(1 / VELOCIDAD_BRT_KMH * 60 + 12.0 + 5.0)


def test_la_ruta_continua_no_cobra_transbordo_y_los_cruces_siguen_cobrando():
    """Con transbordo propio, la propuesta cobra el suyo (0: ruta continua, sin transbordo) y los
     cruces de la red de hoy siguen cobrando el general: el antes no cambia."""
    G = _linea()
    continua = agregar_troncales(G, [_propuesta(G, 1, 5, 4500, 12.0, tramos=3)], transbordo_min=0)
    d = continua[1][5]
    assert peso("tiempo", 5.0)(1, 5, d) == pytest.approx(12.0)
    assert not implica_transbordo(d)
    r = resumen_camino(continua, (2, 1, 5), transbordo_min=5.0)
    assert r["transbordos"] == 0 and r["minutos"] == pytest.approx(1 / VELOCIDAD_BRT_KMH * 60 + 12.0)

    otra = agregar_troncales(G, [_propuesta(G, 1, 5, 4500, 12.0, tramos=3)], transbordo_min=2.5)
    assert peso("tiempo", 5.0)(1, 5, otra[1][5]) == pytest.approx(14.5)
    assert resumen_camino(otra, (2, 1, 5), transbordo_min=5.0)["transbordos"] == 1

    cruce = {"tipo": "cruce", "weight": 300.0}
    assert tiempo_troncal_min(cruce, 5.0) == pytest.approx(0.3 / VELOCIDAD_BRT_KMH * 60 + 5.0)
    assert implica_transbordo(cruce)
    assert ATRIBUTO_TRANSBORDO_PROPIO not in G.get_edge_data(1, 2)  # la red de hoy no lo trae
    with pytest.raises(ValueError, match="no puede ser negativo"):
        agregar_troncales(G, [_propuesta(G, 1, 5, 4500, 12.0)], transbordo_min=-1)


def test_la_ruta_continua_es_la_cota_superior_y_no_cambia_la_estructura():
    """De 1 a 5 por la línea hay 4 km a 25,2 km/h: 9,5 min. Una propuesta de 6 min con 5 min de
     transbordo (11 min) no acorta nada; como ruta continua acorta ese viaje a 6 min. La
     estructura y las distancias por largo y por tramos son las mismas en las dos variantes."""
    from integrabog.scripts.comparar_escenarios import (
        evaluar_variante,
        viajes_entre_puntas,
    )
    G = _linea()
    p = _propuesta(G, 1, 5, 4500, 6.0, tramos=3, nombre="E1 ↔ E5")
    antes = evaluar(G, 5.0)
    fisica, continua = (evaluar_variante(G, [p], antes, m, 5.0) for m in (5.0, 0.0))
    assert (fisica.clave, continua.clave) == ("conexion_fisica", "ruta_continua")
    [(_, hoy, (t_fisica, t_continua))] = viajes_entre_puntas(G, [p], [fisica, continua], 5.0)
    assert hoy == t_fisica == pytest.approx(4 / VELOCIDAD_BRT_KMH * 60) and t_continua == pytest.approx(6.0)

    filas_f, filas_c = ({f["clave"]: f for f in v.filas} for v in (fisica, continua))
    assert filas_f["media_tiempo"]["mejora"] is None and filas_c["media_tiempo"]["mejora"] is True
    assert filas_c["eficiencia"]["despues"] > filas_f["eficiencia"]["despues"]
    for clave in ("ciclomatico", "puentes", "puntos_de_corte", "dependen_estacion", "dependen_enlace",
                  "diametro_distancia", "media_distancia", "diametro_tramos", "media_tramos"):
        assert filas_f[clave]["despues"] == filas_c[clave]["despues"], clave


def test_un_camino_por_la_propuesta_se_dibuja_sin_saltos():
    G = _linea()
    H = agregar_troncales(G, [_propuesta(G, 1, 5, 4500, 12.0)])
    linea = geometria_camino_lonlat(H, (2, 1, 5))
    assert linea[0] == punto_lonlat(H, 2) and linea[-1] == punto_lonlat(H, 5)
    assert len(linea) == 2 + 3 - 1  # 2-1 en recta, 1-5 con su quiebre; el punto de la estación 1, una vez


def test_no_se_agrega_si_ya_hay_arista_o_falta_una_estacion():
    G = _linea()
    with pytest.raises(ValueError, match="ya están unidas por una arista de tramo"):
        agregar_troncales(G, [_propuesta(G, 2, 3, 1200, 3.0)])
    with pytest.raises(ValueError, match="la estación 99 no está en la red"):
        agregar_troncales(G, [TroncalPropuesta(1, 99, 1000, 3.0, 1, ((0, 0), (1, 1)))])


# --- Antes y después en una red con respuesta conocida ------------------------------------

def test_cerrar_un_ciclo_quita_puntos_de_corte_y_puentes():
    """La línea es un árbol: 3 puntos de corte y 4 puentes. Con la propuesta 1-5 queda un anillo:
     ninguno, μ = 1, y ningún par depende de una sola estación o de un solo enlace."""
    G = _linea()
    antes, despues = estructura(G), estructura(agregar_troncales(G, [_propuesta(G, 1, 5, 4500, 12.0, tramos=3)]))
    assert (antes.ciclomatico, len(antes.puntos_de_corte), len(antes.puentes)) == (0, 3, 4)
    assert (despues.ciclomatico, despues.puntos_de_corte, despues.puentes) == (1, (), ())
    assert despues.pares_dependen_estacion == despues.pares_dependen_enlace == 0


def test_la_comparacion_dice_que_mejora_y_que_no_cambia():
    """Por tramos, el anillo 1-2-3-4-5-1 mide 4 + 3 = 7: el diámetro baja de 4 a 3. La
     propuesta cuesta 12 min más el transbordo, así que por tiempo no acorta nada: de 1 a 5 por
     la línea son 4 km a 25,2 km/h, 9,5 min."""
    G = _linea()
    filas = {f["clave"]: f for f in comparar(evaluar(G), evaluar(agregar_troncales(
        G, [_propuesta(G, 1, 5, 4500, 12.0, tramos=3)])))}
    assert (filas["diametro_tramos"]["antes"], filas["diametro_tramos"]["despues"]) == (4, 3)
    assert filas["diametro_tramos"]["mejora"] is True
    assert (filas["puentes"]["cambio"], filas["puentes"]["mejora"]) == (-4, True)
    assert (filas["ciclomatico"]["cambio"], filas["ciclomatico"]["mejora"]) == (1, True)  # aquí subir es mejorar
    assert filas["diametro_tiempo"]["mejora"] is None and filas["diametro_tiempo"]["cambio"] == 0
    assert all(f["mejora"] is None for f in comparar(evaluar(G), evaluar(G)))


# --- La propuesta que arma la app ---------------------------------------------------------

def test_la_propuesta_de_la_app_trae_su_largo_tiempo_y_paradas():
    from integrabog.routing.network_design import sugerir_nueva_troncal
    from tests.test_metricas import _app
    r = sugerir_nueva_troncal(_app(con_t2=False), "o", "d")
    assert r["largo_nueva_ruta_m"] == pytest.approx(50 + 2900 + 50)  # acceso a pie, vía primaria, acceso
    p = propuesta_desde_sugerencia(r, nombre="o ↔ d")
    assert (p.origen, p.destino, p.nombre) == ("o", "d", "o ↔ d")
    assert (p.largo_m, p.tiempo_min) == (r["largo_nueva_ruta_m"], r["tiempo_nueva_ruta_min"])
    assert p.tramos == len(r["estaciones_intermedias_lonlat"]) - 1
    assert p.geometria_lonlat[0] == tuple(r["geometria_lonlat"][0])
    assert (p.tiempo_actual_min, p.ahorro_min) == (r["tiempo_actual_min"], r["ahorro_min"])


def test_codigo_de_estacion():
    assert codigo_estacion("macro_4107") == 4107
    assert codigo_estacion(4107) == 4107 and codigo_estacion("o") == "o"


# --- El GeoJSON de propuestas -------------------------------------------------------------

def test_el_geojson_de_propuestas_ida_y_vuelta(tmp_path):
    G = _linea()
    propuestas = [_propuesta(G, 1, 5, 4500.5, 12.25, tramos=3, nombre="E1 ↔ E5"),
                  _propuesta(G, 2, 4, 2100.0, 6.5, nombre="E2 ↔ E4")]
    ruta = tmp_path / "escenarios" / "propuestas.geojson"
    guardar_propuestas(propuestas, ruta)
    assert leer_propuestas(ruta) == propuestas


def test_leer_un_geojson_incompleto_dice_que_falta(tmp_path):
    ruta = tmp_path / "propuestas.geojson"
    ruta.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"nombre": "a mano", "origen": 1, "destino": 5, "largo_m": 4500, "tramos": 3},
         "geometry": {"type": "LineString", "coordinates": [[-74.1, 4.6], [-74.0, 4.7]]}}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="línea 1 \\(a mano\\): faltan las propiedades tiempo_min"):
        leer_propuestas(ruta)


# --- La red real ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def macro():
    return construir_grafo_macro()


def _par_con_mas_rodeo(G, radio_m=1000.0):
    """Las dos estaciones a menos de radio_m en línea recta, sin arista entre ellas, con más
     rodeo por la red: el mismo criterio de los pares críticos, sin la malla vial."""
    largos = dict(nx.all_pairs_dijkstra_path_length(G, weight="weight"))
    mejor = None
    for a in sorted(G):
        for b in sorted(G):
            recta = ((G.nodes[a]["x"] - G.nodes[b]["x"]) ** 2 + (G.nodes[a]["y"] - G.nodes[b]["y"]) ** 2) ** 0.5
            if a < b and 0 < recta <= radio_m and not G.has_edge(a, b):
                rodeo = largos[a][b] / recta
                if mejor is None or rodeo > mejor[0]:
                    mejor = (rodeo, a, b, recta)
    return mejor


def test_en_la_red_real_una_propuesta_no_alarga_nada(macro):
    _, a, b, recta = _par_con_mas_rodeo(macro)
    largo = 1.4 * recta
    H = agregar_troncales(macro, [_propuesta(macro, a, b, largo, largo / 1000 / VELOCIDAD_BRT_KMH * 60 + 2)])
    for criterio in ("tiempo", "distancia", "tramos"):
        antes, despues = metricas_red(macro, criterio), metricas_red(H, criterio)
        assert all(despues.excentricidad[v] <= antes.excentricidad[v] + 1e-9 for v in macro)
        assert all(despues.media_desde[v] <= antes.media_desde[v] + 1e-9 for v in macro)
        assert despues.media < antes.media  # el par con más rodeo se acorta, y con él otros viajes
    ea, ed = estructura(macro), estructura(H)
    assert ed.ciclomatico == ea.ciclomatico + 1 and ed.enlaces == ea.enlaces + 1
    assert set(ed.puntos_de_corte) <= set(ea.puntos_de_corte) and set(ed.puentes) <= set(ea.puentes)
    assert ed.pares_dependen_estacion <= ea.pares_dependen_estacion


# --- Los scripts ---------------------------------------------------------------------------

def test_proponer_deja_por_fuera_lo_que_no_sirve_y_dice_por_que():
    from integrabog.scripts.proponer_troncales import _unidas, proponer
    from tests.test_metricas import _app
    G = _app(con_t2=False)
    propuestas, avisos = proponer(G, [("o", "d"), ("d", "o"), ("o", "nadie")])
    assert [p.nombre for p in propuestas] == ["o ↔ d"]
    assert any("repetida" in a for a in avisos) and any("'nadie'" in a for a in avisos)
    assert _unidas(G, "o", "t1") and not _unidas(G, "o", "d")


def test_el_script_de_comparacion_deja_los_tres_archivos(macro, tmp_path, monkeypatch):
    from integrabog.scripts import comparar_escenarios as script
    _, a, b, recta = _par_con_mas_rodeo(macro)
    u, v = next(iter(macro.edges()))
    largo = 1.4 * recta
    guardar_propuestas([_propuesta(macro, a, b, largo, largo / 1000 / VELOCIDAD_BRT_KMH * 60 + 2, nombre="prueba"),
                        _propuesta(macro, u, v, 900, 3.0, nombre="ya unidas")], tmp_path / "propuestas.geojson")
    monkeypatch.setattr(sys, "argv", ["comparar_escenarios", "--propuestas", str(tmp_path / "propuestas.geojson"),
                                      "--salida", str(tmp_path)])
    script.main()
    informe = (tmp_path / "antes_despues.md").read_text(encoding="utf-8")
    assert "## Antes y después" in informe and "| prueba |" in informe
    assert "Propuesta 'ya unidas': las dos estaciones ya están unidas" in informe  # la omitida, con su motivo
    assert len((tmp_path / "antes_despues.csv").read_text(encoding="utf-8-sig").splitlines()) == len(macro) + 1
    datos = json.loads((tmp_path / "antes_despues.geojson").read_text(encoding="utf-8"))
    elementos = Counter(f["properties"]["elemento"] for f in datos["features"])
    assert elementos["troncal propuesta"] == 1 and elementos["estación"] == len(macro)


def test_el_script_compara_la_conexion_fisica_con_la_ruta_continua(macro, tmp_path, monkeypatch):
    from integrabog.scripts import comparar_escenarios as script
    _, a, b, recta = _par_con_mas_rodeo(macro)
    largo = 1.4 * recta
    guardar_propuestas([_propuesta(macro, a, b, largo, largo / 1000 / VELOCIDAD_BRT_KMH * 60 + 2, nombre="prueba")],
                       tmp_path / "propuestas.geojson")
    monkeypatch.setattr(sys, "argv", ["comparar_escenarios", "--propuestas", str(tmp_path / "propuestas.geojson"),
                                      "--transbordo-propuestas", "5", "0", "--salida", str(tmp_path / "final")])
    script.main()
    final = tmp_path / "final"
    informe = (final / "comparacion_transbordo.md").read_text(encoding="utf-8")
    for texto in ("## Viaje entre las dos puntas de cada propuesta", "## Indicadores de la red",
                  "Conexión física (5 min de transbordo)", "Ruta continua (sin transbordo)", "| prueba |"):
        assert texto in informe, texto
    filas = (final / "comparacion_transbordo.csv").read_text(encoding="utf-8-sig").splitlines()
    assert "media_tiempo_conexion_fisica_min" in filas[0] and "media_tiempo_ruta_continua_min" in filas[0]
    assert len(filas) == len(macro) + 1
    for carpeta in ("conexion_fisica", "ruta_continua"):
        for archivo in ("antes_despues.md", "antes_despues.csv", "antes_despues.geojson"):
            assert (final / carpeta / archivo).exists(), f"{carpeta}/{archivo}"
    assert "se opera como ruta continua" in (final / "ruta_continua" / "antes_despues.md").read_text(encoding="utf-8")


def test_el_script_no_acepta_transbordos_negativos(tmp_path, monkeypatch):
    from integrabog.scripts import comparar_escenarios as script
    monkeypatch.setattr(sys, "argv", ["comparar_escenarios", "--propuestas", str(tmp_path / "x.geojson"),
                                      "--transbordo-propuestas", "5", "-1"])
    with pytest.raises(SystemExit):
        script.main()


def test_el_script_de_comparacion_sin_propuestas_explica_que_hacer(tmp_path, monkeypatch):
    from integrabog.scripts import comparar_escenarios as script
    monkeypatch.setattr(sys, "argv", ["comparar_escenarios", "--propuestas", str(tmp_path / "no_existe.geojson")])
    with pytest.raises(SystemExit, match="proponer_troncales"):
        script.main()
