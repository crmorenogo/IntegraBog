"""
Configuración central del proyecto IntegraBog.
Aquí viven las rutas y constantes que usan los demás módulos, para no
tener valores sueltos ("magic values") dentro de la lógica de negocio.
"""

from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
RUTA_ESTACIONES = RAIZ_PROYECTO / "data" / "raw" / "Estaciones_Troncales_de_TRANSMILENIO.geojson"
RUTA_TRAZADO = RAIZ_PROYECTO / "data" / "raw" / "Trazado_troncal.geojson"
RUTA_GRAFO_BASE = RAIZ_PROYECTO / "data" / "processed" / "malla_vial_base.graphml"

# Tolerancia máxima (m) para aceptar el acople de una estación a un
# tramo. Se definió revisando la distribución real de distancias: la
# mayoría cae a ~0 m; el único grupo que se aleja son las estaciones
# tipo Portal (tipo_esta == 1), hasta ~256 m.
TOLERANCIA_ACOPLE_M = 300.0

# CRS métrico oficial para Bogotá (MAGNA-SIRGAS / Colombia Bogotá zone).
# Los GeoJSON originales vienen en CRS84 (grados) — no sirve para
# calcular distancias euclidianas correctamente. Ver Paso 2.
CRS_METRICO = "EPSG:3116"


# --- CONFIGURACIÓN FASE 2: OSMNX ---
RUTA_GRAFO_MICRO = RAIZ_PROYECTO / "data" / "processed" / "malla_vial_micro.graphml"
RUTA_GRAFO_BASE = RAIZ_PROYECTO / "data" / "processed" / "malla_vial_base.graphml"

# Radio de buffer (m) para ox.consolidate_intersections. Es un RADIO por
# nodo: dos nodos se fusionan si están a menos de 2x este valor entre sí.
# Elegido en 2.0 (fusión real a <4 m) tras comparar contra 5.0 y 10.0
# inspeccionando el tamaño de los clusters resultantes (osmid_original):
# con radios mayores aparecían clusters de hasta 11 nodos -- evidencia de
# fusionar intersecciones distintas, no solo duplicados de digitalización.
# Con 2.0, el tamaño máximo de cluster observado fue 3.
TOLERANCIA_CONSOLIDACION_M = 2.0

# Política de red vial: ¿conservar nodos donde solo toca una calle (vías
# sin salida / culs-de-sac)? En False, ox.consolidate_intersections las
# descarta ANTES de consolidar por tolerancia -- es un mecanismo aparte,
# independiente de TOLERANCIA_CONSOLIDACION_M, responsable de ~8.300 de
# los nodos removidos en Fase 2 (14% del grafo base). Se fija en False
# porque un corredor BRT no puede terminar en una vía sin salida.
CONSERVAR_VIAS_SIN_SALIDA = False
