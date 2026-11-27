"""Integración real: 3 NodoCompleto + 3 ServidorP2P en 127.0.0.1 (puerto 0), conectados en malla."""
import time

import pytest

from models.nodo_completo import conectar_nodo_y_servidor
from models.red_p2p import ServidorP2P
from tests.laboratorios import bloque_externo, crear_laboratorios, nuevo_nodo, transferencia

RAPIDO = dict(intervalo_ping=0.2, tiempo_sin_respuesta=2.0, tiempo_saludo=3.0, tiempo_sync=5.0)
IDS = ("LAB-A", "LAB-B", "LAB-C")


def esperar(cond, limite=10.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def ahora():
    return time.time() - 100


@pytest.fixture(scope="module")
def labs(tmp_path_factory):
    return crear_laboratorios(tmp_path_factory.mktemp("labs_red"))


@pytest.fixture
def red(tmp_path, labs):
    """Devuelve {id: (nodo, servidor)} con la malla completa ya conectada."""
    nodos, servidores = {}, {}
    for nid in IDS:
        nodos[nid] = nuevo_nodo(tmp_path / nid, labs, nid)
        servidores[nid] = ServidorP2P(nodos[nid], host="127.0.0.1", puerto=0, **RAPIDO)
        servidores[nid].iniciar()
        conectar_nodo_y_servidor(nodos[nid], servidores[nid])
    servidores["LAB-B"].conectar("127.0.0.1", servidores["LAB-A"].puerto)
    servidores["LAB-C"].conectar("127.0.0.1", servidores["LAB-A"].puerto)
    servidores["LAB-C"].conectar("127.0.0.1", servidores["LAB-B"].puerto)
    assert esperar(lambda: all(len(s.pares_publico()) == 2 for s in servidores.values()))
    yield {nid: (nodos[nid], servidores[nid]) for nid in IDS}
    for nodo in nodos.values():
        nodo.detener_minado()
    for s in servidores.values():
        s.detener()


def misma_punta(red, altura):
    puntas = {n.punta for n, _ in red.values()}
    return len(puntas) == 1 and all(n.altura == altura for n, _ in red.values())


def test_tx_se_propaga_y_el_bloque_converge(red, labs):
    a, b, c = (red[i][0] for i in IDS)
    tx = transferencia(labs, "LAB-A", "LAB-B", 5, ahora())
    a.agregar_transaccion(tx)
    assert esperar(lambda: b.pendientes == [tx] and c.pendientes == [tx])
    a.iniciar_minado(2)
    assert esperar(lambda: misma_punta(red, 1))
    assert a.cadena[1]["proponente"] == "LAB-A" and a.cadena[1]["transacciones"] == [tx]
    assert esperar(lambda: b.pendientes == [] and c.pendientes == [] and a.pendientes == [])
    assert b.estado.saldos["LAB-B"] == 105 and c.estado.saldos["LAB-A"] == 95


def test_particion_y_reorganizacion(red, labs):
    (a, sa), (b, sb), (c, sc) = red["LAB-A"], red["LAB-B"], red["LAB-C"]
    for par in sc.pares_publico():
        sc.desconectar(par["id"])
    assert esperar(lambda: not sc.pares_publico() and [p["id"] for p in sa.pares_publico()] == ["LAB-B"]
                   and [p["id"] for p in sb.pares_publico()] == ["LAB-A"])

    tx_c = transferencia(labs, "LAB-C", "LAB-B", 3, ahora())
    c.agregar_transaccion(tx_c)
    c.iniciar_minado(1)
    assert esperar(lambda: c.altura == 1 and not c.minando)

    for k in range(2):                                    # A (con B) mina dos bloques: más trabajo
        a.agregar_transaccion(transferencia(labs, "LAB-A", "LAB-B", 1 + k, ahora() + k))
        a.iniciar_minado(1)
        assert esperar(lambda: a.altura == k + 1 and not a.minando)
    assert esperar(lambda: b.altura == 2 and b.punta == a.punta)
    assert c.altura == 1 and c.punta != a.punta

    sc.conectar("127.0.0.1", sa.puerto)
    sc.conectar("127.0.0.1", sb.puerto)
    assert esperar(lambda: misma_punta(red, 2))
    assert c.pendientes == [tx_c]                         # la tx de la rama perdida volvió a pendientes
    assert a.pendientes == [] and b.pendientes == []


def test_bloque_alterado_recibe_falta_y_nadie_lo_acepta(red, labs):
    (a, sa), (b, sb), (c, sc) = red["LAB-A"], red["LAB-B"], red["LAB-C"]
    bueno = bloque_externo(labs, labs[0], [transferencia(labs, "LAB-C", "LAB-B", 2, ahora())], "LAB-A")
    alterado = {**bueno, "hash": "0" * 64}   # el contenido ya no corresponde al hash
    assert sa.difundir("BLOQUE", {"bloque": alterado}) == 2
    assert esperar(lambda: sb.faltas_de("LAB-A") >= 1 and sc.faltas_de("LAB-A") >= 1)
    assert a.altura == b.altura == c.altura == 0
    assert alterado["hash"] not in b._hashes and alterado["hash"] not in c._hashes
    # el bloque verdadero sí se acepta en toda la red
    assert sa.difundir("BLOQUE", {"bloque": bueno}) == 2
    assert esperar(lambda: b.altura == 1 and c.altura == 1)


def test_nodo_bloqueado_detiene_su_servidor(red):
    a, sa = red["LAB-A"]
    a.bloquear()
    assert esperar(lambda: not sa.activo)
    assert esperar(lambda: len(red["LAB-B"][1].pares_publico()) == 1)
