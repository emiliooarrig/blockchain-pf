"""Sección 5 · PoW: dos ganadores en la misma ronda; minar mientras ya se mina; dificultad que no se resuelve
(límite de rondas o cancelación); recompensa consultada antes de 6 confirmaciones; recompensa falsa.
Además: nonces disjuntos, todos se detienen, difusión y al menos 10 bloques seguidos."""
import time

import pytest

from models import ataques
from models.bloque import hash_bloque, preparar_hasher
from models.errores import ErrorEntrada, ErrorEstado
from models.pow import Minero, cumple_objetivo, ronda_pow
from tests.conftest import minar, nueva_red, todos_sincronizados


def test_hasher_rapido_coincide_con_hash_bloque(red_pow):
    tx = red_pow.crear_transaccion("N00", "N01", 3)
    b = {"numero": 1, "timestamp": 1.5, "transacciones": [tx], "hash_anterior": "a" * 64, "nonce": 0,
         "proponente": "N04", "recompensa": 50, "dificultad": 3}
    calcular = preparar_hasher(b)
    for nonce in (0, 1, 17, 123456789):
        assert calcular(nonce) == hash_bloque({**b, "nonce": nonce})


def test_nonces_disjuntos():
    n, k = 10, 7
    probados = {i: [] for i in range(n)}

    def hasher(i):
        return lambda nonce: probados[i].append(nonce) or "f" * 64

    mineros = [Minero(i, f"N{i:02d}", hasher(i)) for i in range(n)]
    for _ in range(5):
        assert ronda_pow(mineros, n, k, 3) == []
    todos = [x for lista in probados.values() for x in lista]
    assert len(todos) == len(set(todos)) == n * k * 5           # nadie repite un nonce
    for i, lista in probados.items():
        assert lista == [i + j * n for j in range(k * 5)]        # minero i: i, i+N, i+2N, ...


def test_dos_ganadores_en_la_misma_ronda_gana_el_hash_menor():
    hashes = {2: "00ab" + "1" * 60, 5: "00aa" + "1" * 60}

    def hasher(i):
        return lambda nonce: hashes.get(i, "f" * 64)

    mineros = [Minero(i, f"N{i:02d}", hasher(i)) for i in range(10)]
    ganadores = ronda_pow(mineros, 10, 3, 2)
    assert [m.id for _, m in ganadores] == ["N05", "N02"]
    assert mineros[2].nonce == 2 and mineros[5].nonce == 5        # cada uno conserva su nonce ganador


def test_empate_real_en_el_motor(red_pow):
    red_pow.crear_transaccion("N00", "N01", 5)
    red_pow.motor.iniciar(1, 64, 100, pausa_ms=0, en_hilo=False)
    red_pow.motor.tick()
    validos = [m for m in red_pow.motor.mineros if cumple_objetivo(m.ultimo_hash, 1)]
    assert len(validos) > 1 and red_pow.motor.ultimo["empate"]
    ganador = min(validos, key=lambda m: m.ultimo_hash)
    assert red_pow.referencia().ultimo_hash == ganador.ultimo_hash
    assert red_pow.referencia().cadena[-1]["proponente"] == ganador.id
    assert [m.estado for m in red_pow.motor.mineros].count("ganador") == 1
    assert all(m.estado == "detenido" for m in red_pow.motor.mineros if m is not ganador)
    assert any("Desempate" in e["texto"] for e in red_pow.bitacora)


def test_bloque_ganador_se_difunde_y_todos_lo_validan(red_pow):
    red_pow.crear_transaccion("N00", "N01", 5)
    minar(red_pow, 1)
    assert todos_sincronizados(red_pow) and red_pow.referencia().altura == 1
    b = red_pow.referencia().cadena[1]
    assert b["hash"].startswith("00") and b["nonce"] % 10 == red_pow.nodo(b["proponente"]).indice
    assert any("validaron la cadena completa" in e["texto"] for e in red_pow.bitacora)


def test_minar_mientras_ya_se_mina(red_pow):
    red_pow.crear_transaccion("N00", "N01", 5)
    red_pow.motor.iniciar(6, 1, 1000, pausa_ms=0, en_hilo=False)
    with pytest.raises(ErrorEstado, match="Ya hay un minado en curso"):
        red_pow.motor.iniciar(3, 10, 10, en_hilo=False)


def test_limite_de_rondas(red_pow):
    red_pow.crear_transaccion("N00", "N01", 5)
    red_pow.motor.iniciar(6, 1, 3, pausa_ms=0, en_hilo=False)
    for _ in range(3):
        red_pow.motor.tick()
    assert not red_pow.motor.minando
    assert "límite de 3 rondas" in red_pow.motor.mensaje
    assert red_pow.referencia().altura == 0 and len(red_pow.pendientes) == 1


def test_cancelar_minado_en_hilo(red_pow):
    red_pow.crear_transaccion("N00", "N01", 5)
    red_pow.motor.iniciar(6, 50, 100_000, pausa_ms=10)
    time.sleep(0.1)
    assert red_pow.motor.minando
    red_pow.motor.cancelar()
    assert not red_pow.motor.minando
    with pytest.raises(ErrorEstado, match="No hay ningún minado"):
        red_pow.motor.cancelar()
    ronda = red_pow.motor.ronda
    time.sleep(0.1)
    assert red_pow.motor.ronda == ronda                      # el hilo realmente se detuvo


def test_recompensa_madura_tras_6_confirmaciones(red_pow):
    red_pow.crear_transaccion("N00", "N01", 5)
    minar(red_pow, 1)
    ganador = red_pow.referencia().cadena[1]["proponente"]
    fila = lambda: next(r for r in red_pow.recompensas() if r["numero"] == 1)

    assert fila()["estado"] == "pendiente" and fila()["confirmaciones"] == 0
    assert red_pow.referencia().estado.pendiente_de(ganador) >= 50
    # no se puede gastar una recompensa sin madurar
    with pytest.raises(ErrorEntrada, match="Saldo insuficiente"):
        red_pow.crear_transaccion(ganador, "N00" if ganador != "N00" else "N01", red_pow.saldo_disponible(ganador) + 1)

    minar(red_pow, 5)
    assert fila()["estado"] == "pendiente" and fila()["confirmaciones"] == 5
    minar(red_pow, 1)
    assert fila()["estado"] == "acreditada" and fila()["confirmaciones"] == 6
    assert any("Recompensa del bloque #1" in e["texto"] for e in red_pow.bitacora)


def test_recompensa_consultada_antes_de_6_confirmaciones(cliente):
    cliente.post("/api/pow/transacciones", json={"emisor": "N00", "receptor": "N01", "monto": 5})
    resp = cliente.post("/api/pow/minar", json={"dificultad": 1, "nonces_por_ronda": 50, "pausa_ms": 0})
    assert resp.status_code == 200
    for _ in range(200):
        if not cliente.get("/api/pow/estado").get_json()["motor"]["minando"]:
            break
        time.sleep(0.02)
    ganador = cliente.get("/api/pow/cadena").get_json()["bloques"][1]["proponente"]
    datos = cliente.get(f"/api/pow/nodos/{ganador}/recompensas").get_json()
    assert datos["ok"] and datos["pendiente"] == 50
    assert datos["recompensas"][0]["estado"] == "pendiente" and datos["recompensas"][0]["requeridas"] == 6


def test_recompensa_falsa(red_pow):
    minar(red_pow, 1)
    r = ataques.atacar_cadena(red_pow, "recompensa_falsa", "N04")
    assert r["rechazado"] and "recompensa falsa" in r["mensaje"]
    assert red_pow.referencia().altura == 1


def test_diez_bloques_seguidos(red_pow):
    minar(red_pow, 10)
    assert red_pow.referencia().altura == 10
    assert todos_sincronizados(red_pow)
    acreditadas = [r for r in red_pow.recompensas() if r["estado"] == "acreditada"]
    assert [r["numero"] for r in acreditadas] == [1, 2, 3, 4]   # maduran las primeras recompensas
    estado = red_pow.referencia().estado
    total = sum(estado.saldos.values()) + sum(r["monto"] for r in estado.recompensas)
    assert total == 10 * 100 + 10 * 50                          # no se crea ni se pierde dinero


def test_reproducible_con_la_misma_semilla():
    a, b = nueva_red("pow", semilla=11), nueva_red("pow", semilla=11)
    for red in (a, b):
        red.crear_transaccion("N02", "N07", 9)
        minar(red, 3)
    assert a.referencia().ultimo_hash == b.referencia().ultimo_hash
    assert nueva_red("pow", semilla=12).nodos[0].claves.publica != a.nodos[0].claves.publica
