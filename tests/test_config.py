from integrabog.config import (
    CRS_METRICO,
    RAIZ_PROYECTO,
    TOLERANCIA_ACOPLE_M,
    TOLERANCIA_CONSOLIDACION_M,
)


class TestConfig:
    def test_raiz_es_directorio(self):
        assert RAIZ_PROYECTO.is_dir()

    def test_crs_es_el_esperado(self):
        assert CRS_METRICO == "EPSG:3116"

    def test_tolerancia_acople_positiva(self):
        assert TOLERANCIA_ACOPLE_M > 0

    def test_tolerancia_consolidacion_positiva(self):
        assert TOLERANCIA_CONSOLIDACION_M > 0


class TestRutasProyecto:
    def test_data_raw_existe(self):
        assert (RAIZ_PROYECTO / "data" / "raw").exists()

    def test_data_processed_existe(self):
        assert (RAIZ_PROYECTO / "data" / "processed").exists()

    def test_src_integrabog_existe(self):
        assert (RAIZ_PROYECTO / "src" / "integrabog").is_dir()
