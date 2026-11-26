"""Auditoría con IA · pruebas de regresión del grupo G2 (API e interfaz)."""
import pytest

from app import create_app
from tests.test_sellalo_api import app_nodo, desbloqueado, labs, nodo, estado  # noqa: F401  (fixtures)


@pytest.fixture
def sim():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


# ---------------------------------------------------------------- AUD-003
@pytest.mark.parametrize("ruta", ["/api/pow/transacciones/aleatoria", "/api/sellalo/bloquear"])
def test_aud_003_origin_ajeno_rechazado(sim, nodo, ruta):
    c = nodo if "sellalo" in ruta else sim
    r = c.post(ruta, json={}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403 and r.get_json()["ok"] is False
    r = c.post(ruta, json={}, headers={"Origin": "null"})
    assert r.status_code == 403


@pytest.mark.parametrize("valor", ["cross-site", "same-site"])
def test_aud_003_sec_fetch_site_ajeno_rechazado(sim, valor):
    r = sim.post("/api/pow/transacciones/aleatoria", json={}, headers={"Sec-Fetch-Site": valor})
    assert r.status_code == 403 and r.get_json()["ok"] is False


@pytest.mark.parametrize("host", ["evil.example", "evil.example:5000", "127.0.0.1.evil.example"])
def test_aud_003_host_ajeno_rechazado(sim, host):
    r = sim.post("/api/pow/transacciones/aleatoria", json={}, headers={"Host": host})
    assert r.status_code in (400, 403) and r.get_json()["ok"] is False


def test_aud_003_interfaz_propia_y_clientes_sin_origin_funcionan(sim, nodo):
    for host in ("127.0.0.1:5000", "localhost:5000", "[::1]:5000", "localhost"):
        r = sim.post("/api/pow/transacciones/aleatoria", json={},
                     headers={"Host": host, "Origin": f"http://{host}", "Sec-Fetch-Site": "same-origin"})
        assert r.status_code == 200, (host, r.get_json())
    assert sim.post("/api/pow/transacciones/aleatoria", json={}).status_code == 200     # curl: sin Origin
    assert nodo.post("/api/sellalo/bloquear", json={}, headers={"Origin": "http://localhost"}).status_code == 200
    # las lecturas no se ven afectadas
    assert sim.get("/api/pow/estado", headers={"Origin": "http://evil.example"}).status_code == 200


def test_aud_003_host_configurado_permitido():
    app = create_app(host_http="nodo.lab.local")
    app.config["TESTING"] = True
    c = app.test_client()
    r = c.post("/api/pow/transacciones/aleatoria", json={}, headers={"Host": "nodo.lab.local:5000"})
    assert r.status_code == 200
