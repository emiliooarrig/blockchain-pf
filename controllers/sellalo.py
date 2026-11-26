"""Rutas de la red Sellalo (modo nodo). Prefijo /api/sellalo. Contrato C7.

Sólo reciben la petición, validan las entradas y llaman al núcleo (models/). El contenido de los documentos nunca se
guarda ni se transmite: se calcula su SHA-256 por bloques y se descarta.
"""
import copy
import hashlib
import ipaddress
import json
import re
import socket
import threading
import time

from flask import Blueprint, Response, current_app, jsonify, render_template, request

from controllers.entradas import booleano, datos, entero
from models import ataques_sellalo
from models.bloque import MONTO_MAX, nueva_transaccion
from models.certificado import generar_certificado, resumen_certificado
from models.coordinador_sellos import CoordinadorSellos
from models.cripto import es_hex
from models.errores import ErrorEntrada, ErrorEstado
from models.keystore import CONTRASENA_MAX
from models.nodo_completo import NodoCompleto, conectar_nodo_y_servidor
from models.pow import DIF_MAX, DIF_MIN
from models.red_p2p import ServidorP2P
from verificar_certificado import verificar

sellalo = Blueprint("sellalo", __name__, url_prefix="/api/sellalo")
paginas_nodo = Blueprint("paginas_nodo", __name__)

MENSAJE_SIMULADOR = "Este proceso no es un nodo Sellalo; arráncalo con --modo nodo."
TITULO_MAX, INVESTIGADOR_MAX = 120, 80
BLOQUE_LECTURA = 1 << 20
MAX_CERTIFICADO = 16 * 1024 * 1024        # certificado subido a verificar (≈ 23 000 bloques de encabezados)
MAX_ENCABEZADOS = 100_000
MAX_CUERPO_SIN_SUBIDA = 1024 * 1024       # rutas que no reciben documentos ni certificados
RUTAS_CON_SUBIDA = ("/api/sellalo/sellos", "/api/sellalo/prioridad", "/api/sellalo/certificado/verificar")
RE_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


class ContextoNodo:
    """Une el nodo, el coordinador de sellos y el servidor P2P (que se crea cada vez que el nodo se desbloquea)."""

    def __init__(self, nodo: NodoCompleto, coordinador: CoordinadorSellos, host_p2p: str = "0.0.0.0",
                 puerto_p2p: int = 6000, pares: list | None = None, opciones_p2p: dict | None = None):
        self.nodo = nodo
        self.coordinador = coordinador
        self.host_p2p = host_p2p
        self.puerto_p2p = puerto_p2p
        self.pares = list(pares or [])           # [(ip, puerto)]
        self.opciones_p2p = dict(opciones_p2p or {})
        self.servidor: ServidorP2P | None = None
        self._callback = None
        self.lock = threading.RLock()

    def desbloquear(self, contrasena: str) -> None:
        with self.lock:
            self.nodo.desbloquear(contrasena)        # ErrorClave (400) o ErrorEstado (409)
            try:
                servidor = ServidorP2P(self.nodo, host=self.host_p2p, puerto=self.puerto_p2p, **self.opciones_p2p)
                servidor.iniciar()
            except OSError as exc:
                self.nodo.bloquear()
                raise ErrorEstado(f"No se pudo abrir el puerto P2P {self.puerto_p2p}: {exc.strerror or exc}.") from None
            except Exception:
                self.nodo.bloquear()
                raise
            if self._callback in self.nodo.al_cambiar:
                self.nodo.al_cambiar.remove(self._callback)
            self._callback = conectar_nodo_y_servidor(self.nodo, servidor)
            self.coordinador.conectar(servidor)
            self.servidor = servidor
            pares = list(self.pares)
        for ip, puerto in pares:                     # los fallos de conexión van a la bitácora y no detienen nada
            threading.Thread(target=self._conectar_inicial, args=(servidor, ip, puerto), daemon=True,
                             name=f"conexion-{ip}:{puerto}").start()

    def _conectar_inicial(self, servidor, ip, puerto) -> None:
        try:
            servidor.conectar(ip, puerto)
        except Exception as exc:
            self.nodo.evento("p2p", f"No se pudo conectar con {ip}:{puerto}: {exc}")

    def bloquear(self) -> None:
        with self.lock:
            self.nodo.bloquear()                     # detiene el minado y, por el callback, el servidor P2P
            if self.servidor is not None:
                self.servidor.detener()
            self.coordinador.desconectar()
            self.servidor = None

    def activo(self) -> ServidorP2P | None:
        s = self.servidor
        return s if s is not None and s.activo else None


def _ctx() -> ContextoNodo:
    return current_app.config["CONTEXTO_NODO"]


@sellalo.before_request
def _solo_nodo():
    if current_app.config.get("CONTEXTO_NODO") is None:
        raise ErrorEstado(MENSAJE_SIMULADOR)


@sellalo.before_request
def _limite_de_cuerpo():
    """AUD-034: sólo las rutas que suben documentos/certificados aceptan cuerpos grandes."""
    if request.path not in RUTAS_CON_SUBIDA:
        request.max_content_length = MAX_CUERPO_SIN_SUBIDA


def _ok(mensaje: str | None = None, **extra):
    cuerpo = {"ok": True}
    if mensaje:
        cuerpo["mensaje"] = mensaje
    return jsonify(**cuerpo, **extra)


# ---------------------------------------------------------------- páginas (modo nodo)
@paginas_nodo.get("/")
def inicio_sellalo():
    return render_template("sellalo.html")


@paginas_nodo.get("/simulador")
def inicio_simulador():
    return render_template("index.html")


# ---------------------------------------------------------------- entradas
def _entrada() -> dict:
    """Campos de texto de la petición: JSON, formulario o multipart."""
    if request.mimetype == "multipart/form-data":
        return request.form.to_dict()
    return datos()


def _texto(d: dict, campo: str, nombre: str, maximo: int) -> str:
    valor = d.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorEntrada(f"{nombre} es obligatorio (texto).")
    valor = valor.strip()
    if len(valor) > maximo:
        raise ErrorEntrada(f"{nombre} no puede pasar de {maximo} caracteres (tiene {len(valor)}).")
    if not valor.isprintable():
        raise ErrorEntrada(f"{nombre} no puede tener caracteres de control.")
    return valor


def _hex64(valor, nombre: str = "doc_hash") -> str:
    if not isinstance(valor, str) or not es_hex(valor.strip().lower(), 64):
        raise ErrorEntrada(f"{nombre} debe ser un SHA-256 en hexadecimal (64 caracteres).")
    return valor.strip().lower()


def _hash_archivo(archivo) -> str:
    h = hashlib.sha256()
    total = 0
    while True:
        trozo = archivo.stream.read(BLOQUE_LECTURA)
        if not trozo:
            break
        total += len(trozo)
        h.update(trozo)
    if total == 0:
        raise ErrorEntrada("El archivo está vacío; no se puede sellar un documento sin contenido.")
    return h.hexdigest()


def _doc_hash(d: dict) -> str:
    """SHA-256 del campo multipart `archivo` o, si no viene, el `doc_hash` recibido."""
    archivo = request.files.get("archivo")
    if archivo is not None and archivo.filename:
        return _hash_archivo(archivo)
    if "doc_hash" in d and d["doc_hash"] not in (None, ""):
        return _hex64(d["doc_hash"])
    if archivo is not None:
        raise ErrorEntrada("No se seleccionó ningún archivo.")
    raise ErrorEntrada("Indica el documento: sube un archivo (campo «archivo») o envía su doc_hash SHA-256.")


def _lista_autores(valor) -> list[str]:
    if isinstance(valor, str):
        crudo = [x for x in valor.split(",")]
    elif isinstance(valor, list):
        crudo = valor
    else:
        raise ErrorEntrada("Los autores deben ser una lista de ids de laboratorio o texto separado por comas.")
    autores = []
    for a in crudo:
        if not isinstance(a, str):
            raise ErrorEntrada("Cada autor debe ser un id de laboratorio (texto).")
        if a.strip():
            autores.append(a.strip())
    if not autores:
        raise ErrorEntrada("Indica al menos un autor.")
    if len(autores) > 5:
        raise ErrorEntrada("Un sello admite como máximo 5 autores.")
    if len(set(autores)) != len(autores):
        raise ErrorEntrada("La lista de autores tiene ids repetidos.")
    return autores


def resolver_host(host: str) -> str:
    """IP literal o nombre de host -> dirección IP (los nombres se resuelven antes de conectar; AUD-032). Es el mismo
    validador para /pares y --pares. ErrorEntrada si no es una IP ni un nombre que resuelva."""
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    if not RE_HOST.match(host):
        raise ErrorEntrada(f"«{host[:40]}» no es una dirección IP ni un nombre de host válido.")
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        raise ErrorEntrada(f"No se pudo resolver el nombre de host «{host[:40]}».") from None
    return infos[0][4][0]


_CACHE_DIRECCIONES = {"t": 0.0, "valor": None}
_TTL_DIRECCIONES = 60.0


def _direcciones_locales() -> list[str]:
    """Direcciones de este equipo, en caché 60 s: la resolución de nombres puede tardar segundos (AUD-035)."""
    ahora = time.monotonic()
    if _CACHE_DIRECCIONES["valor"] is None or ahora - _CACHE_DIRECCIONES["t"] > _TTL_DIRECCIONES:
        _CACHE_DIRECCIONES.update(valor=_calcular_direcciones_locales(), t=ahora)
    return list(_CACHE_DIRECCIONES["valor"])


def _calcular_direcciones_locales() -> list[str]:
    ips = set()
    try:
        ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))        # UDP: no envía nada, sólo elige la interfaz de salida
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(i for i in ips if not i.startswith("127.")) or ["127.0.0.1"]


# ---------------------------------------------------------------- estado y claves
@sellalo.get("/estado")
def estado():
    ctx = _ctx()
    nodo = ctx.nodo
    servidor = ctx.activo()
    cuentas = nodo.genesis["cuentas"]
    return jsonify(
        ok=True, nodo=nodo.publico(), pares=servidor.pares_publico() if servidor else [],
        red={"nombre": nodo.genesis["parametros"].get("nombre", "Sellalo"), "hash_genesis": nodo.hash_genesis,
             "puerto_p2p": servidor.puerto if servidor else ctx.puerto_p2p, "direcciones": _direcciones_locales()},
        laboratorios=[{"id": nid, "clave_publica": c["clave_publica"]} for nid, c in cuentas.items()],
        sellos_en_firma=ctx.coordinador.en_firma(), solicitudes=ctx.coordinador.solicitudes(),
        ataques=ataques_sellalo.catalogo(),
        laboratorio_ataques=bool(current_app.config.get("LABORATORIO_ATAQUES")), umbral_max_autores=5,
        limites={"dificultad": [DIF_MIN, DIF_MAX], "titulo": TITULO_MAX, "investigador": INVESTIGADOR_MAX,
                 "monto_max": MONTO_MAX})


@sellalo.post("/desbloquear")
def desbloquear():
    d = datos()
    clave = d.get("contrasena")
    if not isinstance(clave, str) or not clave:
        raise ErrorEntrada("La contraseña es obligatoria.")
    if len(clave) > CONTRASENA_MAX:
        raise ErrorEntrada(f"La contraseña no puede pasar de {CONTRASENA_MAX} caracteres.")
    ctx = _ctx()
    ctx.desbloquear(clave)
    return _ok(f"Nodo {ctx.nodo.id} desbloqueado; P2P escuchando en el puerto {ctx.servidor.puerto}.")


@sellalo.post("/bloquear")
def bloquear():
    ctx = _ctx()
    ctx.bloquear()
    return _ok(f"Nodo {ctx.nodo.id} bloqueado: minado y conexiones P2P detenidos.")


# ---------------------------------------------------------------- pares
def _servidor_activo() -> ServidorP2P:
    servidor = _ctx().activo()
    if servidor is None:
        raise ErrorEstado("El nodo no está conectado a la red: desbloquéalo con su contraseña primero.")
    return servidor


@sellalo.post("/pares")
def conectar_par():
    d = datos()
    ip = d.get("ip")
    if not isinstance(ip, str) or not ip.strip():
        raise ErrorEntrada("La dirección IP del par es obligatoria.")
    ip = resolver_host(ip.strip())
    puerto = entero(d, "puerto", "El puerto del par", 1, 65535)
    servidor = _servidor_activo()
    par_id = servidor.conectar(ip, puerto)
    par = next((p for p in servidor.pares_publico() if p["id"] == par_id), {"id": par_id})
    return _ok(f"Conectado con {par_id}.", par=par)


@sellalo.post("/pares/<par_id>/desconectar")
def desconectar_par(par_id):
    servidor = _servidor_activo()
    if not servidor.desconectar(par_id[:60]):
        raise ErrorEstado(f"No hay ningún par conectado con el id «{par_id[:30]}».")
    return _ok(f"Desconectado de {par_id[:30]}.")


# ---------------------------------------------------------------- sellos
@sellalo.post("/sellos")
def crear_sello():
    d = _entrada()
    ctx = _ctx()
    doc_hash = _doc_hash(d)
    titulo = _texto(d, "titulo", "El título", TITULO_MAX)
    investigador = _texto(d, "investigador", "El investigador", INVESTIGADOR_MAX)
    autores = request.form.getlist("autores") if request.mimetype == "multipart/form-data" else d.get("autores")
    if isinstance(autores, list) and request.mimetype == "multipart/form-data":
        autores = ",".join(autores)
    autores = _lista_autores(autores)
    for a in autores:
        if a not in ctx.nodo.genesis["cuentas"]:
            raise ErrorEntrada(f"El laboratorio «{a[:20]}» no existe en esta red.")
    if ctx.nodo.id not in autores:
        raise ErrorEntrada(f"Los autores deben incluir al propio laboratorio ({ctx.nodo.id}).")
    umbral = entero(d, "umbral", "El umbral", 1, len(autores))
    sello = ctx.coordinador.proponer(doc_hash, titulo, investigador, autores, umbral)
    if sello["estado"] == "pendiente":
        mensaje = "Sello firmado y enviado a pendientes: falta minarlo en un bloque."
    else:
        mensaje = f"Sello propuesto: esperando firmas (1/{umbral}). Se avisó a los co-autores."
    return _ok(mensaje, sello=sello)


@sellalo.post("/sellos/<id_sello>/firmar")
def firmar_sello(id_sello):
    sello = _ctx().coordinador.firmar(id_sello)
    if sello["estado"] == "pendiente":
        mensaje = "Firma agregada: el sello alcanzó el umbral y pasó a pendientes."
    else:
        mensaje = f"Firma agregada ({len(sello['firmas'])}/{sello['umbral']})."
    return _ok(mensaje, sello=sello)


# ---------------------------------------------------------------- minado y transferencias
@sellalo.post("/minar")
def minar():
    d = datos()
    # Opcional: si la red fija la dificultad en el génesis, el nodo la ignora (G1); si no viene, se pasa None.
    dificultad = entero(d, "dificultad", "La dificultad", DIF_MIN, DIF_MAX) if d.get("dificultad") not in (None, "") else None
    continuo = booleano(d, "continuo", "El minado continuo", defecto=False)
    return _ok(_ctx().nodo.iniciar_minado(dificultad, continuo))


@sellalo.post("/minar/detener")
def detener_minado():
    _ctx().nodo.detener_minado()
    return _ok("Minado detenido.")


@sellalo.post("/transferencias")
def transferir():
    d = datos()
    nodo = _ctx().nodo
    receptor = d.get("receptor")
    if not isinstance(receptor, str) or receptor not in nodo.genesis["cuentas"]:
        raise ErrorEntrada(f"El receptor «{str(receptor)[:20]}» no es un laboratorio de esta red.")
    if receptor == nodo.id:
        raise ErrorEntrada("No puedes enviarte créditos a ti mismo.")
    monto = entero(d, "monto", "El monto", 1, MONTO_MAX)
    if not nodo.desbloqueado:
        raise ErrorEstado("El nodo está bloqueado: desbloquéalo con su contraseña para firmar la transferencia.")

    class _Firmador:
        firmar = staticmethod(nodo.firmar)

    tx = nueva_transaccion(nodo.id, receptor, monto, time.time(), _Firmador)
    tid = nodo.agregar_transaccion(tx)
    return _ok(f"Transferencia de {monto} a {receptor} en pendientes.", id=tid)


# ---------------------------------------------------------------- prioridad y certificados
@sellalo.get("/bloques/<int:numero>")
def bloque(numero: int):
    """Bloque completo de la copia local (con sus transacciones) para desplegarlo en la interfaz."""
    nodo = _ctx().nodo
    with nodo.lock:
        if not 0 <= numero < len(nodo.cadena):
            raise ErrorEntrada(f"El bloque #{numero} no existe (la altura es {len(nodo.cadena) - 1}).")
        datos = copy.deepcopy(nodo.cadena[numero])
    return _ok(bloque=datos, confirmaciones=max(0, nodo.altura - numero))


@sellalo.post("/prioridad")
def prioridad():
    d = _entrada()
    doc_hash = _doc_hash(d)
    sellos = _ctx().nodo.prioridad(doc_hash)
    mensaje = (f"El documento tiene {len(sellos)} sello(s); la prioridad es del más antiguo (bloque "
               f"#{sellos[0]['numero']})." if sellos else "El documento no está sellado en esta cadena.")
    return _ok(mensaje, doc_hash=doc_hash, sellos=sellos)


@sellalo.get("/certificado/<doc_hash>")
def certificado(doc_hash):
    doc_hash = _hex64(doc_hash)
    nodo = _ctx().nodo
    with nodo.lock:
        cert = generar_certificado(nodo.cadena, doc_hash)
    cuerpo = json.dumps(cert, indent=2, ensure_ascii=False)
    return Response(cuerpo, mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="certificado-{doc_hash[:8]}.json"'})


def _leer_subida(nombre: str, obligatorio: bool, etiqueta: str) -> bytes | None:
    archivo = request.files.get(nombre)
    if archivo is None or not archivo.filename:
        if obligatorio:
            raise ErrorEntrada(f"Falta {etiqueta} (campo multipart «{nombre}»).")
        return None
    maximo = MAX_CERTIFICADO if nombre == "certificado" else None
    contenido = archivo.stream.read(maximo + 1) if maximo else archivo.stream.read()
    if maximo and len(contenido) > maximo:
        raise ErrorEntrada(f"El certificado es demasiado grande (máximo {maximo // (1024 * 1024)} MiB).")
    if not contenido:
        raise ErrorEntrada(f"{etiqueta[0].upper() + etiqueta[1:]} está vacío.")
    return contenido


@sellalo.post("/certificado/verificar")
def verificar_certificado_ruta():
    crudo = _leer_subida("certificado", True, "el archivo del certificado")
    documento = _leer_subida("documento", False, "el documento")
    try:
        cert = json.loads(crudo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ErrorEntrada("El certificado no es un JSON válido.") from None
    if not isinstance(cert, dict):
        raise ErrorEntrada("El certificado debe ser un objeto JSON.")
    encabezados = cert.get("encabezados")
    if isinstance(encabezados, list) and len(encabezados) > MAX_ENCABEZADOS:
        raise ErrorEntrada(f"El certificado tiene demasiados encabezados (máximo {MAX_ENCABEZADOS:,}).")
    resultado = verificar(cert, documento)
    try:
        resumen = resumen_certificado(cert)
    except Exception:
        resumen = None
    genesis = cert.get("genesis")
    misma_red = isinstance(genesis, dict) and genesis.get("hash") == _ctx().nodo.hash_genesis
    mensaje = resultado["motivo"] if resultado["valido"] else f"Certificado NO válido: {resultado['motivo']}."
    return _ok(mensaje, valido=resultado["valido"], motivo=resultado["motivo"], detalle=resultado.get("detalle"),
               resumen=resumen, misma_red=misma_red)


# ---------------------------------------------------------------- ataques
@sellalo.post("/ataques")
def ataque():
    if not current_app.config.get("LABORATORIO_ATAQUES"):
        raise ErrorEstado("El laboratorio de ataques está desactivado: arranca el nodo con --laboratorio-ataques "
                          "(sólo para demostraciones; firma con la clave real del nodo).")
    d = datos()
    tipo = d.get("tipo")
    if not isinstance(tipo, str) or tipo not in ataques_sellalo.TIPOS:
        raise ErrorEntrada(f"El tipo de ataque debe ser uno de: {', '.join(ataques_sellalo.TIPOS)}.")
    destino = d.get("destino", "local")
    if destino not in ataques_sellalo.DESTINOS:
        raise ErrorEntrada("El destino debe ser «local» o «red».")
    ctx = _ctx()
    resultado = ataques_sellalo.ejecutar(ctx.nodo, ctx.activo(), tipo, destino)
    return jsonify(ok=True, **resultado)
