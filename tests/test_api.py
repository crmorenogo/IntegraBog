import pytest


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from integrabog.api.main import app

    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.slow
class TestEstaciones:
    def test_devuelve_lista(self, client):
        resp = client.get("/api/estaciones")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_campos_esperados(self, client):
        resp = client.get("/api/estaciones")
        estacion = resp.json()[0]
        assert "id" in estacion
        assert "nombre" in estacion
        assert "lon" in estacion
        assert "lat" in estacion


@pytest.mark.slow
class TestDiagnostico:
    def test_devuelve_metricas(self, client):
        resp = client.get("/api/diagnostico")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodos" in data
        assert "aristas" in data
        assert "componentes_conexas" in data
        assert data["nodos"] > 0
        assert data["aristas"] > 0


@pytest.mark.slow
class TestSugerir:
    def test_sugerir_con_nombres_validos(self, client):
        resp = client.get("/api/sugerir?origen=Portal&destino=Centro")
        assert resp.status_code == 200
        data = resp.json()
        assert "tiempo_nueva_ruta_min" in data

    def test_sugerir_404_si_no_existe(self, client):
        resp = client.get("/api/sugerir?origen=ZZZ&destino=Centro")
        assert resp.status_code == 404
