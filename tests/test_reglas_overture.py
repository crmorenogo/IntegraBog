"""
Pruebas de la lectura de reglas de Overture en graph/micro.py.

Los casos de acceso y velocidad son los ejemplos oficiales del repositorio
del esquema de Overture (OvertureMaps/schema, carpeta
examples/transportation/docusaurus), copiados aquí como dicts para no
depender de ese repositorio. La pregunta en todos es la misma que se hace al
construir la malla: ¿puede pasar un carro particular en tránsito, a
cualquier hora, en este sentido?

    python -m pytest tests/
"""
import numpy as np
import pytest

from integrabog.graph.micro import _a_python, es_circulable, excluida_por_flags, velocidad_maxima_kmh


def sentidos(reglas, tramo=(0.0, 1.0)):
    return es_circulable(reglas, "forward", tramo), es_circulable(reglas, "backward", tramo)


# --- Acceso: ejemplos oficiales -----------------------------------------------------------

def test_sin_reglas_rige_el_acceso_implicito_de_la_clase():
    assert sentidos(None) == (True, True)


def test_restriccion_general_bloquea_ambos_sentidos():
    # access-restriction-01-blanket.yaml
    assert sentidos([{"access_type": "denied"}]) == (False, False)


def test_restriccion_a_peatones_no_afecta_a_los_carros():
    # access-restriction.yaml (motorway sin peatones)
    assert sentidos([{"access_type": "denied", "when": {"mode": ["foot"]}}]) == (True, True)


def test_via_de_un_solo_sentido_con_contraflujo_solo_para_buses():
    # subjective-heading-scoping.yaml: la regla del bus es la última, pero no aplica al carro
    reglas = [
        {"access_type": "denied", "when": {"heading": "backward"}},
        {"access_type": "allowed", "when": {"heading": "backward", "mode": ["bus"]}},
    ]
    assert sentidos(reglas) == (True, False)


def test_solo_acceso_a_destino_no_sirve_para_transito():
    # access-restriction-03-motor-vehicles-destination-only.yaml
    reglas = [
        {"access_type": "denied", "when": {"mode": ["motor_vehicle"]}},
        {"access_type": "allowed", "when": {"using": ["at_destination"]}},
    ]
    assert sentidos(reglas) == (False, False)


def test_excepciones_condicionales_no_levantan_la_restriccion_general():
    # segment/road/road-acesss-restriction.yaml: camiones, clientes y vehículos de >5 ejes
    reglas = [
        {"access_type": "denied"},
        {"access_type": "designated", "when": {"mode": ["truck"]}, "between": [0.1, 0.25]},
        {"access_type": "allowed", "when": {"using": ["as_customer", "to_farm"],
                                            "recognized": ["as_permitted", "as_employee"]},
         "between": [0.25, 0.50]},
        {"access_type": "allowed", "when": {"vehicle": [{"dimension": "axle_count",
                                                         "comparison": "greater_than", "value": 5}]},
         "between": [0.50, 0.70]},
    ]
    for tramo in [(0.0, 0.1), (0.1, 0.25), (0.3, 0.5), (0.5, 0.7), (0.7, 1.0)]:
        assert sentidos(reglas, tramo) == (False, False)


def test_decide_la_ultima_regla_que_aplica():
    reglas = [{"access_type": "denied"}, {"access_type": "allowed", "when": {"mode": ["motor_vehicle"]}}]
    assert sentidos(reglas) == (True, True)
    assert sentidos(list(reversed(reglas))) == (False, False)


def test_restriccion_por_horario_se_ignora():
    # temporal-scoping.yaml usa 'during'; la red se arma para cualquier hora
    reglas = [{"access_type": "denied", "when": {"during": "Mo-Fr 07:00-09:00"}}]
    assert sentidos(reglas) == (True, True)


def test_campos_nulos_como_llegan_de_los_datos_reales():
    # en los datos reales 'when' trae todas las claves, las que no aplican en null
    regla = {"access_type": "denied", "between": None,
             "when": {"during": None, "heading": "backward", "using": None,
                      "recognized": None, "mode": None, "vehicle": None}}
    assert sentidos([regla]) == (True, False)


@pytest.mark.parametrize("tramo, esperado", [
    ((0.0, 0.25), (True, False)),   # dentro del rango de la regla
    ((0.2, 0.4), (True, False)),    # cubre exactamente la mitad de la pieza: aplica
    ((0.25, 0.75), (True, True)),   # cubre solo el 10%: no aplica
    ((0.5, 1.0), (True, True)),     # fuera del rango
])
def test_reglas_acotadas_a_un_tramo(tramo, esperado):
    reglas = [{"access_type": "denied", "when": {"heading": "backward"}, "between": [0.0, 0.3]}]
    assert sentidos(reglas, tramo) == esperado


# --- Velocidad ----------------------------------------------------------------------------

def test_velocidad_simple_en_kmh():
    # speed-limits-01-simple.yaml
    assert velocidad_maxima_kmh([{"max_speed": {"value": 30, "unit": "km/h"}}], "forward") == 30.0


def test_velocidad_en_mph_y_regla_especifica_de_camiones():
    # speed-limits-02-directional.yaml: 70 mph general, 65 mph para camiones hacia adelante
    reglas = [
        {"max_speed": {"value": 70, "unit": "mph"}},
        {"when": {"mode": ["hgv"], "heading": "forward"}, "max_speed": {"value": 65, "unit": "mph"}},
    ]
    assert velocidad_maxima_kmh(reglas, "forward") == pytest.approx(112.7)
    assert velocidad_maxima_kmh(reglas, "backward") == pytest.approx(112.7)


def test_velocidad_por_tramos():
    # geometric-scoping.yaml: 100 km/h en el primer 15%, 60 km/h en el resto
    reglas = [{"between": [0, 0.15], "max_speed": {"value": 100, "unit": "km/h"}},
              {"between": [0.15, 1], "max_speed": {"value": 60, "unit": "km/h"}}]
    assert velocidad_maxima_kmh(reglas, "forward", (0.0, 0.15)) == 100.0
    assert velocidad_maxima_kmh(reglas, "forward", (0.4, 0.9)) == 60.0


def test_sin_limite_de_velocidad():
    assert velocidad_maxima_kmh(None, "forward") is None


# --- Banderas ---------------------------------------------------------------------------

def test_vias_en_construccion_o_abandonadas_se_excluyen():
    assert excluida_por_flags([{"values": ["is_under_construction"], "between": None}])
    assert excluida_por_flags(["is_abandoned"])  # forma absoluta
    assert not excluida_por_flags([{"values": ["is_bridge", "is_tunnel"]}])
    assert not excluida_por_flags([{"values": ["is_under_construction"], "between": [0.0, 0.2]}], (0.5, 1.0))


# --- Normalización de valores anidados ---------------------------------------------------

def test_normaliza_las_cuatro_formas_en_que_llegan_los_datos():
    esperado = [{"access_type": "denied", "when": {"heading": "backward", "mode": None}}]
    assert _a_python(esperado) == esperado
    assert _a_python('[{"access_type": "denied", "when": {"heading": "backward", "mode": null}}]') == esperado
    assert _a_python("[{'access_type': 'denied', 'when': {'heading': 'backward', 'mode': None}}]") == esperado
    assert _a_python(np.array([{"access_type": "denied",
                                "when": {"heading": "backward", "mode": None}}], dtype=object)) == esperado


def test_normaliza_vacios_y_escalares_de_numpy():
    assert _a_python(float("nan")) is None
    assert _a_python(None) is None
    assert _a_python(np.float64(0.25)) == 0.25 and type(_a_python(np.float64(0.25))) is float
    assert _a_python("Avenida Caracas") == "Avenida Caracas"


# --- Función de costo BRT -----------------------------------------------------------------

def _malla_de_una_arista(**atributos):
    import networkx as nx
    G = nx.MultiDiGraph()
    G.add_edge("micro_a", "micro_b", layer="micro", length=1000.0, **atributos)
    return G


def test_costo_brt_lee_la_clase_de_overture():
    from integrabog.routing.network_design import VELOCIDAD_BRT_KMH, calcular_costo_brt
    primaria, rampa = _malla_de_una_arista(**{"class": "primary"}), _malla_de_una_arista(**{"class": "primary", "subclass": "link"})
    calcular_costo_brt(primaria)
    calcular_costo_brt(rampa)
    esperado = 1.0 / VELOCIDAD_BRT_KMH * 60 * 1.15
    assert primaria.edges["micro_a", "micro_b", 0]["tiempo_brt_min"] == pytest.approx(esperado)
    assert rampa.edges["micro_a", "micro_b", 0]["tiempo_brt_min"] == pytest.approx(esperado)  # como primary_link en OSM


def test_costo_brt_rechaza_una_malla_sin_clase_vial():
    from integrabog.routing.network_design import calcular_costo_brt
    with pytest.raises(ValueError, match="class"):
        calcular_costo_brt(_malla_de_una_arista(highway="primary"))  # caché vieja de OSMnx
