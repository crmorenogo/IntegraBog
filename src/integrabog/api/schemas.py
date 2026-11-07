"""
Esquemas Pydantic: definen la forma exacta de lo que la API recibe y
devuelve. Sirven como contrato explicito para quien consuma la API
(el frontend, o cualquier otro cliente) y ademas generan la
documentacion automatica en /docs.
"""
from pydantic import BaseModel, Field


class EstacionOut(BaseModel):
    """Una estacion de TransMilenio, lista para mostrar en un mapa."""

    id: str = Field(..., description="ID interno del nodo, ej. 'macro_4107'")
    codigo: int = Field(..., description="Codigo de nodo original (cod_nodo)")
    nombre: str = Field(..., description="Nombre oficial (Datos Abiertos); puede repetirse")
    etiqueta: str = Field(..., description="Texto para mostrar: el nombre, con la troncal entre "
                                           "paréntesis si el nombre está repetido. Único por estación")
    troncal: str | None = Field(None, description="Nombre de la troncal (nom_tronc del trazado)")
    num_est: str | None = None
    tipo_estacion: int
    lon: float
    lat: float


class CoordenadaOut(BaseModel):
    lon: float
    lat: float


class SugerenciaOut(BaseModel):
    """Resultado de comparar la red actual contra una ruta nueva propuesta."""

    estacion_origen: str
    estacion_destino: str
    nombre_origen: str
    nombre_destino: str

    tiempo_actual_min: float | None = Field(
        None, description="Tiempo por la red troncal existente, con transbordo_min por cada transbordo. "
                          "None si no hay conexion directa hoy."
    )
    transbordos_actuales: int | None = Field(
        None, description="Transbordos (cruces entre troncales) de la ruta actual. None si no hay ruta actual."
    )
    transbordo_min: float | None = Field(
        None, description="Minutos que se cobran por transbordo (config.TRANSBORDO_MIN); los mismos de las "
                          "metricas de la red."
    )
    geometria_actual_lonlat: list[list[float]] | None = None

    tiempo_nueva_ruta_min: float
    ahorro_min: float | None = Field(
        None, description="tiempo_actual_min - tiempo_nueva_ruta_min. None si no habia ruta actual."
    )
    geometria_lonlat: list[list[float]]
    estaciones_intermedias_lonlat: list[list[float]]

    distancia_geometrica_m: float | None = Field(
        None, description="Solo presente cuando el resultado viene de /pares-criticos"
    )
    factor_rodeo: float | None = Field(
        None, description="Distancia por la red troncal / distancia en línea recta. Solo en "
                          "/pares-criticos; None si el par no tiene conexión troncal"
    )


class ErrorOut(BaseModel):
    detalle: str


class DiagnosticoOut(BaseModel):
    nodos: int
    aristas: int
    componentes_conexas: int
    aristas_por_capa: dict[str, int]
    segundos_construccion_grafo: float


class AristaRedActualOut(BaseModel):
    """Una conexión del grafo macro entre dos estaciones.

    El mapa base ya no se dibuja con esto sino con /api/trazado (el trazado
    oficial); esta ruta sirve para mostrar, aparte, las conexiones que el
    modelo infiere (costura y cruces) y para inspeccionar el grafo."""

    origen_lon: float
    origen_lat: float
    destino_lon: float
    destino_lat: float
    nom_tronc: str | None = None
    origen: str | None = Field(None, description="Etiqueta de la estación de origen")
    destino: str | None = Field(None, description="Etiqueta de la estación de destino")
    tipo: str = Field("tramo", description="'tramo' (estaciones consecutivas del trazado oficial), "
                                           "'costura' o 'cruce' (inferidas por el modelo)")
    geometria_lonlat: list[list[float]] = Field(
        ..., description="Recorrido por el trazado, de origen a destino, en [lon, lat]"
    )


class TrazadoOut(BaseModel):
    """Una troncal del trazado oficial (Datos Abiertos), tal como viene en el
    archivo, para dibujar el mapa base."""

    id_trazado: str
    nom_traz: str | None = None
    nom_tronc: str | None = None
    lineas_lonlat: list[list[list[float]]] = Field(
        ..., description="Una o más líneas (el trazado puede venir partido), cada una en [lon, lat]"
    )
