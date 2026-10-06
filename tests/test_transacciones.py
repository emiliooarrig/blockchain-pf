"""Sección 5 · Transacciones: firma alterada; firmada por otra clave; saldo insuficiente; doble gasto en el mismo
bloque o en bloques distintos; lista de pendientes vacía al intentar minar o proponer."""
import pytest

from models import ataques
from models.bloque import ErrorValidacion, aplicar_transacciones, nueva_transaccion, revisar_transaccion, serializar
from models.cripto import verificar
from models.errores import ErrorEntrada, ErrorEstado
from tests.conftest import minar, todos_sincronizados


def test_firma_valida_y_serializacion_canonica(red_pow):
    tx = red_pow.crear_transaccion("N00", "N01", 10)
    assert serializar(tx) == b'{"emisor":"N00","monto":10,"receptor":"N01","timestamp":%s}' % repr(tx["timestamp"]).encode()
    assert verificar(red_pow.nodo("N00").claves.publica, serializar(tx), tx["firma"])


def test_firma_alterada(red_pow):
    tx = nueva_transaccion("N00", "N01", 10, red_pow.reloj(), red_pow.nodo("N00").claves)
    tx["firma"] = tx["firma"][:-1] + ("0" if tx["firma"][-1] != "0" else "1")
    with pytest.raises(ErrorEntrada, match="firma inválida"):
        red_pow.agregar_pendiente(tx)
    assert red_pow.pendientes == []


def test_contenido_alterado_despues_de_firmar(red_pow):
    resultado = ataques.atacar_transaccion(red_pow, "firma_alterada", "N02")
    assert resultado["rechazado"] and "firma inválida" in resultado["mensaje"]
    assert red_pow.pendientes == []


def test_transaccion_firmada_por_otra_clave(red_pow):
    tx = nueva_transaccion("N00", "N05", 10, red_pow.reloj(), red_pow.nodo("N05").claves)
    with pytest.raises(ErrorEntrada, match="no corresponde a la clave pública de N00"):
        red_pow.agregar_pendiente(tx)
    assert ataques.atacar_transaccion(red_pow, "otra_clave", "N00")["rechazado"]


def test_saldo_insuficiente(red_pow):
    with pytest.raises(ErrorEntrada, match="Saldo insuficiente"):
        red_pow.crear_transaccion("N00", "N01", 101)
    assert red_pow.pendientes == []


def test_doble_gasto_en_pendientes(red_pow):
    red_pow.crear_transaccion("N00", "N01", 60)
    with pytest.raises(ErrorEntrada, match="Saldo insuficiente.*60 ya comprometido"):
        red_pow.crear_transaccion("N00", "N02", 60)
    assert len(red_pow.pendientes) == 1
    assert ataques.atacar_transaccion(red_pow, "doble_gasto", "N03")["rechazado"]


def test_doble_gasto_en_el_mismo_bloque(red_pow):
    estado = red_pow.referencia().estado.copia()
    claves = red_pow.nodo("N00").claves
    txs = [nueva_transaccion("N00", "N01", 70, red_pow.reloj(), claves),
           nueva_transaccion("N00", "N02", 70, red_pow.reloj(), claves)]
    with pytest.raises(ErrorValidacion, match="doble gasto dentro del bloque"):
        aplicar_transacciones(estado, txs)


def test_misma_transaccion_dos_veces_en_un_bloque(red_pow):
    estado = red_pow.referencia().estado.copia()
    tx = nueva_transaccion("N00", "N01", 5, red_pow.reloj(), red_pow.nodo("N00").claves)
    with pytest.raises(ErrorValidacion, match="aparece dos veces"):
        aplicar_transacciones(estado, [tx, dict(tx)])


def test_bloque_minado_con_doble_gasto_es_rechazado_por_la_red(red_pow):
    antes = red_pow.referencia().ultimo_hash
    r = ataques.atacar_cadena(red_pow, "doble_gasto_bloque", "N09")
    assert r["rechazado"] and "doble gasto dentro del bloque" in r["mensaje"]
    assert all(n.ultimo_hash == antes for n in red_pow.nodos)


def test_doble_gasto_en_bloques_distintos(red_pow):
    tx = red_pow.crear_transaccion("N00", "N01", 10)
    minar(red_pow, 1)
    with pytest.raises(ErrorEntrada, match="ya está en la cadena"):
        red_pow.agregar_pendiente(dict(tx))
    with pytest.raises(ErrorValidacion, match="doble gasto entre bloques"):
        revisar_transaccion(red_pow.referencia().estado, tx)
    assert ataques.atacar_transaccion(red_pow, "repetida", None)["rechazado"]


def test_pendientes_vacia_al_minar(red_pow):
    with pytest.raises(ErrorEstado, match="No hay transacciones pendientes"):
        red_pow.motor.iniciar(3, 10, 10, auto_transacciones=False, en_hilo=False)
    assert not red_pow.motor.minando


def test_pendientes_vacia_al_proponer(red_pos):
    with pytest.raises(ErrorEstado, match="No hay transacciones pendientes"):
        red_pos.motor.iniciar_ronda()
    assert red_pos.motor.ronda is None


def test_transacciones_minadas_salen_de_pendientes_y_actualizan_saldos(red_pow):
    red_pow.crear_transaccion("N00", "N01", 30)
    minar(red_pow, 1)
    estado = red_pow.referencia().estado
    assert red_pow.pendientes == []
    assert estado.saldos["N00"] == 70 and estado.saldos["N01"] == 130
    assert todos_sincronizados(red_pow)
