"""
Fusión de los grafos Macro (estaciones TransMilenio) y Micro (malla vial)
en un único grafo multicapa, con aristas de transferencia peatonal entre
cada estación y las intersecciones viales que le dan acceso. La construcción la hace
City2Graph; este módulo solo decide qué capas y qué relaciones existen.

Cómo se arma, y por qué así:

  - Separación de IDs. Cada capa es un TIPO DE NODO del grafo heterogéneo
    de City2Graph, y los IDs viven en un espacio de nombres por tipo: un
    nodo macro y uno micro nunca comparten tabla aunque tengan el mismo ID.
    El ID de texto que el resto del proyecto espera ('macro_4107',
    'micro_<id>') lo reconstruye conversion.py al final, a partir del tipo.
    Con OSMnx esto era indispensable (la malla venía numerada 0..N, rango
    que se solapaba por completo con los cod_nodo 2.000-14.005 y pisaba
    estaciones en silencio). Con Overture los nodos viales son IDs GERS de
    texto y la colisión ya no puede darse, pero la separación por tipos se
    mantiene: no depende de qué fuente alimente la capa micro.

  - Transferencias: cada estación se engancha a su conector vial más
    cercano y, además, a todos los que estén a no más de MARGEN_ACCESO_M
    por encima de esa distancia (con tope RADIO_ACCESO_MAX_M; ver
    config.py). Con Overture cada uno de esos nodos es un conector: un
    punto donde la especificación garantiza que se puede pasar de un
    segmento a otro, así que la estación queda enganchada a puntos de
    decisión reales de la red.

    Por qué más de uno: casi todas las estaciones troncales están en el
    separador de una vía de doble calzada, y cada calzada es de un solo
    sentido. Con un único enganche (k=1, como era antes) la estación
    quedaba amarrada a la calzada que cayera más cerca, y una ruta que
    necesitaba salir hacia el otro lado tenía que recorrer la vía hasta un
    retorno y volver: Escuela Militar <-> San Martín medía 4,4 km por la
    malla, contra 588 m si se ignoraban los sentidos. Con varios enganches
    el bus puede salir por cualquiera de las dos calzadas, como en la
    realidad. Los pesos siguen siendo la distancia en metros (caminando),
    así que un enganche más lejano no es gratis: se paga a velocidad de
    caminata.

    Las dos búsquedas las hace bridge_nodes por lotes con un árbol k-d:
    "knn" con k=1 da la distancia mínima de cada estación, y
    "fixed_radius" da los candidatos dentro del tope.

  - Ensamblado: gdf_to_nx sobre los diccionarios de tipos (ver
    conversion.ensamblar_multicapa), que entrega el mismo grafo, arista por
    arista y en el mismo orden de vecinos, que la fusión manual anterior
    (prefijo + nx.compose + nearest_nodes). Eso se verificó en la iteración
    del refactor con un script de comparación que se retiró junto con
    OSMnx; queda en el historial de git.

  - Área de estudio: antes de fusionar se verifica que todas las estaciones
    caigan dentro del bbox con el que se bajó la malla. Una estación por
    fuera no fallaría por sí sola -- se engancharía al conector más cercano
    aunque estuviera a kilómetros --, así que se detiene aquí con un error.
"""
import geopandas as gpd
import networkx as nx
import pandas as pd
import shapely
from city2graph.proximity import bridge_nodes

from integrabog.config import MARGEN_ACCESO_M, RADIO_ACCESO_MAX_M

from integrabog.graph.conversion import (
    COLUMNA_GEOMETRIA_SINTETICA,
    AristasPorTipo,
    NodosPorTipo,
    asegurar_geometrias_validas,
    ensamblar_multicapa,
    grafo_a_capa,
)

"""el tipo de nodo es también el prefijo del ID en el grafo final -- cambiar
 estos nombres cambia 'macro_4107' por otra cosa y rompe a los consumidores"""
TIPO_MACRO = "macro"
TIPO_MICRO = "micro"
CAPA_TRANSFERENCIA = "transferencia"

RELACION_TRONCAL = (TIPO_MACRO, "troncal", TIPO_MACRO)
RELACION_VIAL = (TIPO_MICRO, "vial", TIPO_MICRO)
RELACION_ACCESO = (TIPO_MACRO, CAPA_TRANSFERENCIA, TIPO_MICRO)  # estación -> intersección
RELACION_SALIDA = (TIPO_MICRO, CAPA_TRANSFERENCIA, TIPO_MACRO)  # intersección -> estación


def construir_capas_multicapa(G_macro: nx.DiGraph, G_micro: nx.MultiDiGraph) -> tuple[NodosPorTipo, AristasPorTipo]:
    """Arma el grafo multicapa en su forma tabular (un GeoDataFrame por
    tipo de nodo y por tipo de relación), antes de pasarlo a NetworkX.

    Está separada de construir_grafo_multicapa() porque esta forma es el
    punto de extensión natural del modelo de datos: cualquier columna que
    se agregue a una de estas tablas termina como atributo en el grafo
    final, sin tocar conversion.py, y si solo se conoce para algunas filas
    las demás simplemente no tienen la clave (no quedan con NaN). Por
    ejemplo, para las extensiones previstas (esquemático, no implementado):

        nodos, aristas = construir_capas_multicapa(G_macro, G_micro)
        # centralidad equity-aware: estrato DANE por estación (join espacial)
        nodos["macro"]["estrato"] = gpd.sjoin(nodos["macro"], manzanas_dane, ...)["estrato"]
        # Max-Flow/Min-Cut: capacidad por arista troncal (pasajeros/hora)
        aristas[RELACION_TRONCAL]["capacidad"] = ...
        G = ensamblar_multicapa(nodos, aristas, atributos_grafo=G_micro.graph)

    (Para Max-Flow, ojo: nx.maximum_flow no acepta multigrafos; habrá que
    colapsar las aristas paralelas sumando su capacidad antes de llamarlo.)

    Args:
        G_macro: grafo de estaciones (construir_grafo_macro()).
        G_micro: malla vial consolidada (obtener_malla_vial()).

    Returns:
        (nodos, aristas). Las aristas van en el orden troncal, vial, acceso,
        salida -- el mismo en que la versión anterior las agregaba, para
        que los vecinos de cada nodo queden en el mismo orden y Dijkstra
        desempate igual que antes los caminos de igual costo.
    """
    nodos_macro, aristas_troncal = grafo_a_capa(G_macro, TIPO_MACRO)
    nodos_micro, aristas_viales = grafo_a_capa(G_micro, TIPO_MICRO)
    _verificar_estaciones_en_area(nodos_macro, G_micro.graph.get("area_estudio_bbox"))
    nodos = {TIPO_MACRO: nodos_macro, TIPO_MICRO: nodos_micro}

    acceso, salida = _aristas_transferencia(nodos)
    aristas = {
        RELACION_TRONCAL: aristas_troncal,
        RELACION_VIAL: aristas_viales,
        RELACION_ACCESO: acceso,
        RELACION_SALIDA: salida,
    }
    return nodos, aristas


def construir_grafo_multicapa(G_macro: nx.DiGraph, G_micro: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Combina macro y micro, y agrega aristas de transferencia
    bidireccionales entre cada estación y sus nodos viales de acceso (el
    más cercano y los que estén dentro del margen; ver el docstring del
    módulo), con peso = distancia euclidiana en metros (EPSG:3116).

    Misma firma que antes del refactor.

    Args:
        G_macro: grafo de estaciones de TransMilenio (construir_grafo_macro()).
        G_micro: grafo de malla vial ya consolidado (obtener_malla_vial()).

    Returns:
        Grafo multicapa único (nx.MultiDiGraph): IDs 'macro_<cod_nodo>' y
        'micro_<ID GERS del conector de Overture>', atributo 'layer' en nodos y aristas, y una
        arista de transferencia en cada sentido por cada par
        estación-conector de acceso (al menos uno por estación). Ni
        G_macro ni G_micro se modifican.
    """
    nodos, aristas = construir_capas_multicapa(G_macro, G_micro)
    """atributos de grafo: los de micro pisan a los de macro, como hacía nx.compose --
     en la práctica el macro no trae ninguno y quedan los de la malla (crs, release de Overture, bbox)"""
    return ensamblar_multicapa(nodos, aristas, atributos_grafo={**G_macro.graph, **G_micro.graph})


def _aristas_transferencia(nodos: NodosPorTipo) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Aristas de transferencia peatonal estación <-> conectores de acceso,
    en los dos sentidos (ver el docstring del módulo para el criterio).

    Args:
        nodos: tipos de nodo ya convertidos; tiene que traer TIPO_MACRO y
            TIPO_MICRO.

    Returns:
        (acceso, salida): acceso indexada (estación, intersección, 0),
        salida (intersección, estación, 0), con los mismos pesos. Por cada
        estación, primero su conector más cercano y después los demás por
        distancia creciente.
    """
    """solo macro -> micro: con los tipos por defecto, bridge_nodes también buscaría la
     estación más cercana a CADA intersección (~100.000 aristas que nadie pidió)"""
    tipos = {"source_node_types": [TIPO_MACRO], "target_node_types": [TIPO_MICRO]}
    relacion = (TIPO_MACRO, "is_nearby", TIPO_MICRO)  # "is_nearby" es el nombre fijo que usa City2Graph

    _, mas_cercano = bridge_nodes(nodos, proximity_method="knn", k=1, **tipos)
    _, en_radio = bridge_nodes(nodos, proximity_method="fixed_radius", radius=RADIO_ACCESO_MAX_M, **tipos)
    mas_cercano, en_radio = mas_cercano[relacion], en_radio[relacion]

    """el más cercano entra siempre, aunque esté por encima del tope (un portal grande puede
     quedar a más de RADIO_ACCESO_MAX_M de toda calle): ninguna estación se queda sin acceso"""
    minimo = pd.Series(mas_cercano["weight"].to_numpy(),
                       index=mas_cercano.index.get_level_values(0)).groupby(level=0).min()
    estacion = en_radio.index.get_level_values(0)
    dentro_margen = en_radio["weight"].to_numpy() <= minimo.reindex(estacion).to_numpy() + MARGEN_ACCESO_M
    acceso = pd.concat([mas_cercano, en_radio[dentro_margen]])
    acceso = acceso[~acceso.index.duplicated(keep="first")]

    """orden estable: estación, luego distancia. El conector más cercano queda primero en la
     lista de vecinos de cada estación, como cuando había uno solo"""
    orden = sorted(range(len(acceso)), key=lambda i: (str(acceso.index[i][0]), float(acceso["weight"].iloc[i])))
    acceso = acceso.iloc[orden]

    """round() de Python y no .round() de pandas: redondean distinto los casos en el borde
     (2.675 -> 2.67 vs 2.68), y el peso tiene que ser idéntico al de la versión anterior"""
    acceso = acceso.assign(weight=[round(float(d), 2) for d in acceso["weight"]], layer=CAPA_TRANSFERENCIA)
    acceso[COLUMNA_GEOMETRIA_SINTETICA] = True  # el segmento recto lo dibuja City2Graph, no es un dato
    acceso.index = pd.MultiIndex.from_tuples([(u, v, 0) for u, v in acceso.index])  # key=0: un par estación-conector es único

    """la salida se arma invirtiendo la entrada fila por fila, y no con symmetrize_edges de
     City2Graph: esa función busca el inverso (v, u) DENTRO de la misma tabla, y aquí los IDs
     macro y micro se solapan -- una estación 4107 acoplada a la intersección 900 y una
     estación 900 acoplada a la intersección 4107 se tomarían como inversas una de otra"""
    salida = acceso.copy()
    salida["geometry"] = acceso.geometry.reverse().to_numpy()
    salida.index = acceso.index.swaplevel(0, 1)

    acceso = asegurar_geometrias_validas(acceso, "transferencia macro->micro")
    salida = asegurar_geometrias_validas(salida, "transferencia micro->macro")
    return acceso, salida


def _verificar_estaciones_en_area(nodos_macro: gpd.GeoDataFrame, bbox: list[float] | None) -> None:
    """Ver el último punto del docstring del módulo.

    Args:
        nodos_macro: estaciones, en el CRS métrico del proyecto.
        bbox: G_micro.graph['area_estudio_bbox'] (min_lon, min_lat, max_lon,
            max_lat en WGS84). Si la malla no lo trae, no hay nada que
            verificar.

    Raises:
        ValueError: con los nombres de las estaciones que quedan por fuera.
    """
    if not bbox:
        return
    area = gpd.GeoSeries([shapely.box(*bbox)], crs="EPSG:4326").to_crs(nodos_macro.crs).iloc[0]
    fuera = nodos_macro[~nodos_macro.geometry.within(area)]
    if not fuera.empty:
        raise ValueError(
            f"{len(fuera)} estaciones quedan fuera del área con la que se descargó la malla vial "
            f"{tuple(bbox)}: {fuera.get('nombre', fuera.index).tolist()[:10]}. "
            f"Ampliar AREA_ESTUDIO_BBOX en config.py y regenerar la malla."
        )