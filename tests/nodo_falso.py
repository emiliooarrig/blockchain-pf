"""Nodo falso para probar el transporte P2P: implementa la interfaz de C5 con claves Ed25519 aleatorias
y una "cadena" simple de diccionarios (cada bloque pesa 1 unidad de trabajo)."""
import threading

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from models.cripto import sha256_hex
from models.errores import ErrorEntrada, ErrorEstado


class ClaveFalsa:
    def __init__(self):
        self._privada = Ed25519PrivateKey.generate()
        self.publica = self._privada.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    def firmar(self, datos: bytes) -> str:
        return self._privada.sign(datos).hex()


def crear_genesis(claves: dict) -> dict:
    g = {"numero": 0, "hash_anterior": "0" * 64,
         "cuentas": {nid: {"clave_publica": c.publica, "saldo": 100} for nid, c in claves.items()}}
    g["hash"] = sha256_hex(repr(sorted(g["cuentas"])) + str(sorted(c.publica for c in claves.values())))
    return g


def hacer_bloque(anterior: dict, marca: str = "") -> dict:
    b = {"numero": anterior["numero"] + 1, "hash_anterior": anterior["hash"], "marca": marca}
    b["hash"] = sha256_hex(f"{b['numero']}|{b['hash_anterior']}|{marca}")
    return b


class NodoFalso:
    def __init__(self, nodo_id: str, claves: dict, genesis: dict | None = None, desbloqueado: bool = True):
        self.id = nodo_id
        self.claves = claves
        self.genesis = genesis or crear_genesis(claves)
        self.hash_genesis = self.genesis["hash"]
        self.desbloqueado = desbloqueado
        self.cadena = [self.genesis]
        self.pendientes = []
        self.eventos = []
        self.lock = threading.RLock()
        self.llamadas_bloque = []      # hash de cada BLOQUE entregado a recibir_bloque
        self.llamadas_bloques_desde = []
        self.cadenas_recibidas = 0

    def extender(self, n: int, marca: str = "") -> None:
        with self.lock:
            for _ in range(n):
                self.cadena.append(hacer_bloque(self.cadena[-1], marca))

    # --- interfaz C5 ---
    def clave_publica_de(self, nodo_id):
        c = self.claves.get(nodo_id)
        return c.publica if c else None

    def firmar(self, datos: bytes) -> str:
        if not self.desbloqueado:
            raise ErrorEstado("Nodo bloqueado")
        return self.claves[self.id].firmar(datos)

    def resumen(self) -> dict:
        with self.lock:
            return {"altura": len(self.cadena) - 1, "trabajo": len(self.cadena) - 1, "punta": self.cadena[-1]["hash"]}

    def bloques_desde(self, numero: int, maximo: int = 100) -> list:
        with self.lock:
            self.llamadas_bloques_desde.append(numero)
            return list(self.cadena[numero:numero + maximo])

    def recibir_bloque(self, bloque, de=""):
        with self.lock:
            self.llamadas_bloque.append(bloque.get("hash"))
            if any(b["hash"] == bloque.get("hash") for b in self.cadena):
                return "duplicado", "ya lo tengo"
            punta = self.cadena[-1]
            if bloque.get("hash_anterior") == punta["hash"] and bloque.get("numero") == punta["numero"] + 1:
                self.cadena.append(bloque)
                return "aceptado", "ok"
            if bloque.get("numero", 0) > punta["numero"] + 1:
                return "sincronizar", "no enlaza"
            return "rechazado", "no enlaza"

    def recibir_cadena(self, cadena, de=""):
        with self.lock:
            self.cadenas_recibidas += 1
            if cadena[0]["hash"] != self.hash_genesis:
                return False, "génesis distinto"
            for a, b in zip(cadena, cadena[1:]):
                if b["hash_anterior"] != a["hash"]:
                    return False, "cadena rota"
            if len(cadena) <= len(self.cadena):
                return False, "no tiene más trabajo"
            self.cadena = list(cadena)
            return True, "adoptada"

    def agregar_transaccion(self, tx, origen=""):
        with self.lock:
            if tx.get("invalida"):
                raise ErrorEntrada("transacción inválida")
            self.pendientes.append(tx)
            return tx.get("id", "")

    def evento(self, tipo, texto):
        self.eventos.append((tipo, texto))
