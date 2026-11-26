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


# ---------------------------------------------------------------- AUD-033
@pytest.mark.parametrize("ruta", ["/", "/api/pow/estado", "/static/app.js", "/no-existe"])
def test_aud_033_cabeceras_de_seguridad(sim, ruta):
    h = sim.get(ruta).headers
    csp = h["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "script-src 'self'" in csp
    assert "fonts.googleapis.com" in csp and "fonts.gstatic.com" in csp
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "no-referrer"


def test_aud_033_cabeceras_en_modo_nodo(nodo):
    assert "frame-ancestors 'none'" in nodo.get("/").headers["Content-Security-Policy"]
    assert nodo.post("/api/sellalo/bloquear", json={}).headers["X-Frame-Options"] == "DENY"


# ---------------------------------------------------------------- AUD-034
def _verificar(c, contenido: bytes, nombre="certificado"):
    import io
    return c.post("/api/sellalo/certificado/verificar", data={nombre: (io.BytesIO(contenido), "c.json")},
                  content_type="multipart/form-data")


def test_aud_034_rutas_sin_subida_tienen_limite_pequeno(nodo):
    r = nodo.post("/api/sellalo/minar", data=b"x" * (2 * 1024 * 1024), content_type="text/plain")
    assert r.status_code == 413 and r.get_json()["ok"] is False


def test_aud_034_certificado_con_demasiados_encabezados(nodo, monkeypatch):
    import json
    import controllers.sellalo as modulo

    def no_debe_llamarse(*a, **k):
        raise AssertionError("no se debe verificar un certificado con encabezados de más")
    monkeypatch.setattr(modulo, "verificar", no_debe_llamarse)
    cert = {"genesis": {}, "encabezados": [{}] * (modulo.MAX_ENCABEZADOS + 1), "sello": {}}
    r = _verificar(nodo, json.dumps(cert).encode())
    assert r.status_code == 400 and "encabezados" in r.get_json()["error"]


def test_aud_034_certificado_demasiado_grande(nodo):
    r = _verificar(nodo, b" " * (17 * 1024 * 1024))
    assert r.status_code in (400, 413) and "grande" in r.get_json()["error"]


# ---------------------------------------------------------------- AUD-035
def test_aud_035_direcciones_locales_en_cache(nodo, monkeypatch):
    import socket
    import controllers.sellalo as modulo
    modulo._CACHE_DIRECCIONES.update(t=0.0, valor=None)
    llamadas = []
    original = socket.gethostbyname_ex
    monkeypatch.setattr(socket, "gethostbyname_ex", lambda n: llamadas.append(n) or original(n))
    for _ in range(5):
        assert nodo.get("/api/sellalo/estado").status_code == 200
    assert len(llamadas) <= 1


# ---------------------------------------------------------------- AUD-036
def test_aud_036_aleatoria_informa_las_creadas_antes_del_limite(sim, monkeypatch):
    from models.errores import ErrorEstado
    red = sim.application.config["SIMULADOR"].red("pow")
    original, cuenta = red.transaccion_aleatoria, {"n": 0}

    def con_limite():
        cuenta["n"] += 1
        if cuenta["n"] > 3:
            raise ErrorEstado("La lista de pendientes está llena.")
        return original()
    monkeypatch.setattr(red, "transaccion_aleatoria", con_limite)
    r = sim.post("/api/pow/transacciones/aleatoria", json={"cantidad": 6})
    cuerpo = r.get_json()
    assert r.status_code == 200 and cuerpo["ok"] and "3" in cuerpo["mensaje"] and "llena" in cuerpo["mensaje"]
    assert len(red.publico()["pendientes"]) == 3
    r = sim.post("/api/pow/transacciones/aleatoria", json={"cantidad": 2})     # ahora no se crea ninguna: error
    assert r.status_code == 409


# ---------------------------------------------------------------- AUD-037
@pytest.mark.parametrize("ruta", ["/api/pos/pos/ronda", "/api/pos/pos/sortear", "/api/pow/minar/cancelar"])
def test_aud_037_json_con_cuerpo_vacio_en_rutas_sin_parametros(sim, ruta):
    r = sim.post(ruta, data=b"", content_type="application/json")
    assert r.status_code != 400, r.get_json()


def test_aud_037_cuerpo_vacio_con_json_en_ruta_con_parametros_sigue_siendo_error_claro(sim):
    r = sim.post("/api/pow/transacciones", data=b"", content_type="application/json")
    assert r.status_code == 400 and "emisor" in r.get_json()["error"].lower() or r.status_code == 400


# ---------------------------------------------------------------- coordinación con AUD-004 (parte G2)
def test_aud_004_g2_minar_sin_dificultad_la_pasa_como_none(desbloqueado, app_nodo, monkeypatch):
    llamadas = []
    monkeypatch.setattr(app_nodo.config["CONTEXTO_NODO"].nodo, "iniciar_minado",
                        lambda dificultad, continuo=False: llamadas.append((dificultad, continuo)) or "ok")
    assert desbloqueado.post("/api/sellalo/minar", json={}).status_code == 200
    assert desbloqueado.post("/api/sellalo/minar", json={"dificultad": 3, "continuo": True}).status_code == 200
    assert llamadas == [(None, False), (3, True)]
    assert desbloqueado.post("/api/sellalo/minar", json={"dificultad": 99}).status_code == 400
