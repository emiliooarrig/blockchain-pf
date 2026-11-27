"""Criptografía del simulador: SHA-256, serialización canónica y firmas Ed25519."""
import hashlib
import json
from functools import lru_cache

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

LARGO_CLAVE_HEX = 64    # 32 bytes
LARGO_FIRMA_HEX = 128   # 64 bytes


def sha256_hex(datos) -> str:
    if isinstance(datos, str):
        datos = datos.encode("utf-8")
    return hashlib.sha256(datos).hexdigest()


def canonico(obj) -> bytes:
    """JSON con orden fijo de llaves y sin espacios: misma entrada, mismos bytes en todos los nodos."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def es_hex(valor, largo: int) -> bool:
    return isinstance(valor, str) and len(valor) == largo and all(c in "0123456789abcdef" for c in valor)


class ParClaves:
    """Par de claves Ed25519. La clave privada nunca se muestra, ni en repr ni en serializaciones."""

    __slots__ = ("_privada", "publica")

    def __init__(self, privada: Ed25519PrivateKey):
        if not isinstance(privada, Ed25519PrivateKey):
            raise TypeError("ParClaves necesita una Ed25519PrivateKey")
        self._privada = privada
        self.publica = privada.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    @classmethod
    def generar(cls) -> "ParClaves":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def desde_bytes(cls, privada: bytes) -> "ParClaves":
        return cls(Ed25519PrivateKey.from_private_bytes(privada))

    def bytes_privados(self) -> bytes:
        """Los 32 bytes crudos de la clave privada; sólo para cifrarlos en el almacén de claves."""
        return self._privada.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())

    def firmar(self, datos: bytes) -> str:
        return self._privada.sign(datos).hex()

    def __repr__(self) -> str:
        return f"ParClaves(publica={self.publica[:16]}…)"


@lru_cache(maxsize=262_144)
def _verificar(publica: str, datos: bytes, firma: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(publica)).verify(bytes.fromhex(firma), datos)
        return True
    except (InvalidSignature, ValueError):
        return False


def verificar(publica_hex, datos: bytes, firma_hex) -> bool:
    """Verifica una firma. Es una función pura, así que se memoriza: cada nodo la invoca sobre la
    cadena completa que recibe, pero la misma firma no se recalcula dos veces."""
    if not (es_hex(publica_hex, LARGO_CLAVE_HEX) and es_hex(firma_hex, LARGO_FIRMA_HEX) and isinstance(datos, bytes)):
        return False
    return _verificar(publica_hex, datos, firma_hex)
