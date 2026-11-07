"""
Traducción entre los dos modelos de grafo que conviven en el proyecto desde
que la capa de construcción usa City2Graph:

- El contrato IntegraBog: un nx.MultiDiGraph con IDs de nodo como texto con
  prefijo de capa ('macro_4107', 'micro_123'), atributo 'layer' en nodos y
  aristas, y la posición de cada nodo en 'x'/'y' (EPSG:3116). Es lo que
  consumen routing/network_design.py, diagnostico.py, la API y los scripts.

- El modelo heterogéneo de City2Graph: un GeoDataFrame de nodos por tipo
  (dict[str, GeoDataFrame]) y uno de aristas por tipo de relación
  (dict[(tipo_origen, relación, tipo_destino), GeoDataFrame]). Es el que
  usan sus utilidades de proximidad (bridge_nodes) y de ensamblado
  (gdf_to_nx).

Por qué hace falta una conversión explícita y no basta con gdf_to_nx(): en
el modelo heterogéneo los IDs viven en un espacio de nombres por tipo -- el
4107 macro y el 4107 micro están en tablas distintas y no pueden pisarse,
que es justo lo que antes había que garantizar a mano con un prefijo. Pero
al pasar a NetworkX, City2Graph reetiqueta TODOS los nodos como enteros
0..N y deja el ID real repartido en dos atributos ('node_type' y
'_original_index'). Ese grafo es correcto, pero rompe a todo el que hoy
busca 'macro_4107' por nombre. multicapa_a_contrato() lo devuelve a la forma
del contrato, y el resto del proyecto no se entera del cambio de librería.

La vuelta por GeoDataFrame tiene además dos efectos secundarios que este
módulo neutraliza a propósito, porque ninguno avisa con un error:

  1. Celdas vacías. Una tabla obliga a que todas las filas tengan las mismas
     columnas, así que un atributo que solo existía en algunas aristas (por
     ejemplo tipo='costura' en el macro, o 'name' en la malla vial) vuelve
     como NaN en todas las demás. Dejarlo así cambia el significado: hoy
     routes.py lee nom_tronc con .get() y espera None cuando falta; con NaN,
     Pydantic rechazaría la respuesta. Al volver al grafo se eliminan esas
     celdas vacías -- "atributo ausente" sigue siendo "la clave no existe".

  2. Geometrías inventadas. City2Graph necesita una geometría por arista y,
     cuando la arista no traía una, dibuja la recta entre sus dos nodos. Esa
     recta no es un dato, así que se marca (COLUMNA_GEOMETRIA_SINTETICA) y
     se quita al volver. Y si la recta sale degenerada (un autobucle sin
     geometría propia da un LineString de dos puntos iguales), la validación
     interna de City2Graph DESCARTA la fila en silencio, con solo un warning
     en el log: se perdería una arista real sin ningún error.
     asegurar_geometrias_validas() le pone a esas filas un sustituto válido
     que se deshace al volver, y ensamblar_multicapa() compara conteos
     antes y después como red de seguridad ante cualquier otro descarte.
"""
import math
from collections import defaultdict

import geopandas as gpd
import networkx as nx
import pandas as pd
from city2graph.utils import gdf_to_nx, nx_to_gdf
from pyproj import CRS
from shapely.geometry import LineString

from integrabog.config import CRS_METRICO

NodosPorTipo = dict[str, gpd.GeoDataFrame]
AristasPorTipo = dict[tuple[str, str, str], gpd.GeoDataFrame]

"""columna booleana por arista: True si su geometría la construyó City2Graph (o este
 módulo) y no venía en el dato fuente -- se elimina antes de entregar el grafo"""
COLUMNA_GEOMETRIA_SINTETICA = "_geometria_sintetica"
"""solo existe si alguna geometría del dato fuente era inválida: guarda la original
 mientras un sustituto válido viaja por City2Graph (ver asegurar_geometrias_validas)"""
COLUMNA_GEOMETRIA_ORIGINAL = "_geometria_original_invalida"

"""atributos que City2Graph agrega para su propia contabilidad; ninguno es parte del
 contrato. 'geometry' de nodo también sale: la posición canónica es (x, y), y tener
 dos fuentes de verdad para lo mismo es invitar a que se desincronicen"""
_INTERNOS_NODO = frozenset({"pos", "geometry", "node_type", "_original_index"})
_INTERNOS_ARISTA = frozenset({"edge_type", "_original_edge_index",
                              COLUMNA_GEOMETRIA_SINTETICA, COLUMNA_GEOMETRIA_ORIGINAL})

_DESPLAZAMIENTO_SUSTITUTO_M = 0.01  # largo del segmento sustituto; nunca llega al grafo final


def grafo_a_capa(G: nx.Graph, capa: str) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Convierte un grafo de una sola capa (macro o micro) en la pareja de
    GeoDataFrames (nodos, aristas) con la que City2Graph representa un tipo
    de nodo y su relación interna.

    Args:
        G: grafo de una sola capa, con 'x' e 'y' en cada nodo. No se
            modifica -- nx_to_gdf escribe 'pos' en los nodos del grafo que
            recibe, por eso se trabaja sobre una copia.
        capa: nombre de la capa; se guarda en la columna 'layer' de nodos
            y aristas, que es de donde sale el atributo 'layer' del grafo
            final.

    Returns:
        (nodos, aristas). Nodos indexados por su ID original. Aristas
        indexadas siempre por (u, v, key), aunque G no sea multigrafo: el
        DiGraph macro no tiene claves, y sin el tercer nivel gdf_to_nx las
        numeraría 0..N en vez de dejar key=0 por par, como hacía la
        conversión DiGraph -> MultiDiGraph anterior.

    Raises:
        ValueError: si G declara un CRS distinto de CRS_METRICO, o si algún
            nodo no tiene coordenadas válidas -- sin posición no hay
            transferencia posible, y eso es un problema del dato, no algo
            que convenga tapar.
    """
    _verificar_crs(G, capa)

    G_trabajo = G.copy()
    G_trabajo.graph["crs"] = CRS_METRICO  # el DiGraph de builder.py no trae CRS propio
    for *_, datos in G_trabajo.edges(data=True):
        datos[COLUMNA_GEOMETRIA_SINTETICA] = "geometry" not in datos

    nodos, aristas = nx_to_gdf(G_trabajo)

    nodos_invalidos = nodos.geometry.isna() | nodos.geometry.is_empty | ~nodos.geometry.is_valid
    if nodos_invalidos.any():
        raise ValueError(f"Capa '{capa}': {int(nodos_invalidos.sum())} nodos sin coordenadas válidas, "
                         f"p. ej. {list(nodos.index[nodos_invalidos][:5])}")

    if aristas.index.nlevels == 2:
        aristas.index = pd.MultiIndex.from_tuples([(u, v, 0) for u, v in aristas.index])

    aristas = asegurar_geometrias_validas(aristas, capa)
    nodos["layer"] = capa
    aristas["layer"] = capa
    return nodos, aristas


def asegurar_geometrias_validas(aristas: gpd.GeoDataFrame, contexto: str) -> gpd.GeoDataFrame:
    """Garantiza que ninguna fila de 'aristas' sea descartada por la
    validación interna de City2Graph (ver punto 2 del docstring del módulo).

    Toda geometría inválida viaja por City2Graph con un sustituto válido (un
    segmento mínimo que arranca en el mismo punto). Al volver al grafo:
      - si era sintética, simplemente desaparece, como cualquier sintética;
      - si venía en el dato fuente, se restaura TAL CUAL desde
        COLUMNA_GEOMETRIA_ORIGINAL. NetworkX nunca validó geometrías, así
        que la versión anterior la aceptaba; rechazarla ahora sería una
        regresión, y descartarla, perder un dato.

    Args:
        aristas: GeoDataFrame de aristas con la columna
            COLUMNA_GEOMETRIA_SINTETICA.
        contexto: nombre de la capa o relación, para los mensajes.

    Returns:
        'aristas' tal cual si no había nada inválido; si no, una copia con
        los sustitutos puestos.

    Raises:
        ValueError: si una arista inválida no tiene ni un punto del cual
            partir (geometría nula o vacía) -- solo pasa si sus nodos no
            tienen 'x'/'y', lo que grafo_a_capa ya habría rechazado antes.
    """
    invalida = aristas.geometry.isna() | aristas.geometry.is_empty | ~aristas.geometry.is_valid
    if not invalida.any():
        return aristas

    aristas = aristas.copy()
    originales = invalida & ~aristas[COLUMNA_GEOMETRIA_SINTETICA].astype(bool)
    if originales.any():
        print(f"[AVISO] '{contexto}': {int(originales.sum())} aristas traen una geometría inválida desde "
              f"el dato fuente (p. ej. {list(aristas.index[originales][:3])}). Se conservan tal cual; "
              f"usadas directo en City2Graph se habrían descartado.")
        aristas[COLUMNA_GEOMETRIA_ORIGINAL] = pd.Series(
            [geom if es_original else None for geom, es_original in zip(aristas.geometry, originales)],
            index=aristas.index, dtype=object,
        )

    sustitutos = []
    for indice, geom in aristas.geometry[invalida].items():
        if geom is None or geom.is_empty:
            raise ValueError(f"'{contexto}': la arista {indice} no tiene ninguna geometría de la cual "
                             f"partir; revisar que sus dos nodos tengan 'x' e 'y'.")
        x, y = geom.coords[0]
        sustitutos.append(LineString([(x, y), (x + _DESPLAZAMIENTO_SUSTITUTO_M, y)]))
    aristas.loc[invalida, "geometry"] = gpd.GeoSeries(sustitutos, index=aristas.index[invalida], crs=aristas.crs)
    return aristas


def ensamblar_multicapa(nodos: NodosPorTipo, aristas: AristasPorTipo,
                        atributos_grafo: dict | None = None) -> nx.MultiDiGraph:
    """Ensambla los tipos de nodo y de relación en un solo grafo con
    City2Graph (gdf_to_nx) y lo entrega ya en la forma del contrato.

    Args:
        nodos: un GeoDataFrame por tipo de nodo, indexado por ID original.
        aristas: un GeoDataFrame por tipo de relación (origen, relación,
            destino), indexado por (u, v, key). Las aristas se agregan en
            el orden del diccionario, y ese orden define el de los vecinos
            de cada nodo -- que es el que usa Dijkstra para desempatar
            caminos de igual costo. Ver multilayer.py.
        atributos_grafo: atributos a nivel de grafo (G.graph) del
            resultado, p. ej. el CRS y los metadatos de la malla vial.

    Returns:
        nx.MultiDiGraph con el contrato IntegraBog (ver
        multicapa_a_contrato).

    Raises:
        RuntimeError: si el grafo ensamblado no tiene exactamente los
            nodos y aristas que entraron -- City2Graph descarta filas con
            solo un warning en el log, y esto lo convierte en un error.
    """
    nodos_esperados = sum(len(gdf) for gdf in nodos.values())
    aristas_esperadas = sum(len(gdf) for gdf in aristas.values())

    G_heterogeneo = gdf_to_nx(nodes=nodos, edges=aristas, multigraph=True, directed=True)

    if (G_heterogeneo.number_of_nodes(), G_heterogeneo.number_of_edges()) != (nodos_esperados, aristas_esperadas):
        raise RuntimeError(
            f"City2Graph descartó elementos al ensamblar: entraron {nodos_esperados} nodos / "
            f"{aristas_esperadas} aristas y salieron {G_heterogeneo.number_of_nodes()} / "
            f"{G_heterogeneo.number_of_edges()}. Revisar el log de city2graph para ver cuáles."
        )
    return multicapa_a_contrato(G_heterogeneo, atributos_grafo)


def multicapa_a_contrato(G_heterogeneo: nx.MultiDiGraph, atributos_grafo: dict | None = None) -> nx.MultiDiGraph:
    """Función de conversión explícita: grafo heterogéneo de City2Graph ->
    contrato IntegraBog.

    - ID de nodo: el entero consecutivo de City2Graph pasa a ser
      '{node_type}_{_original_index}', es decir, el mismo 'macro_4107' /
      'micro_123' que producía el prefijo manual anterior.
    - Atributos: se eliminan los internos de City2Graph, las celdas vacías
      y las geometrías sintéticas (ver docstring del módulo). Todo lo demás
      pasa tal cual, incluida cualquier columna nueva que se haya agregado
      a una capa -- por eso extender el modelo de datos no requiere tocar
      esta función.

    Args:
        G_heterogeneo: salida de city2graph gdf_to_nx(..., multigraph=True,
            directed=True) sobre diccionarios de tipos.
        atributos_grafo: ver ensamblar_multicapa.

    Returns:
        nx.MultiDiGraph nuevo; G_heterogeneo no se modifica.

    Raises:
        ValueError: si algún nodo no trae 'node_type'/'_original_index' (el
            grafo no viene de un ensamblado heterogéneo), o si dos nodos
            terminan con el mismo ID -- la colisión que todo este
            mecanismo existe para evitar.
    """
    G = nx.MultiDiGraph()
    G.graph.update(atributos_grafo or {})

    id_contrato = {}
    for nodo, datos in G_heterogeneo.nodes(data=True):
        if "node_type" not in datos or "_original_index" not in datos:
            raise ValueError(f"El nodo {nodo!r} no trae 'node_type'/'_original_index': "
                             f"el grafo no viene de gdf_to_nx sobre tipos de nodo.")
        nuevo_id = f"{datos['node_type']}_{datos['_original_index']}"
        if nuevo_id in G:
            raise ValueError(f"Colisión de IDs al convertir: '{nuevo_id}' aparece dos veces.")
        id_contrato[nodo] = nuevo_id
        G.add_node(nuevo_id, **_limpiar(datos, _INTERNOS_NODO))

    """las aristas se vuelven a agregar TIPO POR TIPO, en el orden en que se ensamblaron, y no
     en el orden de G.edges() (que recorre nodo origen por nodo origen): así cada nodo conserva
     el orden de sus predecesores. Recorriéndolas por origen, la estación quedaba ANTES que las
     calles entre los predecesores de su intersección -- mismo grafo, pero otro desempate en
     Dijkstra cuando dos caminos cuestan exactamente lo mismo"""
    aristas_por_tipo = defaultdict(list)
    for u, v, clave, datos in G_heterogeneo.edges(keys=True, data=True):
        aristas_por_tipo[datos.get("edge_type")].append(
            (id_contrato[u], id_contrato[v], clave, _limpiar_arista(datos))
        )
    for tipo in G_heterogeneo.graph.get("edge_types") or list(aristas_por_tipo):
        G.add_edges_from(aristas_por_tipo.pop(tuple(tipo), []))
    for restantes in aristas_por_tipo.values():  # tipos que no estuvieran en los metadatos
        G.add_edges_from(restantes)
    return G


def _limpiar_arista(datos: dict) -> dict:
    internos = (_INTERNOS_ARISTA | {"geometry"}) if datos.get(COLUMNA_GEOMETRIA_SINTETICA) else _INTERNOS_ARISTA
    limpio = _limpiar(datos, internos)
    if not es_celda_vacia(geometria_original := datos.get(COLUMNA_GEOMETRIA_ORIGINAL)):
        limpio["geometry"] = geometria_original  # se deshace el sustituto: vuelve el dato fuente
    return limpio


def _limpiar(datos: dict, internos: frozenset[str]) -> dict:
    return {k: v for k, v in datos.items() if k not in internos and not es_celda_vacia(v)}


def es_celda_vacia(valor: object) -> bool:
    """None/NaN/NA/NaT son lo que deja pandas en una celda cuya fila no tenía
    ese atributo. Consecuencia asumida: un atributo que en el dato fuente
    valiera NaN o None a propósito también desaparece; en este proyecto no
    hay ninguno."""
    if valor is None or valor is pd.NA or valor is pd.NaT:
        return True
    return isinstance(valor, float) and math.isnan(valor)


def _verificar_crs(G: nx.Graph, capa: str) -> None:
    crs = G.graph.get("crs")
    if crs is not None and CRS.from_user_input(crs) != CRS.from_user_input(CRS_METRICO):
        raise ValueError(f"Capa '{capa}' está en {crs}, no en {CRS_METRICO}: las distancias de "
                         f"transferencia no tendrían sentido en metros.")
