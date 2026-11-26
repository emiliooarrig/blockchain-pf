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


# ---------------------------------------------------------------- AUD-008
def firma_auth(nodo, reto_iniciador, reto_respondedor, firmante, destinatario):
    """Firma de saludo ligada al canal (AUD-008): dominio, génesis, ambos retos y los dos extremos."""
    return nodo.firmar(f"sellalo-p2p|{nodo.hash_genesis}|{reto_iniciador}|{reto_respondedor}|{firmante}|"
                       f"{destinatario}".encode("utf-8"))


def test_aud_008_firma_de_un_canal_no_sirve_en_otro(claves, servidores):
    a, b = NodoFalso("LAB-A", claves), NodoFalso("LAB-B", claves)
    sa, sb = servidores(a), servidores(b)
    # M dice ser LAB-A ante B y recibe el reto de B ...
    m_b = Crudo(sb.puerto)
    m_b.enviar(hello_de(b, "LAB-A", reto="11" * 16))
    ack_b = m_b.leer()
    assert ack_b["tipo"] == "HELLO_ACK"
    # ... se lo planta como reto propio a LAB-A (que firma "el reto del que llama") y reenvía esa firma a B
    m_a = Crudo(sa.puerto)
    m_a.enviar(hello_de(a, "LAB-B", reto=ack_b["reto"]))
    ack_a = m_a.leer()
    assert ack_a["tipo"] == "HELLO_ACK"
    m_b.enviar({"tipo": "AUTH", "firma_reto": ack_a["firma_reto"]})
    time.sleep(0.5)
    assert "LAB-A" not in ids_de(sb)          # M no puede quedar registrado como LAB-A
    m_a.cerrar()
    m_b.cerrar()


def test_aud_008_saludo_legitimo_con_firma_ligada(claves, servidores):
    a = NodoFalso("LAB-A", claves)
    sa = servidores(a)
    k = Crudo(sa.puerto)
    reto = "cd" * 16
    k.enviar(hello_de(a, "LAB-B", reto=reto))
    ack = k.leer()
    b = NodoFalso("LAB-B", claves, genesis=a.genesis)
    assert ack["tipo"] == "HELLO_ACK"
    k.enviar({"tipo": "AUTH", "firma_reto": firma_auth(b, reto, ack["reto"], "LAB-B", "LAB-A")})
    assert esperar(lambda: ids_de(sa) == {"LAB-B"})
    k.cerrar()


def crudo_autenticado(servidor, nodo_servidor, claves, nombre, **extra):
    """Par manual que completa el saludo (con firma ligada al canal) como `nombre`."""
    k = Crudo(servidor.puerto)
    reto = "ab" * 16
    k.enviar(hello_de(nodo_servidor, nombre, reto=reto, **extra))
    ack = k.leer()
    assert ack["tipo"] == "HELLO_ACK"
    propio = NodoFalso(nombre, claves, genesis=nodo_servidor.genesis)
    k.enviar({"tipo": "AUTH", "firma_reto": firma_auth(propio, reto, ack["reto"], nombre, ack["nodo"])})
    assert esperar(lambda: nombre in ids_de(servidor))
    return k


# ---------------------------------------------------------------- AUD-009
def test_aud_009_bloque_basura_con_hash_ajeno_no_quema_el_legitimo(claves, servidores):
    a = NodoFalso("LAB-A", claves)
    sa = servidores(a)
    legitimo = hacer_bloque(a.cadena[0], "legitimo")
    m = crudo_autenticado(sa, a, claves, "LAB-B")
    basura = {"numero": 1, "hash_anterior": "ff" * 32, "hash": legitimo["hash"], "marca": "basura"}
    m.enviar({"tipo": "BLOQUE", "bloque": basura})
    assert esperar(lambda: sa.faltas_de("LAB-B") >= 1 or len(a.llamadas_bloque) >= 1)
    c = crudo_autenticado(sa, a, claves, "LAB-C")
    c.enviar({"tipo": "BLOQUE", "bloque": legitimo})
    assert esperar(lambda: len(a.cadena) == 2)             # el bloque verdadero entra pese al hash repetido
    m.cerrar()
    c.cerrar()


class NodoRechazaUnaVez(NodoFalso):
    """Rechaza la primera vez cada transacción (p. ej. llegó antes que su financiación) y la acepta después."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.intentos = {}

    def agregar_transaccion(self, tx, origen=""):
        n = self.intentos[tx["id"]] = self.intentos.get(tx["id"], 0) + 1
        if n == 1:
            raise ErrorEntrada("saldo insuficiente")
        return super().agregar_transaccion(tx, origen)


def test_aud_009_tx_rechazada_no_queda_marcada_como_vista(claves, servidores):
    a = NodoRechazaUnaVez("LAB-A", claves)
    sa = servidores(a)
    m = crudo_autenticado(sa, a, claves, "LAB-B")
    tx = {"id": "t" * 64, "emisor": "LAB-B", "receptor": "LAB-A", "monto": 5}
    m.enviar({"tipo": "TX", "tx": tx})
    assert esperar(lambda: a.intentos.get(tx["id"]) == 1)
    m.enviar({"tipo": "TX", "tx": tx})                     # reintento tras llegar la financiación
    assert esperar(lambda: tx in a.pendientes)
    m.cerrar()
