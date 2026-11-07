"""
Sentido de circulación completado en graph/sentido.py, sobre casos armados a
mano con la misma forma que deja micro._aristas_dirigidas(): una fila por
sentido circulable, 'reversed' = va contra el dibujo de Overture, geometría
orientada en el sentido de circulación.

El caso real que los motivó: la Av. Carrera 72 tiene una calzada sin regla de
sentido, y la ruta Toberín -> San Mateo entraba por ella en contravía.
"""
import math

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from integrabog.graph.sentido import completar_sentidos

COLUMNAS = ["u", "v", "key", "overture_id", "class", "name", "length", "oneway", "reversed", "geometry"]


def _pieza(pieza_id, coords, clase="trunk", nombre="Avenida Carrera 72", sentidos=("forward", "backward")):
    """Filas de una pieza dibujada en el orden de 'coords'."""
    dibujo = LineString(coords)
    filas = []
    for sentido in sentidos:
        geom = dibujo if sentido == "forward" else dibujo.reverse()
        u, v = (f"{pieza_id}-a", f"{pieza_id}-b") if sentido == "forward" else (f"{pieza_id}-b", f"{pieza_id}-a")
        filas.append({"u": u, "v": v, "key": 0, "overture_id": pieza_id, "class": clase, "name": nombre,
                      "length": dibujo.length, "oneway": len(sentidos) == 1, "reversed": sentido == "backward",
                      "geometry": geom})
    return filas


def _aristas(*piezas):
    return gpd.GeoDataFrame([f for p in piezas for f in p], columns=COLUMNAS, geometry="geometry",
                            crs="EPSG:3116")


def _sentidos(resultado, pieza_id):
    filas = resultado[resultado["overture_id"] == pieza_id]
    return sorted("backward" if r else "forward" for r in filas["reversed"])


# --- Calzadas separadas ---------------------------------------------------------------
#
#   x = -20      x = 0        x = 20
#   servicio     occidental   oriental
#   (2 sent.)    (solo sur)   (SIN regla)        Av. Carrera 72, de y = 0 a y = 300
#
# En Colombia se circula por la derecha: la calzada oriental va hacia el norte, con el
# separador (la occidental) a su izquierda.

def test_la_calzada_sin_regla_toma_el_sentido_contrario_a_su_vecina():
    occidental = _pieza("occ", [(0, 300), (0, 0)], sentidos=("forward",))      # dibujada hacia el sur
    oriental = _pieza("ori", [(20, 300), (20, 0)])                             # dibujada hacia el sur, 2 sentidos
    resultado = completar_sentidos(_aristas(occidental, oriental), forzados=[])
    assert _sentidos(resultado, "ori") == ["backward"]                         # al revés del dibujo = hacia el norte
    fila = resultado[resultado["overture_id"] == "ori"].iloc[0]
    assert fila["oneway"] and fila["sentido_inferido"] == "calzada separada"
    assert fila.geometry.coords[0][1] < fila.geometry.coords[-1][1]           # de verdad va hacia el norte


def test_una_calzada_de_servicio_por_fuera_no_se_toca():
    """La vía de servicio de doble sentido queda al occidente de la calzada que va al sur: en
     el sentido que se le deduciría (norte), la vecina le quedaría a la DERECHA. No es la otra
     calzada de la avenida, así que no se le inventa un sentido."""
    occidental = _pieza("occ", [(0, 300), (0, 0)], sentidos=("forward",))
    servicio = _pieza("serv", [(-20, 0), (-20, 300)])
    resultado = completar_sentidos(_aristas(occidental, servicio), forzados=[])
    assert _sentidos(resultado, "serv") == ["backward", "forward"]


def test_la_pieza_siguiente_de_la_misma_calle_no_es_la_otra_calzada():
    """Una calle de doble sentido que en un cruce pasa a ser de un solo sentido: las dos piezas
     van en línea, con el mismo nombre, y desde la mitad de la primera la segunda está a 50 m.
     No es una avenida con separador, y la primera no debe perder un sentido."""
    """la pieza de doble sentido trae un vértice 5 m corrido, como casi todas en los datos: con
     eso, desde su mitad la siguiente queda en diagonal y la regla del separador a la izquierda
     no basta para descartarla (así se colaron 8 piezas en la prueba con la malla sintética)"""
    doble = _pieza("doble", [(0, 0), (50, 5), (100, 0)])
    un_sentido = _pieza("sigue", [(100, 0), (400, 0)], sentidos=("forward",))
    un_sentido[0]["u"] = doble[0]["v"]                      # comparten el cruce
    resultado = completar_sentidos(_aristas(doble, un_sentido), forzados=[])
    assert _sentidos(resultado, "doble") == ["backward", "forward"]


def test_una_vecina_corrida_hacia_adelante_tampoco_cuenta():
    """Sin cruce en común, pero la vecina queda adelante y no al costado."""
    doble = _pieza("doble", [(0, 0), (50, 5), (100, 0)])
    adelante = _pieza("adelante", [(105, 0), (400, 0)], sentidos=("forward",))
    resultado = completar_sentidos(_aristas(doble, adelante), forzados=[])
    assert _sentidos(resultado, "doble") == ["backward", "forward"]


@pytest.mark.parametrize("caso", ["otro_nombre", "vecina_de_doble_sentido", "clase_residencial", "muy_lejos"])
def test_sin_una_vecina_confiable_no_se_deduce_nada(caso):
    occidental = _pieza("occ", [(0, 300), (0, 0)],
                        nombre="Avenida Calle 80" if caso == "otro_nombre" else "Avenida Carrera 72",
                        sentidos=("forward", "backward") if caso == "vecina_de_doble_sentido" else ("forward",))
    x = 100 if caso == "muy_lejos" else 20
    oriental = _pieza("ori", [(x, 300), (x, 0)], clase="residential" if caso == "clase_residencial" else "trunk")
    resultado = completar_sentidos(_aristas(occidental, oriental), forzados=[], confirmadas=[])
    assert _sentidos(resultado, "ori") == ["backward", "forward"]


# --- Avenidas confirmadas: las dos calzadas sin regla ----------------------------------

CONFIRMADA = [{"nombre": "avenida carrera 72", "motivo": "prueba"}]  # sin tildes ni mayúsculas: da igual


def test_en_una_avenida_confirmada_cada_calzada_deja_a_la_otra_a_su_izquierda():
    occidental = _pieza("occ", [(0, 300), (0, 0)])    # las dos de doble sentido, dibujadas hacia el sur
    oriental = _pieza("ori", [(20, 300), (20, 0)])
    resultado = completar_sentidos(_aristas(occidental, oriental), forzados=[], confirmadas=CONFIRMADA)
    assert _sentidos(resultado, "occ") == ["forward"]   # occidental hacia el sur (la oriental a su izquierda)
    assert _sentidos(resultado, "ori") == ["backward"]  # oriental hacia el norte (la occidental a su izquierda)
    marcas = set(resultado["sentido_inferido"])
    assert marcas == {"calzada separada (avenida confirmada)"}


def test_sin_confirmar_las_dos_calzadas_sin_regla_no_se_tocan():
    occidental = _pieza("occ", [(0, 300), (0, 0)])
    oriental = _pieza("ori", [(20, 300), (20, 0)])
    resultado = completar_sentidos(_aristas(occidental, oriental), forzados=[], confirmadas=[])
    assert _sentidos(resultado, "occ") == _sentidos(resultado, "ori") == ["backward", "forward"]


def test_una_avenida_confirmada_sin_otra_calzada_al_lado_sigue_de_doble_sentido():
    """Donde la avenida es de una sola calzada no hay separador del cual partir."""
    sola = _pieza("sola", [(0, 300), (0, 0)])
    resultado = completar_sentidos(_aristas(sola), forzados=[], confirmadas=CONFIRMADA)
    assert _sentidos(resultado, "sola") == ["backward", "forward"]


def test_la_zona_limita_la_confirmacion():
    from integrabog.graph.sentido import _A_METRICO
    lon, lat = _A_METRICO.transform(5_000_000, 5_000_000, direction="INVERSE")  # lejos de las calzadas
    lejos = [{"nombre": "Avenida Carrera 72", "cerca_de": (lat, lon), "radio_m": 500, "motivo": "prueba"}]
    occidental = _pieza("occ", [(0, 300), (0, 0)])
    oriental = _pieza("ori", [(20, 300), (20, 0)])
    resultado = completar_sentidos(_aristas(occidental, oriental), forzados=[], confirmadas=lejos)
    assert _sentidos(resultado, "ori") == ["backward", "forward"]


def test_motivos_calzadas_explica_cada_caso():
    from integrabog.graph.sentido import motivos_calzadas
    avenida = _aristas(_pieza("occ", [(0, 300), (0, 0)]), _pieza("ori", [(20, 300), (20, 0)]),
                       _pieza("calle", [(500, 0), (500, 300)], nombre="Calle 1"))
    assert motivos_calzadas(avenida, confirmadas=[]) == {
        "occ": "vecina de doble sentido", "ori": "vecina de doble sentido", "calle": "sin vecina"}
    assert motivos_calzadas(avenida, confirmadas=CONFIRMADA)["ori"] == "completada (avenida confirmada)"


# --- Rotondas -------------------------------------------------------------------------

def _anillo(sentidos_por_arco, horario=False, radio=40.0):
    """Anillo de 4 arcos. Dibujado antihorario (o horario); cada arco con sus sentidos."""
    piezas = []
    for k, sentidos in enumerate(sentidos_por_arco):
        angulos = [math.radians(90 * k + 90 * t / 16) for t in range(17)]
        coords = [(round(radio * math.cos(a), 9), round(radio * math.sin(a), 9)) for a in angulos]
        coords = coords[::-1] if horario else coords
        piezas.append(_pieza(f"arco{k}", coords, clase="primary", nombre=None, sentidos=sentidos))
    return piezas


def test_rotonda_con_un_hueco_se_completa_en_sentido_antihorario():
    un_sentido, doble = ("forward",), ("forward", "backward")
    resultado = completar_sentidos(_aristas(*_anillo([un_sentido, un_sentido, un_sentido, doble])), forzados=[])
    assert _sentidos(resultado, "arco3") == ["forward"]  # dibujado antihorario: se conserva el del dibujo
    assert resultado[resultado["overture_id"] == "arco3"]["sentido_inferido"].iloc[0] == "rotonda"


def test_un_circulo_de_doble_sentido_no_es_una_rotonda_y_no_se_toca():
    """En Bogotá, las caras redondas de doble sentido son manzanas o parques (p. ej. 4,5 ha en
     la Diagonal 89A con Carrera 115): forzarles un sentido inventaría una restricción."""
    doble = ("forward", "backward")
    resultado = completar_sentidos(_aristas(*_anillo([doble] * 4)), forzados=[])
    assert all(_sentidos(resultado, f"arco{k}") == ["backward", "forward"] for k in range(4))


def test_un_anillo_que_circula_en_sentido_horario_no_se_completa():
    un_sentido, doble = ("forward",), ("forward", "backward")
    resultado = completar_sentidos(_aristas(*_anillo([un_sentido, un_sentido, un_sentido, doble], horario=True)),
                                   forzados=[])
    assert _sentidos(resultado, "arco3") == ["backward", "forward"]


# --- Piezas cortas de una calzada completada --------------------------------------------
#
# El caso real: la calzada occidental de la Av. Carrera 72 es un segmento de Overture que
# City2Graph partió en una pieza larga y, antes de la Calle 153, una de 10 m. La regla de
# calzadas completó la larga (hacia el sur) pero no la corta, que quedó de doble sentido.

def _pieza_de_segmento(pieza_id, u, v, coords, sentidos=("forward", "backward"), nombre="Avenida Carrera 72"):
    """Como _pieza, pero con los conectores dados: las piezas de un segmento los comparten."""
    filas = _pieza(pieza_id, coords, nombre=nombre, sentidos=sentidos)
    for fila in filas:
        fila["u"], fila["v"] = (u, v) if not fila["reversed"] else (v, u)
    return filas


def _calzadas_con_piezas_cortas(*cortas, larga_de_doble_sentido=False):
    """Occidental: occ_1 larga (200 m) y las piezas cortas que se pidan, todas dibujadas hacia
     el sur; oriental de un solo sentido hacia el norte (de ahí sale el sentido de occ_1)."""
    piezas = [_pieza_de_segmento("occ_1", "a", "b", [(0, 230), (0, 30)])]
    y = 30
    for k, largo in enumerate(cortas, start=2):
        piezas.append(_pieza_de_segmento(f"occ_{k}", "b" if k == 2 else f"c{k - 1}", f"c{k}", [(0, y), (0, y - largo)]))
        y -= largo
    if larga_de_doble_sentido:
        piezas.append(_pieza_de_segmento("occ_9", f"c{len(cortas) + 1}", "z", [(0, y), (0, y - 200)]))
    """la oriental solo va junto a occ_1: más al sur la avenida ya no tiene otra calzada"""
    oriental = _pieza("ori", [(20, 30), (20, 230)], sentidos=("forward",))  # hacia el norte
    return completar_sentidos(_aristas(*piezas, oriental), forzados=[])


def test_la_pieza_corta_toma_el_sentido_de_su_calzada(capsys):
    resultado = _calzadas_con_piezas_cortas(10)
    assert _sentidos(resultado, "occ_1") == ["forward"]                 # regla de calzadas: al sur
    assert _sentidos(resultado, "occ_2") == ["forward"]                 # la de 10 m, igual
    fila = resultado[resultado["overture_id"] == "occ_2"].iloc[0]
    assert fila["sentido_inferido"] == "calzada separada (pieza corta)" and fila["oneway"]
    assert "+ 1 piezas cortas de esas calzadas" in capsys.readouterr().out


def test_una_cadena_de_piezas_cortas_tambien():
    resultado = _calzadas_con_piezas_cortas(8, 6, 12)
    assert all(_sentidos(resultado, f"occ_{k}") == ["forward"] for k in (2, 3, 4))


def test_si_la_calzada_sigue_de_doble_sentido_la_pieza_corta_no_se_toca():
    """Entre la pieza completada y una pieza larga del mismo segmento que siguió de doble sentido
     (la regla no le encontró la otra calzada): ahí la avenida puede dejar de tener separador."""
    resultado = _calzadas_con_piezas_cortas(10, larga_de_doble_sentido=True)
    assert _sentidos(resultado, "occ_2") == ["backward", "forward"]


def test_una_pieza_corta_sin_calzada_completada_al_lado_no_se_toca():
    sola = _pieza_de_segmento("calle_2", "p", "q", [(500, 0), (510, 0)], nombre="Calle 1")
    larga = _pieza_de_segmento("calle_1", "o", "p", [(300, 0), (500, 0)], nombre="Calle 1")
    resultado = completar_sentidos(_aristas(larga, sola), forzados=[])
    assert _sentidos(resultado, "calle_2") == ["backward", "forward"]


# --- A mano ---------------------------------------------------------------------------

def test_sentido_forzado_por_rumbo_y_por_encima_de_lo_deducido(capsys):
    occidental = _pieza("occ", [(0, 300), (0, 0)], sentidos=("forward",))
    oriental = _pieza("ori_3", [(20, 300), (20, 0)])                            # id con sufijo de pieza
    """lo deducido sería norte; la corrección a mano (por id base, sin el '_3') pide sur"""
    resultado = completar_sentidos(_aristas(occidental, oriental), forzados=[("ori", "sur", "prueba")])
    assert _sentidos(resultado, "ori_3") == ["forward"]
    assert resultado[resultado["overture_id"] == "ori_3"]["sentido_inferido"].iloc[0] == "a mano"


def test_sentido_forzado_ninguno_saca_el_tramo_y_un_id_inexistente_avisa(capsys):
    calle = _pieza("calle", [(0, 0), (300, 0)], clase="residential", nombre="Calle 1")
    resultado = completar_sentidos(_aristas(calle), forzados=[("calle", "ninguno", "cerrada"),
                                                              ("no-existe", "norte", "x")])
    assert "calle" not in set(resultado["overture_id"])
    assert "no-existe" in capsys.readouterr().out


def test_sentido_forzado_invalido_falla_con_un_mensaje_claro():
    calle = _pieza("calle", [(0, 0), (300, 0)])
    with pytest.raises(ValueError, match="no válido"):
        completar_sentidos(_aristas(calle), forzados=[("calle", "arriba", "x")])
