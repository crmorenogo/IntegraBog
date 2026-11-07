"""
Construcción del grafo macro completo (estaciones + aristas + costura)
a partir de los datos crudos de TransMilenio.

Junta en un solo punto de entrada lo que loader.py, snapping.py,
builder.py y costura.py resuelven por separado. Nadie fuera de este
archivo debería tener que llamar a esos cuatro módulos en orden a
mano -- si algún día cambia el orden interno o se agrega un paso, se
cambia acá y el resto del proyecto ni se entera.
"""
import networkx as nx

from integrabog.data.loader import cargar_estaciones, cargar_trazado
from integrabog.graph.snapping import explotar_tramos, acoplar_estaciones
from integrabog.graph.builder import construir_nodos, construir_aristas
from integrabog.graph.costura import calcular_aristas_costura
from integrabog.graph.cruces import calcular_aristas_cruce
from integrabog.graph.correcciones import aplicar_conexiones_bloqueadas
from integrabog.config import CONEXIONES_BLOQUEADAS


def construir_grafo_macro() -> nx.DiGraph:
    """Arma el grafo macro de punta a punta: carga, acople, nodos,
    aristas, costura, cruces entre troncales y correcciones manuales.

    Returns:
        Grafo dirigido con las 150 estaciones de TransMilenio como
        nodos y sus conexiones (por tramo + costura) como aristas, listo
        para usarse tal cual o para fusionarse con el grafo micro en
        multilayer.py.
    """
    estaciones = cargar_estaciones()
    trazado = cargar_trazado()
    tramos = explotar_tramos(trazado)

    G = nx.DiGraph()
    construir_nodos(G, estaciones)
    _nombrar_estaciones(G, trazado)

    acoples = acoplar_estaciones(estaciones, tramos)
    construir_aristas(G, acoples, tramos)  # con tramos: cada arista lleva la forma del trazado

    """validación contra el propio dato oficial, no contra un supuesto propio: si el acople
     geométrico (snapping.py) se desvía de lo que dice id_trazado, esto es lo que lo delata"""
    referencia = estaciones.set_index("cod_nodo")["id_trazado"]
    inferido = acoples.set_index("cod_nodo")["id_trazado"]
    coincidencia = (inferido == referencia.loc[inferido.index]).mean() * 100
    print(f"Validación acople vs id_trazado real: {coincidencia:.1f}%")

    """la costura va DESPUÉS de tener ya el grafo base armado -- necesita saber qué tramos
     quedaron sin ninguna estación acoplada, y eso solo se sabe una vez existe 'acoples'"""
    n_costuras = calcular_aristas_costura(G, tramos, acoples)
    print(f"Aristas de costura agregadas: {n_costuras}")

    """los cruces van después de la costura a propósito: donde una costura ya une dos
     estaciones, ese dato (los extremos del propio trazado) manda sobre la inferencia"""
    n_cruces = calcular_aristas_cruce(G, tramos, acoples)
    print(f"Aristas de cruce entre troncales agregadas: {n_cruces}")

    """al final, sobre todo lo inferido: una corrección manual tiene que poder quitar
     cualquier arista de costura o de cruce, venga del paso que venga"""
    quitadas = aplicar_conexiones_bloqueadas(G, CONEXIONES_BLOQUEADAS)
    if quitadas:
        print(f"Conexiones bloqueadas a mano (config.py): {', '.join(quitadas)}")

    return G


def _nombrar_estaciones(G: nx.DiGraph, trazado) -> None:
    """Agrega a cada estación 'troncal' (nom_tronc de su id_trazado) y
    'etiqueta', el texto con el que se muestra.

    La etiqueta es el nombre tal cual, salvo cuando el nombre se repite: en
    los datos oficiales "Temporal AV. Jiménez - Inter Eléctricas" son dos
    estaciones distintas, una en la Caracas y otra en el Eje Ambiental, a
    147 m. Con el mismo texto el usuario no puede distinguirlas en una
    lista; con la troncal entre paréntesis sí. El nombre original no se
    toca: es el dato de Datos Abiertos.
    """
    troncal_de = dict(zip(trazado["id_trazado"], trazado["nom_tronc"]))
    nombres = [d["nombre"] for _, d in G.nodes(data=True)]
    repetidos = {n for n in nombres if nombres.count(n) > 1}
    for _, d in G.nodes(data=True):
        d["troncal"] = troncal_de.get(d["id_trazado"])
        d["etiqueta"] = (f"{d['nombre']} ({d['troncal'] or d['id_trazado']})"
                         if d["nombre"] in repetidos else d["nombre"])
