"""Coordinación de sellos multifirma: flujo real con 3 nodos, 3 servidores P2P y 3 coordinadores en 127.0.0.1."""
import hashlib
import json
import time

import pytest

from models.coordinador_sellos import CADUCIDAD, CoordinadorSellos
from models.errores import ErrorEntrada, ErrorEstado
from models.multifirma import id_sello
from models.nodo_completo import conectar_nodo_y_servidor
from models.red_p2p import ServidorP2P
from tests.laboratorios import crear_laboratorios, nuevo_nodo

RAPIDO = dict(intervalo_ping=0.2, tiempo_sin_respuesta=2.0, tiempo_saludo=3.0, tiempo_sync=5.0)
IDS = ("LAB-A", "LAB-B", "LAB-C")
TRES = list(IDS)


def esperar(cond, limite=10.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def sha(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


@pytest.fixture(scope="module")
def labs(tmp_path_factory):
    return crear_laboratorios(tmp_path_factory.mktemp("labs_coord"))


@pytest.fixture
def red(tmp_path, labs):
    """{id: (nodo, servidor, coordinador)} con la malla completa conectada."""
    piezas = {}
    for nid in IDS:
        nodo = nuevo_nodo(tmp_path / nid, labs, nid)
        servidor = ServidorP2P(nodo, host="127.0.0.1", puerto=0, **RAPIDO)
        servidor.iniciar()
        conectar_nodo_y_servidor(nodo, servidor)
        coord = CoordinadorSellos(nodo, str(tmp_path / nid))
        coord.conectar(servidor)
        piezas[nid] = (nodo, servidor, coord)
    piezas["LAB-B"][1].conectar("127.0.0.1", piezas["LAB-A"][1].puerto)
    piezas["LAB-C"][1].conectar("127.0.0.1", piezas["LAB-A"][1].puerto)
    piezas["LAB-C"][1].conectar("127.0.0.1", piezas["LAB-B"][1].puerto)
    assert esperar(lambda: all(len(s.pares_publico()) == 2 for _, s, _ in piezas.values()))
    yield piezas
    for nodo, servidor, _ in piezas.values():
        nodo.detener_minado()
        servidor.detener()


def test_flujo_multifirma_completo_y_prioridad(red):
    (a, _, ca), (b, _, cb), (c, _, cc) = (red[i] for i in IDS)
    doc = sha("resultado.pdf")
    res = ca.proponer(doc, "Resultado", "Dra. A", TRES, 2)
    assert res["estado"] == "en_firma" and res["firmas"] == ["LAB-A"]
    assert esperar(lambda: len(cb.solicitudes()) == 1 and len(cc.solicitudes()) == 1)
    assert ca.solicitudes() == [] and len(ca.en_firma()) == 1      # el proponente ya firmó
    sid = res["id"]
    assert cb.solicitudes()[0]["id"] == sid and cb.solicitudes()[0]["faltan"] == 1
    assert a.pendientes == [] and b.pendientes == []

    assert cb.firmar(sid)["estado"] == "pendiente"
    assert esperar(lambda: all(len(n.pendientes) == 1 for n in (a, b, c)))
    assert all(id_sello(n.pendientes[0]) == sid and len(n.pendientes[0]["firmas"]) >= 2 for n in (a, b, c))
    assert esperar(lambda: not ca.en_firma() and not cb.en_firma() and not cc.en_firma())
    with pytest.raises(ErrorEstado):
        cb.firmar(sid)                                              # ya no espera firmas

    a.iniciar_minado(1)
    assert esperar(lambda: all(n.altura == 1 and not n.pendientes for n in (a, b, c)))
    assert len({n.punta for n in (a, b, c)}) == 1
    for n in (a, b, c):
        p = n.prioridad(doc)
        assert len(p) == 1 and p[0]["laboratorio"] == "LAB-A" and p[0]["prioritario"]

    # disputa de prioridad: C sella después el mismo documento; el registro es válido pero posterior
    cc.proponer(doc, "Mismo resultado", "Dr. C", ["LAB-C"], 1)
    assert esperar(lambda: all(len(n.pendientes) == 1 for n in (a, b, c)))
    c.iniciar_minado(1)
    assert esperar(lambda: all(n.altura == 2 for n in (a, b, c)) and len({n.punta for n in (a, b, c)}) == 1)
    p = a.prioridad(doc)
    assert [s["laboratorio"] for s in p] == ["LAB-A", "LAB-C"] and p[0]["prioritario"] and not p[1]["prioritario"]
    assert p[0]["numero"] == 1 and p[1]["numero"] == 2


def test_firma_de_no_autor_y_firma_falsa_se_rechazan(red):
    (a, _, ca), (b, _, cb), (c, _, cc) = (red[i] for i in IDS)
    res = ca.proponer(sha("solo A y B"), "Privado", "Dra. A", ["LAB-A", "LAB-B"], 2)
    sid = res["id"]
    assert esperar(lambda: len(cb.solicitudes()) == 1)
    assert cc.solicitudes() == []                                   # C no es autor: no ve solicitud
    with pytest.raises(ErrorEntrada, match="no es autor"):
        cc.firmar(sid)
    # una firma de C (no autor) o una firma inválida llegan por la red y se descartan sin excepción
    firma_c = c.firmar(b"otro mensaje")
    ca._al_firma("LAB-C", {"id_sello": sid, "autor": "LAB-C", "firma": firma_c})
    ca._al_firma("LAB-B", {"id_sello": sid, "autor": "LAB-B", "firma": "00" * 64})
    ca._al_firma("LAB-B", {"id_sello": sid, "autor": 5, "firma": None})
    assert ca.en_firma()[0]["firmas"] == ["LAB-A"] and a.pendientes == []
    assert any("descartada" in e["texto"] for e in a.bitacora)
    with pytest.raises(ErrorEstado, match="ya firmó"):
        ca.firmar(sid)                                              # A ya firmó al proponer


def test_proponer_valida_y_requiere_desbloqueo(red, labs, tmp_path):
    a, _, ca = red["LAB-A"]
    doc = sha("x")
    with pytest.raises(ErrorEntrada):
        ca.proponer(doc, "T", "I", ["LAB-B", "LAB-C"], 1)           # el propio nodo debe ser autor
    with pytest.raises(ErrorEntrada):
        ca.proponer(doc, "T", "I", ["LAB-A", "LAB-X"], 1)           # laboratorio inexistente
    with pytest.raises(ErrorEntrada):
        ca.proponer(doc, "T", "I", TRES, 4)                         # umbral mayor que los autores
    with pytest.raises(ErrorEntrada):
        ca.proponer("zz", "T", "I", TRES, 2)                        # hash inválido
    nodo2 = nuevo_nodo(tmp_path / "otro", labs, "LAB-A", desbloquear=False)
    with pytest.raises(ErrorEstado):
        CoordinadorSellos(nodo2, str(tmp_path / "otro")).proponer(doc, "T", "I", TRES, 2)
    assert ca.en_firma() == []


def test_manejadores_ignoran_basura_sin_excepcion(red):
    a, _, ca = red["LAB-A"]
    for msg in ({}, {"sello": "x"}, {"sello": {"tipo": "sello"}}, {"sello": None}, {"sello": {"a": [1]}}):
        ca._al_propuesto("LAB-B", msg)
    for msg in ({}, {"id_sello": 1}, {"id_sello": "ab", "autor": "LAB-B", "firma": "x"}):
        ca._al_firma("LAB-B", msg)
    assert ca.en_firma() == []
    assert any(e["tipo"] == "sellos" for e in a.bitacora)


def test_persistencia_y_caducidad(red, tmp_path):
    a, _, ca = red["LAB-A"]
    sid = ca.proponer(sha("persistente"), "P", "I", TRES, 3)["id"]
    ruta = tmp_path / "LAB-A" / "sellos_en_firma.json"
    assert ruta.exists() and sid in json.loads(ruta.read_text(encoding="utf-8"))
    recargado = CoordinadorSellos(a, str(tmp_path / "LAB-A"))
    assert [s["id"] for s in recargado.en_firma()] == [sid]
    recargado._en_firma[sid]["creado"] -= CADUCIDAD + 5
    assert recargado.en_firma() == []
    assert sid not in json.loads(ruta.read_text(encoding="utf-8"))      # la caducidad también se persiste


@pytest.mark.parametrize("tipo", ["merkle_falsa", "multifirma_incompleta", "firma_minero_ajena", "firma_falsa"])
def test_ataque_a_la_red_lo_rechazan_los_pares(red, tipo):
    from models import ataques_sellalo
    (a, sa, _), (b, sb, _), (c, sc, _) = (red[i] for i in IDS)
    r = ataques_sellalo.ejecutar(a, sa, tipo, "red")
    assert r["rechazado"] and r["enviados"] == 2
    assert esperar(lambda: sb.faltas_de("LAB-A") >= 1 and sc.faltas_de("LAB-A") >= 1)
    assert a.altura == b.altura == c.altura == 0 and not b.pendientes and not c.pendientes
