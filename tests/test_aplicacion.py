"""Sección 5 · Aplicación: reiniciar la simulación; recargar la página a mitad de una ronda; dos pestañas enviando
acciones a la vez; peticiones directas a las rutas con datos mal formados."""
import threading
import time

import pytest

from app import create_app

RUTAS_POST = [
    "/api/{v}/simulacion", "/api/{v}/transacciones", "/api/{v}/transacciones/aleatoria", "/api/{v}/ataques",
    "/api/{v}/nodos/N00/deshonesto", "/api/{v}/minar", "/api/{v}/minar/cancelar", "/api/{v}/pos/config",
    "/api/{v}/pos/ronda", "/api/{v}/pos/apostar", "/api/{v}/pos/apuestas-automaticas", "/api/{v}/pos/sortear",
    "/api/{v}/pos/candidato", "/api/{v}/pos/votar", "/api/{v}/pos/votacion-automatica", "/api/{v}/pos/cerrar",
    "/api/{v}/pos/ronda-automatica", "/api/{v}/pos/cancelar",
]
CUERPOS = [
    {"json": None}, {"json": []}, {"json": "texto"}, {"json": 42}, {"json": {}},
    {"json": {"n": {"a": 1}, "monto": [1], "nodo": 5, "emisor": None, "dificultad": "∞", "tipo": "x" * 500,
              "a_favor": "quizás", "deshonesto": 3, "regla": 1, "cantidad": -1}},
    {"data": "{esto no es json", "content_type": "application/json"},
    {"data": "hola", "content_type": "text/plain"},
    {"data": "n=abc&monto=&nodo=N00", "content_type": "application/x-www-form-urlencoded"},
]


def _esperar_minado(cliente, version="pow", limite=5.0):
    fin = time.time() + limite
    while time.time() < fin:
        if not cliente.get(f"/api/{version}/estado").get_json()["motor"]["minando"]:
            return
        time.sleep(0.02)
    raise AssertionError("el minado no terminó")


def test_pagina_principal(cliente):
    resp = cliente.get("/")
    assert resp.status_code == 200 and b"Simulador de blockchain" in resp.data


def test_estado_de_ambas_versiones(cliente):
    for v in ("pow", "pos"):
        datos = cliente.get(f"/api/{v}/estado").get_json()
        assert datos["ok"] and datos["consenso"] == v and len(datos["nodos"]) == 10
        assert all(n["sincronizado"] for n in datos["nodos"])


def test_reiniciar_la_simulacion(cliente):
    cliente.post("/api/pow/transacciones", json={"emisor": "N00", "receptor": "N01", "monto": 5})
    cliente.post("/api/pow/minar", json={"dificultad": 1, "pausa_ms": 0})
    _esperar_minado(cliente)
    assert cliente.get("/api/pow/estado").get_json()["altura"] == 1
    cliente.post("/api/pow/minar", json={"dificultad": 6, "nonces_por_ronda": 5, "auto_transacciones": True})
    resp = cliente.post("/api/pow/simulacion", json={"n": 15, "semilla": 3})   # reinicia en pleno minado
    assert resp.status_code == 200
    datos = cliente.get("/api/pow/estado").get_json()
    assert datos["altura"] == 0 and datos["pendientes"] == [] and len(datos["nodos"]) == 15
    assert datos["motor"]["minando"] is False


def test_reiniciar_con_datos_invalidos_conserva_la_simulacion(cliente):
    cliente.post("/api/pos/transacciones", json={"emisor": "N00", "receptor": "N01", "monto": 5})
    resp = cliente.post("/api/pos/simulacion", json={"n": 30})
    assert resp.status_code == 400
    assert len(cliente.get("/api/pos/estado").get_json()["pendientes"]) == 1


def test_recargar_a_mitad_de_una_ronda(cliente):
    cliente.post("/api/pos/transacciones", json={"emisor": "N00", "receptor": "N01", "monto": 5})
    for ruta in ("/api/pos/pos/ronda", "/api/pos/pos/apuestas-automaticas", "/api/pos/pos/sortear",
                 "/api/pos/pos/candidato"):
        assert cliente.post(ruta).status_code == 200, ruta
    antes = cliente.get("/api/pos/estado").get_json()["motor"]["ronda"]
    assert cliente.get("/").status_code == 200                       # «recargar la página»
    despues = cliente.get("/api/pos/estado").get_json()["motor"]["ronda"]
    assert despues["estado"] == "VOTACION" and despues == antes
    assert cliente.post("/api/pos/pos/ronda-automatica").status_code == 200
    assert cliente.get("/api/pos/estado").get_json()["altura"] == 1


def test_recargar_a_mitad_del_minado(cliente):
    cliente.post("/api/pow/transacciones", json={"emisor": "N00", "receptor": "N01", "monto": 5})
    cliente.post("/api/pow/minar", json={"dificultad": 6, "nonces_por_ronda": 20, "pausa_ms": 20})
    time.sleep(0.15)
    assert cliente.get("/").status_code == 200
    motor = cliente.get("/api/pow/estado").get_json()["motor"]
    assert motor["minando"] and motor["ronda"] > 0 and all(m["intentos"] > 0 for m in motor["mineros"])
    assert cliente.post("/api/pow/minar/cancelar").status_code == 200


def test_dos_pestanas_minando_a_la_vez():
    app = create_app(reproducible=True)
    app.test_client().post("/api/pow/transacciones", json={"emisor": "N00", "receptor": "N01", "monto": 5})
    codigos, barrera = [], threading.Barrier(6)

    def pestana():
        c = app.test_client()
        barrera.wait()
        codigos.append(c.post("/api/pow/minar", json={"dificultad": 6, "nonces_por_ronda": 5}).status_code)

    hilos = [threading.Thread(target=pestana) for _ in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(codigos) == [200] + [409] * 5
    app.config["SIMULADOR"].red("pow").motor.detener()


def test_dos_pestanas_votando_a_la_vez():
    app = create_app(reproducible=True)
    c = app.test_client()
    c.post("/api/pos/transacciones", json={"emisor": "N00", "receptor": "N01", "monto": 5})
    for ruta in ("ronda", "apuestas-automaticas", "sortear", "candidato"):
        c.post(f"/api/pos/pos/{ruta}")
    resultados, barrera = [], threading.Barrier(4)

    def pestana(a_favor):
        cl = app.test_client()
        barrera.wait()
        resultados.append(cl.post("/api/pos/pos/votar", json={"nodo": "N02", "a_favor": a_favor}).get_json())

    hilos = [threading.Thread(target=pestana, args=(i % 2 == 0,)) for i in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sum(r["ok"] for r in resultados) == 1
    assert all("dos veces" in r["error"] for r in resultados if not r["ok"])
    ronda = c.get("/api/pos/estado").get_json()["motor"]["ronda"]
    assert ronda["votacion"]["emitidos"] == 1


def test_transacciones_concurrentes_no_gastan_de_mas():
    app = create_app(reproducible=True)
    resultados, barrera = [], threading.Barrier(8)

    def pestana(i):
        cl = app.test_client()
        barrera.wait()
        resultados.append(cl.post("/api/pow/transacciones",
                                  json={"emisor": "N00", "receptor": f"N0{i + 1}", "monto": 30}).status_code)

    hilos = [threading.Thread(target=pestana, args=(i,)) for i in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert resultados.count(200) == 3 and resultados.count(400) == 5    # 3 × 30 ≤ 100 < 4 × 30


@pytest.mark.parametrize("version", ["pow", "pos"])
@pytest.mark.parametrize("ruta", RUTAS_POST)
def test_rutas_con_datos_mal_formados_nunca_dan_500(cliente, version, ruta, ):
    for cuerpo in CUERPOS:
        resp = cliente.post(ruta.format(v=version), **cuerpo)
        assert resp.status_code < 500, (ruta, cuerpo, resp.get_json())
        datos = resp.get_json()
        assert isinstance(datos, dict) and "ok" in datos
        if not datos["ok"]:
            assert datos["error"]
    cliente.post(f"/api/{version}/minar/cancelar")


def test_json_mal_formado_mensaje_claro(cliente):
    resp = cliente.post("/api/pow/transacciones", data="{malo", content_type="application/json")
    assert resp.status_code == 400 and "JSON" in resp.get_json()["error"]
    resp = cliente.post("/api/pow/transacciones", json=[1, 2])
    assert resp.status_code == 400 and "objeto JSON" in resp.get_json()["error"]


def test_rutas_inexistentes_y_metodos(cliente):
    assert cliente.get("/api/pow/nada").status_code == 404
    assert cliente.get("/api/pow/nada").get_json()["ok"] is False
    assert cliente.get("/api/xyz/estado").status_code == 400
    assert cliente.get("/api/pow/minar").status_code == 405
    assert cliente.delete("/api/pow/estado").status_code == 405
    assert cliente.get("/no-existe").status_code == 404
    assert cliente.post("/api/pow/pos/ronda").get_json()["error"].startswith("Esta acción sólo existe")


def test_peticion_demasiado_grande(cliente):
    resp = cliente.post("/api/pow/transacciones", data="x" * 100_000, content_type="application/json")
    assert resp.status_code == 413 and resp.get_json()["ok"] is False


def test_cadena_de_un_nodo(cliente):
    datos = cliente.get("/api/pow/cadena?nodo=N03").get_json()
    assert datos["ok"] and datos["nodo"] == "N03" and datos["bloques"][0]["numero"] == 0
    assert cliente.get("/api/pow/cadena?nodo=Z").status_code == 400


def test_ataques_desde_la_ruta(cliente):
    resp = cliente.post("/api/pow/ataques", json={"tipo": "hash_alterado"})
    assert resp.status_code == 409 and "bloque" in resp.get_json()["error"]
    resp = cliente.post("/api/pow/ataques", json={"tipo": "otra_clave", "nodo": "N01"})
    assert resp.status_code == 200 and resp.get_json()["rechazado"] is True
    assert cliente.post("/api/pow/ataques", json={"tipo": "voto_doble"}).status_code == 400
    assert cliente.post("/api/pow/ataques", json={"tipo": "inventado"}).status_code == 400
