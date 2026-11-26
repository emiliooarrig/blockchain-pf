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


# ---------------------------------------------------------------- AUD-017
def test_aud_017_laboratorio_de_ataques_desactivado_por_defecto(labs, tmp_path):
    from app import create_app_nodo
    from tests.laboratorios import CONTRASENA
    _, genesis, rutas = labs
    app = create_app_nodo(str(tmp_path / "d"), genesis, "LAB-A", puerto_p2p=0, ruta_clave=rutas["LAB-A"],
                          host_p2p="127.0.0.1")
    desbloqueado = app.test_client()
    assert desbloqueado.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200
    r = desbloqueado.post("/api/sellalo/ataques", json={"tipo": "firma_falsa", "destino": "local"})
    assert r.status_code == 409 and "--laboratorio-ataques" in r.get_json()["error"]
    assert estado(desbloqueado)["laboratorio_ataques"] is False
    app.config["CONTEXTO_NODO"].bloquear()


def test_aud_017_laboratorio_activado_con_la_opcion(labs, tmp_path):
    from app import create_app_nodo
    from tests.laboratorios import CONTRASENA
    _, genesis, rutas = labs
    app = create_app_nodo(str(tmp_path / "d"), genesis, "LAB-A", puerto_p2p=0, ruta_clave=rutas["LAB-A"],
                          host_p2p="127.0.0.1", laboratorio_ataques=True)
    c = app.test_client()
    try:
        assert c.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200
        assert estado(c)["laboratorio_ataques"] is True
        r = c.post("/api/sellalo/ataques", json={"tipo": "merkle_falsa", "destino": "red"})
        assert r.status_code == 200 and r.get_json()["rechazado"]
    finally:
        app.config["CONTEXTO_NODO"].bloquear()


# ---------------------------------------------------------------- AUD-032
def test_aud_032_pares_resuelve_nombres_de_host(desbloqueado, app_nodo):
    servidor = app_nodo.config["CONTEXTO_NODO"].servidor
    llamadas = []
    servidor.conectar = lambda ip, puerto: llamadas.append((ip, puerto)) or "LAB-B"
    r = desbloqueado.post("/api/sellalo/pares", json={"ip": "localhost", "puerto": 6002})
    assert r.status_code == 200 and llamadas == [("127.0.0.1", 6002)]
    r = desbloqueado.post("/api/sellalo/pares", json={"ip": "no-existe.invalid", "puerto": 6002})
    assert r.status_code == 400 and r.get_json()["ok"] is False and len(llamadas) == 1


def test_aud_032_argumento_pares_resuelve_nombres():
    from app import parsear_pares
    from models.errores import ErrorEntrada
    assert parsear_pares("localhost:6002,10.0.0.5:6003") == [("127.0.0.1", 6002), ("10.0.0.5", 6003)]
    with pytest.raises(ErrorEntrada):
        parsear_pares("no-existe.invalid:6002")
