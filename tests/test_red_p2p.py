"""Pruebas del transporte P2P con sockets reales en 127.0.0.1 y nodos falsos."""
import json
import socket
import threading
import time

import pytest

from models.errores import ErrorEntrada, ErrorEstado
from models.red_p2p import ServidorP2P
from tests.nodo_falso import ClaveFalsa, NodoFalso, crear_genesis, hacer_bloque

IDS = ["LAB-A", "LAB-B", "LAB-C", "LAB-D", "LAB-E", "LAB-F"]
RAPIDO = dict(intervalo_ping=0.2, tiempo_sin_respuesta=1.5, tiempo_saludo=2.0, tiempo_sync=3.0)


def esperar(cond, limite=5.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


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


def ids_de(s):
    return {p["id"] for p in s.pares_publico()}


def mallar(claves, servidores, n=3):
    nodos = [NodoFalso(IDS[i], claves) for i in range(n)]
    srv = [servidores(x) for x in nodos]
    for i in range(n):
        for j in range(i + 1, n):
            assert srv[i].conectar("127.0.0.1", srv[j].puerto) == IDS[j]
    assert esperar(lambda: all(len(s.pares_publico()) == n - 1 for s in srv))   # ambos extremos registrados
    return nodos, srv


class Crudo:
    """Par manual para probar el servidor con mensajes a mano."""

    def __init__(self, puerto):
        self.sock = socket.create_connection(("127.0.0.1", puerto), timeout=3)
        self.buf = b""

    def enviar(self, obj):
        self.sock.sendall(json.dumps(obj).encode() + b"\n")

    def crudo(self, datos: bytes):
        self.sock.sendall(datos)

    def leer(self, espera=3.0):
        self.sock.settimeout(espera)
        while b"\n" not in self.buf:
            try:
                d = self.sock.recv(65536)
            except (socket.timeout, OSError):
                return None
            if not d:
                return {"tipo": "<cerrado>"}
            self.buf += d
        linea, self.buf = self.buf.split(b"\n", 1)
        return json.loads(linea)

    def cerrado(self, espera=3.0):
        fin = time.monotonic() + espera
        while time.monotonic() < fin:
            m = self.leer(0.3)
            if m is not None and m["tipo"] == "<cerrado>":
                return True
        return False

    def saludar(self, nodo, firma_mala=False):
        reto = "ab" * 16
        self.enviar({"tipo": "HELLO", "version": 2, "nodo": nodo.id, "genesis": nodo.hash_genesis,
                     "altura": 0, "trabajo": 0, "punta": nodo.cadena[0]["hash"], "reto": reto, "puerto": 1234})
        ack = self.leer()
        if ack is None or ack["tipo"] != "HELLO_ACK":
            return ack
        datos = f"{ack['reto']}|{nodo.id}".encode()
        firma = nodo.firmar(b"otra cosa" if firma_mala else datos)
        self.enviar({"tipo": "AUTH", "firma_reto": firma})
        return ack

    def cerrar(self):
        self.sock.close()


def test_malla_de_tres_nodos_autenticados(claves, servidores):
    nodos, srv = mallar(claves, servidores)
    assert esperar(lambda: all(len(s.pares_publico()) == 2 for s in srv))
    for s, n in zip(srv, nodos):
        assert ids_de(s) == set(IDS[:3]) - {n.id}
    p = srv[0].pares_publico()[0]
    assert set(p) >= {"id", "direccion", "altura", "punta", "trabajo", "latencia_ms", "estado", "conectado_desde"}
    assert esperar(lambda: all(q["latencia_ms"] is not None for q in srv[0].pares_publico()))


def test_genesis_distinto_rechazado(claves, servidores):
    a = NodoFalso("LAB-A", claves)
    otro = crear_genesis({i: ClaveFalsa() for i in IDS})
    b = NodoFalso("LAB-B", claves, genesis=otro)
    sa, sb = servidores(a), servidores(b)
    with pytest.raises(ErrorEstado, match="génesis"):
        sb.conectar("127.0.0.1", sa.puerto)
    assert not sa.pares_publico() and not sb.pares_publico()


def test_id_desconocido_propio_y_repetido(claves, servidores):
    a, b = NodoFalso("LAB-A", claves), NodoFalso("LAB-B", claves)
    sa, sb = servidores(a), servidores(b)
    desconocido = NodoFalso("LAB-X", {**claves, "LAB-X": ClaveFalsa()}, genesis=a.genesis)
    c = Crudo(sa.puerto)
    r = c.saludar(desconocido)
    assert r["tipo"] == "HELLO_REJECT" and "desconocida" in r["motivo"]
    c.cerrar()
    c = Crudo(sa.puerto)
    assert c.saludar(NodoFalso("LAB-A", claves, genesis=a.genesis))["tipo"] == "HELLO_REJECT"
    c.cerrar()
    sb.conectar("127.0.0.1", sa.puerto)
    with pytest.raises(ErrorEstado, match="ya conectado"):
        sb.conectar("127.0.0.1", sa.puerto)
    assert len(sa.pares_publico()) == 1


def test_firma_de_reto_falsa_rechazada(claves, servidores):
    a = NodoFalso("LAB-A", claves)
    sa = servidores(a)
    c = Crudo(sa.puerto)
    c.saludar(NodoFalso("LAB-D", claves, genesis=a.genesis), firma_mala=True)
    r = c.leer()
    assert r["tipo"] == "HELLO_REJECT" and "firma" in r["motivo"]
    assert c.cerrado()
    assert not sa.pares_publico()


def test_nodo_bloqueado_no_inicia_ni_conecta(claves):
    bloqueado = NodoFalso("LAB-A", claves, desbloqueado=False)
    s = ServidorP2P(bloqueado, host="127.0.0.1", puerto=0)
    with pytest.raises(ErrorEstado):
        s.iniciar()
    with pytest.raises(ErrorEstado):
        s.conectar("127.0.0.1", 6000)


def test_conectar_valida_ip_y_puerto(claves, servidores):
    s = servidores(NodoFalso("LAB-A", claves))
    for ip, puerto in [("999.1.1.1", 6000), ("hola", 6000), ("127.0.0.1", 0), ("127.0.0.1", 70000),
                       ("127.0.0.1", "abc"), ("127.0.0.1", None)]:
        with pytest.raises(ErrorEntrada):
            s.conectar(ip, puerto)


def test_bloque_llega_a_todos_por_gossip_sin_duplicarse(claves, servidores):
    nodos, srv = mallar(claves, servidores)
    b = hacer_bloque(nodos[0].cadena[-1], "nuevo")
    nodos[0].cadena.append(b)
    assert srv[0].difundir("BLOQUE", {"bloque": b}) == 2
    assert esperar(lambda: all(n.cadena[-1]["hash"] == b["hash"] for n in nodos))
    time.sleep(0.5)
    assert nodos[1].llamadas_bloque == [b["hash"]] and nodos[2].llamadas_bloque == [b["hash"]]
    assert nodos[0].llamadas_bloque == []


def test_tx_se_entrega_y_se_reenvia(claves, servidores):
    nodos, srv = mallar(claves, servidores)
    tx = {"id": "t1", "monto": 5}
    srv[0].difundir("TX", {"tx": tx})
    assert esperar(lambda: all(n.pendientes == [tx] for n in nodos[1:]))
    time.sleep(0.3)
    assert nodos[1].pendientes == [tx] and nodos[2].pendientes == [tx]


def test_sincronizacion_por_paginas(claves, servidores):
    a = NodoFalso("LAB-A", claves)
    b = NodoFalso("LAB-B", claves, genesis=a.genesis)
    a.extender(250)
    sa, sb = servidores(a), servidores(b)
    sb.conectar("127.0.0.1", sa.puerto)
    assert esperar(lambda: len(b.cadena) == 251)
    assert b.cadena == a.cadena
    assert a.llamadas_bloques_desde == [1, 101, 201]
    assert b.cadenas_recibidas == 1


def test_bloque_lejano_provoca_sincronizacion(claves, servidores):
    nodos, srv = mallar(claves, servidores, 2)
    a, b = nodos
    a.extender(5)
    siguiente = hacer_bloque(a.cadena[-1], "x")
    a.cadena.append(siguiente)          # b esta 6 bloques atras: el bloque no enlaza
    srv[0].difundir("BLOQUE", {"bloque": siguiente})
    assert esperar(lambda: b.cadena == a.cadena)


def test_datos_malos_suman_faltas_y_vetan(claves, servidores):
    a = NodoFalso("LAB-A", claves)
    sa = servidores(a, segundos_veto=30)
    d = NodoFalso("LAB-D", claves, genesis=a.genesis)
    c = Crudo(sa.puerto)
    assert c.saludar(d)["tipo"] == "HELLO_ACK"
    assert esperar(lambda: ids_de(sa) == {"LAB-D"})
    c.crudo(b"esto no es json\n")
    c.enviar({"tipo": "TIPO_RARO"})
    c.enviar({"sin_tipo": 1})
    assert esperar(lambda: sa.faltas_de("LAB-D") == 3)
    c.crudo(b"[1,2,3]\n")
    c.crudo(b"basura otra vez\n")        # 5a falta: veto y cierre
    assert c.cerrado()
    assert sa.vetado("LAB-D")
    assert not sa.pares_publico()
    c.cerrar()
    c2 = Crudo(sa.puerto)
    r = c2.saludar(d)
    assert r["tipo"] == "HELLO_REJECT" and "vetado" in r["motivo"]
    c2.cerrar()
    # el servidor sigue vivo para los demas
    sb = servidores(NodoFalso("LAB-B", claves, genesis=a.genesis))
    assert sb.conectar("127.0.0.1", sa.puerto) == "LAB-A"


def test_linea_mayor_a_1mib_cierra_y_no_tumba(claves, servidores):
    a = NodoFalso("LAB-A", claves)
    sa = servidores(a)
    c = Crudo(sa.puerto)
    c.saludar(NodoFalso("LAB-E", claves, genesis=a.genesis))
    assert esperar(lambda: ids_de(sa) == {"LAB-E"})
    try:
        c.crudo(b"x" * (1024 * 1024 + 2048))
    except OSError:
        pass
    assert c.cerrado()
    assert esperar(lambda: not sa.pares_publico())
    assert sa.faltas_de("LAB-E") == 1
    sb = servidores(NodoFalso("LAB-B", claves, genesis=a.genesis))
    assert sb.conectar("127.0.0.1", sa.puerto) == "LAB-A"


def test_mensaje_antes_de_auth_suma_falta_y_cierra(claves, servidores):
    sa = servidores(NodoFalso("LAB-A", claves))
    c = Crudo(sa.puerto)
    c.enviar({"tipo": "TX", "tx": {"id": "x"}})
    assert c.leer()["tipo"] == "HELLO_REJECT"
    assert c.cerrado()
    assert sa.faltas_de("127.0.0.1") >= 1
    assert not sa.pares_publico()
    assert sa.nodo.pendientes == []
    c = Crudo(sa.puerto)                   # tambien tras HELLO, sin AUTH
    c.enviar({"tipo": "HELLO", "version": 2, "nodo": "LAB-D", "genesis": sa.nodo.hash_genesis, "altura": 0,
              "trabajo": 0, "punta": "", "reto": "cd" * 16, "puerto": 1})
    assert c.leer()["tipo"] == "HELLO_ACK"
    c.enviar({"tipo": "BLOQUE", "bloque": {}})
    assert c.leer()["tipo"] == "HELLO_REJECT"
    c.cerrar()
    assert not sa.pares_publico()


def test_par_que_no_responde_ping_se_desconecta(claves, servidores):
    a = NodoFalso("LAB-A", claves)
    sa = servidores(a, tiempo_sin_respuesta=0.8)
    c = Crudo(sa.puerto)
    c.saludar(NodoFalso("LAB-D", claves, genesis=a.genesis))
    assert esperar(lambda: ids_de(sa) == {"LAB-D"})
    assert esperar(lambda: not sa.pares_publico(), 4)
    c.cerrar()


def test_desconexion_y_reconexion(claves, servidores):
    nodos, srv = mallar(claves, servidores, 2)
    assert srv[0].desconectar("LAB-B")
    assert esperar(lambda: not srv[0].pares_publico() and not srv[1].pares_publico())
    assert not srv[0].desconectar("LAB-B")
    assert srv[1].conectar("127.0.0.1", srv[0].puerto) == "LAB-A"
    assert esperar(lambda: ids_de(srv[0]) == {"LAB-B"})
    srv[1].detener()                       # caida del nodo B
    assert esperar(lambda: not srv[0].pares_publico())


def test_manejador_registrado_recibe_sello_firma(claves, servidores):
    nodos, srv = mallar(claves, servidores, 2)
    recibidos = []
    srv[0].registrar_manejador("SELLO_FIRMA", lambda par, m: recibidos.append((par, m)))
    srv[0].registrar_manejador("SELLO_PROPUESTO", lambda par, m: 1 / 0)   # no debe tumbar el hilo
    srv[1].difundir("SELLO_PROPUESTO", {"sello": {}})
    srv[1].difundir("SELLO_FIRMA", {"id_sello": "s1", "autor": "LAB-B", "firma": "ff"})
    assert esperar(lambda: len(recibidos) == 1)
    par, m = recibidos[0]
    assert par == "LAB-B" and m["id_sello"] == "s1" and m["tipo"] == "SELLO_FIRMA"
    assert esperar(lambda: any("manejador" in t for _, t in nodos[0].eventos))
    assert ids_de(srv[0]) == {"LAB-B"}
    with pytest.raises(ErrorEntrada):
        srv[0].registrar_manejador("BLOQUE", lambda *a: None)


def test_detener_cierra_hilos(claves, servidores):
    antes = {t for t in threading.enumerate() if t.name.startswith("p2p")}
    nodos, srv = mallar(claves, servidores)
    for s in srv:
        s.detener()
    assert esperar(lambda: not ({t for t in threading.enumerate() if t.name.startswith("p2p")} - antes), 5)
