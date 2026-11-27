"""Pruebas adversariales: secretos, concurrencia, P2P malicioso a nivel socket, datos de cadena inválidos, archivos
corruptos en disco y certificados hostiles. Cada prueba busca que el nodo NO se caiga y que explique el rechazo."""
import copy
import hashlib
import io
import json
import logging
import os
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import create_app_nodo
from models import merkle
from models.bloque import ErrorValidacion, Estado, hash_bloque
from models.certificado import generar_certificado
from models.errores import ErrorEntrada
from models.keystore import abrir_almacen
from models.multifirma import revisar_sello
from models.validacion import validar_cadena
from tests.laboratorios import CONTRASENA, bloque_externo, crear_laboratorios, nuevo_nodo, rama, sello, transferencia
from verificar_certificado import verificar

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPCIONES = dict(intervalo_ping=0.2, tiempo_sin_respuesta=3.0, tiempo_saludo=1.5, tiempo_sync=1.0, segundos_veto=0.02)
DOC = b"documento adversarial"
HASH_DOC = hashlib.sha256(DOC).hexdigest()


def esperar(cond, limite=10.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


@pytest.fixture(scope="module")
def labs(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("labs_adv")
    genesis, rutas, claves = crear_laboratorios(carpeta)
    ruta = carpeta / "genesis.json"
    ruta.write_text(json.dumps(genesis), encoding="utf-8")
    return genesis, rutas, claves, str(ruta)


@pytest.fixture(scope="module")
def labs_otra_red(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("labs_otra")
    genesis, rutas, claves = crear_laboratorios(carpeta)
    ruta = carpeta / "genesis.json"
    ruta.write_text(json.dumps(genesis), encoding="utf-8")
    return genesis, rutas, claves, str(ruta)


def crear_app(labs, carpeta, nodo_id="LAB-A"):
    genesis, rutas, _, ruta_genesis = labs
    app = create_app_nodo(str(carpeta), ruta_genesis, nodo_id, puerto_p2p=0, ruta_clave=rutas[nodo_id],
                          host_p2p="127.0.0.1", opciones_p2p=OPCIONES, laboratorio_ataques=True)
    app.config["TESTING"] = True
    return app


def cerrar_app(app):
    ctx = app.config["CONTEXTO_NODO"]
    ctx.nodo.detener_minado()
    ctx.bloquear()


@pytest.fixture
def app_nodo(labs, tmp_path):
    app = crear_app(labs, tmp_path / "datos")
    yield app
    cerrar_app(app)


@pytest.fixture
def desbloqueado(app_nodo):
    c = app_nodo.test_client()
    assert c.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200
    return c


def estado(c):
    return c.get("/api/sellalo/estado").get_json()


# ================================================================ 1. almacén de claves y secretos
def test_gitignore_protege_claves_y_datos():
    with open(os.path.join(RAIZ, ".gitignore"), encoding="utf-8") as f:
        lineas = {l.strip() for l in f if l.strip() and not l.startswith("#")}
    assert {"data/", "clave.json", "*.key"} <= lineas


def test_ningun_archivo_versionado_contiene_claves_privadas():
    try:
        salida = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("git no disponible")
    if salida.returncode != 0:
        pytest.skip("no es un repositorio git")
    archivos = salida.stdout.split()
    assert archivos
    for ruta in archivos:
        nombre = os.path.basename(ruta)
        assert nombre != "clave.json" and not nombre.endswith((".key", ".pem")), f"{ruta} es un archivo de claves"
        completa = os.path.join(RAIZ, ruta)
        if not os.path.isfile(completa) or os.path.getsize(completa) > 2_000_000:
            continue
        with open(completa, "rb") as f:
            texto = f.read().decode("utf-8", "ignore")
        assert not re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", texto), f"{ruta} contiene una clave PEM"
        assert not re.search(r'"(clave_privada|private_key)"\s*:\s*"[0-9a-fA-F]{64}"', texto), f"{ruta} guarda una clave en claro"
        if ruta.endswith(".json"):
            assert '"texto_cifrado"' not in texto, f"{ruta} es un almacén de claves"


def test_historial_sin_claves_ni_almacenes():
    """Ningún archivo de ninguna versión del repositorio es un almacén de claves ni contiene una clave PEM.
    Se buscan contenidos (git grep sobre todas las revisiones) y se excluye este archivo, que menciona el patrón."""
    patron = "BEGIN " + "PRIVATE KEY"
    try:
        out = subprocess.run(["git", "log", "--all", "--name-only", "--format="], cwd=RAIZ, capture_output=True,
                             text=True, timeout=60)
        revs = subprocess.run(["git", "rev-list", "--all"], cwd=RAIZ, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("git no disponible")
    if out.returncode != 0 or revs.returncode != 0:
        pytest.skip("no es un repositorio git")
    nombres = {os.path.basename(x) for x in out.stdout.split()}
    assert "clave.json" not in nombres and not [n for n in nombres if n.endswith(".key")]
    pem = subprocess.run(["git", "grep", "-l", "-F", patron, *revs.stdout.split()], cwd=RAIZ, capture_output=True,
                         text=True, timeout=60)
    este = os.path.relpath(__file__, RAIZ).replace(os.sep, "/")
    hallados = {linea.split(":", 1)[1] for linea in pem.stdout.split() if ":" in linea}
    assert hallados <= {este}, f"posible clave privada versionada en: {sorted(hallados - {este})}"


def test_secretos_no_salen_en_respuestas_bitacora_ni_logs(labs, app_nodo, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    privados = abrir_almacen(labs[1]["LAB-A"], CONTRASENA).bytes_privados()
    secretos = [CONTRASENA, privados.hex(), privados.hex().upper()]
    c = app_nodo.test_client()
    respuestas = []
    mala = "SECRETO-incorrecto-9f3a7c"
    for cuerpo in ({"contrasena": mala}, {"contrasena": "x" * 5000}, {"contrasena": {"a": mala}},
                   {"contrasena": [mala]}, {"contrasena": 12345678901}, {"contrasena": ""}, {}):
        r = c.post("/api/sellalo/desbloquear", json=cuerpo)
        assert r.status_code == 400, cuerpo
        assert r.get_json()["error"]
        respuestas.append(r.data)
        assert mala.encode() not in r.data and b"x" * 200 not in r.data
    r = c.post("/api/sellalo/desbloquear", data=f'{{"contrasena": "{mala}", ', content_type="application/json")
    assert r.status_code == 400 and mala.encode() not in r.data
    r = c.post("/api/sellalo/desbloquear", data=f"contrasena={mala}", content_type="text/plain")
    assert r.status_code == 400 and mala.encode() not in r.data
    assert c.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200
    respuestas.append(c.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).data)   # ya desbloqueado
    r = c.post("/api/sellalo/sellos", data={"doc_hash": HASH_DOC, "titulo": "t", "investigador": "i",
                                            "autores": "LAB-A", "umbral": "1"})
    assert r.status_code == 200
    assert c.post("/api/sellalo/minar", json={"dificultad": 1}).status_code == 200
    assert esperar(lambda: not estado(c)["nodo"]["minando"])
    assert c.post("/api/sellalo/transferencias", json={"receptor": "LAB-B", "monto": 1}).status_code in (200, 400)
    assert c.get(f"/api/sellalo/certificado/{HASH_DOC}").status_code in (200, 400)
    nodo = app_nodo.config["CONTEXTO_NODO"].nodo
    texto = " ".join(x.decode("utf-8", "replace") for x in respuestas) + json.dumps(estado(c))
    texto += json.dumps(nodo.publico()) + caplog.text + " ".join(str(e) for e in nodo.bitacora)
    capturado = capsys.readouterr()
    texto += capturado.out + capturado.err
    for secreto in secretos + [mala]:
        assert secreto not in texto
    assert privados not in b"".join(respuestas)
    assert nodo.desbloqueado and privados.hex() not in repr(nodo._claves)


# ================================================================ 2. concurrencia
def test_peticiones_concurrentes_no_dan_500_ni_duplican_pendientes(app_nodo, desbloqueado):
    app = app_nodo
    estatus: list[int] = []
    cuerpos: list[str] = []
    bloqueo = threading.Lock()
    contador = iter(range(10_000))

    def registrar(r):
        with bloqueo:
            estatus.append(r.status_code)
            if r.status_code >= 500:
                cuerpos.append(r.data.decode("utf-8", "replace")[:300])

    def trabajador(i):
        c = app.test_client()
        for j in range(12):
            op = (i + j) % 5
            if op == 0:
                with bloqueo:
                    n = next(contador)
                registrar(c.post("/api/sellalo/sellos", json={
                    "doc_hash": hashlib.sha256(f"doc-{n}".encode()).hexdigest(), "titulo": f"Sello {n}",
                    "investigador": "Dra. Hilo", "autores": ["LAB-A"], "umbral": 1}))
            elif op == 1:
                registrar(c.post("/api/sellalo/minar", json={"dificultad": 1}))
            elif op == 2:
                registrar(c.post(f"/api/sellalo/sellos/{hashlib.sha256(str(j).encode()).hexdigest()}/firmar"))
            elif op == 3:
                registrar(c.post("/api/sellalo/transferencias", json={"receptor": "LAB-B", "monto": 1}))
            else:
                registrar(c.get("/api/sellalo/estado"))

    with ThreadPoolExecutor(max_workers=10) as pool:
        for f in [pool.submit(trabajador, i) for i in range(10)]:
            f.result(timeout=60)
    nodo = app.config["CONTEXTO_NODO"].nodo
    nodo.detener_minado()
    assert not cuerpos, cuerpos
    assert len(estatus) == 120 and set(estatus) <= {200, 400, 409}, sorted(set(estatus))
    with nodo.lock:
        ids = [p["id"] for p in nodo.publico()["pendientes"]]
        validar_cadena(copy.deepcopy(nodo.cadena), nodo.hash_genesis)
        en_cadena = {t.get("firma") or t.get("doc_hash") for b in nodo.cadena[1:] for t in b["transacciones"]}
        pendientes = {t.get("firma") or t.get("doc_hash") for t in nodo.pendientes}
    assert len(ids) == len(set(ids)), "hay pendientes duplicadas"
    assert not (en_cadena & pendientes), "una transacción está a la vez en la cadena y en pendientes"
    assert nodo.altura >= 1


# ================================================================ 3. P2P malicioso por socket
class Cruda:
    """Conexión TCP cruda al puerto P2P de un nodo (sin ninguna lógica del protocolo)."""

    def __init__(self, puerto):
        self.s = socket.create_connection(("127.0.0.1", puerto), timeout=5)
        self.buf = b""

    def enviar(self, dato) -> bool:
        if not isinstance(dato, (bytes, bytearray)):
            dato = json.dumps(dato).encode() + b"\n"
        try:
            self.s.sendall(dato)
            return True
        except OSError:
            return False

    def leer(self, espera=3.0):
        """Siguiente mensaje JSON, o None si se cerró o venció el tiempo."""
        fin = time.monotonic() + espera
        while b"\n" not in self.buf:
            self.s.settimeout(max(0.05, fin - time.monotonic()))
            try:
                d = self.s.recv(65536)
            except OSError:
                return None
            if not d:
                return None
            self.buf += d
        linea, self.buf = self.buf.split(b"\n", 1)
        return json.loads(linea)

    def cerrar(self):
        try:
            self.s.close()
        except OSError:
            pass


def hello(genesis_hash, nodo="LAB-B", **cambios):
    msg = {"tipo": "HELLO", "version": 2, "nodo": nodo, "genesis": genesis_hash, "altura": 0, "trabajo": 0,
           "punta": genesis_hash, "reto": os.urandom(16).hex(), "puerto": 1}
    msg.update(cambios)
    return msg


def firma_saludo(genesis_hash, reto_iniciador, reto_respondedor, firmante, destinatario) -> bytes:
    """Mensaje que se firma en el AUTH (AUD-008): ligado a la red, a los dos retos y a los dos extremos."""
    return f"sellalo-p2p|{genesis_hash}|{reto_iniciador}|{reto_respondedor}|{firmante}|{destinatario}".encode()


def autenticar(destino, labs, nodo="LAB-B", **cambios_hello):
    """Saludo completo y válido como `nodo` (con su clave real). Devuelve la conexión o None si no se pudo."""
    genesis, _, claves, _ = labs
    fin = time.monotonic() + 4
    while time.monotonic() < fin:
        k = Cruda(destino)
        saludo = hello(genesis["hash"], nodo, **cambios_hello)
        k.enviar(saludo)
        ack = k.leer()
        if ack and ack.get("tipo") == "HELLO_ACK":
            k.enviar({"tipo": "AUTH", "firma_reto": claves[nodo].firmar(firma_saludo(
                genesis["hash"], saludo["reto"], ack["reto"], nodo, ack["nodo"]))})
            time.sleep(0.15)
            return k
        k.cerrar()
        time.sleep(0.05)     # vetado o "par ya conectado" de una prueba anterior: se reintenta
    return None


@pytest.fixture
def nodo_p2p(labs, app_nodo, desbloqueado):
    ctx = app_nodo.config["CONTEXTO_NODO"]
    return app_nodo, ctx, ctx.servidor.puerto


def _rechazar_constante(c):
    raise AssertionError(f"JSON no estándar en /estado: {c}")


def vivo(app, ctx, altura=0):
    """El nodo sigue respondiendo, su servidor P2P escucha y su cadena no cambió; /estado es JSON estricto."""
    r = app.test_client().get("/api/sellalo/estado")
    assert r.status_code == 200
    json.loads(r.data, parse_constant=_rechazar_constante)
    assert ctx.servidor.activo and ctx.nodo.altura == altura
    with socket.create_connection(("127.0.0.1", ctx.servidor.puerto), timeout=3):
        pass


def test_saludo_con_genesis_ajeno_es_rechazado(nodo_p2p, labs_otra_red):
    app, ctx, puerto = nodo_p2p
    k = Cruda(puerto)
    k.enviar(hello(labs_otra_red[0]["hash"]))
    resp = k.leer()
    assert resp["tipo"] == "HELLO_REJECT" and "génesis" in resp["motivo"]
    k.cerrar()
    vivo(app, ctx)
    assert estado(app.test_client())["pares"] == []


@pytest.mark.parametrize("cambio,motivo", [({"version": 1}, "versión"), ({"nodo": "LAB-X"}, "desconocida"),
                                           ({"nodo": "LAB-A"}, "propia")])
def test_saludo_con_identidad_o_version_invalidas(nodo_p2p, labs, cambio, motivo):
    app, ctx, puerto = nodo_p2p
    k = Cruda(puerto)
    k.enviar(hello(labs[0]["hash"], **cambio))
    resp = k.leer()
    assert resp["tipo"] == "HELLO_REJECT" and motivo in resp["motivo"]
    k.cerrar()
    vivo(app, ctx)


def test_reto_mal_firmado_no_autentica(nodo_p2p, labs):
    app, ctx, puerto = nodo_p2p
    genesis, _, claves, _ = labs
    for firma in (os.urandom(64).hex(),                       # al azar
                  "",                                         # ausente
                  12345,                                      # tipo incorrecto
                  claves["LAB-B"].firmar(b"otro mensaje"),    # firma válida de LAB-B, pero de otra cosa
                  "00" * 63):                                 # largo incorrecto
        k = Cruda(puerto)
        k.enviar(hello(genesis["hash"]))
        assert k.leer()["tipo"] == "HELLO_ACK"
        k.enviar({"tipo": "AUTH", "firma_reto": firma})
        resp = k.leer()
        assert resp and resp["tipo"] == "HELLO_REJECT" and "firma" in resp["motivo"]
        k.cerrar()
        time.sleep(0.05)
    vivo(app, ctx)
    assert estado(app.test_client())["pares"] == []


def test_suplantacion_de_identidad_con_firma_de_otro_laboratorio(nodo_p2p, labs):
    """LAB-C firma el reto diciendo ser LAB-B: la firma no se verifica con la clave de LAB-B."""
    app, ctx, puerto = nodo_p2p
    genesis, _, claves, _ = labs
    k = Cruda(puerto)
    saludo = hello(genesis["hash"], "LAB-B")
    k.enviar(saludo)
    ack = k.leer()
    k.enviar({"tipo": "AUTH", "firma_reto": claves["LAB-C"].firmar(firma_saludo(
        genesis["hash"], saludo["reto"], ack["reto"], "LAB-B", ack["nodo"]))})
    assert k.leer()["tipo"] == "HELLO_REJECT"
    k.cerrar()
    vivo(app, ctx)


def test_flood_de_lineas_antes_y_despues_del_saludo(nodo_p2p, labs):
    app, ctx, puerto = nodo_p2p
    k = Cruda(puerto)
    k.enviar(b'{"tipo":"PING"}\n' * 20000)
    k.cerrar()
    vivo(app, ctx)
    k = autenticar(puerto, labs)
    assert k is not None
    k.enviar(b'{"tipo":"PING","t":1}\n' * 20000)
    k.cerrar()
    time.sleep(0.3)
    vivo(app, ctx)


@pytest.mark.parametrize("autenticado", [False, True])
def test_linea_de_2_mib_cierra_la_conexion(nodo_p2p, labs, autenticado):
    app, ctx, puerto = nodo_p2p
    k = autenticar(puerto, labs) if autenticado else Cruda(puerto)
    assert k is not None
    k.enviar(b'{"tipo":"PING","relleno":"' + b"a" * (2 * 1024 * 1024) + b'"}\n')
    assert esperar(lambda: k.leer(0.3) is None, 5)
    k.cerrar()
    vivo(app, ctx)


def anidado(profundidad):
    return b"[" * profundidad + b"]" * profundidad


@pytest.mark.parametrize("autenticado", [False, True])
@pytest.mark.parametrize("carga", [b"[" * 200_000 + b"\n", anidado(5000) + b"\n",
                                   b'{"tipo":"BLOQUE","bloque":' + anidado(900) + b"}\n",
                                   b'{"tipo":"TX","tx":' + anidado(900) + b"}\n",
                                   b'{"tipo":"SELLO_PROPUESTO","sello":' + anidado(900) + b"}\n",
                                   b'{"tipo":"' + b"x" * 100_000 + b'"}\n', b"\xff\xfe\x00 no es utf-8\n",
                                   b"{" * 100_000 + b"\n"],
                         ids=["abre-200k", "anidado-5000", "bloque-anidado", "tx-anidada", "sello-anidado", "tipo-100k",
                              "no-utf8", "llaves-100k"])
def test_json_profundo_y_basura(nodo_p2p, labs, autenticado, carga):
    app, ctx, puerto = nodo_p2p
    k = autenticar(puerto, labs) if autenticado else Cruda(puerto)
    assert k is not None
    k.enviar(carga)
    time.sleep(0.2)
    k.enviar({"tipo": "PING", "t": time.time()})
    k.cerrar()
    time.sleep(0.1)
    vivo(app, ctx)


def test_basura_repetida_de_un_par_autenticado_se_cuenta_y_se_corta(nodo_p2p, labs):
    """JSON anidado en exceso (RecursionError) debe contar como falta, no sólo cerrar la conexión en silencio."""
    app, ctx, puerto = nodo_p2p
    k = autenticar(puerto, labs)
    assert k is not None
    for _ in range(8):
        if not k.enviar(b"[" * 100_000 + b"\n"):
            break
    assert esperar(lambda: k.leer(0.3) is None, 5)
    k.cerrar()
    vivo(app, ctx)
    assert any("Falta de LAB-B" in e["texto"] for e in ctx.nodo.bitacora)


def test_bloques_con_10000_elementos_es_falta(nodo_p2p, labs):
    app, ctx, puerto = nodo_p2p
    k = autenticar(puerto, labs)
    assert k is not None
    k.enviar({"tipo": "BLOQUES", "desde": 1, "bloques": [{"numero": i} for i in range(10_000)]})
    time.sleep(0.3)
    k.enviar({"tipo": "BLOQUES", "desde": 1, "bloques": [1, 2, 3]})
    time.sleep(0.2)
    k.cerrar()
    vivo(app, ctx)
    assert any("BLOQUES mal formado" in e["texto"] for e in ctx.nodo.bitacora)


@pytest.mark.parametrize("desde", ["-1", "0", str(-(10**30)), str(10**30), str(10**1000), "true", "false", "1.5", '"1"',
                                   "null", "[]", "{}", "NaN", "1e999"],
                         ids=lambda d: d[:20])
def test_get_bloques_con_desde_invalido(nodo_p2p, labs, desde):
    app, ctx, puerto = nodo_p2p
    k = autenticar(puerto, labs)
    assert k is not None
    k.enviar(f'{{"tipo":"GET_BLOQUES","desde":{desde}}}\n'.encode())
    resp = k.leer(1.0) if desde in (str(10**30), str(10**1000)) else None
    while resp and resp["tipo"] != "BLOQUES":          # el nodo puede intercalar un PING
        resp = k.leer(1.0)
    if desde in (str(10**30), str(10**1000)):
        assert resp and resp["tipo"] == "BLOQUES" and resp["bloques"] == []
    k.cerrar()
    time.sleep(0.1)
    vivo(app, ctx)


@pytest.mark.parametrize("grande", [10**1000, 10**4000], ids=["1e1000", "1e4000"])
def test_numeros_gigantes_en_el_saludo_y_en_estado(nodo_p2p, labs, grande):
    app, ctx, puerto = nodo_p2p
    k = autenticar(puerto, labs, altura=grande, trabajo=grande, puerto=grande)
    vivo(app, ctx)               # aceptado o no, /estado debe seguir siendo JSON válido
    if k is not None:
        k.cerrar()


@pytest.mark.parametrize("campo", ["version", "nodo", "genesis", "altura", "trabajo", "punta", "reto", "puerto", "tipo"])
@pytest.mark.parametrize("basura", [None, True, -1, 1.5, "x", [], {"a": 1}, 10**1000, "\u0000" * 20, "a" * 5000],
                         ids=lambda b: repr(b)[:15])
def test_tipos_incorrectos_en_cada_campo_del_saludo(nodo_p2p, labs, campo, basura):
    app, ctx, puerto = nodo_p2p
    msg = hello(labs[0]["hash"])
    msg[campo] = basura
    k = Cruda(puerto)
    k.enviar(msg)
    resp = k.leer(1.5)
    assert resp is None or resp["tipo"] in ("HELLO_REJECT", "HELLO_ACK")
    k.cerrar()
    time.sleep(0.03)
    vivo(app, ctx)


MENSAJES_BASURA = [
    {"tipo": 5}, {"tipo": None}, {"tipo": []}, {"tipo": "DESCONOCIDO"}, {"tipo": "HELLO"}, {"tipo": "AUTH"},
    {"tipo": "BLOQUE"}, {"tipo": "BLOQUE", "bloque": None}, {"tipo": "BLOQUE", "bloque": 5},
    {"tipo": "BLOQUE", "bloque": "x"}, {"tipo": "BLOQUE", "bloque": []}, {"tipo": "BLOQUE", "bloque": {}},
    {"tipo": "BLOQUE", "bloque": {"hash": 5}}, {"tipo": "BLOQUE", "bloque": {"hash": "a" * 64, "numero": "x"}},
    {"tipo": "BLOQUE", "bloque": {"hash": "a" * 64, "numero": 10**1000}},
    {"tipo": "BLOQUE", "bloque": {"hash": "a" * 64, "numero": 1, "timestamp": "x", "hash_anterior": 5}},
    {"tipo": "BLOQUE", "bloque": {"hash": "a" * 64, "numero": -5, "timestamp": 1e300}},
    {"tipo": "BLOQUE", "bloque": {"hash": "a" * 64, "numero": 1, "transacciones": "x", "dificultad": "3"}},
    {"tipo": "TX"}, {"tipo": "TX", "tx": None}, {"tipo": "TX", "tx": []}, {"tipo": "TX", "tx": {"monto": 10**1000}},
    {"tipo": "TX", "tx": {"emisor": 5, "receptor": [], "monto": True, "timestamp": "x", "firma": {}}},
    {"tipo": "TX", "tx": {"tipo": "sello", "autores": 5, "firmas": 7, "umbral": True}},
    {"tipo": "SELLO_PROPUESTO"}, {"tipo": "SELLO_PROPUESTO", "sello": "x"},
    {"tipo": "SELLO_PROPUESTO", "sello": {"tipo": "sello"}},
    {"tipo": "SELLO_FIRMA"}, {"tipo": "SELLO_FIRMA", "id_sello": 5, "autor": [], "firma": {}},
    {"tipo": "SELLO_FIRMA", "id_sello": "a" * 64, "autor": "LAB-B", "firma": "z" * 128},
    {"tipo": "GET_BLOQUES"}, {"tipo": "BLOQUES"}, {"tipo": "BLOQUES", "bloques": "x"}, {"tipo": "BLOQUES", "bloques": [1]},
    {"tipo": "PING", "t": "x"}, {"tipo": "PING", "t": [1]}, {"tipo": "PONG", "t": 10**1000}, {"tipo": "PONG", "t": "x"},
    {"tipo": "PONG", "t": None}, {"tipo": "BYE"}, [], "texto", 5, None,
]


@pytest.mark.parametrize("mensaje", MENSAJES_BASURA, ids=lambda m: json.dumps(m)[:50])
def test_mensajes_autenticados_con_tipos_incorrectos(nodo_p2p, labs, mensaje):
    app, ctx, puerto = nodo_p2p
    k = autenticar(puerto, labs)
    assert k is not None
    k.enviar(mensaje)
    time.sleep(0.1)
    k.enviar({"tipo": "PING", "t": time.time()})
    k.cerrar()
    time.sleep(0.05)
    vivo(app, ctx)


@pytest.mark.parametrize("t", ["-1e308", "-1e999", "1e999", "NaN", "Infinity", "-Infinity"])
def test_pong_con_marca_de_tiempo_extrema_no_rompe_estado(nodo_p2p, labs, t):
    """La latencia se calcula con un dato del par: no puede volver «Infinity» o NaN el JSON de /estado."""
    app, ctx, puerto = nodo_p2p
    k = autenticar(puerto, labs)
    assert k is not None
    k.enviar(f'{{"tipo":"PONG","t":{t}}}\n'.encode())
    time.sleep(0.2)
    texto = app.test_client().get("/api/sellalo/estado").get_data(as_text=True)
    assert "Infinity" not in texto and "NaN" not in texto
    k.cerrar()
    vivo(app, ctx)


# ================================================================ 4. reglas de cadena
@pytest.fixture
def nodo_cadena(labs, tmp_path):
    paquete = (labs[0], labs[1], labs[2])
    return nuevo_nodo(tmp_path / "n", paquete, "LAB-A"), paquete


def rehacer(bloque, claves, **cambios):
    """Copia del bloque con cambios; recalcula (y mina si procede) el hash y vuelve a firmar."""
    b = copy.deepcopy(bloque)
    b.update(cambios)
    b["raiz_merkle"] = merkle.raiz_transacciones(b["transacciones"])
    dif = b["dificultad"]
    minable = type(dif) is int and 0 <= dif <= 3
    b["nonce"] = 0
    while True:
        h = hash_bloque(b)
        if not minable or h.startswith("0" * dif):
            break
        b["nonce"] += 1
    b["hash"] = h
    b["firma_minero"] = claves[b["proponente"]].firmar(bytes.fromhex(h))
    return b


def bloque_valido(paquete, nodo):
    return bloque_externo(paquete, nodo.cadena[-1], [transferencia(paquete, "LAB-A", "LAB-C", 3, time.time() - 400)])


def test_bloque_con_timestamp_en_el_futuro(nodo_cadena):
    nodo, paquete = nodo_cadena
    b = rehacer(bloque_valido(paquete, nodo), paquete[2], timestamp=time.time() + 3600)
    estado_, motivo = nodo.recibir_bloque(b)
    assert estado_ == "rechazado" and "futuro" in motivo
    ok, motivo = nodo.recibir_cadena([nodo.genesis, b])
    assert not ok and "futuro" in motivo
    assert nodo.altura == 0


@pytest.mark.parametrize("dificultad", [0, 7, "3", True, 3.0, None, -1, 10**1000], ids=lambda d: repr(d)[:12])
def test_bloque_con_dificultad_invalida(nodo_cadena, dificultad):
    nodo, paquete = nodo_cadena
    b = rehacer(bloque_valido(paquete, nodo), paquete[2], dificultad=dificultad)
    estado_, motivo = nodo.recibir_bloque(b)
    assert estado_ == "rechazado" and "dificultad fuera de rango" in motivo, (estado_, motivo)
    ok, motivo = nodo.recibir_cadena([nodo.genesis, b])
    assert not ok and "dificultad fuera de rango" in motivo
    assert nodo.altura == 0 and nodo.resumen()["trabajo"] == 0


@pytest.mark.parametrize("recompensa", [10**6, 0, 11, -10, True, 10.0])
def test_bloque_con_recompensa_falsa(nodo_cadena, recompensa):
    nodo, paquete = nodo_cadena
    b = rehacer(bloque_valido(paquete, nodo), paquete[2], recompensa=recompensa)
    estado_, motivo = nodo.recibir_bloque(b)
    assert estado_ == "rechazado" and ("recompensa falsa" in motivo or "recompensa con tipo inválido" in motivo), motivo
    assert nodo.altura == 0


def sellos_malos(paquete):
    base = sello(paquete, HASH_DOC)

    def con(**c):
        s = copy.deepcopy(base)
        s.update(c)
        return s
    return {
        "umbral bool": (con(umbral=True), "umbral"), "umbral float": (con(umbral=2.0), "umbral"),
        "umbral cero": (con(umbral=0), "umbral"), "umbral enorme": (con(umbral=10**1000), "umbral"),
        "autores texto": (con(autores="LAB-A,LAB-B"), "autores"), "autores numeros": (con(autores=[1, 2]), "autores"),
        "autores vacio": (con(autores=[]), "autores"), "autores dict": (con(autores={"LAB-A": 1}), "autores"),
        "autores repetidos": (con(autores=["LAB-A", "LAB-A"]), "autores"),
        "autores sin ordenar": (con(autores=["LAB-C", "LAB-A", "LAB-B"]), "ordenado"),
        "firmas lista": (con(firmas=[]), "firmas"), "firmas texto": (con(firmas="x"), "firmas"),
        "firmas nulo": (con(firmas=None), "firmas"),
        "titulo 10000": (con(titulo="x" * 10_000), "título"), "titulo control": (con(titulo="a\x00b"), "control"),
        "titulo salto": (con(titulo="a\nb"), "control"), "titulo vacio": (con(titulo="  "), "título"),
        "titulo numero": (con(titulo=5), "título"),
        "investigador control": (con(investigador="x\x07y"), "control"),
        "doc_hash corto": (con(doc_hash="abc"), "doc_hash"), "doc_hash mayusculas": (con(doc_hash="A" * 64), "doc_hash"),
        "timestamp texto": (con(timestamp="ayer"), "timestamp"), "timestamp nan": (con(timestamp=float("nan")), "timestamp"),
        "campo extra": (con(extra=1), "exactamente"),
        "sin firma suficiente": (con(firmas={}), "sin firmas suficientes"),
        "firma de no autor": (con(laboratorio="LAB-A", autores=["LAB-A", "LAB-B"], umbral=1,
                                  firmas={"LAB-C": "00" * 64}), "no es autor"),
    }


def test_sellos_malformados_se_rechazan_con_motivo(nodo_cadena):
    nodo, paquete = nodo_cadena
    estado_ = Estado(nodo.genesis)
    casos = sellos_malos(paquete)
    assert len(casos) >= 25
    for nombre, (tx, fragmento) in casos.items():
        with pytest.raises(ErrorValidacion) as exc:
            revisar_sello(estado_, tx)
        assert fragmento in str(exc.value), (nombre, str(exc.value))
        with pytest.raises(ErrorEntrada) as exc2:
            nodo.agregar_transaccion(tx)
        assert "rechazada" in str(exc2.value), nombre
        b = bloque_externo(paquete, nodo.cadena[-1], [tx])
        r, motivo = nodo.recibir_bloque(b)
        assert r == "rechazado" and motivo, nombre
    assert nodo.altura == 0 and nodo.pendientes == []


@pytest.mark.parametrize("monto", [1.5, 2.0, True, -5, 0, "5", None, 10**10, float("nan"), float("inf")], ids=repr)
def test_transferencias_con_monto_invalido(nodo_cadena, monto):
    nodo, paquete = nodo_cadena
    tx = {"emisor": "LAB-A", "receptor": "LAB-B", "monto": monto, "timestamp": time.time(), "firma": "00" * 64}
    with pytest.raises(ErrorEntrada) as exc:
        nodo.agregar_transaccion(tx)
    assert "monto inválido" in str(exc.value)
    r, motivo = nodo.recibir_bloque(bloque_externo(paquete, nodo.cadena[-1], [tx]))
    assert r == "rechazado" and "monto inválido" in motivo


@pytest.mark.parametrize("monto", [1.5, True, -5, 0, "abc", 10**10, None, [], {}, 1e300], ids=repr)
def test_api_transferencias_con_monto_invalido(desbloqueado, monto):
    r = desbloqueado.post("/api/sellalo/transferencias", json={"receptor": "LAB-B", "monto": monto})
    assert r.status_code == 400 and "monto" in r.get_json()["error"].lower()


@pytest.mark.parametrize("campos", [{"titulo": "x" * 10_000}, {"titulo": "a\x00b"}, {"titulo": "a\x1b[31m"},
                                    {"umbral": True}, {"umbral": "dos"}, {"umbral": 0}, {"umbral": 9},
                                    {"autores": 5}, {"autores": {"a": 1}}, {"autores": [1, 2]},
                                    {"autores": ["LAB-A", "LAB-A"]}, {"autores": ["LAB-A", "LAB-ZZ"]},
                                    {"autores": ["LAB-B"]}, {"investigador": "x" * 500},
                                    {"doc_hash": "no-es-hash"}, {"doc_hash": 5}])
def test_api_sellos_con_datos_invalidos(desbloqueado, campos):
    cuerpo = {"doc_hash": HASH_DOC, "titulo": "Titulo", "investigador": "Inv", "autores": ["LAB-A"], "umbral": 1}
    cuerpo.update(campos)
    r = desbloqueado.post("/api/sellalo/sellos", json=cuerpo)
    assert r.status_code == 400 and r.get_json()["error"], (campos, r.data)


# ================================================================ 5. archivos corruptos en disco
def nodo_con_cadena_en_disco(paquete, carpeta):
    nodo = nuevo_nodo(carpeta, paquete, "LAB-A", desbloquear=False)
    cadena = rama(paquete, [[transferencia(paquete, "LAB-A", "LAB-C", 3, time.time() - 400)],
                            [transferencia(paquete, "LAB-B", "LAB-C", 2, time.time() - 300)]])
    ok, motivo = nodo.recibir_cadena(cadena)
    assert ok, motivo
    return nodo


def eventos(app):
    return list(app.config["CONTEXTO_NODO"].nodo.bitacora)


def _editar(campo):
    def f(ruta):
        with open(ruta, encoding="utf-8") as h:
            cadena = json.load(h)
        campo(cadena)
        with open(ruta, "w", encoding="utf-8") as h:
            json.dump(cadena, h)
    return f


def _truncar(ruta):
    datos = open(ruta, "rb").read()
    open(ruta, "wb").write(datos[: len(datos) // 2])


def _escribir(contenido):
    def f(ruta):
        with open(ruta, "wb") as h:
            h.write(contenido)
    return f


MALAS_CADENAS = {
    "truncada": _truncar,
    "json valido alterado": _editar(lambda c: c[1]["transacciones"][0].update(monto=99)),
    "recompensa cambiada": _editar(lambda c: c[2].update(recompensa=9999)),
    "bloque duplicado": _editar(lambda c: c.append(c[-1])),
    "vacia": _escribir(b""), "basura binaria": _escribir(b"\x00\xff\xfe\x80 basura"), "lista vacia": _escribir(b"[]"),
    "objeto": _escribir(b"{}"), "texto": _escribir(b'"x"'), "nulo": _escribir(b"null"),
    "elementos no dict": _escribir(b"[1,2,3]"),
    "genesis ajeno": _escribir(b'[{"hash": "' + b"0" * 64 + b'"}]'), "anidada": _escribir(b"[" * 200_000),
    "nan": _escribir(b"[NaN, Infinity]"),
}


@pytest.mark.parametrize("nombre", sorted(MALAS_CADENAS), ids=str)
def test_cadena_json_corrupta_no_tumba_el_nodo(labs, tmp_path, nombre):
    nodo_con_cadena_en_disco((labs[0], labs[1], labs[2]), tmp_path / "datos")
    MALAS_CADENAS[nombre](str(tmp_path / "datos" / "cadena.json"))
    app = crear_app(labs, tmp_path / "datos")
    r = app.test_client().get("/api/sellalo/estado")
    assert r.status_code == 200 and r.get_json()["nodo"]["altura"] == 0
    assert any(e["tipo"] == "corrupto" for e in eventos(app)), eventos(app)
    assert [f for f in os.listdir(tmp_path / "datos") if f.startswith("cadena.json.corrupto")]


@pytest.mark.parametrize("contenido", [b"\x00\xff garbage", b'{"a": 1}', b'[1, 2, {"tipo": "sello"}]', b"[" * 200_000,
                                       b"", b'[{"emisor": "LAB-A"}]', b'"texto"', b"[NaN]"],
                         ids=["basura", "objeto", "sello-incompleto", "anidado", "vacio", "tx-incompleta", "texto", "nan"])
def test_pendientes_corruptos_no_tumban_el_nodo(labs, tmp_path, contenido):
    nodo_con_cadena_en_disco((labs[0], labs[1], labs[2]), tmp_path / "datos")
    (tmp_path / "datos" / "pendientes.json").write_bytes(contenido)
    app = crear_app(labs, tmp_path / "datos")
    r = app.test_client().get("/api/sellalo/estado").get_json()
    assert r["nodo"]["altura"] == 2 and r["nodo"]["pendientes"] == []          # la cadena buena se conserva
    assert any(e["tipo"] in ("pendientes", "rechazo") for e in eventos(app)), eventos(app)


@pytest.mark.parametrize("contenido", [
    b"\x00\xff garbage", b"[]", b'"x"', b"null", b"[" * 200_000, b"",
    b'{"a": 1, "b": [], "c": {"sello": 5, "creado": "x"}}',
    b'{"' + b"a" * 64 + b'": {"sello": {"tipo": "sello"}, "creado": 1}}',
    b'{"' + b"a" * 64 + b'": {"sello": {}, "creado": 1e999}}',
    b'{"' + b"a" * 64 + b'": {"sello": {}, "creado": ' + b"9" * 400 + b"}}",
    b'{"' + b"a" * 64 + b'": 5}',
], ids=["basura", "lista", "texto", "nulo", "anidado", "vacio", "entradas-mal", "sello-incompleto", "creado-inf",
        "creado-gigante", "entrada-no-dict"])
def test_sellos_en_firma_corruptos_no_tumban_el_nodo(labs, tmp_path, contenido):
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "sellos_en_firma.json").write_bytes(contenido)
    app = crear_app(labs, tmp_path / "datos")
    r = app.test_client().get("/api/sellalo/estado")
    assert r.status_code == 200 and r.get_json()["sellos_en_firma"] == []


def test_sellos_en_firma_ilegible_deja_evento(labs, tmp_path):
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "sellos_en_firma.json").write_bytes(b"\x00 basura {")
    app = crear_app(labs, tmp_path / "datos")
    assert any(e["tipo"] == "sellos" and "sellos_en_firma" in e["texto"] for e in eventos(app))


def test_nodo_con_cadena_valida_en_disco_la_recarga(labs, tmp_path):
    paquete = (labs[0], labs[1], labs[2])
    original = nodo_con_cadena_en_disco(paquete, tmp_path / "datos")
    nuevo = nuevo_nodo(tmp_path / "datos", paquete, "LAB-A", desbloquear=False)
    assert nuevo.altura == 2 and nuevo.punta == original.punta
    assert not [e for e in nuevo.bitacora if e["tipo"] == "corrupto"]


# ================================================================ 6. certificados hostiles
@pytest.fixture(scope="module")
def certificado(labs, tmp_path_factory):
    paquete = (labs[0], labs[1], labs[2])
    nodo = nuevo_nodo(tmp_path_factory.mktemp("cert"), paquete, "LAB-A", desbloquear=False)
    ok, motivo = nodo.recibir_cadena(rama(paquete, [[sello(paquete, HASH_DOC)]], proponente="LAB-B"))
    assert ok, motivo
    return generar_certificado(nodo.cadena, HASH_DOC)


def subir_certificado(c, cert, documento=DOC):
    cuerpo = {"certificado": (io.BytesIO(json.dumps(cert).encode()), "c.json")}
    if documento is not None:
        cuerpo["documento"] = (io.BytesIO(documento), "d.pdf")
    return c.post("/api/sellalo/certificado/verificar", data=cuerpo, content_type="multipart/form-data")


def test_certificado_de_otra_red_se_reconoce(labs, labs_otra_red, certificado, tmp_path):
    app = crear_app(labs_otra_red, tmp_path / "otra")
    app2 = crear_app(labs, tmp_path / "propia")
    try:
        r = subir_certificado(app.test_client(), certificado).get_json()
        # AUD-005: un certificado de otra red NO es válido para este nodo (antes se daba por válido "por sí mismo")
        assert r["ok"] and r["valido"] is False and r["misma_red"] is False and "génesis" in r["motivo"]
        propio = subir_certificado(app2.test_client(), certificado).get_json()
        assert propio["misma_red"] is True and propio["valido"] is True
    finally:
        cerrar_app(app)
        cerrar_app(app2)
    res = verificar(certificado, DOC, genesis_esperado=labs_otra_red[0]["hash"])
    assert not res["valido"] and "red distinta" in res["motivo"]
    assert verificar(certificado, DOC, genesis_esperado=labs[0]["hash"])["valido"]


@pytest.mark.parametrize("pasos", [100, 65, 10_000])
def test_camino_merkle_demasiado_largo_se_rechaza(certificado, pasos):
    cert = copy.deepcopy(certificado)
    cert["prueba_merkle"]["camino"] = [{"lado": "izq", "hash": "0" * 64}] * pasos
    t0 = time.monotonic()
    r = verificar(cert, DOC)
    assert not r["valido"] and "Merkle" in r["motivo"]
    assert time.monotonic() - t0 < 2


def test_certificado_con_10000_encabezados_basura_se_rechaza_rapido(certificado):
    cert = copy.deepcopy(certificado)
    cert["encabezados"] = cert["encabezados"] * 10_000
    t0 = time.monotonic()
    r = verificar(cert, DOC)
    assert not r["valido"] and r["motivo"]
    assert time.monotonic() - t0 < 5


def cadena_larga_de_encabezados(certificado, claves, n):
    """Extiende los encabezados del certificado hasta `n` con bloques de verdad (dificultad 1, firmados por LAB-B)."""
    encabezados = copy.deepcopy(certificado["encabezados"])
    raiz_vacia = merkle.raiz_transacciones([])
    while len(encabezados) < n:
        previo = encabezados[-1]
        h = {"numero": previo["numero"] + 1, "timestamp": previo["timestamp"] + 1, "hash_anterior": previo["hash"],
             "raiz_merkle": raiz_vacia, "nonce": 0, "dificultad": 1, "proponente": "LAB-B", "recompensa": 10}
        while not hash_bloque(h).startswith("0"):
            h["nonce"] += 1
        h["hash"] = hash_bloque(h)
        h["firma_minero"] = claves["LAB-B"].firmar(bytes.fromhex(h["hash"]))
        encabezados.append(h)
    return encabezados


def test_certificado_con_10000_encabezados_validos_no_se_cuelga(labs, certificado):
    cert = copy.deepcopy(certificado)
    cert["encabezados"] = cadena_larga_de_encabezados(certificado, labs[2], 10_000)
    t0 = time.monotonic()
    r = verificar(cert, DOC, certificado["genesis"]["hash"])
    assert r["valido"] and r["detalle"]["confirmaciones"] == 9_999
    assert time.monotonic() - t0 < 30
    cert["encabezados"][-1]["firma_minero"] = "0" * 128           # un solo encabezado falso al final
    t0 = time.monotonic()
    r = verificar(cert, DOC)
    assert not r["valido"] and "firma del minero" in r["motivo"]
    assert time.monotonic() - t0 < 30


@pytest.mark.parametrize("dificultad", [0, 10**8, 7, 99], ids=repr)
def test_encabezado_con_dificultad_trivial_o_absurda_se_rechaza(labs, certificado, dificultad):
    """Un proponente con clave válida no puede «minar» a dificultad 0 ni forzar una cadena de ceros gigantesca."""
    cert = copy.deepcopy(certificado)
    h = cert["encabezados"][0]
    h["dificultad"] = dificultad
    h["hash"] = hash_bloque(h)
    h["firma_minero"] = labs[2][h["proponente"]].firmar(bytes.fromhex(h["hash"]))
    t0 = time.monotonic()
    r = verificar(cert, DOC)
    assert not r["valido"] and "prueba de trabajo" in r["motivo"], r
    assert time.monotonic() - t0 < 2


def test_certificados_con_basura_estructural(certificado):
    casos = []
    for campo in ("sello", "prueba_merkle", "genesis", "encabezados", "numero_bloque", "doc_hash", "version", "formato"):
        for basura in (None, 5, "x", [], {}, True, 10**1000, [[]], {"a": {"b": {}}}):
            cert = copy.deepcopy(certificado)
            cert[campo] = basura
            casos.append(cert)
    profundo = []
    for _ in range(900):
        profundo = [profundo]
    cert = copy.deepcopy(certificado)
    cert["sello"]["titulo"] = profundo
    casos.append(cert)
    for cert in casos:
        r = verificar(cert, DOC)
        assert r["valido"] is False and r["motivo"]
    for basura in (None, [], "x", 5, [[]]):
        assert verificar(basura, DOC)["valido"] is False


def test_api_verificar_con_certificado_hostil(labs, tmp_path, certificado):
    app = crear_app(labs, tmp_path / "datos")
    try:
        c = app.test_client()
        enorme = copy.deepcopy(certificado)
        enorme["encabezados"] = enorme["encabezados"] * 10_000
        r = subir_certificado(c, enorme)
        assert r.status_code == 200 and r.get_json()["valido"] is False
        raro = copy.deepcopy(certificado)
        raro["encabezados"][0]["timestamp"] = 1e300
        r = subir_certificado(c, raro)
        assert r.status_code == 200 and r.get_json()["valido"] is False
        for crudo in (b"no es json", b"[]", b"5", b"\xff\xfe", b"[" * 100_000):
            r = c.post("/api/sellalo/certificado/verificar", data={"certificado": (io.BytesIO(crudo), "c.json")},
                       content_type="multipart/form-data")
            assert r.status_code == 400, crudo
    finally:
        cerrar_app(app)


# ================================================================ 7. cuerpos JSON hostiles en la API y archivos de sellos
@pytest.mark.parametrize("ruta", ["/api/sellalo/desbloquear", "/api/sellalo/sellos", "/api/sellalo/minar",
                                  "/api/sellalo/transferencias", "/api/sellalo/pares", "/api/sellalo/ataques",
                                  "/api/sellalo/prioridad"])
def test_json_anidado_en_exceso_en_la_api_da_400_no_500(desbloqueado, ruta):
    r = desbloqueado.post(ruta, data=b"[" * 200_000, content_type="application/json")
    assert r.status_code == 400, (ruta, r.status_code, r.data[:100])
    r = desbloqueado.post(ruta, data=b'{"a":' * 3000 + b"1" + b"}" * 3000, content_type="application/json")
    assert r.status_code in (400, 409), (ruta, r.status_code, r.data[:100])


def test_creado_gigante_en_sellos_en_firma_no_tumba_el_arranque(labs, tmp_path):
    """Un sello real en firma cuyo `creado` es un entero que no cabe en float (float() lanza OverflowError)."""
    app = crear_app(labs, tmp_path / "datos")
    c = app.test_client()
    try:
        assert c.post("/api/sellalo/desbloquear", json={"contrasena": CONTRASENA}).status_code == 200
        r = c.post("/api/sellalo/sellos", json={"doc_hash": HASH_DOC, "titulo": "t", "investigador": "i",
                                                "autores": ["LAB-A", "LAB-B"], "umbral": 2})
        assert r.status_code == 200 and r.get_json()["sello"]["estado"] == "en_firma"
    finally:
        cerrar_app(app)
    ruta = tmp_path / "datos" / "sellos_en_firma.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert len(datos) == 1
    for entrada in datos.values():
        entrada["creado"] = 10**400
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    app2 = crear_app(labs, tmp_path / "datos")
    assert app2.test_client().get("/api/sellalo/estado").status_code == 200
