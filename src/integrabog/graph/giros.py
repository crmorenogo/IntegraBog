"""
Giros prohibidos de Overture ('prohibited_transitions') en la malla vial, y
la ruta más corta que los respeta.

Por qué hace falta: la malla es un grafo por intersecciones (un nodo por
conector de Overture), y en un grafo así el giro no existe como objeto. Si
dos calles comparten un conector, la ruta pasa de una a la otra en cualquier
dirección que permita el sentido de cada una. Overture trae aparte los giros
que no se pueden hacer, como reglas en el segmento por el que se llega:
"desde este segmento, por el conector c, no se puede entrar al segmento t en
el sentido h". A veces la regla es una secuencia de varios conectores, como
un giro en U por un cruce del separador. Caso que lo motivó: sin el filtro
de factibilidad, la ruta Toberín -> San Mateo pasó a la Av. Carrera 72 por
un giro que el diagnóstico marcó como prohibido en los datos.

Hay dos formas de respetarlos:
  - pasar a un grafo por tramos (cada arista un nodo, cada giro permitido
    una arista). Es exacto, pero cambia el contrato del grafo que usan todos
    los módulos (estaciones, transferencias, costura, mapa);
  - dejar el grafo como está y hacer que la búsqueda recuerde por dónde
    llegó a cada nodo. Es lo que se hace aquí: un Dijkstra cuyos estados son
    (nodo, giros prohibidos en curso). Donde no hay ninguna regla, el estado
    es el nodo solo y la búsqueda es la de siempre, así que el costo extra se
    limita a las intersecciones con reglas.

Representación: al construir la malla, cada regla se traduce a aristas
dirigidas concretas, identificadas por (overture_id, reversed): la pieza de
City2Graph y el sentido en que se recorre. Ese par no cambia al guardar la
malla en caché ni al armar el grafo multicapa (los nodos sí cambian de
nombre allí). La arista por la que se llega, la primera de la secuencia,
guarda en el atributo 'giros_prohibidos' (texto JSON) la lista de
continuaciones prohibidas. Cada continuación es la lista de aristas que
siguen, hasta la que no se puede tomar inclusive.

Lectura de una regla (esquema de Overture): 'sequence' es la lista ordenada
de pares (conector, segmento) que no se puede seguir desde el segmento que
tiene la regla, y 'final_heading' el sentido prohibido en el último
segmento. 'when.heading', si viene, limita la regla a un sentido de llegada.

Giros en U: con los giros prohibidos ya respetados, la corrida real encontró
la forma de sortear uno. La regla era "llegando por la Calle 153, por esta
pieza de la Av. Carrera 72, no se puede seguir al sur"; la ruta subía 10 m
por la avenida, daba la vuelta en U y bajaba, y como ya no llegaba desde la
Calle 153, la regla no le aplicaba. Un biarticulado no puede devolverse en un
cruce, así que la búsqueda tampoco deja girar más de GIRO_MAXIMO_BUS_GRADOS
entre dos tramos seguidos de la malla. Para eso el estado guarda también el
rumbo con que se llegó al nodo. Cada arista de la malla trae 'rumbo_inicial'
y 'rumbo_final' (grados, 0 = oriente, en sentido antihorario), medidos sobre
sus primeros y últimos TRAMO_RUMBO_M: un vértice suelto a 1 m del conector
daría giros falsos de 90°.
"""
import heapq
import itertools
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from typing import NamedTuple

import networkx as nx
import numpy as np
import shapely

from integrabog.config import GIRO_MAXIMO_BUS_GRADOS

ATRIBUTO_GIROS = "giros_prohibidos"
TRAMO_RUMBO_M = 20.0
_VACIO = frozenset()

Identificador = tuple[str, bool]  # (overture_id de la pieza, reversed)


class _Arista(NamedTuple):
    u: object
    v: object
    clave: object
    ident: Identificador


def identificador(datos: dict) -> Identificador | None:
    """(overture_id, reversed) de una arista de la malla; None en las demás
    capas (troncal, transferencias), que nunca forman parte de un giro."""
    pieza = datos.get("overture_id")
    return None if pieza is None else (str(pieza), bool(datos.get("reversed")))


_CACHE_TEXTO: dict[str, tuple] = {}


def continuaciones(datos: dict) -> tuple[tuple[Identificador, ...], ...]:
    """Las continuaciones prohibidas desde esta arista, ya leídas del JSON.
    El mismo texto se repite en muchas consultas (una por ruta), así que se
    lee una sola vez."""
    texto = datos.get(ATRIBUTO_GIROS)
    if not texto or not isinstance(texto, str):
        return ()
    if texto not in _CACHE_TEXTO:
        _CACHE_TEXTO[texto] = tuple(tuple((str(p), bool(r)) for p, r in secuencia)
                                    for secuencia in json.loads(texto))
    return _CACHE_TEXTO[texto]


# --- Rumbo de cada tramo y ángulo de giro -----------------------------------------------

def anotar_rumbos(G: nx.MultiDiGraph) -> None:
    """Guarda 'rumbo_inicial' y 'rumbo_final' en cada arista de la malla (las
    que traen 'overture_id' y 'geometry'), calculados de una vez para todas."""
    claves = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True)
              if d.get("overture_id") is not None and d.get("geometry") is not None]
    if not claves:
        return
    iniciales, finales = _rumbos(np.array([G.edges[c]["geometry"] for c in claves], dtype=object))
    for clave, inicial, final in zip(claves, iniciales, finales):
        G.edges[clave]["rumbo_inicial"], G.edges[clave]["rumbo_final"] = round(float(inicial), 2), round(float(final), 2)


def _rumbos(geometrias: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    largo = shapely.length(geometrias)
    tramo = np.minimum(TRAMO_RUMBO_M, largo)
    a, b = shapely.line_interpolate_point(geometrias, 0.0), shapely.line_interpolate_point(geometrias, tramo)
    c, d = shapely.line_interpolate_point(geometrias, largo - tramo), shapely.line_interpolate_point(geometrias, largo)

    def rumbo(p, q):
        return np.degrees(np.arctan2(shapely.get_y(q) - shapely.get_y(p), shapely.get_x(q) - shapely.get_x(p)))
    return rumbo(a, b), rumbo(c, d)


def rumbos(datos: dict) -> tuple[float, float] | None:
    """(rumbo_inicial, rumbo_final) de una arista de la malla; None en las
    demás capas, que no forman parte de ningún giro."""
    if datos.get("overture_id") is None:
        return None
    if datos.get("rumbo_inicial") is not None and datos.get("rumbo_final") is not None:
        return float(datos["rumbo_inicial"]), float(datos["rumbo_final"])
    geometria = datos.get("geometry")
    if geometria is None or geometria.is_empty:
        return None
    inicial, final = _rumbos(np.array([geometria], dtype=object))
    return float(inicial[0]), float(final[0])


def angulo_de_giro(rumbo_llegada: float, rumbo_salida: float) -> float:
    """Cuánto cambia el rumbo al pasar de un tramo al siguiente: 0 = sigue
    derecho, 90 = esquina, 180 = se devuelve por donde vino."""
    return abs((rumbo_llegada - rumbo_salida + 180.0) % 360.0 - 180.0)


def giros_en_u(aristas: Sequence[dict], giro_maximo_grados: float = GIRO_MAXIMO_BUS_GRADOS) -> list[int]:
    """Posiciones de 'aristas' (un camino, en orden) a las que se entra con un
    giro más cerrado que 'giro_maximo_grados' desde la arista anterior."""
    marcadas, anterior = [], None
    for i, d in enumerate(aristas):
        actual = rumbos(d)
        if anterior is not None and actual is not None and angulo_de_giro(anterior[1], actual[0]) > giro_maximo_grados:
            marcadas.append(i)
        anterior = actual
    return marcadas


# --- De las reglas de Overture a aristas de la malla ------------------------------------

def segmento_de(pieza: str, segmentos: set[str]) -> str:
    """Segmento de Overture de una pieza de City2Graph: si el segmento se
    partió, la pieza lleva su id con un sufijo '_<n>'."""
    return pieza if pieza in segmentos else re.sub(r"_\d+$", "", pieza)


def anotar_giros_prohibidos(G: nx.MultiDiGraph, segmentos, alcance: Callable[[dict], str | None]) -> Counter:
    """Traduce las reglas 'prohibited_transitions' de 'segmentos' a aristas
    de G y las guarda en el atributo ATRIBUTO_GIROS de cada arista de llegada.

    Se corre sobre la malla ya podada (sin vías sin salida, componente
    principal): una regla que pasa por un tramo que ya no está no puede
    ocurrir, y se descarta.

    Args:
        G: malla vial con nodos = IDs de conector y aristas con
            'overture_id' y 'reversed' (micro.py).
        segmentos: los segmentos viales de Overture, con 'id', 'connectors'
            y 'prohibited_transitions' ya normalizados a listas/dicts.
        alcance: alcance(regla) -> None si la regla le aplica al bus de
            referencia, o el motivo por el que no (micro.alcance_para_bus).

    Returns:
        Conteo por resultado: 'aplicada', 'fuera de la malla',
        'inconsistente' y 'no aplica: <motivo>'.
    """
    informe = Counter()
    if "prohibited_transitions" not in segmentos.columns:
        return informe
    ids = set(map(str, segmentos["id"]))
    conectores_de = {str(s): {str(c["connector_id"]): float(c["at"]) for c in (cs if isinstance(cs, list) else [])
                              if isinstance(c, dict) and c.get("connector_id") is not None and c.get("at") is not None}
                     for s, cs in zip(segmentos["id"], segmentos["connectors"])}
    por_segmento = defaultdict(list)
    for u, v, k, d in G.edges(keys=True, data=True):
        if d.get("overture_id") is not None:
            por_segmento[segmento_de(str(d["overture_id"]), ids)].append(_Arista(u, v, k, identificador(d)))

    prohibidas = defaultdict(set)  # arista de llegada -> continuaciones
    for segmento, reglas in zip(segmentos["id"], segmentos["prohibited_transitions"]):
        for regla in reglas if isinstance(reglas, list) else []:
            if not isinstance(regla, dict):
                continue
            motivo = alcance(regla)
            if motivo is not None:
                informe[f"no aplica: {motivo}"] += 1
                continue
            pasos = _pasos(regla)
            if pasos is None or not _es_consistente(str(segmento), regla, pasos, conectores_de):
                informe["inconsistente"] += 1
                continue
            if not _en_tramo(regla.get("between"), conectores_de.get(str(segmento), {}).get(pasos[0][0])):
                informe["no aplica: fuera del tramo ('between')"] += 1
                continue
            variantes = _resolver(str(segmento), regla, pasos, por_segmento)
            if not variantes:
                informe["fuera de la malla"] += 1
                continue
            informe["aplicada"] += 1
            for llegada, continuacion in variantes:
                prohibidas[llegada].add(continuacion)

    for llegada, conjunto in prohibidas.items():
        texto = json.dumps(sorted([list(map(list, c)) for c in conjunto]))
        G.edges[llegada.u, llegada.v, llegada.clave][ATRIBUTO_GIROS] = texto
    informe["aristas de llegada"] = len(prohibidas)
    return informe


def _pasos(regla: dict) -> list[tuple[str, str]] | None:
    secuencia = regla.get("sequence")
    if not isinstance(secuencia, list) or not secuencia:
        return None
    pasos = [(p.get("connector_id"), p.get("segment_id")) for p in secuencia if isinstance(p, dict)]
    if len(pasos) != len(secuencia) or any(c is None or s is None for c, s in pasos):
        return None
    return [(str(c), str(s)) for c, s in pasos]


def _es_consistente(segmento: str, regla: dict, pasos: list, conectores_de: dict) -> bool:
    """¿La regla describe un recorrido posible? Cada conector tiene que estar
    en el segmento de antes y en el de después, y los sentidos tienen que
    poder llegar a él / salir de él (no se llega 'hacia adelante' al
    conector del inicio de un segmento). Un segmento que no está en la malla
    (no vehicular) no la hace inconsistente: solo queda fuera."""
    anterior = segmento
    for conector, siguiente in pasos:
        for s in (anterior, siguiente):
            if s in conectores_de and conector not in conectores_de[s]:
                return False
        anterior = siguiente
    llegada, at_llegada = (regla.get("when") or {}).get("heading"), conectores_de.get(segmento, {}).get(pasos[0][0])
    if at_llegada is not None and ((llegada == "forward" and at_llegada <= 0.0) or
                                   (llegada == "backward" and at_llegada >= 1.0)):
        return False
    final, at_final = regla.get("final_heading"), conectores_de.get(pasos[-1][1], {}).get(pasos[-1][0])
    if at_final is not None and ((final == "forward" and at_final >= 1.0) or
                                 (final == "backward" and at_final <= 0.0)):
        return False
    return True


def _en_tramo(entre: list | None, at: float | None) -> bool:
    """Una regla con 'between' aplica si el conector por el que se gira cae
    dentro de ese tramo del segmento de llegada."""
    if not entre or at is None:
        return True
    return float(entre[0]) - 1e-9 <= at <= float(entre[1]) + 1e-9


def _resolver(segmento: str, regla: dict, pasos: list, por_segmento: dict) -> list:
    """Todas las formas de recorrer la regla en la malla, como (arista de
    llegada, continuación). Casi siempre es una; son más si la regla no dice
    por qué sentido se llega."""
    llegada_sentido = (regla.get("when") or {}).get("heading")
    primero = pasos[0][0]
    llegadas = [a for a in por_segmento.get(segmento, ())
                if a.v == primero and (llegada_sentido is None or a.ident[1] == (llegada_sentido == "backward"))]
    tramos = []
    for i, (conector, siguiente) in enumerate(pasos[:-1]):
        """paso intermedio: del conector de este paso al del siguiente, sin salirse del segmento 'siguiente'"""
        tramos.append(_recorridos(por_segmento.get(siguiente, ()), conector, pasos[i + 1][0]))
    conector_final, segmento_final = pasos[-1]
    final = regla.get("final_heading")
    salidas = [a for a in por_segmento.get(segmento_final, ())
               if a.u == conector_final and (final is None or a.ident[1] == (final == "backward"))]
    variantes = []
    for llegada in llegadas:
        for combinacion in itertools.product(*tramos):
            for salida in salidas:
                variantes.append((llegada, tuple(itertools.chain(*combinacion)) + (salida.ident,)))
    return variantes


def _recorridos(aristas: Sequence[_Arista], desde, hasta) -> list[tuple[Identificador, ...]]:
    """Las piezas de un segmento, en orden, para ir de un conector a otro
    sin salirse de él (una lista por cada sentido que llegue)."""
    resultado = []
    for inicio in (a for a in aristas if a.u == desde):
        camino, actual, vistas = [inicio.ident], inicio, {inicio.ident}
        while actual.v != hasta:
            siguientes = [a for a in aristas if a.u == actual.v and a.ident[1] == inicio.ident[1]
                          and a.ident not in vistas]
            if len(siguientes) != 1:
                break
            actual = siguientes[0]
            camino.append(actual.ident)
            vistas.add(actual.ident)
        else:
            resultado.append(tuple(camino))
    return resultado


# --- Ruta que respeta los giros ---------------------------------------------------------

def _avanzar(en_curso: frozenset, ident: Identificador | None, tabla: dict) -> tuple[frozenset, bool]:
    """Giros en curso después de tomar la arista 'ident', y si tomarla
    completa un giro prohibido. Un giro en curso es (arista de llegada,
    número de continuación, posición de la arista que tiene que seguir)."""
    if not en_curso and ident not in tabla:
        return _VACIO, False
    prohibido, nuevos = False, []
    for llegada, j, posicion in en_curso:
        secuencia = tabla[llegada][j]
        if secuencia[posicion] == ident:
            if posicion == len(secuencia) - 1:
                prohibido = True
            else:
                nuevos.append((llegada, j, posicion + 1))
    if ident in tabla:
        nuevos.extend((ident, j, 0) for j in range(len(tabla[ident])))
    return (frozenset(nuevos) if nuevos else _VACIO), prohibido


def camino_respetando_giros(G: nx.MultiDiGraph, origen, destino,
                            peso: Callable[[object, object, dict], float | None], *,
                            aristas: Iterable[tuple] | None = None,
                            giro_maximo_grados: float | None = GIRO_MAXIMO_BUS_GRADOS) -> tuple[list, list, float]:
    """Ruta de menor costo de 'origen' a 'destino' que no hace ningún giro
    prohibido ni gira más de 'giro_maximo_grados' entre dos tramos seguidos
    de la malla (ver el docstring del módulo).

    Args:
        G: grafo dirigido (MultiDiGraph); las aristas de la malla traen
            'overture_id', 'reversed', 'rumbo_inicial'/'rumbo_final' y, si
            de ellas sale algún giro prohibido, ATRIBUTO_GIROS.
        peso: peso(u, v, datos de UNA arista) -> costo, o None si la arista
            no se puede usar.
        aristas: (u, v, clave) permitidas; None = todas las de G.
        giro_maximo_grados: None = sin tope de giro (solo los prohibidos).

    Returns:
        (nodos, claves, costo): los nodos del camino, la clave de la arista
        usada entre cada par de nodos seguidos (entre dos conectores puede
        haber más de una pieza, y la que se puede tomar depende del giro) y
        el costo total.

    Raises:
        nx.NodeNotFound: si el origen o el destino no están en G.
        nx.NetworkXNoPath: si no hay ruta sin giros prohibidos.
    """
    for nodo in (origen, destino):
        if nodo not in G:
            raise nx.NodeNotFound(f"El nodo {nodo} no está en el grafo")
    adyacencia, tabla = defaultdict(list), {}
    fuente = (G.edges(keys=True, data=True) if aristas is None
              else ((u, v, k, G.adj[u][v][k]) for u, v, k in aristas))
    for u, v, k, d in fuente:
        costo = peso(u, v, d)
        if costo is None:
            continue
        ident = identificador(d)
        if ident is not None and d.get(ATRIBUTO_GIROS):
            tabla[ident] = continuaciones(d)
        inicial, final = (rumbos(d) if giro_maximo_grados is not None else None) or (None, None)
        adyacencia[u].append((v, k, costo, ident, inicial, final))

    """estado = (nodo, rumbo con que se llegó, giros prohibidos en curso). El rumbo es None al
     salir del origen y después de una arista que no es de la malla (una transferencia). El
     ciclo está escrito para la velocidad (se recorre ~500.000 veces por ruta en Bogotá): las
     cuentas de angulo_de_giro y el caso sin giros en curso de _avanzar van en línea"""
    inicio = (origen, None, _VACIO)
    distancia, previo = {inicio: 0.0}, {}
    orden = itertools.count()
    cola = [(0.0, next(orden), inicio)]
    sacar, meter, infinito = heapq.heappop, heapq.heappush, math.inf
    tope = giro_maximo_grados
    while cola:
        costo, _, estado = sacar(cola)
        if costo > distancia[estado]:
            continue  # entrada vieja de la cola: este estado ya salió con un costo menor
        nodo, llegada, en_curso = estado
        if nodo == destino:
            return _reconstruir(previo, estado, costo)
        for v, k, w, ident, inicial, final in adyacencia.get(nodo, ()):
            if llegada is not None and inicial is not None and abs((llegada - inicial + 180.0) % 360.0 - 180.0) > tope:
                continue
            if en_curso or ident in tabla:
                siguiente_en_curso, prohibido = _avanzar(en_curso, ident, tabla)
                if prohibido:
                    continue
            else:
                siguiente_en_curso = _VACIO
            siguiente = (v, final, siguiente_en_curso)
            nuevo = costo + w
            if nuevo < distancia.get(siguiente, infinito):
                distancia[siguiente] = nuevo
                previo[siguiente] = (estado, k)
                meter(cola, (nuevo, next(orden), siguiente))
    raise nx.NetworkXNoPath(f"No hay ruta de {origen} a {destino} sin giros prohibidos ni giros en U")


def _reconstruir(previo: dict, estado, costo: float) -> tuple[list, list, float]:
    nodos, claves = [estado[0]], []
    while estado in previo:
        estado, clave = previo[estado]
        nodos.append(estado[0])
        claves.append(clave)
    return nodos[::-1], claves[::-1], costo


def giros_prohibidos_en(aristas: Sequence[dict]) -> list[int]:
    """Posiciones de 'aristas' (los datos de cada arista de un camino, en
    orden) a las que se entra por un giro prohibido. Para revisar una ruta
    calculada sin respetarlos (diagnóstico, pruebas)."""
    tabla = {identificador(d): continuaciones(d) for d in aristas if identificador(d) and continuaciones(d)}
    en_curso, marcadas = _VACIO, []
    for i, d in enumerate(aristas):
        en_curso, prohibido = _avanzar(en_curso, identificador(d), tabla)
        if prohibido:
            marcadas.append(i)
    return marcadas
