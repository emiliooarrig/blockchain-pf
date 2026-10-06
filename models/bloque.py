"""Transacciones, bloques, hash canónico y estado de cuentas derivado de una cadena.

Estructura común del bloque (PoW y PoS):
    numero, timestamp, transacciones, hash_anterior, nonce, proponente, recompensa, hash
PoW agrega:  dificultad
PoS agrega:  validadores, intento, excluidos, castigos, firma_proponente, votos
El génesis (numero 0) agrega: cuentas (clave pública y saldo inicial de cada nodo) y parametros.
"""
import copy
import hashlib
import json
import math

from models.cripto import LARGO_FIRMA_HEX, es_hex, sha256_hex, verificar

CAMPOS_TX = ("emisor", "receptor", "monto", "timestamp")
MONTO_MAX = 10**9
MAX_TX_POR_BLOQUE = 10
HASH_CERO = "0" * 64

CAMPOS_COMUNES = ("numero", "timestamp", "transacciones", "hash_anterior", "nonce", "proponente", "recompensa", "hash")
CAMPOS_POW = CAMPOS_COMUNES + ("dificultad",)
CAMPOS_POS = CAMPOS_COMUNES + ("validadores", "intento", "excluidos", "castigos", "firma_proponente", "votos")
CAMPOS_GENESIS = CAMPOS_COMUNES + ("cuentas", "parametros")


class ErrorValidacion(Exception):
    """Un bloque, transacción o cadena no cumple las reglas; el mensaje explica cuál."""


# ---------------------------------------------------------------- utilidades de tipo
def es_entero(v) -> bool:
    return type(v) is int


def es_numero(v) -> bool:
    return type(v) in (int, float) and math.isfinite(v)


def copiar(obj):
    return copy.deepcopy(obj)


# ---------------------------------------------------------------- transacciones
def serializar(tx) -> bytes:
    """Serialización canónica que firma el emisor (orden fijo de llaves = misma firma en todos lados)."""
    datos = {k: tx[k] for k in CAMPOS_TX}
    return json.dumps(datos, sort_keys=True, separators=(",", ":")).encode()


def id_transaccion(tx) -> str:
    return sha256_hex(serializar(tx))


def nueva_transaccion(emisor: str, receptor: str, monto: int, timestamp: float, claves) -> dict:
    tx = {"emisor": emisor, "receptor": receptor, "monto": monto, "timestamp": timestamp}
    tx["firma"] = claves.firmar(serializar(tx))
    return tx


# ---------------------------------------------------------------- bloques
def hash_bloque(b) -> str:
    """SHA-256 de todos los campos del bloque en forma canónica; el campo "hash" nunca entra en su propio cálculo."""
    datos = {k: v for k, v in b.items() if k != "hash"}
    return hashlib.sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()


_MARCA_NONCE = "__NONCE__"


def preparar_hasher(bloque):
    """Devuelve f(nonce) -> hash idéntico a hash_bloque(bloque con ese nonce), pero precalculando todo
    lo que no cambia entre intentos (el JSON se parte alrededor del nonce)."""
    datos = {k: v for k, v in bloque.items() if k != "hash"}
    datos["nonce"] = _MARCA_NONCE
    texto = json.dumps(datos, sort_keys=True)
    partes = texto.split(json.dumps(_MARCA_NONCE))
    if len(partes) != 2:  # no debería pasar; se usa el cálculo directo
        return lambda nonce: hash_bloque({**bloque, "nonce": nonce})
    prefijo = hashlib.sha256(partes[0].encode())
    sufijo = partes[1]

    def calcular(nonce: int) -> str:
        h = prefijo.copy()
        h.update(f"{nonce}{sufijo}".encode())
        return h.hexdigest()

    return calcular


def crear_genesis(cuentas: dict, parametros: dict, timestamp: float) -> dict:
    b = {
        "numero": 0,
        "timestamp": timestamp,
        "transacciones": [],
        "hash_anterior": HASH_CERO,
        "nonce": 0,
        "proponente": "génesis",
        "recompensa": 0,
        "cuentas": cuentas,
        "parametros": parametros,
    }
    b["hash"] = hash_bloque(b)
    return b


def revisar_campos(b, campos: tuple) -> None:
    if not isinstance(b, dict):
        raise ErrorValidacion("el bloque no es un objeto")
    faltan = [c for c in campos if c not in b]
    if faltan:
        raise ErrorValidacion(f"faltan campos obligatorios: {', '.join(faltan)}")
    sobran = [c for c in b if c not in campos]
    if sobran:
        raise ErrorValidacion(f"campos desconocidos: {', '.join(sobran)}")
    if not es_entero(b["numero"]) or not es_numero(b["timestamp"]) or not es_entero(b["nonce"]):
        raise ErrorValidacion("numero, timestamp o nonce con tipo inválido")
    if not es_hex(b["hash"], 64) or not es_hex(b["hash_anterior"], 64):
        raise ErrorValidacion("hash o hash_anterior con formato inválido")
    if not isinstance(b["transacciones"], list) or not isinstance(b["proponente"], str):
        raise ErrorValidacion("transacciones o proponente con tipo inválido")
    if not es_entero(b["recompensa"]) or b["recompensa"] < 0:
        raise ErrorValidacion("recompensa con tipo inválido")


# ---------------------------------------------------------------- estado de cuentas
class Estado:
    """Saldos y datos derivados de recorrer una cadena válida desde el génesis."""

    def __init__(self, genesis: dict):
        self.claves = {nid: c["clave_publica"] for nid, c in genesis["cuentas"].items()}
        self.saldos = {nid: c["saldo"] for nid, c in genesis["cuentas"].items()}
        self.params = dict(genesis["parametros"])
        self.recompensas = []   # recompensas aún sin madurar: {"numero", "nodo", "monto"}
        self.tx_ids = set()     # transacciones ya incluidas (evita repetirlas: doble gasto entre bloques)
        self.altura = 0
        self.ultimo_hash = genesis["hash"]
        self.ultimo_ts = genesis["timestamp"]

    def copia(self) -> "Estado":
        nuevo = copy.copy(self)
        nuevo.saldos = dict(self.saldos)
        nuevo.recompensas = list(self.recompensas)
        nuevo.tx_ids = set(self.tx_ids)
        return nuevo

    def madurar(self) -> list:
        """Acredita las recompensas que ya tienen las confirmaciones requeridas."""
        conf = self.params["confirmaciones"]
        maduras = [r for r in self.recompensas if self.altura - r["numero"] >= conf]
        for r in maduras:
            self.saldos[r["nodo"]] += r["monto"]
        self.recompensas = [r for r in self.recompensas if r not in maduras]
        return maduras

    def pendiente_de(self, nodo: str) -> int:
        return sum(r["monto"] for r in self.recompensas if r["nodo"] == nodo)


def revisar_transaccion(estado: Estado, tx, vistos: set | None = None) -> str:
    """Formato, cuentas, firma y no repetición. Devuelve el id de la transacción."""
    if not isinstance(tx, dict):
        raise ErrorValidacion("la transacción no es un objeto")
    if set(tx) != set(CAMPOS_TX) | {"firma"}:
        raise ErrorValidacion("la transacción debe tener exactamente emisor, receptor, monto, timestamp y firma")
    emisor, receptor, monto = tx["emisor"], tx["receptor"], tx["monto"]
    if not isinstance(emisor, str) or emisor not in estado.claves:
        raise ErrorValidacion(f"el emisor {emisor!r} no existe")
    if not isinstance(receptor, str) or receptor not in estado.claves:
        raise ErrorValidacion(f"el receptor {receptor!r} no existe")
    if emisor == receptor:
        raise ErrorValidacion("el emisor y el receptor son el mismo nodo")
    if not es_entero(monto) or not 0 < monto <= MONTO_MAX:
        raise ErrorValidacion(f"monto inválido ({monto!r}); debe ser entero entre 1 y {MONTO_MAX}")
    if not es_numero(tx["timestamp"]) or tx["timestamp"] < 0:
        raise ErrorValidacion("timestamp de la transacción inválido")
    if not es_hex(tx["firma"], LARGO_FIRMA_HEX) or not verificar(estado.claves[emisor], serializar(tx), tx["firma"]):
        raise ErrorValidacion(f"firma inválida: no corresponde a la clave pública de {emisor}")
    tid = id_transaccion(tx)
    if tid in estado.tx_ids:
        raise ErrorValidacion(f"la transacción {tid[:12]}… ya está en la cadena (doble gasto entre bloques)")
    if vistos is not None and tid in vistos:
        raise ErrorValidacion(f"la transacción {tid[:12]}… aparece dos veces en el bloque (doble gasto)")
    return tid


def aplicar_transacciones(estado: Estado, transacciones: list) -> None:
    """Valida y aplica en orden. Detecta el doble gasto dentro del mismo bloque."""
    vistos, gastado = set(), {}
    for i, tx in enumerate(transacciones, 1):
        try:
            tid = revisar_transaccion(estado, tx, vistos)
        except ErrorValidacion as exc:
            raise ErrorValidacion(f"transacción {i}: {exc}") from None
        emisor, monto = tx["emisor"], tx["monto"]
        saldo = estado.saldos[emisor]
        if monto > saldo:
            previo = gastado.get(emisor, 0)
            if previo and monto <= saldo + previo:
                raise ErrorValidacion(f"transacción {i}: doble gasto dentro del bloque; {emisor} ya gastó {previo} "
                                      f"y su saldo restante ({saldo}) no cubre {monto}")
            raise ErrorValidacion(f"transacción {i}: saldo insuficiente de {emisor} (tiene {saldo}, intenta gastar {monto})")
        estado.saldos[emisor] -= monto
        estado.saldos[tx["receptor"]] += monto
        gastado[emisor] = gastado.get(emisor, 0) + monto
        vistos.add(tid)
    estado.tx_ids |= vistos
