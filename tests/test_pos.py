"""Sección 5 · PoS: ningún validador con saldo; apuesta mayor al saldo, cero o negativa; votación exactamente
en 2/3; voto de un nodo que no es validador o que vota dos veces; proponente deshonesto; todos los
validadores castigados hasta quedar sin saldo. Además: sorteo ponderado y reproducible, castigo y nuevo sorteo."""
import collections

import pytest

from models import ataques
from models.bloque import ErrorValidacion, copiar, hash_bloque
from models.errores import ErrorEntrada, ErrorEstado
from models.pos import calcular_castigo, sortear
from models.validacion import validar_cadena
from tests.conftest import nueva_red, todos_sincronizados


def _ronda_manual(red, comite=3, apuesta=10):
    """Ronda con un comité de `comite` validadores que apuestan lo mismo, lista para votar."""
    red.motor.configurar(comite, "A", 50, "firma")
    if not red.pendientes:
        red.crear_transaccion("N00", "N01", 5)
    red.motor.iniciar_ronda()
    r = red.motor.ronda
    for nid in r["validadores"]:
        red.motor.apostar(nid, apuesta)
    red.motor.sortear_proponente()
    red.motor.construir_candidato()
    return r


# ---------------------------------------------------------------- sorteo
def test_sorteo_reproducible():
    vals = [{"id": "N00", "apuesta": 5}, {"id": "N01", "apuesta": 7}, {"id": "N02", "apuesta": 1}]
    assert sortear(vals, "ab" * 32, 3, 0) == sortear(vals, "ab" * 32, 3, 0)


def test_sorteo_ponderado_por_apuesta():
    vals = [{"id": "A", "apuesta": 1}, {"id": "B", "apuesta": 3}]
    conteo = collections.Counter(sortear(vals, f"{i:064x}", 1, 0)[0]["id"] for i in range(8000))
    assert abs(conteo["B"] / 8000 - 0.75) < 0.03


def test_sorteo_sin_apuestas_no_elige():
    assert sortear([], "0" * 64, 1, 0) == (None, None)


# ---------------------------------------------------------------- comité y apuestas
def test_ningun_validador_con_saldo(red_pos):
    for i, n in enumerate(red_pos.nodos):
        destino = red_pos.nodos[(i + 1) % len(red_pos.nodos)].id
        red_pos.crear_transaccion(n.id, destino, 100)        # todo el saldo queda comprometido
    with pytest.raises(ErrorEstado, match="Ningún nodo tiene saldo disponible"):
        red_pos.motor.iniciar_ronda()
    assert not red_pos.motor.activa()


@pytest.mark.parametrize("monto,mensaje", [(0, "mayor que cero"), (-5, "mayor que cero"), (101, "mayor al saldo"),
                                           (10**6, "mayor al saldo"), ("10", "mayor que cero")])
def test_apuestas_invalidas(red_pos, monto, mensaje):
    red_pos.crear_transaccion("N00", "N01", 5)
    red_pos.motor.iniciar_ronda()
    with pytest.raises(ErrorEntrada, match=mensaje):
        red_pos.motor.apostar("N02", monto)
    assert red_pos.motor.ronda["apuestas"] == {}


def test_apuesta_descuenta_lo_comprometido(red_pos):
    red_pos.crear_transaccion("N00", "N01", 60)
    red_pos.motor.iniciar_ronda()
    with pytest.raises(ErrorEntrada, match="sólo tiene 40"):
        red_pos.motor.apostar("N00", 41)
    red_pos.motor.apostar("N00", 40)
    assert red_pos.saldo_disponible("N00") == 0
    with pytest.raises(ErrorEntrada, match="Saldo insuficiente"):
        red_pos.crear_transaccion("N00", "N02", 1)        # la apuesta queda bloqueada durante la ronda


def test_apuesta_de_nodo_fuera_del_comite_y_fuera_de_etapa(red_pos):
    r = _ronda_manual(red_pos)
    with pytest.raises(ErrorEstado, match="APUESTAS"):
        red_pos.motor.apostar(r["validadores"][0], 5)
    red_pos.motor.cancelar_ronda()
    red_pos.motor.iniciar_ronda()
    fuera = next(n.id for n in red_pos.nodos if n.id not in red_pos.motor.ronda["validadores"])
    with pytest.raises(ErrorEntrada, match="no es validador"):
        red_pos.motor.apostar(fuera, 5)


def test_sorteo_sin_apuestas(red_pos):
    red_pos.crear_transaccion("N00", "N01", 5)
    red_pos.motor.iniciar_ronda()
    with pytest.raises(ErrorEstado, match="Ningún validador ha apostado"):
        red_pos.motor.sortear_proponente()


# ---------------------------------------------------------------- votación
def test_votacion_exactamente_dos_tercios_se_acepta(red_pos):
    r = _ronda_manual(red_pos)
    a, b, c = r["validadores"]
    red_pos.motor.votar(a, True)
    red_pos.motor.votar(b, True)
    red_pos.motor.votar(c, False)                                   # V = 20, A = 30 → 3V = 2A
    mensaje = red_pos.motor.cerrar_votacion()
    assert r["estado"] == "ACEPTADO", mensaje
    assert red_pos.referencia().altura == 1 and todos_sincronizados(red_pos)
    bloque = red_pos.referencia().cadena[1]
    assert sum(v["peso"] for v in bloque["votos"] if v["a_favor"]) * 3 == 2 * 30


def test_votacion_por_debajo_de_dos_tercios_se_rechaza(red_pos):
    r = _ronda_manual(red_pos)
    a, b, c = r["validadores"]
    proponente = r["proponente"]
    red_pos.motor.votar(a, True)
    red_pos.motor.votar(b, False)                                   # c no vota: cuenta como no a favor
    red_pos.motor.cerrar_votacion()
    assert r["estado"] == "RECHAZADO" and r["excluidos"] == [proponente]
    assert red_pos.referencia().altura == 0
    assert r["castigos"][0]["monto"] == 10                          # regla A: pierde toda la apuesta


def test_votos_pesan_por_apuesta(red_pos):
    red_pos.motor.configurar(3, "A", 50, "firma")
    red_pos.crear_transaccion("N00", "N01", 5)
    red_pos.motor.iniciar_ronda()
    r = red_pos.motor.ronda
    a, b, c = r["validadores"]
    red_pos.motor.apostar(a, 80)
    red_pos.motor.apostar(b, 10)
    red_pos.motor.apostar(c, 10)
    red_pos.motor.sortear_proponente()
    red_pos.motor.construir_candidato()
    red_pos.motor.votar(a, True)                                    # un solo voto, pero con 80% del peso
    red_pos.motor.votar(b, False)
    red_pos.motor.votar(c, False)
    red_pos.motor.cerrar_votacion()
    assert r["estado"] == "ACEPTADO"


def test_voto_de_no_validador_y_voto_doble(red_pos):
    r = _ronda_manual(red_pos)
    fuera = next(n.id for n in red_pos.nodos if n.id not in r["validadores"])
    with pytest.raises(ErrorEntrada, match="no es validador"):
        red_pos.motor.votar(fuera, True)
    red_pos.motor.votar(r["validadores"][0], True)
    with pytest.raises(ErrorEntrada, match="no puede votar dos veces"):
        red_pos.motor.votar(r["validadores"][0], False)
    with pytest.raises(ErrorEntrada, match="no existe"):
        red_pos.motor.votar("N55", True)
    assert len(r["votos"]) == 1


def test_votos_falsos_dentro_de_un_bloque_se_rechazan(red_pos):
    red_pos.crear_transaccion("N00", "N01", 5)
    red_pos.motor.ronda_automatica()
    for tipo, motivo in (("voto_no_validador", "no es validador"), ("voto_doble", "votó dos veces")):
        r = ataques.atacar_cadena(red_pos, tipo, "N03")
        assert r["rechazado"] and motivo in r["mensaje"]
    cadena = copiar(red_pos.referencia().cadena)
    cadena[1]["votos"][0]["peso"] += 1000
    cadena[1]["hash"] = hash_bloque(cadena[1])
    with pytest.raises(ErrorValidacion, match="no coincide con su apuesta"):
        validar_cadena(cadena, cadena[0]["hash"])


def test_bloque_sin_votos_suficientes_no_es_valido(red_pos):
    red_pos.crear_transaccion("N00", "N01", 5)
    red_pos.motor.ronda_automatica()
    cadena = copiar(red_pos.referencia().cadena)
    for v in cadena[1]["votos"]:
        v["a_favor"] = False                                        # la firma del voto ya no corresponde
    cadena[1]["hash"] = hash_bloque(cadena[1])
    with pytest.raises(ErrorValidacion, match="firma del voto"):
        validar_cadena(cadena, cadena[0]["hash"])
    cadena[1]["votos"] = cadena[1]["votos"][:1]
    cadena[1]["votos"][0]["a_favor"] = True
    cadena[1]["hash"] = hash_bloque(cadena[1])
    with pytest.raises(ErrorValidacion, match="votos insuficientes"):
        validar_cadena(cadena, cadena[0]["hash"])


def test_proponente_falso_no_pasa_el_sorteo(red_pos):
    red_pos.crear_transaccion("N00", "N01", 5)
    red_pos.motor.ronda_automatica()
    cadena = copiar(red_pos.referencia().cadena)
    otro = next(v["id"] for v in cadena[1]["validadores"] if v["id"] != cadena[1]["proponente"])
    cadena[1]["proponente"] = otro
    cadena[1]["hash"] = hash_bloque(cadena[1])
    with pytest.raises(ErrorValidacion, match="sorteo"):
        validar_cadena(cadena, cadena[0]["hash"])


# ---------------------------------------------------------------- deshonestos y castigos
@pytest.mark.parametrize("regla,fraude", [("A", "firma"), ("B", "firma"), ("A", "gasto"), ("B", "gasto")])
def test_proponente_deshonesto_castigado_y_nuevo_sorteo(red_pos, regla, fraude):
    red_pos.motor.configurar(0, regla, 50, fraude)
    red_pos.crear_transaccion("N00", "N01", 20)
    red_pos.motor.iniciar_ronda()
    red_pos.motor.apuestas_automaticas()
    red_pos.motor.sortear_proponente()
    r = red_pos.motor.ronda
    malo = r["proponente"]
    red_pos.nodo(malo).deshonesto = True
    saldo_antes = red_pos.referencia().estado.saldos[malo]
    apuesta = r["apuestas"][malo]

    red_pos.motor.construir_candidato()
    red_pos.motor.votacion_automatica()
    red_pos.motor.cerrar_votacion()
    assert r["estado"] == "RECHAZADO" and r["excluidos"] == [malo]
    valor = sum(tx["monto"] for tx in r["candidato"]["transacciones"])
    castigo = calcular_castigo(regla, apuesta, valor, 50)
    assert r["castigos"][0]["monto"] == castigo
    if regla == "B" and fraude == "firma":
        assert castigo == min(apuesta, 10)                          # ⌈0.5 · 20⌉

    red_pos.motor.ronda_automatica()                                # nuevo sorteo sin el castigado
    assert r["estado"] == "ACEPTADO"
    bloque = red_pos.referencia().cadena[1]
    assert bloque["intento"] >= 1 and bloque["excluidos"][0] == malo and bloque["proponente"] != malo
    assert todos_sincronizados(red_pos)
    estado = red_pos.referencia().estado                            # perdió el castigo y no recibió recompensa
    assert estado.saldos[malo] == saldo_antes - castigo - sum(
        tx["monto"] for tx in bloque["transacciones"] if tx["emisor"] == malo) + sum(
        tx["monto"] for tx in bloque["transacciones"] if tx["receptor"] == malo)


def test_honestos_votan_en_contra_del_deshonesto(red_pos):
    red_pos.crear_transaccion("N00", "N01", 5)
    red_pos.motor.iniciar_ronda()
    red_pos.motor.apuestas_automaticas()
    red_pos.motor.sortear_proponente()
    r = red_pos.motor.ronda
    red_pos.nodo(r["proponente"]).deshonesto = True
    red_pos.motor.construir_candidato()
    red_pos.motor.votacion_automatica()
    for nid, voto in r["votos"].items():
        assert voto["a_favor"] is (nid == r["proponente"])
        if nid != r["proponente"]:
            assert "firma inválida" in r["evaluaciones"][nid]


def test_castigos_de_ronda_fallida_se_registran_en_la_cadena(red_pos):
    red_pos.crear_transaccion("N00", "N01", 5)
    for n in red_pos.nodos:
        n.deshonesto = True
    red_pos.motor.ronda_automatica()
    assert red_pos.motor.ronda["estado"] == "FALLIDA"
    pendientes = list(red_pos.motor.castigos_pendientes)
    assert len(pendientes) == len(red_pos.motor.ronda["comite"])
    perdido = {c["validador"]: c["monto"] for c in pendientes}
    assert all(red_pos.saldo_disponible(nid) <= 100 - m for nid, m in perdido.items())

    for n in red_pos.nodos:
        n.deshonesto = False
    red_pos.motor.ronda_automatica()
    assert red_pos.motor.ronda["estado"] == "ACEPTADO" and red_pos.motor.castigos_pendientes == []
    bloque = red_pos.referencia().cadena[1]
    assert bloque["castigos"][:len(pendientes)] == pendientes
    assert todos_sincronizados(red_pos)


def test_todos_los_validadores_castigados_hasta_quedar_sin_saldo(red_pos):
    red_pos.motor.configurar(0, "A", 50, "gasto")
    red_pos.crear_transaccion("N00", "N01", 1)
    for n in red_pos.nodos:
        n.deshonesto = True
    rondas = 0
    with pytest.raises(ErrorEstado, match="Ningún nodo tiene saldo disponible"):
        for rondas in range(200):
            red_pos.motor.ronda_automatica()
            assert red_pos.motor.ronda["estado"] == "FALLIDA"
    assert rondas > 0
    assert all(red_pos.saldo_disponible(n.id) == 0 for n in red_pos.nodos)
    assert red_pos.referencia().altura == 0 and todos_sincronizados(red_pos)
    assert all(s >= 0 for s in red_pos.referencia().estado.saldos.values())


def test_ronda_automatica_y_recompensa_inmediata(red_pos):
    red_pos.crear_transaccion("N00", "N01", 5)
    red_pos.motor.ronda_automatica()
    bloque = red_pos.referencia().cadena[1]
    estado = red_pos.referencia().estado
    assert bloque["nonce"] == 0 and bloque["votos"] and bloque["validadores"]
    assert estado.pendiente_de(bloque["proponente"]) == 0           # en PoS se paga al aceptar
    total = sum(estado.saldos.values())
    assert total == 10 * 100 + 10
    assert red_pos.motor.retenido("N00") == 0                       # apuestas liberadas


def test_acciones_fuera_de_orden(red_pos):
    with pytest.raises(ErrorEstado, match="No hay una ronda"):
        red_pos.motor.sortear_proponente()
    with pytest.raises(ErrorEstado, match="No hay una ronda"):
        red_pos.motor.votar("N00", True)
    red_pos.crear_transaccion("N00", "N01", 5)
    red_pos.motor.iniciar_ronda()
    with pytest.raises(ErrorEstado, match="Ya hay una ronda en curso"):
        red_pos.motor.iniciar_ronda()
    with pytest.raises(ErrorEstado, match="VOTACION"):
        red_pos.motor.cerrar_votacion()
    with pytest.raises(ErrorEstado, match="CANDIDATO"):
        red_pos.motor.construir_candidato()
    with pytest.raises(ErrorEstado, match="ronda en curso"):
        red_pos.motor.configurar(0, "B", 50, "firma")


def test_configuracion_invalida(red_pos):
    for args in [(25, "A", 50, "firma"), (0, "C", 50, "firma"), (0, "B", 0, "firma"), (0, "B", 101, "firma"),
                 (0, "A", 50, "otro"), (-1, "A", 50, "firma")]:
        with pytest.raises(ErrorEntrada):
            red_pos.motor.configurar(*args)
