"""Contrato C8: la rúbrica en la interfaz (dificultad de red, consenso, persistencia, verificación detallada,
protección de la clave, certificado paso a paso, auditoría con IA, entrega y tablero de la rúbrica)."""
import ast
import hashlib
import io
import json
import os
import threading
import time

import pytest

import verificar_certificado as vc
from app import create_app_nodo
from models import rubrica
from models.bloque import crear_genesis
from models.errores import ErrorEntrada
from models.keystore import abrir_almacen, crear_almacen
from models.verificacion_detallada import (COMPROBACIONES, COMPROBACIONES_ESPERADAS, TIPOS_ALTERACION,
                                           alterar_copia, verificar_cadena_detallada)
from scripts import estado_auditoria
from tests.laboratorios import CONTRASENA, IDS, bloque_externo, rama, sello, transferencia

OPCIONES = dict(intervalo_ping=0.2, tiempo_sin_respuesta=2.0, tiempo_sync=5.0, tiempo_saludo=3.0)
DOC = b"articulo con resultado cientifico"
HASH_DOC = hashlib.sha256(DOC).hexdigest()
API = "/api/sellalo"
RAIZ_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def esperar(cond, limite=15.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


@pytest.fixture(scope="module")
def labs(tmp_path_factory):
    """Laboratorios con almacén real y un génesis que FIJA la dificultad de la red (1)."""
    carpeta = tmp_path_factory.mktemp("labs_rubrica")
    rutas, claves, cuentas = {}, {}, {}
    for nid in IDS:
        rutas[nid] = os.path.join(str(carpeta), nid, "clave.json")
        publica = crear_almacen(rutas[nid], nid, CONTRASENA)
        claves[nid] = abrir_almacen(rutas[nid], CONTRASENA)
        cuentas[nid] = {"clave_publica": publica, "saldo": 100}
    parametros = {"consenso": "pow", "recompensa": 10, "confirmaciones": 6, "red": "sellalo", "nombre": "prueba",
                  "dificultad": 1}
    genesis = crear_genesis(cuentas, parametros, time.time() - 1000)
    ruta = carpeta / "genesis.json"
    ruta.write_text(json.dumps(genesis), encoding="utf-8")
    return (genesis, rutas, claves), str(ruta)


@pytest.fixture
def app_nodo(labs, tmp_path):
    (genesis, rutas, _), ruta_genesis = labs
    app = create_app_nodo(str(tmp_path / "datos"), ruta_genesis, "LAB-A", puerto_p2p=0, ruta_clave=rutas["LAB-A"],
                          host_p2p="127.0.0.1", opciones_p2p=OPCIONES, laboratorio_ataques=True)
    app.config["TESTING"] = True
    ctx = app.config["CONTEXTO_NODO"]
    ctx.nodo.pausa = lambda s: None           # sin esperas reales tras contraseñas incorrectas
    yield app
    ctx.nodo.detener_minado()
    ctx.bloquear()


@pytest.fixture
def ctx(app_nodo):
    return app_nodo.config["CONTEXTO_NODO"]


@pytest.fixture
def nodo(app_nodo):
    return app_nodo.test_client()


@pytest.fixture
def abierto(nodo):
    assert nodo.post(f"{API}/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200
    return nodo


def get(c, ruta):
    r = c.get(API + ruta)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def bloque_malo(labs, anterior):
    """Bloque nuevo sobre `anterior` (PoW correcto) con la firma del minero falsificada."""
    b = bloque_externo(labs, anterior, [transferencia(labs, "LAB-B", "LAB-C", 1, time.time() - 10)], "LAB-B")
    return dict(b, firma_minero="0" * 128)


def cadena_real(labs):
    """Génesis + bloque 1 (sello 2-de-3 firmado por A y B, y una transferencia) + bloque 2 (transferencia)."""
    s = sello(labs, HASH_DOC, ("LAB-A", "LAB-B"))
    t1 = transferencia(labs, "LAB-A", "LAB-B", 5, time.time() - 400)
    t2 = transferencia(labs, "LAB-B", "LAB-C", 3, time.time() - 300)
    return rama(labs, [[s, t1], [t2]], proponente="LAB-B")


@pytest.fixture
def con_cadena(abierto, ctx, labs):
    cadena = cadena_real(labs[0])
    ok, motivo = ctx.nodo.recibir_cadena(cadena, de="LAB-B")
    assert ok, motivo
    return abierto, cadena


# ================================================================ 1. dificultad de red
def test_minar_sin_dificultad_usa_la_del_genesis(abierto, ctx):
    pub = get(abierto, "/estado")["nodo"]
    assert pub["dificultad_red"] == 1 and pub["trabajo"] == 0
    r = abierto.post(f"{API}/sellos", json={"doc_hash": HASH_DOC, "titulo": "t", "investigador": "i",
                                            "autores": "LAB-A", "umbral": 1})
    assert r.status_code == 200
    assert abierto.post(f"{API}/minar", json={}).status_code == 200
    assert esperar(lambda: get(abierto, "/estado")["nodo"]["altura"] == 1)
    assert ctx.nodo.cadena[1]["dificultad"] == 1
    assert get(abierto, "/estado")["nodo"]["trabajo"] == 16


def test_minar_con_otra_dificultad_es_error_claro(abierto, ctx):
    r = abierto.post(f"{API}/minar", json={"dificultad": 3})
    assert r.status_code == 400 and "fijada en el génesis (1)" in r.get_json()["error"]
    with pytest.raises(ErrorEntrada, match="fijada"):
        ctx.nodo.iniciar_minado(2)


def test_iniciar_minado_sin_dificultad_ni_genesis_que_la_fije(tmp_path, labs):
    from models.nodo_completo import NodoCompleto
    (g, rutas, claves), _ = labs
    sin = dict(g, parametros={k: v for k, v in g["parametros"].items() if k != "dificultad"})
    from models.bloque import hash_bloque
    sin["hash"] = hash_bloque(sin)
    nodo = NodoCompleto(str(tmp_path), sin, "LAB-A", rutas["LAB-A"])
    nodo.desbloquear(CONTRASENA)
    assert nodo.publico()["dificultad_red"] is None
    with pytest.raises(ErrorEntrada, match="Indica la dificultad"):
        nodo.iniciar_minado()


# ================================================================ 2. consenso y persistencia
def test_consenso_registra_reorganizacion_y_rechazos(abierto, ctx, labs):
    g = labs[0]
    pub = get(abierto, "/estado")["nodo"]
    assert "Proof of Work" in pub["consenso"]["regla"] and pub["consenso"]["reorganizaciones"] == []
    abierto.post(f"{API}/sellos", json={"doc_hash": HASH_DOC, "titulo": "t", "investigador": "i",
                                        "autores": "LAB-A", "umbral": 1})
    abierto.post(f"{API}/minar", json={})
    assert esperar(lambda: ctx.nodo.altura == 1 and not ctx.nodo.minando)
    propia = ctx.nodo.punta
    alterna = rama(g, [[transferencia(g, "LAB-B", "LAB-C", 1, time.time() - 200)],
                       [transferencia(g, "LAB-B", "LAB-C", 2, time.time() - 100)]], proponente="LAB-B")
    ok, _ = ctx.nodo.recibir_cadena(alterna, de="LAB-B")
    assert ok
    con = get(abierto, "/estado")["nodo"]["consenso"]
    assert len(con["reorganizaciones"]) == 1
    r = con["reorganizaciones"][0]
    assert set(r) == {"t", "de", "altura_antes", "altura_despues", "punta_antes", "punta_despues",
                      "bloques_descartados", "tx_devueltas"}
    assert (r["de"], r["altura_antes"], r["altura_despues"], r["punta_antes"], r["punta_despues"]) == \
           ("LAB-B", 1, 2, propia, alterna[-1]["hash"])
    assert r["bloques_descartados"] == 1 and r["tx_devueltas"] == 1 and r["t"].endswith("Z")
    # rechazos: un bloque con la firma del minero alterada y una cadena con menos trabajo
    estado_bloque, _ = ctx.nodo.recibir_bloque(bloque_malo(g, alterna[-1]), de="LAB-B")
    assert estado_bloque == "rechazado"
    ok, motivo = ctx.nodo.recibir_cadena(alterna[:2], de="LAB-C")
    assert not ok and "menos trabajo" in motivo
    con = get(abierto, "/estado")["nodo"]["consenso"]
    assert con["bloques_rechazados"] == 1 and con["cadenas_rechazadas"] == 1


def test_historial_de_reorganizaciones_acotado(abierto, ctx):
    for i in range(25):
        ctx.nodo._reorgs.append({"t": "x", "de": str(i), "altura_antes": 0, "altura_despues": 0, "punta_antes": "",
                                 "punta_despues": "", "bloques_descartados": 0, "tx_devueltas": 0})
    hist = get(abierto, "/estado")["nodo"]["consenso"]["reorganizaciones"]
    assert len(hist) == 20 and hist[-1]["de"] == "24"


def test_persistencia_expone_archivo_bytes_y_error(abierto, ctx, labs, monkeypatch):
    p = get(abierto, "/estado")["nodo"]["persistencia"]
    assert set(p) == {"archivo_cadena", "bytes", "ultima_escritura", "error"}
    assert p["archivo_cadena"].endswith("cadena.json") and p["error"] is None
    ok, _ = ctx.nodo.recibir_cadena(cadena_real(labs[0]), de="LAB-B")
    assert ok
    p = get(abierto, "/estado")["nodo"]["persistencia"]
    assert p["bytes"] == os.path.getsize(p["archivo_cadena"]) > 0
    assert p["ultima_escritura"].endswith("Z") and p["error"] is None

    def falla(*a, **k):
        raise PermissionError(13, "disco lleno")
    monkeypatch.setattr("models.nodo_completo._escribir_atomico", falla)
    ctx.nodo._guardar_cadena()
    assert "disco lleno" in get(abierto, "/estado")["nodo"]["persistencia"]["error"]


# ================================================================ 3. /estado ampliado
def test_estado_trae_consistencia_sesion_y_recorrido(nodo):
    e = get(nodo, "/estado")
    assert e["consistencia"] == {"nodos": 1, "con_mi_punta": 1}
    assert set(e["sesion"]) == {"certificados_emitidos", "certificados_validos", "certificados_invalidos",
                                "prioridad_consultas", "ataques_rechazados", "verificaciones", "simulaciones"}
    assert all(v == 0 for v in e["sesion"].values())
    ids = [p["id"] for p in e["recorrido"]]
    assert ids == ["desbloquear", "conectar", "proponer", "umbral", "minar", "replicar", "prioridad", "emitir",
                   "verificar", "alteracion"]
    assert all(set(p) == {"id", "texto", "hecho", "detalle"} for p in e["recorrido"])
    assert not any(p["hecho"] for p in e["recorrido"])           # nada se marca sin evidencia


def test_los_contadores_de_sesion_y_el_recorrido_siguen_el_uso_real(con_cadena, ctx, nodo):
    c, cadena = con_cadena
    hechos = lambda: {p["id"] for p in get(c, "/estado")["recorrido"] if p["hecho"]}
    assert hechos() == {"desbloquear", "proponer", "umbral", "minar"}     # sin pares: ni conectar ni replicar
    assert c.post(f"{API}/prioridad", json={"doc_hash": HASH_DOC}).status_code == 200
    cert = c.get(f"{API}/certificado/{HASH_DOC}")
    assert cert.status_code == 200
    r = c.post(f"{API}/certificado/verificar", data={"certificado": (io.BytesIO(cert.data), "c.json")},
               content_type="multipart/form-data")
    assert r.get_json()["valido"] is True
    malo = json.loads(cert.data)
    malo["sello"]["titulo"] = "otro"
    r = c.post(f"{API}/certificado/verificar",
               data={"certificado": (io.BytesIO(json.dumps(malo).encode()), "c.json")},
               content_type="multipart/form-data")
    assert r.get_json()["valido"] is False
    assert c.post(f"{API}/verificacion/simular", json={"tipo": "hash", "bloque": 1}).status_code == 200
    assert c.post(f"{API}/ataques", json={"tipo": "firma_falsa", "destino": "local"}).get_json()["rechazado"]
    assert get(c, "/verificacion")["valida"]
    e = get(c, "/estado")
    assert e["sesion"] == {"certificados_emitidos": 1, "certificados_validos": 1, "certificados_invalidos": 1,
                           "prioridad_consultas": 1, "ataques_rechazados": 1, "verificaciones": 1,
                           "simulaciones": 1}
    assert hechos() == {"desbloquear", "proponer", "umbral", "minar", "prioridad", "emitir", "verificar",
                        "alteracion"}


def test_el_recorrido_detecta_conexion_y_replica(abierto, ctx):
    pares = [{"id": "LAB-B", "punta": ctx.nodo.punta}, {"id": "LAB-C", "punta": ctx.nodo.punta}]
    from controllers import sellalo as c8
    cons = c8._consistencia(ctx.nodo.publico(), pares)
    assert cons == {"nodos": 3, "con_mi_punta": 3}
    pares[1]["punta"] = "otra"
    assert c8._consistencia(ctx.nodo.publico(), pares) == {"nodos": 3, "con_mi_punta": 2}


# ================================================================ 4. verificación detallada
def test_cadena_real_pasa_todas_las_comprobaciones(con_cadena):
    c, cadena = con_cadena
    v = get(c, "/verificacion")
    assert v["valida"] is True and v["copia_alterada"] is False and v["alteracion"] is None
    assert v["primer_error"] is None and v["duracion_ms"] >= 0 and v["genesis"]["ok"] is True
    assert [b["numero"] for b in v["bloques"]] == [1, 2]
    for b in v["bloques"]:
        assert b["ok"] and b["errores"] == [] and list(b["comprobaciones"]) == list(COMPROBACIONES)
        assert all(b["comprobaciones"].values())
    sello_tx = v["bloques"][0]["transacciones"][0]
    assert sello_tx["tipo"] == "sello" and sello_tx["ok"] and sello_tx["firma"]
    mf = sello_tx["multifirma"]
    assert mf["autores"] == ["LAB-A", "LAB-B", "LAB-C"] and mf["umbral"] == 2 and mf["alcanzado"] is True
    assert mf["firmas"] == [{"autor": "LAB-A", "firmo": True, "valida": True},
                            {"autor": "LAB-B", "firmo": True, "valida": True},
                            {"autor": "LAB-C", "firmo": False, "valida": False}]
    assert v["bloques"][0]["transacciones"][1]["tipo"] == "transferencia"


@pytest.mark.parametrize("tipo", list(TIPOS_ALTERACION))
def test_cada_alteracion_se_detecta_en_su_comprobacion(con_cadena, ctx, tipo):
    c, cadena = con_cadena
    punta, archivo = ctx.nodo.punta, open(ctx.nodo.ruta_cadena, "rb").read()
    r = c.post(f"{API}/verificacion/simular", json={"tipo": tipo, "bloque": 1})
    assert r.status_code == 200, r.get_json()
    v = r.get_json()
    assert v["ok"] and v["valida"] is False and v["copia_alterada"] is True and v["cadena_real_intacta"] is True
    assert v["alteracion"]["tipo"] == tipo and v["alteracion"]["bloque"] == 1 and v["alteracion"]["descripcion"]
    b1 = v["bloques"][0]
    for esperada in COMPROBACIONES_ESPERADAS[tipo]:
        assert b1["comprobaciones"][esperada] is False, (tipo, esperada, b1["comprobaciones"])
    assert b1["ok"] is False and b1["errores"] and v["primer_error"]["bloque"] in (1, 2)
    if tipo == "multifirma":
        assert b1["transacciones"][0]["multifirma"]["alcanzado"] is False
    # la cadena real no cambió: ni la punta, ni el archivo, ni la verificación posterior
    assert ctx.nodo.punta == punta and open(ctx.nodo.ruta_cadena, "rb").read() == archivo
    assert get(c, "/verificacion")["valida"] is True


def test_alterar_copia_sobre_transferencias_y_sin_tocar_el_original(labs):
    cadena = cadena_real(labs[0])
    antes = json.dumps(cadena, sort_keys=True)
    for tipo in ("transaccion", "firma_tx"):
        copia, descripcion = alterar_copia(cadena, tipo, 2)         # el bloque 2 sólo trae una transferencia
        assert "transferencia" in descripcion
        v = verificar_cadena_detallada(copia, labs[0][0]["hash"])
        assert not v["valida"]
        for esperada in COMPROBACIONES_ESPERADAS[tipo]:
            assert v["bloques"][1]["comprobaciones"][esperada] is False
    assert json.dumps(cadena, sort_keys=True) == antes
    assert verificar_cadena_detallada(cadena, labs[0][0]["hash"])["valida"]


def test_la_verificacion_no_se_detiene_en_el_primer_error(labs):
    cadena = cadena_real(labs[0])
    copia, _ = alterar_copia(cadena, "firma_minero", 1)
    copia, _ = alterar_copia(copia, "merkle", 2)
    v = verificar_cadena_detallada(copia, labs[0][0]["hash"])
    assert v["bloques"][0]["comprobaciones"]["firma_minero"] is False
    assert v["bloques"][1]["comprobaciones"]["merkle"] is False
    assert v["primer_error"]["bloque"] == 1 and v["primer_error"]["comprobacion"] == "firma_minero"


def test_simulacion_rechaza_entradas_invalidas(con_cadena):
    c, _ = con_cadena
    for cuerpo, texto in (({"tipo": "inventado", "bloque": 1}, "tipo de alteración"),
                          ({"tipo": "hash", "bloque": 9}, "no existe"),
                          ({"tipo": "hash", "bloque": 0}, "mayor que cero"),
                          ({"tipo": "hash"}, "obligatorio"),
                          ({"tipo": "multifirma", "bloque": 2}, "no tiene sellos")):
        r = c.post(f"{API}/verificacion/simular", json=cuerpo)
        assert r.status_code == 400 and texto in r.get_json()["error"], cuerpo
    with pytest.raises(ErrorEntrada):
        alterar_copia([{"numero": 0}], "hash", 1)


def test_verificacion_y_simulacion_con_el_nodo_bloqueado(nodo, ctx, labs):
    assert ctx.nodo.recibir_cadena(cadena_real(labs[0]), de="LAB-B")[0]
    assert get(nodo, "/verificacion")["valida"] is True
    r = nodo.post(f"{API}/verificacion/simular", json={"tipo": "nonce", "bloque": 1})
    assert r.status_code == 200 and r.get_json()["valida"] is False


# ================================================================ 5. /clave
def test_clave_muestra_metadatos_sin_secretos(nodo, ctx, labs):
    doc = json.load(open(ctx.nodo.ruta_clave, encoding="utf-8"))
    c = get(nodo, "/clave")
    assert c["formato"] == "sellalo-clave" and c["version"] == 1 and c["id"] == "LAB-A"
    assert c["clave_publica"] == doc["clave_publica"] and c["archivo"].endswith("clave.json")
    assert c["kdf"]["alg"] == "scrypt" and (c["kdf"]["n"], c["kdf"]["r"], c["kdf"]["p"]) == (32768, 8, 1)
    assert c["kdf"]["largo"] == 32 and c["kdf"]["bytes_sal"] == 16
    assert c["cifrado"] == {"alg": "AES-256-GCM", "bytes_nonce": 12, "bytes_texto_cifrado": 48}
    assert c["aad"] == f"sellalo-clave|LAB-A|{doc['clave_publica']}"
    assert c["clave_en_claro_en_disco"] is False and c["desbloqueado"] is False
    assert (c["intentos_fallidos"], c["espera_s"]) == (0, 0)


def test_clave_nunca_devuelve_sal_nonce_texto_cifrado_ni_contrasena(abierto, ctx):
    doc = json.load(open(ctx.nodo.ruta_clave, encoding="utf-8"))
    secretos = [doc["kdf"]["sal"], doc["cifrado"]["nonce"], doc["cifrado"]["texto_cifrado"], CONTRASENA,
                ctx.nodo._claves.bytes_privados().hex()]
    abierto.post(f"{API}/desbloquear", json={"contrasena": "contrasena-incorrecta-1"})
    cuerpo = abierto.get(f"{API}/clave").get_data(as_text=True)
    cuerpo += abierto.get(f"{API}/estado").get_data(as_text=True) + abierto.get(f"{API}/rubrica").get_data(as_text=True)
    for secreto in secretos:
        assert secreto not in cuerpo
    assert get(abierto, "/clave")["desbloqueado"] is True
    assert get(abierto, "/clave")["clave_en_claro_en_disco"] is False


def test_clave_en_claro_se_detecta_si_la_clave_privada_esta_en_el_archivo(abierto, ctx):
    assert ctx.nodo.clave_en_claro_en_disco() is False
    doc = json.load(open(ctx.nodo.ruta_clave, encoding="utf-8"))
    doc["cifrado"]["texto_cifrado"] = ctx.nodo._claves.bytes_privados().hex() + "0" * 32      # simula un archivo mal hecho
    copia = ctx.nodo.ruta_clave + ".malo"
    json.dump(doc, open(copia, "w", encoding="utf-8"))
    original, ctx.nodo.ruta_clave = ctx.nodo.ruta_clave, copia
    try:
        assert ctx.nodo.clave_en_claro_en_disco() is True
    finally:
        ctx.nodo.ruta_clave = original
        os.unlink(copia)


def test_espera_creciente_tras_contrasenas_incorrectas(nodo, ctx):
    esperas = []
    ctx.nodo.pausa = esperas.append
    mala = {"contrasena": "contrasena-incorrecta-1"}
    for _ in range(4):
        assert nodo.post(f"{API}/desbloquear", json=mala).status_code == 400
    assert esperas == [1, 2, 4]                                   # el primer intento no espera
    c = get(nodo, "/clave")
    assert (c["intentos_fallidos"], c["espera_s"]) == (4, 8)
    ctx.nodo._fallos_desbloqueo = 50
    assert get(nodo, "/clave")["espera_s"] == 30                  # tope
    ctx.nodo._fallos_desbloqueo = 4
    assert nodo.post(f"{API}/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200
    assert esperas[-1] == 8
    c = get(nodo, "/clave")
    assert (c["intentos_fallidos"], c["espera_s"], c["desbloqueado"]) == (0, 0, True)


def test_la_espera_de_desbloqueo_ocurre_fuera_del_candado_del_nodo(nodo, ctx):
    ctx.nodo._fallos_desbloqueo = 2
    libre = []

    def pausa(segundos):
        def intentar():
            libre.append(ctx.nodo.lock.acquire(timeout=2))
            if libre[-1]:
                ctx.nodo.lock.release()
        hilo = threading.Thread(target=intentar)
        hilo.start(), hilo.join()
    ctx.nodo.pausa = pausa
    nodo.post(f"{API}/desbloquear", json={"contrasena": "contrasena-incorrecta-1"})
    assert libre == [True]                                        # otro hilo pudo tomar el candado durante la espera
    assert ctx.lock.acquire(timeout=1)                             # tampoco se retuvo el candado del contexto
    ctx.lock.release()


# ================================================================ 6. certificado con pasos y Merkle
def _certificado(c):
    r = c.get(f"{API}/certificado/{HASH_DOC}")
    assert r.status_code == 200
    return json.loads(r.data)


def _verificar_web(c, cert, documento=None):
    datos = {"certificado": (io.BytesIO(json.dumps(cert).encode()), "c.json")}
    if documento is not None:
        datos["documento"] = (io.BytesIO(documento), "d.pdf")
    r = c.post(f"{API}/certificado/verificar", data=datos, content_type="multipart/form-data")
    assert r.status_code == 200
    return r.get_json()


def test_certificado_valido_trae_los_seis_pasos_y_el_camino_merkle(con_cadena):
    c, cadena = con_cadena
    cert = _certificado(c)
    r = _verificar_web(c, cert, DOC)
    assert r["valido"] is True and r["detalle"]["documento_comprobado"] is True
    assert [p["paso"] for p in r["pasos"]] == ["génesis", "encabezados", "sello", "multifirma", "merkle", "documento"]
    assert all(p["ok"] is True and p["evaluado"] and p["detalle"] for p in r["pasos"])
    m = r["merkle"]
    assert m["hoja"] == cert["prueba_merkle"]["hoja"] and m["raiz"] == cadena[1]["raiz_merkle"]
    assert len(m["camino"]) == len(cert["prueba_merkle"]["camino"]) >= 1
    assert m["camino"][-1]["resultado"] == m["raiz"]
    assert all(set(p) == {"lado", "hash", "resultado"} for p in m["camino"])


def test_certificado_sin_documento_y_con_fallos_marca_lo_no_evaluado(con_cadena):
    c, _ = con_cadena
    cert = _certificado(c)
    r = _verificar_web(c, cert)
    assert r["pasos"][-1]["ok"] is None and r["pasos"][-1]["evaluado"] is False and r["valido"] is True
    cert["sello"]["firmas"]["LAB-A"] = "0" * 128                  # firma falsa
    r = _verificar_web(c, cert)
    estados = {p["paso"]: p["ok"] for p in r["pasos"]}
    assert r["valido"] is False and estados == {"génesis": True, "encabezados": True, "sello": True,
                                                 "multifirma": False, "merkle": None, "documento": None}
    assert "LAB-A" in r["pasos"][3]["detalle"] and r["merkle"] is None
    cert = _certificado(c)
    cert["prueba_merkle"]["camino"][0]["hash"] = "f" * 64          # camino roto: se ve dónde se desvía
    r = _verificar_web(c, cert)
    assert {p["paso"]: p["ok"] for p in r["pasos"]}["merkle"] is False
    assert r["merkle"]["camino"][-1]["resultado"] != r["merkle"]["raiz"]


def test_verificador_conserva_semantica_y_codigos_de_salida(con_cadena, tmp_path):
    c, _ = con_cadena
    cert = _certificado(c)
    g = cert["genesis"]["hash"]
    assert vc.verificar(cert, genesis_esperado=g)["valido"] is True
    sin = vc.verificar(cert)
    assert sin["valido"] is False and sin["concluyente"] is False and sin["genesis_confirmado"] is False
    assert all(p["ok"] is not False for p in sin["pasos"])
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps(cert), encoding="utf-8")
    assert vc.main([str(ruta), "--genesis", g]) == 0 and vc.main([str(ruta)]) == 3
    cert["doc_hash"] = "no"
    assert vc.verificar(cert)["pasos"][0]["ok"] is False
    ruta.write_text(json.dumps(cert), encoding="utf-8")
    assert vc.main([str(ruta), "--genesis", g]) == 1
    assert vc.verificar("no es dict")["valido"] is False


def test_el_verificador_sigue_siendo_independiente():
    arbol = ast.parse(open(os.path.join(RAIZ_REPO, "verificar_certificado.py"), encoding="utf-8").read())
    modulos = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos |= {a.name.split(".")[0] for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom):
            modulos.add(nodo.module.split(".")[0])
    assert modulos <= {"argparse", "hashlib", "json", "sys", "datetime", "cryptography"}, modulos


# ================================================================ 7. auditoría con IA
def test_script_de_auditoria_parsea_hallazgos_triaje_y_commits():
    d = estado_auditoria.generar(RAIZ_REPO)
    assert d["resumen"]["total"] == 62 == len(d["hallazgos"])
    por = {h["id"]: h for h in d["hallazgos"]}
    assert por["AUD-001"]["estado"] == "corregido" and por["AUD-001"]["commits"] and por["AUD-001"]["prueba"]
    assert por["AUD-001"]["decision"] == "C" and por["AUD-001"]["severidad"] == "Alta"
    assert por["AUD-006"]["estado"] == "resuelto_por_eliminacion" and por["AUD-015"]["estado"] == "justificado"
    assert por["AUD-023"]["estado"] == "justificado" and por["AUD-021"]["estado"] == "resuelto_por_eliminacion"
    assert por["AUD-012"]["estado"] == "pendiente" and not por["AUD-012"]["commits"]
    assert por["AUD-008"]["descripcion"].startswith("Autenticación P2P")
    assert sum(d["resumen"]["por_estado"].values()) == 62
    for h in d["hallazgos"]:
        assert h["estado"] != "corregido" or (h["decision"] in ("C", "CP") and h["commits"])
        assert h["decision"] and h["titulo"] and h["grupo"].startswith("G")


def test_estado_auditoria_reglas_y_tabla_con_barras():
    assert estado_auditoria.estado_de("C", "", ["abc"]) == "corregido"
    assert estado_auditoria.estado_de("C", "", []) == "pendiente"
    assert estado_auditoria.estado_de("CP", "", ["abc"]) == "corregido"
    assert estado_auditoria.estado_de("NA", "", ["abc"]) == "justificado"
    assert estado_auditoria.estado_de("D", "", []) == "justificado"
    assert estado_auditoria.estado_de("RE", "", []) == "resuelto_por_eliminacion"
    md = ("## 3. Tabla maestra\n\n| ID | a |\n|---|---|\n"
          "| AUD-009 | Seguridad | Alta | G1-red | `a.py:1` | Firma `reto|id_propio` mala. Otra frase. | P1-1 | Pendiente | — | — | Pendiente |\n"
          "\n## 4. Fichas\n")
    fila = estado_auditoria.leer_tabla_maestra(md)["AUD-009"]
    assert fila["descripcion"] == "Firma `reto|id_propio` mala. Otra frase." and fila["grupo"] == "G1-red"


def test_auditoria_ruta(abierto, tmp_path, monkeypatch):
    a = get(abierto, "/auditoria")
    assert a["resumen"]["total"] == 62 and len(a["hallazgos"]) == 62 and a["generado"].endswith("Z")
    h = a["hallazgos"][0]
    assert set(h) >= {"id", "titulo", "severidad", "categoria", "grupo", "decision", "estado", "commits", "prueba"}
    monkeypatch.setattr(rubrica, "RAIZ", str(tmp_path))
    r = abierto.get(f"{API}/auditoria")
    assert r.status_code == 409 and "estado_auditoria.py" in r.get_json()["error"]
    (tmp_path / "docs" / "auditoria").mkdir(parents=True)
    (tmp_path / "docs" / "auditoria" / "estado.json").write_text("{roto", encoding="utf-8")
    assert abierto.get(f"{API}/auditoria").status_code == 409


def test_estado_json_versionado_coincide_con_las_fuentes():
    """Los datos que vienen de HALLAZGOS.md y TRIAJE.md deben estar al día en el JSON versionado. (Commits y estado
    cambian con cada corrección: se regeneran con `python scripts/estado_auditoria.py`, sin romper esta prueba.)"""
    versionado = json.load(open(os.path.join(RAIZ_REPO, "docs", "auditoria", "estado.json"), encoding="utf-8"))
    nuevo = estado_auditoria.generar(RAIZ_REPO)
    campos = ("id", "titulo", "descripcion", "severidad", "categoria", "grupo", "decision", "accion")
    recortar = lambda d: [{k: h[k] for k in campos} for h in d["hallazgos"]]
    assert recortar(versionado) == recortar(nuevo), "regenera: python scripts/estado_auditoria.py"
    assert versionado["resumen"]["total"] == nuevo["resumen"]["total"] == 62


# ================================================================ 8. entrega y rúbrica
def test_entrega_refleja_los_archivos_reales(nodo, monkeypatch, tmp_path):
    e = get(nodo, "/entrega")["entregables"]
    por = {x["nombre"]: x for x in e}
    assert por["README con instalación y ejecución"]["existe"] is True
    assert por["Pruebas automáticas"]["existe"] and "función(es) de prueba" in por["Pruebas automáticas"]["detalle"]
    assert por["Guía de demostración"]["archivo"] == "scripts/demo_e2e.py"
    assert por["Reporte técnico final"]["existe"] == os.path.isfile(os.path.join(RAIZ_REPO, "docs", "REPORTE_FINAL.md"))
    assert all(set(x) == {"nombre", "archivo", "existe", "detalle"} for x in e)
    monkeypatch.setattr(rubrica, "RAIZ", str(tmp_path))                       # repositorio vacío: nada se inventa
    vacio = get(nodo, "/entrega")["entregables"]
    assert not any(x["existe"] for x in vacio)


def test_rubrica_con_nodo_nuevo_no_demuestra_nada(nodo):
    r = get(nodo, "/rubrica")
    assert [c["id"] for c in r["criterios"]] == ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "EX"]
    assert [c["puntos"] for c in r["criterios"]] == [1, 1, 1, 1, 1, 1, 2, 2, 1]
    for c in r["criterios"]:
        assert c["estado"] in ("parcial", "pendiente"), c           # sin uso en vivo nada está «demostrado»
        assert c["evidencias"] and all(set(e) == {"texto", "ok"} for e in c["evidencias"]) and c["seccion"]
    por = {c["id"]: c for c in r["criterios"]}
    assert por["R7"]["estado"] == "pendiente" and por["R5"]["estado"] == "pendiente"
    assert len(r["recorrido"]) == 10
    assert get(nodo, "/estado")["recorrido"] == r["recorrido"]


def test_rubrica_sigue_la_evidencia_real(con_cadena, ctx, labs):
    c, cadena = con_cadena
    c.post(f"{API}/desbloquear", json={"contrasena": CONTRASENA})            # 409: ya abierto (no cuenta como fallo)
    por = lambda: {x["id"]: x for x in get(c, "/rubrica")["criterios"]}
    assert por()["R1"]["estado"] == "parcial" and por()["R6"]["estado"] == "parcial"
    c.post(f"{API}/verificacion/simular", json={"tipo": "multifirma", "bloque": 1})
    c.post(f"{API}/verificacion/simular", json={"tipo": "merkle", "bloque": 2})
    assert por()["R1"]["estado"] == "demostrado" and por()["R2"]["estado"] == "demostrado"
    assert all(e["ok"] for e in por()["R1"]["evidencias"])
    # R3: falta una contraseña incorrecta rechazada
    assert por()["R3"]["estado"] == "parcial"
    ctx.nodo.bloquear()
    assert c.post(f"{API}/desbloquear", json={"contrasena": "contrasena-incorrecta-1"}).status_code == 400
    assert c.post(f"{API}/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200
    assert por()["R3"]["estado"] == "demostrado"
    # R4: conflicto resuelto + rechazos
    assert por()["R4"]["estado"] == "parcial"
    alterna = rama(labs[0], [[transferencia(labs[0], "LAB-C", "LAB-A", 1, time.time() - 50)]] * 1, proponente="LAB-C")
    assert not ctx.nodo.recibir_cadena(alterna, de="LAB-C")[0]               # menos trabajo: rechazada
    assert ctx.nodo.recibir_bloque(bloque_malo(labs[0], cadena[-1]), de="LAB-B")[0] == "rechazado"
    mas = rama(labs[0], [[transferencia(labs[0], "LAB-C", "LAB-A", 1, time.time() - 60)],
                         [transferencia(labs[0], "LAB-C", "LAB-A", 2, time.time() - 50)],
                         [transferencia(labs[0], "LAB-C", "LAB-A", 3, time.time() - 40)]], proponente="LAB-C")
    assert ctx.nodo.recibir_cadena(mas, de="LAB-C")[0]
    r4 = por()["R4"]
    assert r4["estado"] == "demostrado", r4["evidencias"]
    # R5 no puede demostrarse sin pares; R8/EX se calculan de los archivos y reflejan lo que falta
    assert por()["R5"]["estado"] == "parcial"
    ent = get(c, "/entrega")["entregables"]
    assert [e["ok"] for e in por()["R8"]["evidencias"]] == [x["existe"] for x in ent]
    ex = por()["EX"]
    assert ex["estado"] == "parcial" and ex["evidencias"][-1]["ok"] is False and "pendiente" in ex["evidencias"][-1]["texto"]


def test_rubrica_honesta_sin_estado_de_auditoria(nodo, monkeypatch, tmp_path):
    monkeypatch.setattr(rubrica, "RAIZ", str(tmp_path))
    por = {x["id"]: x for x in get(nodo, "/rubrica")["criterios"]}
    assert por["EX"]["estado"] == "pendiente" and "estado_auditoria.py" in por["EX"]["evidencias"][0]["texto"]
    assert por["R8"]["estado"] == "pendiente" and por["R1"]["evidencias"][-1]["ok"] is False


# ================================================================ 9. rutas: bloqueado, CSRF, nunca 500
RUTAS_GET = ("/rubrica", "/verificacion", "/clave", "/auditoria", "/entrega", "/estado")


def test_rutas_nuevas_funcionan_con_el_nodo_bloqueado(nodo):
    for ruta in RUTAS_GET:
        r = nodo.get(API + ruta)
        assert r.status_code == 200 and r.get_json()["ok"], ruta


def test_rutas_nuevas_son_get_salvo_simular(nodo):
    for ruta in RUTAS_GET:
        assert nodo.post(API + ruta).status_code == 405, ruta
    assert nodo.get(f"{API}/verificacion/simular").status_code == 405


def test_simular_respeta_la_defensa_csrf_y_de_host(con_cadena):
    c, _ = con_cadena
    cuerpo = {"tipo": "hash", "bloque": 1}
    assert c.post(f"{API}/verificacion/simular", json=cuerpo, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post(f"{API}/verificacion/simular", json=cuerpo, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert c.post(f"{API}/verificacion/simular", json=cuerpo, headers={"Host": "evil.example"}).status_code == 403
    assert c.post(f"{API}/verificacion/simular", json=cuerpo, headers={"Origin": "http://localhost"}).status_code == 200


def test_entradas_malas_en_simular_nunca_dan_500(con_cadena):
    c, _ = con_cadena
    for cuerpo in ({"tipo": None, "bloque": 1}, {"tipo": ["x"], "bloque": 1}, {"tipo": "hash", "bloque": "a"},
                   {"tipo": "hash", "bloque": 1e30}, {"tipo": "hash", "bloque": True}, {"tipo": "hash", "bloque": -1},
                   [], "texto"):
        assert c.post(f"{API}/verificacion/simular", json=cuerpo).status_code == 400, cuerpo
    assert c.post(f"{API}/verificacion/simular", data="no json",
                  headers={"Content-Type": "application/json"}).status_code == 400


def test_modo_simulador_responde_409_en_las_rutas_nuevas():
    from app import create_app
    c = create_app().test_client()
    for ruta in RUTAS_GET[:-1]:
        assert c.get(API + ruta).status_code == 409
    assert c.post(f"{API}/verificacion/simular", json={}).status_code == 409


def test_verificar_cadena_detallada_tolera_basura(labs):
    g = labs[0][0]["hash"]
    for basura in ([], [None], [{"hash": 1}], "x", None, [labs[0][0], {"numero": 1}], [labs[0][0], 5]):
        v = verificar_cadena_detallada(basura, g)
        assert v["valida"] is False
