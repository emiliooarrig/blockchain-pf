"""Pruebas de regresión de la auditoría con IA, grupo G1 (red P2P, nodo completo y coordinador de sellos).

Cada prueba `test_aud_0NN_*` reproduce el defecto descrito en docs/auditoria/HALLAZGOS.md (falla sin la corrección).
"""
import threading
import time

import pytest

from models.errores import ErrorEntrada, ErrorEstado
from models.red_p2p import ServidorP2P
from tests.nodo_falso import ClaveFalsa, NodoFalso, hacer_bloque
from tests.test_red_p2p import RAPIDO, Crudo, esperar, ids_de

IDS = ["LAB-A", "LAB-B", "LAB-C", "LAB-D", "LAB-E", "LAB-F"]


@pytest.fixture
def claves():
    return {i: ClaveFalsa() for i in IDS}


@pytest.fixture
def servidores():
    lista = []

    def crear(nodo, **kw):
        s = ServidorP2P(nodo, host="127.0.0.1", puerto=0, **{**RAPIDO, **kw})
        s.iniciar()
        lista.append(s)
        return s
    yield crear
    for s in lista:
        s.detener()


def hello_de(nodo, nombre, reto="ab" * 16, **cambios):
    msg = {"tipo": "HELLO", "version": 2, "nodo": nombre, "genesis": nodo.hash_genesis, "altura": 0, "trabajo": 0,
           "punta": nodo.cadena[0]["hash"], "reto": reto, "puerto": 1234}
    msg.update(cambios)
    return msg


# ---------------------------------------------------------------- AUD-001
def test_aud_001_hello_falso_no_veta_a_la_identidad_real(claves, servidores):
    a = NodoFalso("LAB-A", claves)
    sa = servidores(a)
    for _ in range(7):                       # un atacante dice ser LAB-B y manda un AUTH basura
        k = Crudo(sa.puerto)
        k.enviar(hello_de(a, "LAB-B"))
        assert k.leer()["tipo"] == "HELLO_ACK"
        k.enviar({"tipo": "AUTH", "firma_reto": "00" * 64})
        k.leer()
        k.cerrar()
    assert not sa.vetado("LAB-B")
    assert sa.faltas_de("LAB-B") == 0
    sb = servidores(NodoFalso("LAB-B", claves, genesis=a.genesis))
    assert sb.conectar("127.0.0.1", sa.puerto) == "LAB-A"      # el LAB-B verdadero sigue pudiendo entrar


def test_aud_001_sondas_calladas_no_vetan_el_loopback(claves, servidores):
    a = NodoFalso("LAB-A", claves)
    sa = servidores(a, tiempo_saludo=0.2)
    sondas = [Crudo(sa.puerto) for _ in range(8)]
    time.sleep(1.0)                          # todas vencen el saludo
    for s in sondas:
        s.cerrar()
    assert not sa.vetado("127.0.0.1")
    sb = servidores(NodoFalso("LAB-B", claves, genesis=a.genesis))
    assert sb.conectar("127.0.0.1", sa.puerto) == "LAB-A"
