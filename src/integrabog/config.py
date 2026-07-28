from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
RUTA_ESTACIONES = RAIZ_PROYECTO / "data" / "raw" / "Estaciones_Troncales_de_TRANSMILENIO.geojson"
RUTA_TRAZADO = RAIZ_PROYECTO / "data" / "raw" / "Trazado_troncal.geojson"
RUTA_GRAFO_BASE = RAIZ_PROYECTO / "data" / "processed" / "malla_vial_base.graphml"

TOLERANCIA_ACOPLE_M = 300.0

CRS_METRICO = "EPSG:3116"


RUTA_GRAFO_MICRO = RAIZ_PROYECTO / "data" / "processed" / "malla_vial_micro.graphml"
RUTA_GRAFO_BASE = RAIZ_PROYECTO / "data" / "processed" / "malla_vial_base.graphml"

TOLERANCIA_CONSOLIDACION_M = 2.0

CONSERVAR_VIAS_SIN_SALIDA = False
