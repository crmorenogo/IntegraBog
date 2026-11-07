"""
Sentido de circulación que Overture no trae: se completa antes de armar la
malla vial (micro.py, después de evaluar las reglas de acceso).

Por qué hace falta: micro.py deja recorrer una pieza en los sentidos que
permiten las reglas de Overture, y eso está bien, pero los datos tienen
huecos. El diagnóstico sobre Bogotá (scripts/diagnostico_sentido.py, release
2026-09-23.1) encontró dos, y el primero produjo la ruta en contravía
reportada entre Toberín y San Mateo:

  1. Calzadas separadas sin sentido. Una avenida con separador son dos
     líneas paralelas con el mismo nombre, cada una de un solo sentido. En
     ~1.800 piezas, una de las dos calzadas viene SIN su regla de sentido
     (140 solo en la Av. Carrera 72), así que el modelo la deja recorrer en
     los dos sentidos: una ruta que llega por la calzada equivocada sigue
     por ella en contravía. En la ruta reportada fueron 3 km de la Av.
     Carrera 72 recién se entra desde la Calle 153.
  2. Rotondas con huecos. Overture sí trae el sentido de la mayoría de las
     rotondas, pero en algunas faltan una o dos piezas del anillo, y por ahí
     la ruta "corta" la rotonda en sentido horario.

Cómo se completa, y por qué así:

  - Calzadas: una pieza de doble sentido (vía arterial, con nombre) que
    tiene al lado, a 5-60 m y paralela, una pieza de UN solo sentido con el
    mismo nombre, toma el sentido contrario al de esa vecina. "Al lado"
    quiere decir que no comparten ningún cruce y que la vecina queda de
    costado (no adelante ni atrás): la pieza siguiente de la misma calle,
    que sigue en línea, no cuenta. Se exige
    además la regla de tránsito por la derecha: recorriendo la pieza en el
    sentido deducido, la otra calzada tiene que quedar a la IZQUIERDA (el
    separador va a la izquierda del conductor). Esa segunda condición es la
    que evita equivocarse con una calzada de servicio que va por fuera y es
    de doble sentido de verdad: en ese caso la vecina queda a la derecha, la
    pieza no se toca y se cuenta como "contradictoria" en el informe. Si las
    dos calzadas vienen sin sentido no se deduce nada: no hay una vecina
    confiable de la cual partir: la geometría sola no distingue una avenida
    con las dos calzadas sin regla de dos calles paralelas de doble sentido.
    Para eso está config.AVENIDAS_CON_SEPARADOR: en las avenidas que alguien
    confirmó que son de calzadas separadas, cada calzada toma el sentido que
    deja a la otra a su izquierda, aunque la otra tampoco traiga regla. La
    primera corrida sobre Bogotá completó 517 piezas con la regla general;
    los 3 km de la Av. Carrera 72 del caso reportado no estaban entre ellas,
    por este motivo.
  - Piezas cortas de una calzada: las de menos de LARGO_MIN_PIEZA_M no se
    revisan con las reglas anteriores (su rumbo es poco confiable), pero si
    son de un segmento de Overture cuyas piezas vecinas sí se completaron,
    toman el mismo sentido que ellas: el sentido de Overture va por segmento,
    y una calzada no cambia de sentido en 10 m. Caso que lo motivó: la última
    pieza de la calzada occidental de la Av. Carrera 72 antes de la Calle 153
    mide 10 m y había quedado de doble sentido; la ruta la usaba para dar la
    vuelta en U.
  - Rotondas: solo se completan las que ya son mayoritariamente de un
    sentido (>= 50 % del anillo, por largo) y antihorarias (>= 90 % de lo que
    tiene sentido). Las demás caras casi circulares de la malla son, en los
    datos de Bogotá, manzanas o parques redondos de varias hectáreas con
    calles de doble sentido (Diagonal 89A, Carrera 115...), y forzarles un
    sentido sería inventar una restricción.
  - A mano: config.SENTIDOS_FORZADOS, al final, por encima de lo deducido.

Todo lo que se cambia queda marcado en la arista ('sentido_inferido':
"calzada separada", "rotonda" o "a mano") y contado en el informe que se
imprime al construir la malla.
"""
import math
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache

import geopandas as gpd
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Point
from shapely.strtree import STRtree

from integrabog.config import AVENIDAS_CON_SEPARADOR, CRS_METRICO, SENTIDOS_FORZADOS

CLASES_CALZADA = frozenset({"motorway", "trunk", "primary", "secondary"})
SEPARACION_CALZADAS_M = (5.0, 60.0)  # menos de 5 m es la misma línea; más de 60 m ya no es la otra calzada
PARALELISMO_MAX_GRADOS = 20.0
DESVIO_LATERAL_MAX_GRADOS = 30.0  # la vecina tiene que estar al lado: a 90° ± 30° del rumbo de la pieza
LARGO_MIN_PIEZA_M = 20.0  # piezas más cortas tienen un rumbo poco confiable

AREA_ROTONDA_M2 = (300.0, 50_000.0)
COMPACIDAD_MIN_ROTONDA = 0.85  # 4·pi·área/perímetro² (1 = círculo perfecto)
FRACCION_MIN_UN_SENTIDO = 0.5
FRACCION_MIN_ANTIHORARIO = 0.9

RUMBOS = {"oriente": 0.0, "norte": 90.0, "occidente": 180.0, "sur": 270.0}  # ángulo matemático (x = este, y = norte)


def completar_sentidos(aristas: gpd.GeoDataFrame,
                       forzados: list[tuple[str, str, str]] = SENTIDOS_FORZADOS,
                       confirmadas: list[dict] | None = None) -> gpd.GeoDataFrame:
    """Quita las filas (sentidos) que sobran según el docstring del módulo.

    Args:
        aristas: una fila por sentido circulable de cada pieza, como las deja
            micro._aristas_dirigidas(): 'overture_id' identifica la pieza,
            'reversed' dice si la fila va contra el sentido de dibujo, y la
            geometría va orientada en el sentido de circulación.
        forzados: ver config.SENTIDOS_FORZADOS.
        confirmadas: ver config.AVENIDAS_CON_SEPARADOR (None = la de config).

    Returns:
        Las aristas sin los sentidos descartados, con 'oneway' y 'key'
        recalculados y la columna 'sentido_inferido'.
    """
    aristas = aristas.reset_index(drop=True).copy()
    aristas["sentido_inferido"] = None
    filas = defaultdict(list)
    for indice, pieza in enumerate(aristas["overture_id"].to_numpy()):
        filas[pieza].append(indice)

    quitar, marcas = set(), {}
    informe = Counter()
    _calzadas_separadas(aristas, filas, quitar, marcas, informe, confirmadas)
    _piezas_cortas(aristas, filas, quitar, marcas, informe)
    _rotondas_con_huecos(aristas, filas, quitar, marcas, informe)
    _sentidos_forzados(aristas, filas, forzados, quitar, marcas, informe)

    for indice, marca in marcas.items():
        aristas.at[indice, "sentido_inferido"] = marca
    resultado = aristas.drop(index=sorted(quitar)).reset_index(drop=True)
    resultado["oneway"] = resultado.groupby("overture_id")["overture_id"].transform("size").to_numpy() == 1
    if "key" in resultado:
        resultado["key"] = resultado.groupby(["u", "v"], sort=False).cumcount()

    print(f"  Sentido completado: calzadas separadas {informe['calzada']} piezas "
          f"+ {informe['calzada_confirmada']} en avenidas confirmadas "
          f"+ {informe['pieza_corta']} piezas cortas de esas calzadas "
          f"(de {informe['calzada_revisada']} piezas arteriales de doble sentido revisadas; "
          f"con la otra calzada también sin regla, en avenidas no confirmadas: {informe['calzada_vecina_doble']}; "
          f"con la vecina del lado equivocado: {informe['calzada_contradictoria']}) | "
          f"rotondas {informe['rotonda']} piezas en {informe['rotondas_completadas']} rotondas "
          f"({informe['caras_redondas_sin_tocar']} caras redondas de doble sentido sin tocar) | "
          f"a mano {informe['forzado']}")
    return resultado


# --- Geometría ------------------------------------------------------------------------

def sentido_alrededor(linea, centro: Point) -> str:
    """'antihorario' si al recorrer la línea el centro queda a la izquierda
    (sentido de circulación de una rotonda en Colombia), 'horario' si queda
    a la derecha. Suma del área con signo de los triángulos centro-p_i-p_i+1."""
    coords = np.asarray(linea.coords)[:, :2] - (centro.x, centro.y)
    area = np.sum(coords[:-1, 0] * coords[1:, 1] - coords[1:, 0] * coords[:-1, 1])
    return "antihorario" if area > 0 else "horario"


def _tangente(linea, distancia: float) -> np.ndarray | None:
    """Vector unitario del sentido de la línea alrededor de una distancia
    sobre ella (±5 m: un vértice suelto no cambia el rumbo)."""
    a = linea.interpolate(max(0.0, distancia - 5.0))
    b = linea.interpolate(min(linea.length, distancia + 5.0))
    v = np.array([b.x - a.x, b.y - a.y])
    norma = math.hypot(*v)
    return v / norma if norma > 0 else None


def _dibujo(aristas: gpd.GeoDataFrame, indices: list[int]):
    """Geometría de la pieza en el sentido de dibujo de Overture."""
    for i in indices:
        if not aristas.at[i, "reversed"]:
            return aristas.geometry.iat[i]
    return aristas.geometry.iat[indices[0]].reverse()


def _vigentes(filas: dict, pieza: str, quitar: set) -> list[int]:
    return [i for i in filas[pieza] if i not in quitar]


@lru_cache(maxsize=65536)
def normalizar_nombre(nombre) -> str:
    """Minúsculas, sin tildes y con un solo espacio entre palabras."""
    if not isinstance(nombre, str):
        return ""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", nombre) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


# --- 1. Calzadas separadas ------------------------------------------------------------

def _calzadas_separadas(aristas, filas, quitar, marcas, informe, confirmadas=None, motivos=None) -> None:
    """Regla 1 y regla 2 del docstring del módulo.

    Args:
        confirmadas: avenidas de calzadas separadas confirmadas a mano (ver
            config.AVENIDAS_CON_SEPARADOR); None = la de config.
        motivos: si se pasa un dict, se llena con {pieza: motivo} para cada
            pieza arterial de doble sentido revisada ('completada',
            'completada (avenida confirmada)', 'contradictoria',
            'vecina de doble sentido', 'sin vecina'). Lo usa el diagnóstico.
    """
    confirmadas = _zonas_confirmadas(AVENIDAS_CON_SEPARADOR if confirmadas is None else confirmadas)
    clases = aristas["class"].to_numpy()
    nombres = [normalizar_nombre(n) for n in aristas["name"].to_numpy()] if "name" in aristas else [""] * len(aristas)
    nodos_u, nodos_v = aristas["u"].to_numpy(), aristas["v"].to_numpy()

    un_sentido, dobles, candidatas = [], [], []
    for pieza, indices in filas.items():
        i = indices[0]
        if clases[i] not in CLASES_CALZADA or not nombres[i]:
            continue
        if len(indices) == 1:
            un_sentido.append((i, aristas.geometry.iat[i]))  # ya orientada en su sentido de circulación
        elif len(indices) == 2:
            dobles.append((i, _dibujo(aristas, indices)))
            candidatas.append(pieza)
    if not candidatas:
        return
    indice_un_sentido = _Vecinas(un_sentido, nombres, nodos_u, nodos_v)
    indice_dobles = _Vecinas(dobles, nombres, nodos_u, nodos_v)

    for pieza in candidatas:
        indices = filas[pieza]
        dibujo = _dibujo(aristas, indices)
        if dibujo.length < LARGO_MIN_PIEZA_M:
            continue
        mitad = dibujo.length / 2
        medio = dibujo.interpolate(mitad)
        t_p = _tangente(dibujo, mitad)
        if t_p is None:
            continue
        informe["calzada_revisada"] += 1
        propios = {nodos_u[i] for i in indices} | {nodos_v[i] for i in indices}
        nombre = nombres[indices[0]]

        """regla 1: la otra calzada sí trae su sentido, y esta toma el contrario"""
        vecina = indice_un_sentido.mas_cercana(medio, t_p, nombre, propios)
        if vecina is not None:
            hacia_vecina, t_q = vecina
            ida = float(np.dot(t_p, t_q)) < 0  # la vecina va al revés del dibujo: esta pieza va como se dibujó
            t = t_p if ida else -t_p
            if t[0] * hacia_vecina[1] - t[1] * hacia_vecina[0] <= 0:  # la vecina quedaría a la derecha
                informe["calzada_contradictoria"] += 1
                _anotar(motivos, pieza, "contradictoria")
                continue
            _conservar(aristas, indices, ida, quitar, marcas, "calzada separada")
            informe["calzada"] += 1
            _anotar(motivos, pieza, "completada")
            continue

        """regla 2: las dos calzadas vienen sin sentido. Solo en una avenida confirmada a
         mano, y solo con la regla del separador: esta calzada va en el sentido que deja a
         la otra a su izquierda"""
        vecina = indice_dobles.mas_cercana(medio, t_p, nombre, propios)
        if vecina is None:
            _anotar(motivos, pieza, "sin vecina")  # de doble sentido de verdad
            continue
        if not _es_confirmada(confirmadas, nombre, medio):
            informe["calzada_vecina_doble"] += 1
            _anotar(motivos, pieza, "vecina de doble sentido")
            continue
        hacia_vecina, _ = vecina
        ida = t_p[0] * hacia_vecina[1] - t_p[1] * hacia_vecina[0] > 0  # la otra a la izquierda del dibujo
        _conservar(aristas, indices, ida, quitar, marcas, "calzada separada (avenida confirmada)")
        informe["calzada_confirmada"] += 1
        _anotar(motivos, pieza, "completada (avenida confirmada)")


class _Vecinas:
    """Índice espacial de piezas candidatas a ser 'la otra calzada'."""

    def __init__(self, piezas: list[tuple[int, object]], nombres, nodos_u, nodos_v):
        self.filas = [i for i, _ in piezas]
        self.geometrias = [g for _, g in piezas]
        self.arbol = STRtree(self.geometrias) if piezas else None
        self.nombres, self.nodos_u, self.nodos_v = nombres, nodos_u, nodos_v
        self.paralelo_min = math.cos(math.radians(PARALELISMO_MAX_GRADOS))
        self.de_lado_max = math.cos(math.radians(90 - DESVIO_LATERAL_MAX_GRADOS))

    def mas_cercana(self, medio: Point, t_p: np.ndarray, nombre: str, propios: set):
        """(vector hacia la vecina, rumbo de la vecina) de la calzada vecina más
        cercana, o None: mismo nombre, 5-60 m, paralela, de costado y sin ningún
        cruce en común con la pieza."""
        if self.arbol is None:
            return None
        mejor = None
        for j in self.arbol.query(medio.buffer(SEPARACION_CALZADAS_M[1])):  # 'dwithin' exige Shapely 2.1
            fila, q = self.filas[j], self.geometrias[j]
            if self.nombres[fila] != nombre:
                continue
            """la pieza siguiente de la MISMA calle (comparte un cruce con esta) no es la otra
             calzada: si una calle pasa de doble a un solo sentido en un cruce, su pieza de un
             sentido queda en línea y a pocos metros, y sin esta condición le contagiaría el
             sentido a la de doble. También excluye a la pieza misma"""
            if {self.nodos_u[fila], self.nodos_v[fila]} & propios:
                continue
            distancia = q.distance(medio)
            if not SEPARACION_CALZADAS_M[0] <= distancia <= SEPARACION_CALZADAS_M[1]:
                continue
            s_q = q.project(medio)
            t_q = _tangente(q, s_q)
            if t_q is None or abs(float(np.dot(t_p, t_q))) < self.paralelo_min:
                continue
            punto_q = q.interpolate(s_q)
            hacia_vecina = np.array([punto_q.x - medio.x, punto_q.y - medio.y])
            if abs(float(np.dot(hacia_vecina / distancia, t_p))) > self.de_lado_max:
                continue  # la vecina queda adelante o atrás, no al lado
            if mejor is None or distancia < mejor[0]:
                mejor = (distancia, hacia_vecina, t_q)
        return None if mejor is None else mejor[1:]


def _conservar(aristas, indices, ida: bool, quitar, marcas, marca: str) -> None:
    """Deja solo el sentido del dibujo (ida) o solo el contrario."""
    for i in indices:
        if bool(aristas.at[i, "reversed"]) == ida:  # la fila del sentido descartado
            quitar.add(i)
        else:
            marcas[i] = marca


def _anotar(motivos, pieza, motivo: str) -> None:
    if motivos is not None:
        motivos[pieza] = motivo


_A_METRICO = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)


def _zonas_confirmadas(confirmadas: list[dict]) -> list[tuple[str, Point | None, float]]:
    """(nombre normalizado, centro de la zona o None, radio) de cada avenida confirmada."""
    zonas = []
    for entrada in confirmadas:
        nombre = normalizar_nombre(entrada.get("nombre"))
        if not nombre:
            raise ValueError(f"AVENIDAS_CON_SEPARADOR: la entrada {entrada} no trae 'nombre'.")
        centro = None
        if entrada.get("cerca_de"):
            lat, lon = entrada["cerca_de"]
            centro = Point(*_A_METRICO.transform(lon, lat))
        zonas.append((nombre, centro, float(entrada.get("radio_m", 0.0))))
    return zonas


def _es_confirmada(zonas, nombre: str, punto: Point) -> bool:
    return any(nombre == z_nombre and (centro is None or punto.distance(centro) <= radio)
               for z_nombre, centro, radio in zonas)


def motivos_calzadas(aristas: gpd.GeoDataFrame, confirmadas: list[dict] | None = None) -> dict:
    """Por qué cada pieza arterial de doble sentido quedó así: {pieza: motivo}
    (ver _calzadas_separadas). No cambia nada; es para el diagnóstico, que lo
    corre sobre la malla ya construida para explicar las que siguen de doble
    sentido."""
    aristas = aristas.reset_index(drop=True)
    filas = defaultdict(list)
    for indice, pieza in enumerate(aristas["overture_id"].to_numpy()):
        filas[pieza].append(indice)
    motivos = {}
    _calzadas_separadas(aristas, filas, set(), {}, Counter(), confirmadas, motivos)
    return motivos


# --- 1b. Piezas cortas de una calzada completada --------------------------------------

_PIEZA_DE_SEGMENTO = re.compile(r"^(.+)_(\d+)$")  # City2Graph: '<id del segmento>_<n>' si lo partió


def _piezas_cortas(aristas, filas, quitar, marcas, informe) -> None:
    """Regla de las piezas cortas (docstring del módulo). Una pieza corta de
    doble sentido toma el sentido de sus piezas vecinas del mismo segmento
    (las que comparten un conector con ella) si todas las que tienen sentido
    lo recibieron de las reglas de calzada y en la misma orientación respecto
    al dibujo. Si una vecina es de doble sentido larga, o de un solo sentido
    por los datos, la calzada no es continua ahí y no se toca. Se repite
    hasta que no cambie nada, para las cadenas de varias piezas cortas."""
    piezas_de = aristas["overture_id"].to_numpy()

    def segmento(pieza) -> str | None:
        coincide = _PIEZA_DE_SEGMENTO.match(str(pieza))
        return coincide.group(1) if coincide else None

    """solo los segmentos con alguna pieza completada por las reglas de calzada (unos cientos de
     los ~100.000 de Bogotá); el resto no puede tener una pieza corta que completar"""
    con_calzada = {segmento(piezas_de[i]) for i, marca in marcas.items() if str(marca).startswith("calzada separada")}
    con_calzada.discard(None)
    if not con_calzada:
        return
    por_segmento = defaultdict(list)
    for pieza in filas:
        s = segmento(pieza)
        if s in con_calzada:
            por_segmento[s].append(pieza)
    clases, invertidas = aristas["class"].to_numpy(), aristas["reversed"].to_numpy()
    nodos_u, nodos_v = aristas["u"].to_numpy(), aristas["v"].to_numpy()

    def estado(pieza) -> str:
        """'F' / 'B': un solo sentido deducido por las reglas de calzada, a favor o en contra
         del dibujo; 'corta': candidata; 'otra': cualquier otra cosa"""
        vigentes = _vigentes(filas, pieza, quitar)
        if len(vigentes) == 1 and str(marcas.get(vigentes[0], "")).startswith("calzada separada"):
            return "B" if invertidas[vigentes[0]] else "F"
        if (len(vigentes) == 2 and clases[vigentes[0]] in CLASES_CALZADA
                and _dibujo(aristas, vigentes).length < LARGO_MIN_PIEZA_M):
            return "corta"
        return "otra"

    for piezas in por_segmento.values():
        if len(piezas) < 2:
            continue
        conectores = {p: {nodos_u[i] for i in filas[p]} | {nodos_v[i] for i in filas[p]} for p in piezas}
        estados = {p: estado(p) for p in piezas}
        cambio = True
        while cambio:
            cambio = False
            for p in [p for p in piezas if estados[p] == "corta"]:
                vecinas = {estados[q] for q in piezas if q != p and conectores[q] & conectores[p]}
                sentidos = vecinas & {"F", "B"}
                if "otra" in vecinas or len(sentidos) != 1:
                    continue
                sentido = sentidos.pop()
                _conservar(aristas, _vigentes(filas, p, quitar), sentido == "F", quitar, marcas,
                           "calzada separada (pieza corta)")
                estados[p], cambio = sentido, True
                informe["pieza_corta"] += 1


# --- 2. Rotondas con huecos -----------------------------------------------------------

def _rotondas_con_huecos(aristas, filas, quitar, marcas, informe) -> None:
    piezas = list(filas)
    posicion = {p: k for k, p in enumerate(piezas)}
    lineas = [_dibujo(aristas, filas[p]) for p in piezas]
    caras = [c for c in shapely.get_parts(shapely.polygonize(lineas))
             if AREA_ROTONDA_M2[0] <= c.area <= AREA_ROTONDA_M2[1]
             and 4 * math.pi * c.area / c.length ** 2 >= COMPACIDAD_MIN_ROTONDA]
    if not caras:
        return
    arbol = STRtree(lineas)
    for cara in caras:
        borde = [piezas[j] for j in arbol.query(cara.exterior.buffer(1.0), predicate="contains")]
        if not borde:
            continue
        centro = cara.centroid
        largo = {p: lineas[posicion[p]].length for p in borde}
        total = sum(largo.values())
        un_sentido = [p for p in borde if len(_vigentes(filas, p, quitar)) == 1]
        dobles = [p for p in borde if len(_vigentes(filas, p, quitar)) == 2]
        if not dobles:
            continue
        largo_un_sentido = sum(largo[p] for p in un_sentido)
        antihorario = sum(largo[p] for p in un_sentido
                          if sentido_alrededor(aristas.geometry.iat[_vigentes(filas, p, quitar)[0]], centro)
                          == "antihorario")
        if (total == 0 or largo_un_sentido / total < FRACCION_MIN_UN_SENTIDO
                or antihorario / largo_un_sentido < FRACCION_MIN_ANTIHORARIO):
            informe["caras_redondas_sin_tocar"] += 1
            continue
        for p in dobles:
            for i in _vigentes(filas, p, quitar):
                if sentido_alrededor(aristas.geometry.iat[i], centro) == "horario":
                    quitar.add(i)
                else:
                    marcas[i] = "rotonda"
            informe["rotonda"] += 1
        informe["rotondas_completadas"] += 1


# --- 3. A mano ------------------------------------------------------------------------

def _rumbo_grados(linea) -> float:
    (x0, y0), (x1, y1) = linea.coords[0][:2], linea.coords[-1][:2]
    return math.degrees(math.atan2(y1 - y0, x1 - x0)) % 360


def _sentidos_forzados(aristas, filas, forzados, quitar, marcas, informe) -> None:
    """Va al final y por encima de lo deducido: si una corrección a mano pide
    un sentido que la deducción había quitado, se recupera."""
    for overture_id, sentido, motivo in forzados:
        piezas = [p for p in filas if p == overture_id or re.sub(r"_\d+$", "", str(p)) == overture_id]
        if not piezas:
            print(f"[ADVERTENCIA] SENTIDOS_FORZADOS: no hay ningún tramo con id '{overture_id}' en la malla "
                  f"(¿cambió el release de Overture?). Motivo anotado: {motivo}")
            continue
        sentido = sentido.strip().lower()
        if sentido != "ninguno" and sentido not in RUMBOS:
            raise ValueError(f"SENTIDOS_FORZADOS: sentido '{sentido}' no válido para '{overture_id}'. "
                             f"Usar uno de {sorted(RUMBOS) + ['ninguno']}.")
        for p in piezas:
            indices = filas[p]
            if sentido == "ninguno":
                conservar = []
            else:
                conservar = [i for i in indices
                             if abs((_rumbo_grados(aristas.geometry.iat[i]) - RUMBOS[sentido] + 180) % 360 - 180) < 90]
                if not conservar:
                    print(f"[ADVERTENCIA] SENTIDOS_FORZADOS: el tramo '{p}' no tiene ningún sentido de "
                          f"circulación hacia el {sentido}; no se cambia.")
                    continue
            quitar.difference_update(indices)
            quitar.update(i for i in indices if i not in conservar)
            for i in conservar:
                marcas[i] = "a mano"
            informe["forzado"] += 1
