"""Ayudas de prueba: laboratorios con almacén de claves real (scrypt es lento: se crean una vez por módulo),
génesis compartido y construcción manual de bloques PoW para alimentar a un NodoCompleto."""
import os
import time

from models.bloque import crear_genesis, nueva_transaccion
from models.keystore import abrir_almacen, crear_almacen
from models.nodo_completo import NodoCompleto
from tests.cadena_v2 import crear_sello, minar_bloque

CONTRASENA = "contrasena-de-prueba-123"   # fixture de prueba: no protege ninguna clave real
IDS = ("LAB-A", "LAB-B", "LAB-C")


def crear_laboratorios(carpeta, ids=IDS, saldo: int = 100, dificultad: int | None = None):
    """Devuelve (genesis, rutas, claves): rutas del almacén de cada id y su ParClaves ya abierto.
    Con `dificultad` el génesis la fija (AUD-004) y la red admite ajustes co-firmados (C9)."""
    rutas, claves, cuentas = {}, {}, {}
    for nid in ids:
        rutas[nid] = os.path.join(str(carpeta), nid, "clave.json")
        publica = crear_almacen(rutas[nid], nid, CONTRASENA)
        claves[nid] = abrir_almacen(rutas[nid], CONTRASENA)
        cuentas[nid] = {"clave_publica": publica, "saldo": saldo}
    parametros = {"consenso": "pow", "recompensa": 10, "confirmaciones": 6, "red": "sellalo", "nombre": "prueba"}
    if dificultad is not None:
        parametros["dificultad"] = dificultad
    genesis = crear_genesis(cuentas, parametros, time.time() - 1000)
    return genesis, rutas, claves


def nuevo_nodo(carpeta, labs, nodo_id="LAB-A", desbloquear=True) -> NodoCompleto:
    genesis, rutas, _ = labs
    nodo = NodoCompleto(str(carpeta), genesis, nodo_id, rutas[nodo_id])
    if desbloquear:
        nodo.desbloquear(CONTRASENA)
    return nodo


def transferencia(labs, emisor, receptor, monto, ts):
    return nueva_transaccion(emisor, receptor, monto, ts, labs[2][emisor])


def sello(labs, doc_hash, firmantes=("LAB-A", "LAB-B"), ts=None, titulo="Hallazgo de prueba"):
    return crear_sello(doc_hash, labs[2], list(firmantes), titulo=titulo, timestamp=ts or time.time() - 500)


def bloque_externo(labs, anterior, txs, proponente="LAB-B", dificultad=1):
    return minar_bloque(anterior, txs, labs[2], proponente, dificultad)


def rama(labs, txs_por_bloque, proponente="LAB-B", dificultad=1, desde=None):
    """Cadena [génesis, b1, b2, ...] con un bloque por cada lista de transacciones."""
    cadena = [desde or labs[0]]
    for txs in txs_por_bloque:
        cadena.append(bloque_externo(labs, cadena[-1], txs, proponente, dificultad))
    return cadena
