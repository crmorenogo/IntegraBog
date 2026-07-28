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
    nombre: str
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
        None,
        description="Tiempo por la red troncal existente. None si no hay conexion directa hoy.",
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

    recomendacion: str = Field(
        "ruta_nueva",
        description=(
            "'ruta_nueva': la ruta propuesta es mejor. "
            "'ruta_actual': la ruta actual de TransMilenio ya es mejor. "
            "'sin_conexion_actual': no hay troncal directa hoy."
        ),
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
    """Una arista de la red troncal existente, para dibujar el mapa base."""

    origen_lon: float
    origen_lat: float
    destino_lon: float
    destino_lat: float
    nom_tronc: str | None = None
