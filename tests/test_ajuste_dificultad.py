"""Ajuste de dificultad co-firmado (C9): validación en bloque, aplicación desde h+1, reorganización, minado,
API, flujo real con 3 nodos + 3 servidores P2P y certificado con el verificador independiente."""
import copy
import hashlib
import json
import time

import pytest

import verificar_certificado as vc
from app import create_app_nodo
from models.ajuste_dificultad import id_ajuste, mensaje_ajuste
from models.bloque import ErrorValidacion
from models.certificado import generar_certificado
from models.coordinador_ajustes import CADUCIDAD, CoordinadorAjustes
from models.errores import ErrorEntrada, ErrorEstado
from models.nodo_completo import conectar_nodo_y_servidor
from models.red_p2p import ServidorP2P
from models.validacion import validar_cadena
from tests.laboratorios import CONTRASENA, bloque_externo, crear_laboratorios, nuevo_nodo, sello, transferencia

RAPIDO = dict(intervalo_ping=0.2, tiempo_sin_respuesta=2.0, tiempo_saludo=3.0, tiempo_sync=5.0)
IDS = ("LAB-A", "LAB-B", "LAB-C")


def esperar(cond, limite=15.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


@pytest.fixture(scope="module")
def labs(tmp_path_factory):
    return crear_laboratorios(tmp_path_factory.mktemp("labs_ajuste"), dificultad=1)


@pytest.fixture(scope="module")
def labs_sin_fija(tmp_path_factory):
    return crear_laboratorios(tmp_path_factory.mktemp("labs_sin_fija"))


def ajuste(labs, dificultad, proponente="LAB-A", firmantes=("LAB-A", "LAB-B"), ts=1000.0):
    tx = {"tipo": "ajuste_dificultad", "dificultad": dificultad, "proponente": proponente, "timestamp": ts, "firmas": {}}
    mensaje = mensaje_ajuste(tx)
    tx["firmas"] = {f: labs[2][f].firmar(mensaje) for f in firmantes}
    return tx


def tr(labs, monto=1, ts=10.0):
    return transferencia(labs, "LAB-A", "LAB-B", monto, ts)


def cadena_con(labs, bloques):
    """bloques: [(txs, dificultad)] -> [génesis, b1, ...]"""
    cadena = [labs[0]]
    for txs, dif in bloques:
        cadena.append(bloque_externo(labs, cadena[-1], txs, "LAB-B", dif))
    return cadena


def invalida(labs, bloques, fragmento):
    with pytest.raises(ErrorValidacion) as exc:
        validar_cadena(cadena_con(labs, bloques), labs[0]["hash"])
    assert fragmento in str(exc.value), str(exc.value)


# ---------------------------------------------------------------- validación
def test_ajuste_valido_y_aplicacion_desde_el_bloque_siguiente(labs):
    aj = ajuste(labs, 2)
    estado = validar_cadena(cadena_con(labs, [([aj], 1), ([tr(labs)], 2), ([tr(labs, 2)], 2)]), labs[0]["hash"])
    assert estado.dificultad_vigente == 2 and len(estado.ajustes) == 1
    a = estado.ajustes[0]
    assert a["numero"] == 1 and a["dificultad_anterior"] == 1 and a["dificultad"] == 2
    assert a["firmantes"] == ["LAB-A", "LAB-B"] and a["id"] == id_ajuste(aj)
    solo = validar_cadena(cadena_con(labs, [([aj], 1)]), labs[0]["hash"])          # el ajuste no mueve saldos
    assert solo.saldos == {"LAB-A": 100, "LAB-B": 100, "LAB-C": 100}


def test_el_bloque_siguiente_con_la_dificultad_anterior_se_rechaza(labs):
    invalida(labs, [([ajuste(labs, 2)], 1), ([tr(labs)], 1)], "dificultad vigente de la red (2)")


def test_el_propio_bloque_del_ajuste_usa_la_anterior(labs):
    invalida(labs, [([ajuste(labs, 2)], 2)], "dificultad vigente de la red (1)")


def test_campos_exactos(labs):
    extra = ajuste(labs, 2)
    extra["extra"] = 1
    invalida(labs, [([extra], 1)], "exactamente")
    falta = ajuste(labs, 2)
    del falta["timestamp"]
    invalida(labs, [([falta], 1)], "exactamente")


@pytest.mark.parametrize("dificultad", [0, 7, True, "3", 2.0])
def test_rango_y_tipo_de_la_dificultad(labs, dificultad):
    aj = ajuste(labs, 2)
    aj["dificultad"] = dificultad
    invalida(labs, [([aj], 1)], "ajuste de dificultad inválido")


def test_igual_a_la_vigente(labs):
    invalida(labs, [([ajuste(labs, 1)], 1)], "ya es la vigente")


def test_sin_mayoria(labs):
    invalida(labs, [([ajuste(labs, 2, firmantes=("LAB-A",))], 1)], "sin mayoría")


def test_proponente_debe_firmar_y_ser_laboratorio(labs):
    invalida(labs, [([ajuste(labs, 2, proponente="LAB-C", firmantes=("LAB-A", "LAB-B"))], 1)], "no lo firmó")
    invalida(labs, [([ajuste(labs, 2, proponente="LAB-X", firmantes=("LAB-A", "LAB-B"))], 1)], "no es laboratorio")


def test_firma_de_quien_no_es_laboratorio(labs):
    aj = ajuste(labs, 2, firmantes=("LAB-A", "LAB-B"))
    aj["firmas"]["LAB-X"] = aj["firmas"]["LAB-A"]
    invalida(labs, [([aj], 1)], "no es laboratorio")


def test_firma_alterada_o_de_otro_mensaje(labs):
    aj = ajuste(labs, 2)
    aj["firmas"]["LAB-B"] = "0" * 128
    invalida(labs, [([aj], 1)], "no corresponde a este ajuste")
    aj2 = ajuste(labs, 2)
    otro = ajuste(labs, 3)
    aj2["firmas"]["LAB-B"] = otro["firmas"]["LAB-B"]                       # firma válida pero de otro ajuste
    invalida(labs, [([aj2], 1)], "no corresponde a este ajuste")
    aj3 = ajuste(labs, 2)
    aj3["dificultad"] = 3                                                    # se altera lo firmado
    invalida(labs, [([aj3], 1)], "no corresponde a este ajuste")


def test_dos_ajustes_en_un_bloque(labs):
    invalida(labs, [([ajuste(labs, 2), ajuste(labs, 3, ts=1001.0)], 1)], "como máximo un ajuste de dificultad")


def test_ajuste_repetido_entre_bloques(labs):
    primero = ajuste(labs, 2)
    vuelta = ajuste(labs, 1, ts=1001.0)
    invalida(labs, [([primero], 1), ([vuelta], 2), ([primero], 1)], "ya está en la cadena")


def test_red_sin_dificultad_fija_no_admite_ajustes(labs_sin_fija):
    with pytest.raises(ErrorValidacion, match="no fija la dificultad"):
        validar_cadena(cadena_con(labs_sin_fija, [([ajuste(labs_sin_fija, 2)], 1)]), labs_sin_fija[0]["hash"])


def test_dos_laboratorios_de_tres_son_mayoria_y_con_tres_firmas_tambien(labs):
    validar_cadena(cadena_con(labs, [([ajuste(labs, 2, firmantes=IDS)], 1)]), labs[0]["hash"])
    validar_cadena(cadena_con(labs, [([ajuste(labs, 3, proponente="LAB-C", firmantes=("LAB-B", "LAB-C"))], 1)]),
                   labs[0]["hash"])


# ---------------------------------------------------------------- nodo: pendientes, reorganización y minado
def test_pendientes_descarta_ajuste_obsoleto_tras_un_bloque(labs, tmp_path):
    nodo = nuevo_nodo(tmp_path / "n", labs)
    aj = ajuste(labs, 2)
    nodo.agregar_transaccion(aj)
    assert nodo.publico()["pendientes"][0]["tipo"] == "ajuste_dificultad"
    nodo.recibir_bloque(bloque_externo(labs, labs[0], [aj], "LAB-B", 1))        # otro nodo lo minó
    assert nodo.altura == 1 and nodo.pendientes == []
    # un ajuste a la vigente ya no entra a pendientes
    with pytest.raises(ErrorEntrada):
        nodo.agregar_transaccion(ajuste(labs, 2, ts=1002.0))
    # uno equivalente a la vigente que estaba pendiente se descarta al cambiar la vigente
    otro = ajuste(labs, 3, ts=1003.0)
    n2 = nuevo_nodo(tmp_path / "n2", labs)
    n2.agregar_transaccion(otro)
    n2.recibir_bloque(bloque_externo(labs, labs[0], [ajuste(labs, 3, ts=1004.0)], "LAB-B", 1))
    assert n2.estado.dificultad_vigente == 3 and n2.pendientes == []


def test_reorganizacion_que_descarta_el_bloque_del_ajuste_restaura_la_anterior(labs, tmp_path):
    nodo = nuevo_nodo(tmp_path / "n", labs)
    aj = ajuste(labs, 2)
    b1 = bloque_externo(labs, labs[0], [aj], "LAB-B", 1)
    assert nodo.recibir_bloque(b1)[0] == "aceptado"
    assert nodo.dificultad_red == 2 and nodo.publico()["dificultad_red"] == 2
    assert nodo.publico()["dificultad_genesis"] == 1 and nodo.publico()["ajustes"][0]["dificultad"] == 2
    rival = [labs[0]]
    for i in range(2):                                                          # rama más larga sin ajuste (más trabajo)
        rival.append(bloque_externo(labs, rival[-1], [tr(labs, i + 1, 20.0 + i)], "LAB-C", 1))
    ok, _ = nodo.recibir_cadena(rival)
    assert ok and nodo.altura == 2
    assert nodo.dificultad_red == 1 and nodo.publico()["ajustes"] == []
    assert any(id_ajuste(p) == id_ajuste(aj) for p in nodo.pendientes)          # el ajuste vuelve a pendientes


def test_iniciar_minado_usa_la_vigente(labs, tmp_path):
    nodo = nuevo_nodo(tmp_path / "n", labs)
    nodo.recibir_bloque(bloque_externo(labs, labs[0], [ajuste(labs, 2)], "LAB-B", 1))
    with pytest.raises(ErrorEntrada, match="fijada"):
        nodo.iniciar_minado(1)
    nodo.agregar_transaccion(tr(labs))
    nodo.iniciar_minado()
    try:
        assert esperar(lambda: nodo.altura == 2)
    finally:
        nodo.detener_minado()
    assert nodo.cadena[2]["dificultad"] == 2 and nodo.cadena[2]["hash"].startswith("00")
    assert nodo.publico()["estadisticas"]["dificultad"] == 2


def test_el_minado_continuo_cambia_de_dificultad_al_aplicarse_un_ajuste(labs, tmp_path):
    nodo = nuevo_nodo(tmp_path / "n", labs)
    nodo.agregar_transaccion(ajuste(labs, 2))
    nodo.iniciar_minado(continuo=True)
    try:
        assert esperar(lambda: nodo.altura == 1)
        nodo.agregar_transaccion(tr(labs))
        assert esperar(lambda: nodo.altura == 2)
    finally:
        nodo.detener_minado()
    assert [b["dificultad"] for b in nodo.cadena[1:]] == [1, 2]


def test_un_solo_ajuste_por_bloque_al_minar(labs, tmp_path):
    nodo = nuevo_nodo(tmp_path / "n", labs)
    nodo.agregar_transaccion(ajuste(labs, 2))
    nodo.agregar_transaccion(ajuste(labs, 3, ts=1001.0))
    elegidas, _ = nodo._seleccionar()
    assert len(elegidas) == 1


# ---------------------------------------------------------------- coordinador: robustez
def test_coordinador_valida_y_persiste(labs, tmp_path):
    nodo = nuevo_nodo(tmp_path / "n", labs)
    coord = CoordinadorAjustes(nodo, str(tmp_path / "n"))
    for malo in (0, 7, "2", None, True):
        with pytest.raises(ErrorEntrada):
            coord.proponer(malo)
    with pytest.raises(ErrorEstado, match="ya es la vigente"):
        coord.proponer(1)
    res = coord.proponer(3)
    assert res["estado"] == "en_firma" and res["umbral"] == 2
    nuevo = coord.proponer(2)                                                   # reemplaza a la anterior del proponente
    assert [a["dificultad"] for a in coord.en_firma()] == [2]
    otra = CoordinadorAjustes(nodo, str(tmp_path / "n"))                        # persistencia: recarga del disco
    assert [a["id"] for a in otra.en_firma()] == [nuevo["id"]]
    with pytest.raises(ErrorEstado, match="ya firmó"):
        coord.firmar(nuevo["id"])
    with pytest.raises(ErrorEntrada):
        coord.firmar("xyz")
    with pytest.raises(ErrorEstado):
        coord.firmar("0" * 64)


def test_coordinador_caduca_y_descarta_datos_invalidos(labs, tmp_path, monkeypatch):
    nodo = nuevo_nodo(tmp_path / "n", labs)
    coord = CoordinadorAjustes(nodo, str(tmp_path / "n"))
    res = coord.proponer(2)
    for basura in (None, 5, {}, {"ajuste": 5}, {"ajuste": {"tipo": "ajuste_dificultad"}},
                   {"ajuste": {**ajuste(labs, 2), "dificultad": "x"}}):
        coord._al_propuesto("LAB-X", basura)                                    # nunca lanza
    for basura in (None, {}, {"id_ajuste": 5}, {"id_ajuste": res["id"], "lab": "LAB-B", "firma": "00" * 64},
                   {"id_ajuste": res["id"], "lab": "LAB-X", "firma": "00" * 64}):
        coord._al_firma("LAB-X", basura)
    assert len(coord.en_firma()) == 1 and coord.en_firma()[0]["firmas"] == ["LAB-A"]
    reloj = time.time() + CADUCIDAD + 5
    monkeypatch.setattr("models.coordinador_ajustes.time.time", lambda: reloj)
    assert coord.en_firma() == []


def test_red_sin_dificultad_fija_no_permite_proponer(labs_sin_fija, tmp_path):
    nodo = nuevo_nodo(tmp_path / "n", labs_sin_fija)
    with pytest.raises(ErrorEstado, match="no fija la dificultad"):
        CoordinadorAjustes(nodo, str(tmp_path / "n")).proponer(2)


# ---------------------------------------------------------------- flujo real: 3 nodos + 3 servidores
@pytest.fixture
def red(tmp_path, labs):
    piezas = {}
    for nid in IDS:
        nodo = nuevo_nodo(tmp_path / nid, labs, nid)
        servidor = ServidorP2P(nodo, host="127.0.0.1", puerto=0, **RAPIDO)
        servidor.iniciar()
        conectar_nodo_y_servidor(nodo, servidor)
        coord = CoordinadorAjustes(nodo, str(tmp_path / nid))
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


def test_flujo_completo_con_tres_nodos(red, labs):
    (a, _, ca), (b, _, cb), (c, _, cc) = (red[i] for i in IDS)
    res = ca.proponer(2)
    assert res["estado"] == "en_firma" and res["firmas"] == ["LAB-A"]
    assert esperar(lambda: len(cb.solicitudes()) == 1 and len(cc.solicitudes()) == 1)
    assert ca.solicitudes() == [] and a.pendientes == [] and b.pendientes == []
    assert cb.solicitudes()[0]["id"] == res["id"] and cb.solicitudes()[0]["faltan"] == 1

    assert cb.firmar(res["id"])["estado"] == "pendiente"
    assert esperar(lambda: all(len(n.pendientes) == 1 for n in (a, b, c)))
    assert esperar(lambda: not ca.en_firma() and not cb.en_firma() and not cc.en_firma())
    for n in (a, b, c):
        assert n.pendientes[0]["tipo"] == "ajuste_dificultad" and len(n.pendientes[0]["firmas"]) == 2
        assert n.dificultad_red == 1                                           # aún no se minó

    a.iniciar_minado(1)
    assert esperar(lambda: all(n.altura == 1 and not n.pendientes for n in (a, b, c)))
    a.detener_minado()
    for n in (a, b, c):
        assert n.dificultad_red == 2 and n.estado.ajustes[0]["numero"] == 1
        assert n.publico()["ajustes"][0]["firmantes"] == ["LAB-A", "LAB-B"]
    assert len({n.punta for n in (a, b, c)}) == 1

    a.agregar_transaccion(transferencia(labs, "LAB-A", "LAB-B", 3, time.time() - 5))
    b.iniciar_minado()                                                          # el siguiente bloque usa 2
    assert esperar(lambda: all(n.altura == 2 for n in (a, b, c)))
    b.detener_minado()
    assert [x["dificultad"] for x in a.cadena[1:]] == [1, 2] and a.cadena[2]["hash"].startswith("00")
    assert len({n.punta for n in (a, b, c)}) == 1


# ---------------------------------------------------------------- certificado y verificador independiente
@pytest.fixture(scope="module")
def mundo(labs):
    doc = b"articulo tras el ajuste"
    cadena = cadena_con(labs, [([tr(labs)], 1), ([tr(labs, 3, 15.0), ajuste(labs, 2)], 1), ([sello(labs, hashlib.sha256(doc).hexdigest())], 2),
                               ([tr(labs, 2, 30.0)], 2)])
    return cadena, doc


def test_certificado_a_traves_de_un_ajuste_valido(mundo):
    cadena, doc = mundo
    cert = generar_certificado(cadena, hashlib.sha256(doc).hexdigest())
    assert [a["bloque"] for a in cert["ajustes"]] == [2]
    r = vc.verificar(cert, doc, cert["genesis"]["hash"])
    assert r["valido"] and r["genesis_confirmado"], r["motivo"]
    paso = next(p for p in r["pasos"] if p["paso"] == "encabezados")
    assert "ajuste(s) de dificultad" in paso["detalle"]


def test_encabezado_de_dificultad_cambiada_sin_ajuste_no_es_valido(mundo, labs):
    cadena, doc = mundo
    cert = generar_certificado(cadena, hashlib.sha256(doc).hexdigest())
    cert["ajustes"] = []                                                         # se omite la prueba del ajuste
    r = vc.verificar(cert, doc, cert["genesis"]["hash"])
    assert not r["valido"] and "la vigente es 1" in r["motivo"]


@pytest.mark.parametrize("cambio,fragmento", [
    (lambda c: c["ajustes"][0]["tx"]["firmas"].pop("LAB-B"), "se necesitan más de la mitad"),
    (lambda c: c["ajustes"][0]["tx"]["firmas"].update({"LAB-B": "0" * 128}), "no es válida"),
    (lambda c: c["ajustes"][0]["tx"]["firmas"].update({"LAB-X": "0" * 128}), "no es laboratorio"),
    (lambda c: c["ajustes"][0]["tx"].update(dificultad=3), "no es válida"),
    (lambda c: c["ajustes"][0].update(bloque=3), "la vigente es 1"),
    (lambda c: c["ajustes"][0]["prueba_merkle"].update(camino=[]), "Merkle"),
    (lambda c: c["ajustes"][0].update(bloque=99), "la vigente es 1"),
    (lambda c: c["ajustes"].append({**copy.deepcopy(c["ajustes"][0]), "bloque": 4}), "ya era la vigente"),
    (lambda c: c["ajustes"].append({**copy.deepcopy(c["ajustes"][0]), "bloque": 99}), "no están en los encabezados"),
    (lambda c: c["ajustes"].append(copy.deepcopy(c["ajustes"][0])), "no son válidos"),
    (lambda c: c.update(ajustes="x"), "no son válidos"),
])
def test_ajuste_alterado_en_el_certificado(mundo, cambio, fragmento):
    cadena, doc = mundo
    cert = generar_certificado(cadena, hashlib.sha256(doc).hexdigest())
    cambio(cert)
    r = vc.verificar(cert, doc, cert["genesis"]["hash"])
    assert not r["valido"] and fragmento in r["motivo"], r["motivo"]


def test_certificado_antiguo_sin_ajustes_sigue_siendo_valido(labs):
    doc = b"sin ajustes"
    cadena = cadena_con(labs, [([sello(labs, hashlib.sha256(doc).hexdigest())], 1)])
    cert = generar_certificado(cadena, hashlib.sha256(doc).hexdigest())
    assert cert["ajustes"] == []
    cert.pop("ajustes")
    assert vc.verificar(cert, doc, cert["genesis"]["hash"])["valido"]


# ---------------------------------------------------------------- API
@pytest.fixture
def api(labs, tmp_path):
    carpeta = tmp_path / "g"
    carpeta.mkdir()
    ruta = carpeta / "genesis.json"
    ruta.write_text(json.dumps(labs[0]), encoding="utf-8")
    app = create_app_nodo(str(tmp_path / "datos"), str(ruta), "LAB-A", puerto_p2p=0, ruta_clave=labs[1]["LAB-A"],
                          host_p2p="127.0.0.1", opciones_p2p=RAPIDO)
    app.config["TESTING"] = True
    yield app.test_client()
    ctx = app.config["CONTEXTO_NODO"]
    ctx.nodo.detener_minado()
    ctx.bloquear()


def test_api_dificultad_y_errores_sin_500(api):
    cuerpo = api.get("/api/sellalo/dificultad").get_json()
    assert cuerpo["ok"] and cuerpo["vigente"] == 1 and cuerpo["genesis"] == 1 and cuerpo["umbral"] == 2
    assert cuerpo["minimo"] == 1 and cuerpo["maximo"] == 6 and cuerpo["laboratorios"] == list(IDS)
    assert cuerpo["ajustes"] == [] and cuerpo["en_firma"] == [] and cuerpo["solicitudes"] == []
    assert api.get("/api/sellalo/estado").get_json()["dificultad"]["vigente"] == 1

    r = api.post("/api/sellalo/dificultad/proponer", json={"dificultad": 2})
    assert r.status_code == 409 and "bloqueado" in r.get_json()["error"]            # nodo bloqueado
    assert api.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200

    for cuerpo_malo in ({}, {"dificultad": "2"}, {"dificultad": 2.5}, {"dificultad": None}, {"dificultad": True},
                        {"dificultad": 0}, {"dificultad": 7}, {"dificultad": -1}):
        r = api.post("/api/sellalo/dificultad/proponer", json=cuerpo_malo)
        assert r.status_code == 400, (cuerpo_malo, r.get_json())
    r = api.post("/api/sellalo/dificultad/proponer", json={"dificultad": 1})
    assert r.status_code == 409 and "ya es la vigente" in r.get_json()["error"]
    assert api.post("/api/sellalo/dificultad/proponer", data="no json", content_type="text/plain").status_code == 400

    r = api.post("/api/sellalo/dificultad/proponer", json={"dificultad": 3})
    assert r.status_code == 200 and r.get_json()["ajuste"]["estado"] == "en_firma"
    aid = r.get_json()["ajuste"]["id"]
    cuerpo = api.get("/api/sellalo/dificultad").get_json()
    assert cuerpo["en_firma"][0]["id"] == aid and cuerpo["en_firma"][0]["firmado_por_mi"] and cuerpo["solicitudes"] == []
    r = api.post(f"/api/sellalo/dificultad/{aid}/firmar")
    assert r.status_code == 409 and "ya firmó" in r.get_json()["error"]
    assert api.post("/api/sellalo/dificultad/" + "0" * 64 + "/firmar").status_code == 409
    assert api.post("/api/sellalo/dificultad/xyz/firmar").status_code == 400


def test_api_red_sin_dificultad_fija(labs_sin_fija, tmp_path):
    carpeta = tmp_path / "g"
    carpeta.mkdir()
    ruta = carpeta / "genesis.json"
    ruta.write_text(json.dumps(labs_sin_fija[0]), encoding="utf-8")
    app = create_app_nodo(str(tmp_path / "datos"), str(ruta), "LAB-A", puerto_p2p=0,
                          ruta_clave=labs_sin_fija[1]["LAB-A"], host_p2p="127.0.0.1", opciones_p2p=RAPIDO)
    c = app.test_client()
    try:
        assert c.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200
        cuerpo = c.get("/api/sellalo/dificultad").get_json()
        assert cuerpo["vigente"] is None and cuerpo["genesis"] is None
        r = c.post("/api/sellalo/dificultad/proponer", json={"dificultad": 2})
        assert r.status_code == 409 and "no fija la dificultad" in r.get_json()["error"]
    finally:
        ctx = app.config["CONTEXTO_NODO"]
        ctx.nodo.detener_minado()
        ctx.bloquear()


def test_api_defensa_csrf_y_host(api):
    api.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA})
    r = api.post("/api/sellalo/dificultad/proponer", json={"dificultad": 2}, headers={"Origin": "http://malo.example"})
    assert r.status_code == 403
    r = api.post("/api/sellalo/dificultad/proponer", json={"dificultad": 2}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = api.post("/api/sellalo/dificultad/proponer", json={"dificultad": 2}, headers={"Host": "malo.example"})
    assert r.status_code == 403
    assert api.get("/api/sellalo/dificultad").get_json()["en_firma"] == []


def test_detalle_de_bloque_y_verificacion_detallada_muestran_el_ajuste(api, labs):
    from models.verificacion_detallada import verificar_cadena_detallada
    cadena = cadena_con(labs, [([ajuste(labs, 2)], 1), ([tr(labs)], 2)])
    r = verificar_cadena_detallada(cadena, labs[0]["hash"])
    assert r["valida"] and r["dificultad_final"] == 2 and r["ajustes"][0]["bloque"] == 1
    t = r["bloques"][0]["transacciones"][0]
    assert t["tipo"] == "ajuste_dificultad" and t["ok"] and t["ajuste"]["alcanzado"] and t["ajuste"]["necesarias"] == 2
    assert [f["valida"] for f in t["ajuste"]["firmas"]] == [True, True, False]
    mala = cadena_con(labs, [([ajuste(labs, 2)], 1), ([tr(labs)], 1)])
    r = verificar_cadena_detallada(mala, labs[0]["hash"])
    assert not r["valida"] and r["bloques"][1]["comprobaciones"]["pow"] is False
    sin_mayoria = copy.deepcopy(cadena)
    sin_mayoria[1]["transacciones"][0]["firmas"].pop("LAB-B")
    r = verificar_cadena_detallada(sin_mayoria, labs[0]["hash"])
    assert not r["valida"] and not r["bloques"][0]["transacciones"][0]["ajuste"]["alcanzado"]


def test_pagina_del_nodo_tiene_el_panel_y_el_js_no_usa_innerhtml(api):
    html = api.get("/").get_data(as_text=True)
    for ident in ("panel-dificultad", "dif-vigente", "in-dif-nueva", "btn-dif-proponer", "dif-en-firma", "dif-historial",
                  "dif-sin-fija", "dif-tiempo"):
        assert f'id="{ident}"' in html, ident
    assert html.count('id="panel-dificultad"') == 1
    assert html.index('id="panel-dificultad"') < html.index('id="form-minar"')       # al inicio del minado
    import re
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "views" / "static" / "sellalo.js").read_text(encoding="utf-8")
    assert "renderDificultad" in js and "/dificultad/proponer" in js and "ajuste_dificultad" in js
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|alert\(|confirm\(|prompt\(", js)
