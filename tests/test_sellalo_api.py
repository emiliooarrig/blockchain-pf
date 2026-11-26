"""API de la red Sellalo (modo nodo): flujo completo con un nodo real, ataques locales y entradas mal formadas."""
import hashlib
import io
import json
import time

import pytest

from app import create_app, create_app_nodo
from tests.laboratorios import CONTRASENA, crear_laboratorios

DOC = b"contenido del articulo sellado"
HASH_DOC = hashlib.sha256(DOC).hexdigest()
OPCIONES = dict(intervalo_ping=0.2, tiempo_sin_respuesta=2.0, tiempo_saludo=3.0, tiempo_sync=5.0)


def esperar(cond, limite=10.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


@pytest.fixture(scope="module")
def labs(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("labs_api")
    genesis, rutas, claves = crear_laboratorios(carpeta)
    ruta = carpeta / "genesis.json"
    ruta.write_text(json.dumps(genesis), encoding="utf-8")
    return carpeta, str(ruta), rutas


@pytest.fixture
def app_nodo(labs, tmp_path):
    carpeta, genesis, rutas = labs
    app = create_app_nodo(str(tmp_path / "datos"), genesis, "LAB-A", puerto_p2p=0, ruta_clave=rutas["LAB-A"],
                          host_p2p="127.0.0.1", opciones_p2p=OPCIONES, laboratorio_ataques=True)
    app.config["TESTING"] = True
    yield app
    ctx = app.config["CONTEXTO_NODO"]
    ctx.nodo.detener_minado()
    ctx.bloquear()


@pytest.fixture
def nodo(app_nodo):
    return app_nodo.test_client()


@pytest.fixture
def desbloqueado(nodo):
    assert nodo.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200
    return nodo


def estado(c):
    return c.get("/api/sellalo/estado").get_json()


def sellar(c, doc=DOC, umbral=1, autores="LAB-A", **extra):
    datos = {"titulo": "Hallazgo", "investigador": "Dra. Prueba", "autores": autores, "umbral": str(umbral), **extra}
    if doc is not None:
        datos["archivo"] = (io.BytesIO(doc), "resultado.pdf")
    return c.post("/api/sellalo/sellos", data=datos, content_type="multipart/form-data")


def minar_hasta(c, altura):
    assert c.post("/api/sellalo/minar", json={"dificultad": 1}).status_code == 200
    assert esperar(lambda: estado(c)["nodo"]["altura"] >= altura and not estado(c)["nodo"]["minando"])


# ---------------------------------------------------------------- modos
def test_modo_simulador_responde_409():
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    for metodo, ruta in (("get", "/api/sellalo/estado"), ("post", "/api/sellalo/desbloquear"),
                         ("post", "/api/sellalo/ataques"), ("get", "/api/sellalo/certificado/" + "0" * 64)):
        r = getattr(c, metodo)(ruta)
        assert r.status_code == 409 and "--modo nodo" in r.get_json()["error"]
    assert b"Simulador de blockchain" in c.get("/").data


def test_paginas_en_modo_nodo(nodo):
    assert b'id="app"' in nodo.get("/").data and b"sellalo.js" in nodo.get("/").data
    assert b"Simulador de blockchain" in nodo.get("/simulador").data
    assert nodo.get("/static/sellalo.js").status_code == 200
    assert nodo.get("/api/pow/estado").status_code == 200       # el simulador sigue disponible


# ---------------------------------------------------------------- flujo de un nodo
def test_estado_bloqueado_y_desbloqueo(nodo):
    e = estado(nodo)
    assert e["ok"] and e["nodo"]["desbloqueado"] is False and e["pares"] == []
    assert [x["id"] for x in e["laboratorios"]] == ["LAB-A", "LAB-B", "LAB-C"]
    assert e["sellos_en_firma"] == [] and e["solicitudes"] == [] and e["red"]["direcciones"]
    mal = nodo.post("/api/sellalo/desbloquear", json={"contrasena": "contrasena-incorrecta-1"})
    assert mal.status_code == 400 and not mal.get_json()["ok"]
    assert estado(nodo)["nodo"]["desbloqueado"] is False
    assert nodo.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200
    assert estado(nodo)["nodo"]["desbloqueado"] is True
    assert nodo.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).status_code == 409
    assert nodo.post("/api/sellalo/bloquear").status_code == 200
    assert estado(nodo)["nodo"]["desbloqueado"] is False and estado(nodo)["pares"] == []
    assert nodo.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200   # puede reabrirse


def test_flujo_sello_minado_prioridad_y_certificado(desbloqueado):
    c = desbloqueado
    r = sellar(c)
    cuerpo = r.get_json()
    assert r.status_code == 200 and cuerpo["sello"]["estado"] == "pendiente" and cuerpo["sello"]["doc_hash"] == HASH_DOC
    assert [p["tipo"] for p in estado(c)["nodo"]["pendientes"]] == ["sello"]
    minar_hasta(c, 1)

    por_archivo = c.post("/api/sellalo/prioridad", data={"archivo": (io.BytesIO(DOC), "x.pdf")},
                         content_type="multipart/form-data").get_json()
    por_hash = c.post("/api/sellalo/prioridad", json={"doc_hash": HASH_DOC}).get_json()
    assert por_archivo["doc_hash"] == por_hash["doc_hash"] == HASH_DOC
    assert len(por_archivo["sellos"]) == 1 and por_archivo["sellos"][0]["prioritario"]
    sin = c.post("/api/sellalo/prioridad", json={"doc_hash": "a" * 64}).get_json()
    assert sin["ok"] and sin["sellos"] == []

    d = c.get(f"/api/sellalo/certificado/{HASH_DOC}")
    assert d.status_code == 200 and "attachment" in d.headers["Content-Disposition"]
    assert f"certificado-{HASH_DOC[:8]}.json" in d.headers["Content-Disposition"]
    cert = d.data

    def verificar(certificado=cert, documento=None):
        datos = {"certificado": (io.BytesIO(certificado), "cert.json")}
        if documento is not None:
            datos["documento"] = (io.BytesIO(documento), "doc.pdf")
        return c.post("/api/sellalo/certificado/verificar", data=datos, content_type="multipart/form-data")

    ok = verificar(documento=DOC).get_json()
    assert ok["valido"] is True and ok["detalle"]["documento_comprobado"] and ok["resumen"]["bloque"] == 1
    assert ok["misma_red"] is True
    alterado = verificar(documento=DOC + b"!")
    assert alterado.status_code == 200 and alterado.get_json()["valido"] is False
    assert "documento" in alterado.get_json()["motivo"]
    roto = verificar(certificado=b"{esto no es json")
    assert roto.status_code == 400 and not roto.get_json()["ok"]
    assert verificar(certificado=b"[1, 2]").status_code == 400
    manipulado = json.loads(cert)
    manipulado["sello"]["titulo"] = "otro"
    assert verificar(certificado=json.dumps(manipulado).encode()).get_json()["valido"] is False
    assert c.get("/api/sellalo/certificado/" + "0" * 64).status_code == 400    # no sellado


def test_sello_multifirma_queda_en_firma(desbloqueado):
    c = desbloqueado
    r = sellar(c, doc=b"otro documento", umbral=2, autores="LAB-A,LAB-B,LAB-C")
    s = r.get_json()["sello"]
    assert r.status_code == 200 and s["estado"] == "en_firma" and s["firmas"] == ["LAB-A"]
    e = estado(c)
    assert e["sellos_en_firma"][0]["faltan"] == 1 and e["solicitudes"] == [] and e["nodo"]["pendientes"] == []
    assert c.post(f"/api/sellalo/sellos/{s['id']}/firmar").status_code == 409     # ya firmó
    assert c.post("/api/sellalo/sellos/" + "f" * 64 + "/firmar").status_code == 409
    assert c.post("/api/sellalo/sellos/no-es-hex/firmar").status_code == 400


def test_transferencia(desbloqueado):
    c = desbloqueado
    r = c.post("/api/sellalo/transferencias", json={"receptor": "LAB-B", "monto": 5})
    assert r.status_code == 200 and len(r.get_json()["id"]) == 64
    assert estado(c)["nodo"]["pendientes"][0]["tipo"] == "transferencia"
    assert c.post("/api/sellalo/transferencias", json={"receptor": "LAB-B", "monto": 10**6}).status_code == 400


@pytest.mark.parametrize("tipo", ["sello_alterado", "firma_falsa", "merkle_falsa", "cadena_corta",
                                  "multifirma_incompleta", "firma_minero_ajena"])
def test_ataques_locales_son_rechazados(desbloqueado, tipo):
    c = desbloqueado
    assert sellar(c).status_code == 200
    minar_hasta(c, 1)
    antes = estado(c)["nodo"]
    r = c.post("/api/sellalo/ataques", json={"tipo": tipo, "destino": "local"})
    cuerpo = r.get_json()
    assert r.status_code == 200 and cuerpo["rechazado"] is True and cuerpo["motivos"] and cuerpo["motivos"][0]
    despues = estado(c)["nodo"]
    assert despues["punta"] == antes["punta"] and despues["altura"] == antes["altura"]
    assert despues["pendientes"] == antes["pendientes"]


def test_ataque_sin_datos_da_409_claro(desbloqueado):
    c = desbloqueado
    for tipo in ("sello_alterado", "cadena_corta"):
        r = c.post("/api/sellalo/ataques", json={"tipo": tipo, "destino": "local"})
        assert r.status_code == 409 and r.get_json()["error"]
    r = c.post("/api/sellalo/ataques", json={"tipo": "merkle_falsa", "destino": "red"})    # sin pares: nadie la recibe
    assert r.status_code == 200 and r.get_json()["rechazado"] and r.get_json()["enviados"] == 0


def test_ataque_con_nodo_bloqueado_da_409(nodo):
    r = nodo.post("/api/sellalo/ataques", json={"tipo": "firma_falsa", "destino": "local"})
    assert r.status_code == 409


# ---------------------------------------------------------------- entradas mal formadas
CUERPOS_JSON = [None, [], "texto", 42, {}, {"x": {"a": 1}},
                {"contrasena": 5, "ip": [], "puerto": "abc", "receptor": {}, "monto": "mucho", "dificultad": "∞",
                 "tipo": 7, "destino": None, "continuo": "quizás", "doc_hash": 3}]
RUTAS_POST = ["/api/sellalo/desbloquear", "/api/sellalo/bloquear", "/api/sellalo/pares",
              "/api/sellalo/pares/LAB-Z/desconectar", "/api/sellalo/sellos", "/api/sellalo/sellos/xx/firmar",
              "/api/sellalo/minar", "/api/sellalo/minar/detener", "/api/sellalo/transferencias",
              "/api/sellalo/prioridad", "/api/sellalo/certificado/verificar", "/api/sellalo/ataques"]


@pytest.mark.parametrize("abierto", [False, True])
def test_datos_mal_formados_nunca_dan_500(nodo, abierto):
    if abierto:
        nodo.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA})
    for ruta in RUTAS_POST:
        if ruta.endswith("/bloquear"):
            continue
        for cuerpo in CUERPOS_JSON:
            r = nodo.post(ruta, json=cuerpo)
            assert r.status_code in (200, 400, 409), (ruta, cuerpo, r.status_code, r.data[:200])
            if r.status_code != 200:
                assert r.get_json()["ok"] is False and r.get_json()["error"]
        for datos, tipo in (("{no json", "application/json"), ("hola", "text/plain"),
                            ("a=1&b=", "application/x-www-form-urlencoded")):
            r = nodo.post(ruta, data=datos, content_type=tipo)
            assert r.status_code in (200, 400, 409, 415), (ruta, tipo, r.status_code)
    for ruta in ("/api/sellalo/certificado/zz", "/api/sellalo/certificado/" + "0" * 64,
                 "/api/sellalo/certificado/" + "A" * 63):
        assert nodo.get(ruta).status_code in (400, 409)


def test_validacion_estricta_de_sellos(desbloqueado):
    c = desbloqueado
    malos = [
        dict(doc=None),                                            # sin archivo ni hash
        dict(doc=b""),                                             # archivo vacío
        dict(titulo=""), dict(titulo="x" * 121), dict(investigador="y" * 81), dict(investigador="  "),
        dict(autores="LAB-B"),                                     # no incluye al propio nodo
        dict(autores="LAB-A,LAB-X"), dict(autores="LAB-A,LAB-A"), dict(autores=""),
        dict(umbral=0), dict(umbral=2), dict(umbral="abc"), dict(umbral="1.5"),
    ]
    for extra in malos:
        extra = dict(extra)
        doc = extra.pop("doc", DOC)
        datos = {"titulo": "T", "investigador": "I", "autores": "LAB-A", "umbral": "1"}
        datos.update(extra)
        if doc is not None:
            datos["archivo"] = (io.BytesIO(doc), "d.bin")
        r = c.post("/api/sellalo/sellos", data=datos, content_type="multipart/form-data")
        assert r.status_code == 400, (extra, r.status_code, r.get_json())
    base = {"titulo": "T", "investigador": "I", "autores": ["LAB-A"], "umbral": 1}
    assert c.post("/api/sellalo/sellos", json={**base, "doc_hash": "xyz"}).status_code == 400
    assert c.post("/api/sellalo/sellos", json={**base, "doc_hash": "b" * 64}).status_code == 200   # hash directo
    assert c.post("/api/sellalo/minar", json={"dificultad": 99}).status_code == 400
    assert estado(c)["nodo"]["altura"] == 0


def test_detalle_de_bloque(desbloqueado):
    c = desbloqueado
    assert sellar(c).status_code == 200
    minar_hasta(c, 1)
    r = c.get("/api/sellalo/bloques/1")
    assert r.status_code == 200
    cuerpo = r.get_json()
    assert cuerpo["ok"] and cuerpo["bloque"]["numero"] == 1
    assert any(tx.get("tipo") == "sello" for tx in cuerpo["bloque"]["transacciones"])
    assert c.get("/api/sellalo/bloques/0").get_json()["bloque"]["numero"] == 0
    for ruta in ("/api/sellalo/bloques/99", "/api/sellalo/bloques/-1", "/api/sellalo/bloques/x"):
        assert c.get(ruta).status_code in (400, 404)
