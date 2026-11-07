"""
Forma de las aristas del grafo macro, recortada del trazado oficial.

Por qué existe: builder.py, costura.py y cruces.py siempre midieron el
peso de cada arista POR EL TRAZADO (diferencia de posición de arco), pero
no guardaban por dónde pasa. El mapa, sin esa forma, unía las dos
estaciones con una recta: en las curvas la red "cortaba camino" y en las
costuras y cruces aparecían diagonales de más de un kilómetro sobre
manzanas y parques. Con la forma guardada en el atributo 'geometry' de la
arista, el dibujo y el peso salen del mismo recorrido.

Convenciones (las mismas de micro.py para la malla vial):
  - CRS métrico del proyecto (EPSG:3116) y solo 2D: el trazado oficial
    trae una coordenada Z en 0 que no aporta nada.
  - La línea va orientada de u a v. La arista inversa (v, u) lleva la
    misma línea invertida.
  - El largo de la línea coincide con 'weight' (salvo el redondeo a 2
    decimales del peso): si no coincidiera, el mapa estaría mostrando un
    recorrido distinto del que se midió.
"""
import shapely
from shapely.geometry import LineString
from shapely.ops import substring


def tramo_entre(pieza: LineString, s_desde: float, s_hasta: float) -> list[tuple[float, float]]:
    """Coordenadas de la pieza entre dos posiciones de arco, en el sentido
    de s_desde a s_hasta (si s_desde > s_hasta, la pieza se recorre al revés).

    Devuelve una lista y no una geometría porque casi siempre es una parte
    de una arista más larga (costura, cruce) que se arma pegando tramos.
    """
    if abs(s_hasta - s_desde) < 1e-9:
        punto = pieza.interpolate(s_desde)
        return [(punto.x, punto.y)]
    corte = shapely.force_2d(substring(pieza, s_desde, s_hasta))
    return list(corte.coords) if corte.geom_type == "LineString" else [(corte.x, corte.y)]


def unir_tramos(*tramos: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Pega tramos consecutivos en una sola lista de coordenadas.

    Si un tramo no empieza donde terminó el anterior, el salto queda como
    segmento recto: es exactamente el caso de las brechas de digitalización
    que cierra la costura (hasta TOLERANCIA_COSTURA_M) y de la separación
    entre dos troncales en un cruce. Los puntos repetidos en la unión se
    quitan.
    """
    coords: list[tuple[float, float]] = []
    for tramo in tramos:
        for x, y in tramo:
            if coords and abs(coords[-1][0] - x) < 1e-6 and abs(coords[-1][1] - y) < 1e-6:
                continue
            coords.append((x, y))
    return coords


def a_linea(coords: list[tuple[float, float]], respaldo: tuple[tuple[float, float], tuple[float, float]]) -> LineString:
    """LineString válida a partir de las coordenadas armadas.

    Args:
        coords: recorrido ya unido.
        respaldo: (posición de u, posición de v). Se usa solo si el
            recorrido tiene un único punto -- dos estaciones acopladas a la
            misma posición de arco, peso 0 --, porque una LineString de un
            punto es inválida y City2Graph descartaría la arista en
            silencio (ver conversion.asegurar_geometrias_validas).
    """
    if len(coords) >= 2:
        return LineString(coords)
    return LineString(respaldo)


def invertir(linea: LineString) -> LineString:
    """La misma línea recorrida de v a u, para la arista inversa."""
    return LineString(list(linea.coords)[::-1])
