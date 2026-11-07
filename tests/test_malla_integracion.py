"""
La construcción completa de la malla (micro.construir_malla_desde_overture),
con City2Graph de verdad, sobre un extracto en el formato de Overture armado
a mano con los casos que encontró el diagnóstico en Bogotá:

    x = -200      x = 0         x = 20        x = 220
    Carrera 70    Av. Cra 72    Av. Cra 72    Carrera 74
    (solo hasta   calzada       calzada       (destapada)
     10 t)        occidental    oriental
                  (solo sur)    (SIN regla)       y = 0, 200, 400, 600: Calles 1-4

La calzada oriental tiene que salir de un solo sentido, hacia el norte; la
Carrera 70 y la 74 tienen que quedar en la malla pero no aptas para una
troncal, cada una con su motivo.
"""
import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point

from integrabog.graph.micro import construir_malla_desde_overture

BASE = (1_000_000.0, 1_000_000.0)
YS = (0, 200, 400, 600)


def _punto(x, y):
    return (BASE[0] + x, BASE[1] + y)


def _segmento(sid, nodos, pos, clase, nombre, **extra):
    """Segmento de Overture que pasa por 'nodos' (conectores), con su 'at' en cada uno."""
    coords = [pos[n] for n in nodos]
    linea = LineString(coords)
    acumulado, ats = 0.0, [0.0]
    for a, b in zip(coords[:-1], coords[1:]):
        acumulado += Point(a).distance(Point(b))
        ats.append(acumulado / linea.length)
    return {"id": sid, "theme": "transportation", "type": "segment", "version": 0, "subtype": "road",
            "class": clase, "subclass": None, "names": {"primary": nombre, "common": None, "rules": None},
            "connectors": [{"connector_id": n, "at": round(at, 9)} for n, at in zip(nodos, ats)],
            "access_restrictions": extra.get("acceso"), "speed_limits": None, "road_flags": None,
            "road_surface": extra.get("superficie"), "geometry": linea}


@pytest.fixture(scope="module")
def malla():
    return _construir(regla_occidental=True)


@pytest.fixture(scope="module")
def malla_sin_reglas():
    """Las DOS calzadas sin regla, como en los 3 km de la Av. Carrera 72 cerca de la Calle 153."""
    return _construir(regla_occidental=False)


@pytest.fixture(scope="module")
def malla_con_pieza_corta():
    """Como malla_sin_reglas, pero la calzada occidental tiene un conector 10 m antes de su
     extremo norte: City2Graph la parte y deja una pieza de 10 m (el caso de la Calle 153)."""
    return _construir(regla_occidental=False, pieza_corta=True)


def _construir(regla_occidental: bool, pieza_corta: bool = False):
    pos = {}
    for k, y in enumerate(YS):
        for prefijo, x in (("L", -200), ("W", 0), ("E", 20), ("R", 220)):
            pos[f"{prefijo}{k}"] = _punto(x, y)
    hacia_el_sur = [f"{{}}{k}" for k in reversed(range(4))]
    if pieza_corta:
        pos["Wc"] = _punto(0, YS[-1] - 10)
    un_sentido_sur = [{"access_type": "denied", "when": {"heading": "backward"}, "between": None}]
    hasta_10_t = [{"access_type": "denied",
                   "when": {"vehicle": [{"dimension": "weight", "comparison": "greater_than", "value": 10, "unit": "t"}]},
                   "between": None}]
    occidental = [n.format("W") for n in hacia_el_sur]
    if pieza_corta:
        occidental.insert(1, "Wc")
    segmentos = [
        _segmento("cra72-occ", occidental, pos, "trunk", "Avenida Carrera 72",
                  acceso=un_sentido_sur if regla_occidental else None),
        _segmento("cra72-ori", [n.format("E") for n in hacia_el_sur], pos, "trunk", "Avenida Carrera 72"),  # sin regla
        _segmento("cra70", [f"L{k}" for k in range(4)], pos, "secondary", "Carrera 70", acceso=hasta_10_t),
        _segmento("cra74", [f"R{k}" for k in range(4)], pos, "secondary", "Carrera 74",
                  superficie=[{"value": "unpaved", "between": None}]),
    ] + [_segmento(f"calle{k}", [f"L{k}", f"W{k}", f"E{k}", f"R{k}"], pos, "secondary", f"Calle {k + 1}")
         for k in range(4)]
    seg = gpd.GeoDataFrame(segmentos, geometry="geometry", crs="EPSG:3116")
    con = gpd.GeoDataFrame({"id": list(pos)}, geometry=[Point(p) for p in pos.values()], crs="EPSG:3116")
    return construir_malla_desde_overture(seg, con)


def _aristas(G, nombre, x=None):
    return [(u, v, d) for u, v, d in G.edges(data=True)
            if d.get("name") == nombre and (x is None or abs(d["geometry"].coords[0][0] - BASE[0] - x) < 1)]


def test_la_calzada_sin_regla_queda_de_un_solo_sentido_hacia_el_norte(malla):
    oriental = _aristas(malla, "Avenida Carrera 72", x=20)
    assert len(oriental) == 3  # 3 piezas, un solo sentido cada una
    for _, _, d in oriental:
        (_, y0), (_, y1) = d["geometry"].coords[0], d["geometry"].coords[-1]
        assert y1 > y0 and d["oneway"] and d["sentido_inferido"] == "calzada separada"


def test_la_calzada_con_regla_no_cambia(malla):
    occidental = _aristas(malla, "Avenida Carrera 72", x=0)
    assert len(occidental) == 3
    assert all(d["geometry"].coords[-1][1] < d["geometry"].coords[0][1] for _, _, d in occidental)
    assert all(not d.get("sentido_inferido") for _, _, d in occidental)


def test_vias_en_la_malla_pero_no_aptas_para_troncal(malla):
    destapada, limitada = _aristas(malla, "Carrera 74"), _aristas(malla, "Carrera 70")
    assert destapada and limitada  # siguen en la malla: un carro sí pasa
    assert all(not d["apta_troncal"] and d["motivo_no_apta"] == "superficie: unpaved" for *_, d in destapada)
    assert all(not d["apta_troncal"] and d["motivo_no_apta"] == "restricción para el bus: weight > 10 t"
               for *_, d in limitada)
    assert all(d["apta_troncal"] for *_, d in _aristas(malla, "Calle 2"))


def test_la_marca_de_no_apta_sobrevive_a_la_cache(malla, tmp_path, monkeypatch):
    """La malla se guarda en GeoParquet y se recarga en cada arranque: un 'apta_troncal' = False
     que se perdiera ahí dejaría pasar la troncal por una vía destapada sin ningún error."""
    import integrabog.graph.micro as micro
    monkeypatch.setattr(micro, "RUTA_MALLA_PROCESADA", tmp_path / "malla")
    parametros = {"prueba": True}
    micro._guardar_malla_procesada(malla, parametros, {"release": "prueba"})
    recargada = micro._cargar_malla_procesada(parametros)
    antes = {(u, v, k): (d["apta_troncal"], d.get("motivo_no_apta"), d.get("sentido_inferido"))
             for u, v, k, d in malla.edges(keys=True, data=True)}
    despues = {(u, v, k): (bool(d["apta_troncal"]), d.get("motivo_no_apta"), d.get("sentido_inferido"))
               for u, v, k, d in recargada.edges(keys=True, data=True)}
    assert despues == antes
    assert sum(not a for a, _, _ in despues.values()) == 12


def test_la_pieza_corta_de_la_calzada_sigue_su_sentido(malla_con_pieza_corta):
    """Por la construcción completa, con los ids que pone City2Graph ('cra72-occ_1', ...): la
     pieza de 10 m queda de un solo sentido hacia el sur, como el resto de su calzada."""
    occidental = _aristas(malla_con_pieza_corta, "Avenida Carrera 72", x=0)
    assert len(occidental) == 4
    for _, _, d in occidental:
        (_, y0), (_, y1) = d["geometry"].coords[0], d["geometry"].coords[-1]
        assert y1 < y0 and d["oneway"]
    corta = [d for *_, d in occidental if d["length"] < 20]
    assert len(corta) == 1 and corta[0]["sentido_inferido"] == "calzada separada (pieza corta)"


def test_avenida_confirmada_con_las_dos_calzadas_sin_regla(malla_sin_reglas):
    """La Av. Carrera 72 está en config.AVENIDAS_CON_SEPARADOR: cada calzada toma el sentido que
     deja a la otra a su izquierda (oriental al norte, occidental al sur)."""
    for x, al_norte in ((20, True), (0, False)):
        calzada = _aristas(malla_sin_reglas, "Avenida Carrera 72", x=x)
        assert len(calzada) == 3
        for _, _, d in calzada:
            (_, y0), (_, y1) = d["geometry"].coords[0], d["geometry"].coords[-1]
            assert (y1 > y0) == al_norte
            assert d["sentido_inferido"] == "calzada separada (avenida confirmada)"
