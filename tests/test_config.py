"""Tests para los módulos de config y constantes."""
from integrabog.config import (
    CRS_METRICO,
    RAIZ_PROYECTO,
    TOLERANCIA_ACOPLE_M,
    TOLERANCIA_CONSOLIDACION_M,
)


class TestConfig:
    """Valores de configuración deben ser coherentes."""

    def test_raiz_es_directorio(self):
        assert RAIZ_PROYECTO.is_dir()

    def test_crs_es_el_esperado(self):
        assert CRS_METRICO == "EPSG:3116"

    def test_tolerancia_acople_positiva(self):
        assert TOLERANCIA_ACOPLE_M > 0

    def test_tolerancia_consolidacion_positiva(self):
        assert TOLERANCIA_CONSOLIDACION_M > 0


class TestRutasProyecto:
    """Verifica que la estructura de carpetas existe."""

    def test_data_raw_existe(self):
        assert (RAIZ_PROYECTO / "data" / "raw").exists()

    def test_data_processed_existe(self):
        assert (RAIZ_PROYECTO / "data" / "processed").exists()

    def test_src_integrabog_existe(self):
        assert (RAIZ_PROYECTO / "src" / "integrabog").is_dir()
