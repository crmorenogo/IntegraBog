"""Tests para el módulo data.loader."""

import pytest

from integrabog.config import (
    CRS_METRICO,
    RAIZ_PROYECTO,
    RUTA_ESTACIONES,
    RUTA_TRAZADO,
)


class TestRutas:
    """Las rutas a los archivos crudos existen y apuntan a donde deben."""

    def test_raiz_proyecto_existe(self):
        assert RAIZ_PROYECTO.exists()

    def test_ruta_estaciones_es_geojson(self):
        assert RUTA_ESTACIONES.suffix == ".geojson"

    def test_ruta_trazado_es_geojson(self):
        assert RUTA_TRAZADO.suffix == ".geojson"

    def test_crs_metrico_es_epsg3116(self):
        assert CRS_METRICO == "EPSG:3116"


class TestCargaGeoespacial:
    """Requiere que los archivos .geojson existan en data/raw/."""

    @pytest.mark.slow
    def test_cargar_estaciones_devuelve_geodataframe(self):
        from integrabog.data.loader import cargar_estaciones

        gdf = cargar_estaciones()
        assert not gdf.empty
        assert "geometry" in gdf.columns
        assert gdf.crs is not None

    @pytest.mark.slow
    def test_cargar_trazado_devuelve_geodataframe(self):
        from integrabog.data.loader import cargar_trazado

        gdf = cargar_trazado()
        assert not gdf.empty
        assert "geometry" in gdf.columns

    @pytest.mark.slow
    def test_reproyeccion_crs_metrico(self):
        from integrabog.data.loader import cargar_estaciones

        gdf = cargar_estaciones()
        assert str(gdf.crs).startswith("EPSG:3116")
