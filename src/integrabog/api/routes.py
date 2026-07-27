"""
Rutas HTTP de la API de IntegraBog.

Todas las rutas leen el grafo multicapa desde `request.app.state.grafo`
(ver state.py y main.py) -- nunca lo reconstruyen, solo lo consultan.
"""
from collections import Counter

import networkx as nx
from fastapi import APIRouter, HTTPException, Query, Request

from integrabog.api.schemas import (
    AristaRedActualOut,
    DiagnosticoOut,
    EstacionOut,
    SugerenciaOut,
)
from integrabog.api.state import TRANSFORMADOR_A_LONLAT, EstadoGrafo
from integrabog.routing.network_design import (
    EstacionNoEncontradaError,
    identificar_pares_criticos,
    sugerir_nueva_troncal,
)

router = APIRouter(prefix="/api")


def _estado(request: Request) -> EstadoGrafo:
    return request.app.state.estado_grafo


def _a_lonlat(x: float, y: float) -> tuple[float, float]:
    lon, lat = TRANSFORMADOR_A_LONLAT.transform(x, y)
    return round(lon, 6), round(lat, 6)


def _resultado_a_schema(r: dict, G: nx.MultiDiGraph) -> SugerenciaOut:
    """Convierte el dict que devuelve sugerir_nueva_troncal en el schema
    de salida, agregando los nombres legibles de las estaciones."""
    return SugerenciaOut(
        estacion_origen=r["estacion_origen"],
        estacion_destino=r["estacion_destino"],
        nombre_origen=G.nodes[r["estacion_origen"]].get("nombre", r["estacion_origen"]),
        nombre_destino=G.nodes[r["estacion_destino"]].get("nombre", r["estacion_destino"]),
        tiempo_actual_min=r["tiempo_actual_min"],
        geometria_actual_lonlat=r["geometria_actual_lonlat"],
        tiempo_nueva_ruta_min=r["tiempo_nueva_ruta_min"],
        ahorro_min=r["ahorro_min"],
        geometria_lonlat=r["geometria_lonlat"],
        estaciones_intermedias_lonlat=r["estaciones_intermedias_lonlat"],
        distancia_geometrica_m=r.get("distancia_geometrica_m"),
    )


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/estaciones", response_model=list[EstacionOut])
def listar_estaciones(request: Request):
    """Todas las estaciones de TransMilenio, para poblar selectores y
    marcadores en el mapa."""
    G = _estado(request).grafo
    estaciones = []
    for nodo, datos in G.nodes(data=True):
        if datos.get("layer") != "macro":
            continue
        lon, lat = _a_lonlat(datos["x"], datos["y"])
        estaciones.append(
            EstacionOut(
                id=nodo,
                codigo=int(nodo.removeprefix("macro_")),
                nombre=datos.get("nombre", ""),
                num_est=datos.get("num_est"),
                tipo_estacion=datos.get("tipo_estacion", -1),
                lon=lon,
                lat=lat,
            )
        )
    estaciones.sort(key=lambda e: e.nombre)
    return estaciones


@router.get("/red-actual", response_model=list[AristaRedActualOut])
def red_actual(request: Request):
    """Aristas de la red troncal existente (linea recta entre estaciones
    consecutivas), para dibujar la red base en el mapa antes de mostrar
    ninguna sugerencia."""
    G = _estado(request).grafo
    aristas = []
    vistas = set()
    for u, v, datos in G.edges(data=True):
        if datos.get("layer") != "macro":
            continue
        clave = frozenset((u, v))
        if clave in vistas:
            continue  # las aristas macro son bidireccionales -> no duplicar en el mapa
        vistas.add(clave)

        du, dv = G.nodes[u], G.nodes[v]
        lon_u, lat_u = _a_lonlat(du["x"], du["y"])
        lon_v, lat_v = _a_lonlat(dv["x"], dv["y"])
        aristas.append(
            AristaRedActualOut(
                origen_lon=lon_u, origen_lat=lat_u,
                destino_lon=lon_v, destino_lat=lat_v,
                nom_tronc=datos.get("nom_tronc"),
            )
        )
    return aristas


@router.get("/sugerir", response_model=SugerenciaOut)
def sugerir(
    request: Request,
    origen: str = Query(..., description="ID, numero o nombre parcial de la estacion origen"),
    destino: str = Query(..., description="ID, numero o nombre parcial de la estacion destino"),
):
    """Compara el tiempo actual por la red troncal contra una ruta nueva
    propuesta sobre la malla vial, entre dos estaciones dadas por el
    usuario."""
    G = _estado(request).grafo
    try:
        resultado = sugerir_nueva_troncal(G, origen, destino)
    except EstacionNoEncontradaError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except (nx.NetworkXNoPath, nx.NodeNotFound) as err:
        raise HTTPException(
            status_code=422,
            detail=f"No fue posible calcular una ruta nueva entre esas estaciones: {err}",
        ) from err
    return _resultado_a_schema(resultado, G)


@router.get("/pares-criticos", response_model=list[SugerenciaOut])
def pares_criticos(
    request: Request,
    top_n: int = Query(5, ge=1, le=20, description="Cuantos pares candidatos devolver"),
):
    """Encuentra automaticamente los pares de estaciones mas prometedores
    para una troncal nueva, sin que el usuario elija origen/destino."""
    G = _estado(request).grafo
    resultados = identificar_pares_criticos(G, top_n=top_n)
    return [_resultado_a_schema(r, G) for r in resultados]


@router.get("/diagnostico", response_model=DiagnosticoOut)
def diagnostico(request: Request):
    """Resumen del grafo multicapa: tamano, conexidad y aristas por capa."""
    estado = _estado(request)
    G = estado.grafo
    G_no_dirigido = G.to_undirected()
    conteo_capas = Counter(d.get("layer") for _, _, d in G.edges(data=True))
    return DiagnosticoOut(
        nodos=G.number_of_nodes(),
        aristas=G.number_of_edges(),
        componentes_conexas=nx.number_connected_components(G_no_dirigido),
        aristas_por_capa=dict(conteo_capas),
        segundos_construccion_grafo=round(estado.segundos_construccion, 1),
    )
