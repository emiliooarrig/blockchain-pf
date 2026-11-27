"""Almacén de claves cifrado: la clave privada Ed25519 nunca se guarda en claro.

Formato (JSON): la contraseña se convierte en una clave de 256 bits con scrypt (costosa a propósito, para frenar
ataques de fuerza bruta) y con ella se cifra la clave privada con AES-256-GCM. Los datos asociados (AAD) ligan el
cifrado al id y a la clave pública: cambiar cualquiera de los dos hace fallar el descifrado.
"""
import json
import os
import re
import secrets
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from models.cripto import ParClaves, es_hex
from models.errores import ErrorEntrada

FORMATO = "sellalo-clave"
VERSION = 1
CONTRASENA_MIN = 10
CONTRASENA_MAX = 256
ID_VALIDO = re.compile(r"^[A-Z0-9-]{2,16}$")
SCRYPT_N, SCRYPT_R, SCRYPT_P, LARGO_CLAVE = 2**15, 8, 1, 32
SCRYPT_N_SIMULADOR = 2**14
N_MAX_ACEPTADO = 2**20          # un archivo alterado no puede pedir una cantidad absurda de memoria
LARGO_SAL, LARGO_NONCE = 16, 12
LARGO_CIFRADO = 32 + 16         # clave privada + etiqueta de autenticación GCM

MENSAJE_ABRIR = ("No se pudo abrir el almacén de claves: la contraseña es incorrecta o el archivo fue alterado.")


class ErrorClave(ErrorEntrada):
    """Problema con el almacén de claves o con la contraseña."""


def _validar_contrasena(contrasena) -> str:
    if not isinstance(contrasena, str):
        raise ErrorClave("La contraseña debe ser texto.")
    if len(contrasena) < CONTRASENA_MIN:
        raise ErrorClave(f"La contraseña debe tener al menos {CONTRASENA_MIN} caracteres.")
    if len(contrasena) > CONTRASENA_MAX:
        raise ErrorClave(f"La contraseña no puede pasar de {CONTRASENA_MAX} caracteres.")
    return contrasena


def _validar_id(nodo_id) -> str:
    if not isinstance(nodo_id, str) or not ID_VALIDO.fullmatch(nodo_id):
        raise ErrorClave("El id del nodo debe tener de 2 a 16 caracteres: letras mayúsculas, números y guiones.")
    return nodo_id


def _kdf(contrasena: str, sal: bytes, n: int, r: int = SCRYPT_R, p: int = SCRYPT_P, largo: int = LARGO_CLAVE) -> bytes:
    return Scrypt(salt=sal, length=largo, n=n, r=r, p=p).derive(contrasena.encode("utf-8"))


def _aad(nodo_id: str, publica: str) -> bytes:
    return f"sellalo-clave|{nodo_id}|{publica}".encode()


def _documento(par: ParClaves, nodo_id: str, contrasena: str) -> dict:
    sal, nonce = secrets.token_bytes(LARGO_SAL), secrets.token_bytes(LARGO_NONCE)
    clave = _kdf(contrasena, sal, SCRYPT_N)
    cifrado = AESGCM(clave).encrypt(nonce, par.bytes_privados(), _aad(nodo_id, par.publica))
    return {
        "formato": FORMATO, "version": VERSION, "id": nodo_id, "clave_publica": par.publica,
        "kdf": {"alg": "scrypt", "sal": sal.hex(), "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P, "largo": LARGO_CLAVE},
        "cifrado": {"alg": "AES-256-GCM", "nonce": nonce.hex(), "texto_cifrado": cifrado.hex()},
    }


def _escribir(ruta: str, documento: dict) -> None:
    """Escritura atómica: se escribe un temporal en la misma carpeta y se reemplaza el destino de una vez."""
    carpeta = os.path.dirname(os.path.abspath(ruta))
    os.makedirs(carpeta, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix=".clave-", suffix=".tmp", dir=carpeta)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(documento, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(temporal, 0o600)
        except OSError:
            pass
        os.replace(temporal, ruta)
    except BaseException:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise


def _leer(ruta: str) -> dict:
    """Lee y valida la estructura del archivo (sin contraseña)."""
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        raise ErrorClave(f"No existe el almacén de claves «{ruta}».") from None
    except (OSError, ValueError):
        raise ErrorClave(MENSAJE_ABRIR) from None
    if not isinstance(doc, dict) or doc.get("formato") != FORMATO:
        raise ErrorClave("El archivo no es un almacén de claves de Sellalo.")
    if doc.get("version") != VERSION:
        raise ErrorClave(f"Versión de almacén de claves desconocida ({str(doc.get('version'))[:20]}); "
                         f"esta aplicación entiende la versión {VERSION}.")
    kdf, cif = doc.get("kdf"), doc.get("cifrado")
    ok = (set(doc) == {"formato", "version", "id", "clave_publica", "kdf", "cifrado"}
          and isinstance(doc["id"], str) and ID_VALIDO.fullmatch(doc["id"]) and es_hex(doc["clave_publica"], 64)
          and isinstance(kdf, dict) and set(kdf) == {"alg", "sal", "n", "r", "p", "largo"} and kdf["alg"] == "scrypt"
          and es_hex(kdf["sal"], 2 * LARGO_SAL)
          and all(type(kdf[k]) is int for k in ("n", "r", "p", "largo"))
          and 2 <= kdf["n"] <= N_MAX_ACEPTADO and kdf["n"] & (kdf["n"] - 1) == 0
          and 1 <= kdf["r"] <= 16 and 1 <= kdf["p"] <= 4 and kdf["largo"] == LARGO_CLAVE
          and isinstance(cif, dict) and set(cif) == {"alg", "nonce", "texto_cifrado"} and cif["alg"] == "AES-256-GCM"
          and es_hex(cif["nonce"], 2 * LARGO_NONCE) and es_hex(cif["texto_cifrado"], 2 * LARGO_CIFRADO))
    if not ok:
        raise ErrorClave(MENSAJE_ABRIR)
    return doc


def crear_almacen(ruta: str, nodo_id: str, contrasena: str) -> str:
    """Genera una clave aleatoria, la cifra y la guarda en `ruta`. Devuelve la clave pública."""
    _validar_id(nodo_id)
    _validar_contrasena(contrasena)
    if os.path.exists(ruta):
        raise ErrorClave(f"Ya existe un almacén de claves en «{ruta}»; no se sobrescribe.")
    par = ParClaves.generar()
    _escribir(ruta, _documento(par, nodo_id, contrasena))
    return par.publica


def abrir_almacen(ruta: str, contrasena: str) -> ParClaves:
    par, _ = _abrir(ruta, contrasena)
    return par


def _abrir(ruta: str, contrasena) -> tuple[ParClaves, dict]:
    if not isinstance(contrasena, str):
        raise ErrorClave("La contraseña debe ser texto.")
    doc = _leer(ruta)
    kdf, cif = doc["kdf"], doc["cifrado"]
    try:
        clave = _kdf(contrasena, bytes.fromhex(kdf["sal"]), kdf["n"], kdf["r"], kdf["p"], kdf["largo"])
        crudo = AESGCM(clave).decrypt(bytes.fromhex(cif["nonce"]), bytes.fromhex(cif["texto_cifrado"]),
                                      _aad(doc["id"], doc["clave_publica"]))
        par = ParClaves.desde_bytes(crudo)
    except (InvalidTag, ValueError):
        raise ErrorClave(MENSAJE_ABRIR) from None
    if par.publica != doc["clave_publica"]:
        raise ErrorClave(MENSAJE_ABRIR)
    return par, doc


def leer_publica(ruta: str) -> tuple[str, str]:
    """(id, clave pública) del almacén, sin necesitar la contraseña."""
    doc = _leer(ruta)
    return doc["id"], doc["clave_publica"]


def cambiar_contrasena(ruta: str, actual: str, nueva: str) -> None:
    _validar_contrasena(nueva)
    par, doc = _abrir(ruta, actual)
    _escribir(ruta, _documento(par, doc["id"], nueva))


def derivar_claves(contrasena: str, sal: str) -> ParClaves:
    """Claves reproducibles para el simulador: scrypt(contraseña, sal) → semilla Ed25519."""
    _validar_contrasena(contrasena)
    return ParClaves.desde_bytes(_kdf(contrasena, sal.encode("utf-8"), SCRYPT_N_SIMULADOR))


def metadatos_publicos(ruta: str) -> dict:
    """Metadatos del almacén que pueden mostrarse sin contraseña (contrato C8 `/clave`): formato, algoritmos,
    parámetros de scrypt y LONGITUDES en bytes de sal, nonce y texto cifrado. Nunca devuelve la sal, el nonce ni el
    texto cifrado en sí. ErrorClave si el archivo no existe o no tiene el formato esperado."""
    doc = _leer(ruta)
    kdf, cif = doc["kdf"], doc["cifrado"]
    return {"formato": doc["formato"], "version": doc["version"], "id": doc["id"], "clave_publica": doc["clave_publica"],
            "kdf": {"alg": kdf["alg"], "n": kdf["n"], "r": kdf["r"], "p": kdf["p"], "largo": kdf["largo"],
                    "bytes_sal": len(kdf["sal"]) // 2, "memoria_kib": 128 * kdf["n"] * kdf["r"] // 1024},
            "cifrado": {"alg": cif["alg"], "bytes_nonce": len(cif["nonce"]) // 2,
                        "bytes_texto_cifrado": len(cif["texto_cifrado"]) // 2},
            "aad": _aad(doc["id"], doc["clave_publica"]).decode()}
