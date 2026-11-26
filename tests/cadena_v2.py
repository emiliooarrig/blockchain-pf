"""Helper de pruebas: construye a mano una cadena v2 (génesis + bloques PoW) siguiendo los contratos C1-C3.

No depende del núcleo (ni de `ParClaves`): usa `cryptography` directamente. Otros agentes pueden reusarlo.
"""
import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from models import merkle

T0 = 1767225600.0
EXCLUIDOS = ("hash", "transacciones", "firma_minero")
CAMPOS_SELLO = ("tipo", "doc_hash", "titulo", "investigador", "laboratorio", "autores", "umbral", "timestamp")


def sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def hash_bloque(b: dict) -> str:
    datos = {k: v for k, v in b.items() if k not in EXCLUIDOS}
    return hashlib.sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()


def mensaje_sello(tx: dict) -> bytes:
    return json.dumps({k: tx[k] for k in CAMPOS_SELLO}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


class Claves:
    def __init__(self):
        self.privada = Ed25519PrivateKey.generate()
        self.publica = self.privada.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    def firmar(self, datos: bytes) -> str:
        return self.privada.sign(datos).hex()


def transferencia(emisor: str, receptor: str, monto: int, timestamp: float) -> dict:
    return {"emisor": emisor, "receptor": receptor, "monto": monto, "timestamp": timestamp, "firma": "00" * 64}


def crear_sello(doc_hash, claves, autores_firmantes, titulo="Hallazgo de prueba", investigador="Dra. Ñandú",
                laboratorio="LAB-A", autores=("LAB-A", "LAB-B", "LAB-C"), umbral=2, timestamp=T0 + 5.0) -> dict:
    tx = {"tipo": "sello", "doc_hash": doc_hash, "titulo": titulo, "investigador": investigador,
          "laboratorio": laboratorio, "autores": list(autores), "umbral": umbral, "timestamp": timestamp,
          "firmas": {}}
    msg = mensaje_sello(tx)
    tx["firmas"] = {a: claves[a].firmar(msg) for a in autores_firmantes}
    return tx


def crear_genesis(claves: dict) -> dict:
    g = {"numero": 0, "timestamp": T0, "transacciones": [], "hash_anterior": "0" * 64,
         "raiz_merkle": merkle.raiz_transacciones([]), "nonce": 0, "proponente": "genesis", "recompensa": 0,
         "cuentas": {n: {"clave_publica": c.publica, "saldo": 100} for n, c in claves.items()},
         "parametros": {"consenso": "pow", "red": "sellalo", "nombre": "prueba"}}
    g["hash"] = hash_bloque(g)
    return g


def minar_bloque(anterior: dict, transacciones: list, claves: dict, proponente: str, dificultad: int = 1) -> dict:
    b = {"numero": anterior["numero"] + 1, "timestamp": anterior["timestamp"] + 10.0, "transacciones": transacciones,
         "hash_anterior": anterior["hash"], "raiz_merkle": merkle.raiz_transacciones(transacciones),
         "nonce": 0, "dificultad": dificultad, "proponente": proponente, "recompensa": 10}
    while True:
        h = hash_bloque(b)
        if h.startswith("0" * dificultad):
            break
        b["nonce"] += 1
    b["hash"] = h
    b["firma_minero"] = claves[proponente].firmar(bytes.fromhex(h))
    return b


DOC_A = b"contenido del articulo A"
DOC_B = b"contenido del articulo B"
DOC_NO_SELLADO = b"nunca sellado"


def construir_cadena(dificultad: int = 1):
    """Devuelve (cadena, claves). Bloque 1: transferencias; 2: sello 2-de-3 de DOC_A + transferencias (con índice > 0);
    3: sello de DOC_B y un segundo sello posterior de DOC_A; 4: transferencia."""
    claves = {n: Claves() for n in ("LAB-A", "LAB-B", "LAB-C")}
    g = crear_genesis(claves)
    ha, hb = sha(DOC_A), sha(DOC_B)
    b1 = minar_bloque(g, [transferencia("LAB-A", "LAB-B", 5, T0 + 1), transferencia("LAB-B", "LAB-C", 2, T0 + 2)],
                      claves, "LAB-A", dificultad)
    b2 = minar_bloque(b1, [transferencia("LAB-C", "LAB-A", 1, T0 + 3),
                           crear_sello(ha, claves, ["LAB-A", "LAB-B"], titulo="Primer sello", timestamp=T0 + 11),
                           transferencia("LAB-A", "LAB-C", 3, T0 + 12)], claves, "LAB-B", dificultad)
    b3 = minar_bloque(b2, [crear_sello(hb, claves, ["LAB-B", "LAB-C"], laboratorio="LAB-B", timestamp=T0 + 21),
                           crear_sello(ha, claves, ["LAB-A", "LAB-C"], titulo="Sello posterior", timestamp=T0 + 22),
                           transferencia("LAB-B", "LAB-A", 4, T0 + 23)], claves, "LAB-C", dificultad)
    b4 = minar_bloque(b3, [transferencia("LAB-A", "LAB-B", 1, T0 + 31)], claves, "LAB-A", dificultad)
    return [g, b1, b2, b3, b4], claves
