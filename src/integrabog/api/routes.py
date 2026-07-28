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
    ts = r["tiempo_actual_min"]
    tn = r["tiempo_nueva_ruta_min"]
    if ts is None:
        recomendacion = "sin_conexion_actual"
    elif ts <= tn:
        recomendacion = "ruta_actual"
    else:
        recomendacion = "ruta_nueva"

    return SugerenciaOut(
        estacion_origen=r["estacion_origen"],
        estacion_destino=r["estacion_destino"],
        nombre_origen=G.nodes[r["estacion_origen"]].get("nombre", r["estacion_origen"]),
        nombre_destino=G.nodes[r["estacion_destino"]].get("nombre", r["estacion_destino"]),
        tiempo_actual_min=ts,
        geometria_actual_lonlat=r.get("geometria_actual_lonlat"),
        tiempo_nueva_ruta_min=tn,
        ahorro_min=r.get("ahorro_min"),
        geometria_lonlat=r["geometria_lonlat"],
        estaciones_intermedias_lonlat=r["estaciones_intermedias_lonlat"],
        distancia_geometrica_m=r.get("distancia_geometrica_m"),
        recomendacion=recomendacion,
    )


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/estaciones", response_model=list[EstacionOut])
def listar_estaciones(request: Request):
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
    vistos: set[str] = set()
    unicas: list[EstacionOut] = []
    for e in estaciones:
        if e.nombre not in vistos:
            vistos.add(e.nombre)
            unicas.append(e)
    return unicas


@router.get("/red-actual", response_model=list[AristaRedActualOut])
def red_actual(request: Request):
    G = _estado(request).grafo
    aristas = []
    vistas = set()
    for u, v, datos in G.edges(data=True):
        if datos.get("layer") != "macro":
            continue
        clave = frozenset((u, v))
        if clave in vistas:
            continue
        vistas.add(clave)

        du, dv = G.nodes[u], G.nodes[v]
        lon_u, lat_u = _a_lonlat(du["x"], du["y"])
        lon_v, lat_v = _a_lonlat(dv["x"], dv["y"])
        aristas.append(
            AristaRedActualOut(
                origen_lon=lon_u,
                origen_lat=lat_u,
                destino_lon=lon_v,
                destino_lat=lat_v,
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
    G = _estado(request).grafo
    resultados = identificar_pares_criticos(G, top_n=top_n)
    return [_resultado_a_schema(r, G) for r in resultados]


@router.get("/diagnostico", response_model=DiagnosticoOut)
def diagnostico(request: Request):
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
