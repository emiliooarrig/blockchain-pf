"""Verificación detallada de una cadena (rubro «Métodos de verificación») y simulación de alteraciones.

`verificar_cadena_detallada` aplica las mismas reglas que `validar_bloque`, pero evalúa CADA comprobación por
separado y no se detiene en el primer error, para poder mostrar qué falla y qué no:

    hash          el hash recalculado del encabezado coincide con el `hash` declarado
    enlace        `numero` = anterior + 1 y `hash_anterior` = hash del bloque anterior
    merkle        la raíz de Merkle de las transacciones coincide con `raiz_merkle`
    pow           el hash cumple la dificultad del bloque (y la de red, si el génesis la fija)
    firma_minero  el hash está firmado por la clave del proponente (clave del génesis)
    transacciones toda transferencia tiene firma válida del emisor y todo sello es válido (firmas correctas y
                  umbral alcanzado)

Además se ejecuta `validar_cadena` (el validador del nodo): si encuentra algo que aquí no se itemiza (timestamps,
recompensa, saldos, doble gasto...) la cadena queda `valida: false` y el motivo va en `otras_reglas`.

`alterar_copia` fabrica una COPIA profunda de la cadena con una alteración concreta; la cadena original nunca se toca.
`COMPROBACIONES_ESPERADAS` dice qué comprobaciones tienen que fallar con cada tipo de alteración.
"""
import copy
import time

from models import merkle
from models.bloque import (ErrorValidacion, es_entero, hash_bloque, id_transaccion, serializar)
from models.cripto import LARGO_FIRMA_HEX, es_hex, verificar
from models.errores import ErrorEntrada
from models.multifirma import es_sello, firmas_validas, id_sello
from models.pow import DIF_MAX, DIF_MIN, cumple_objetivo
from models.validacion import validar_cadena

COMPROBACIONES = ("hash", "enlace", "merkle", "pow", "firma_minero", "transacciones")

TIPOS_ALTERACION = {
    "transaccion": "Cambiar un dato de una transacción (monto de una transferencia o título de un sello)",
    "firma_tx": "Alterar la firma de una transacción",
    "hash": "Cambiar el hash declarado del bloque",
    "enlace": "Romper el enlace con el bloque anterior (hash_anterior)",
    "merkle": "Cambiar la raíz de Merkle del bloque",
    "firma_minero": "Alterar la firma del minero",
    "multifirma": "Quitar firmas de un sello hasta bajar del umbral",
    "nonce": "Cambiar el nonce (invalida la prueba de trabajo)",
}

# Comprobaciones que DEBEN quedar en false al aplicar cada alteración (pueden fallar además otras, porque el hash
# compromete la raíz de Merkle y el enlace: es el efecto en cascada normal de alterar un bloque sin volver a minarlo).
COMPROBACIONES_ESPERADAS = {
    "transaccion": ("merkle", "transacciones"),
    "firma_tx": ("transacciones",),
    "hash": ("hash",),
    "enlace": ("enlace",),
    "merkle": ("merkle",),
    "firma_minero": ("firma_minero",),
    "multifirma": ("transacciones",),
    "nonce": ("hash",),
}


# ---------------------------------------------------------------- verificación
def _hex_a_bytes(h) -> bytes | None:
    return bytes.fromhex(h) if es_hex(h, 64) else None


def _comprobar_tx(tx, indice: int, claves: dict) -> dict:
    """Detalle de una transacción: tipo, id, ok, firma y (en sellos) el detalle por autor."""
    if es_sello(tx):
        try:
            autores = list(tx["autores"])
            firmas = tx["firmas"] if isinstance(tx["firmas"], dict) else {}
            umbral = tx["umbral"]
            validas = set(firmas_validas(tx, claves))
            try:
                tid = id_sello(tx)
            except (KeyError, TypeError, ValueError):
                tid = None
            detalle = [{"autor": a, "firmo": a in firmas, "valida": a in validas} for a in autores]
            ajenas = [a for a in firmas if a not in autores]
            firma_ok = not ajenas and all(d["valida"] for d in detalle if d["firmo"])
            alcanzado = es_entero(umbral) and len(validas) >= umbral
            return {"indice": indice, "tipo": "sello", "id": tid, "ok": bool(firma_ok and alcanzado),
                    "firma": bool(firma_ok),
                    "multifirma": {"autores": autores, "umbral": umbral, "firmas": detalle,
                                   "alcanzado": bool(alcanzado), "firmas_ajenas": ajenas}}
        except (KeyError, TypeError, ValueError, AttributeError):
            return {"indice": indice, "tipo": "sello", "id": None, "ok": False, "firma": False, "multifirma": None}
    try:
        tid = id_transaccion(tx)
        firma = es_hex(tx["firma"], LARGO_FIRMA_HEX) and verificar(claves.get(tx["emisor"]), serializar(tx), tx["firma"])
    except (KeyError, TypeError, ValueError, AttributeError):
        tid, firma = None, False
    return {"indice": indice, "tipo": "transferencia", "id": tid, "ok": bool(firma), "firma": bool(firma),
            "multifirma": None}


def _comprobar_bloque(b, anterior, claves: dict, dif_red) -> dict:
    errores = []
    try:
        hash_ok = hash_bloque(b) == b.get("hash")
    except (TypeError, ValueError):
        hash_ok = False
    if not hash_ok:
        errores.append("el hash no coincide con el contenido del bloque (fue alterado)")
    enlace_ok = (b.get("numero") == anterior["numero"] + 1 and b.get("hash_anterior") == anterior["hash"])
    if not enlace_ok:
        errores.append("el bloque no enlaza con el anterior (número o hash_anterior)")
    try:
        merkle_ok = merkle.raiz_transacciones(b["transacciones"]) == b.get("raiz_merkle")
    except (KeyError, TypeError, ValueError):
        merkle_ok = False
    if not merkle_ok:
        errores.append("la raíz de Merkle no coincide con las transacciones")
    d = b.get("dificultad")
    pow_ok = (es_entero(d) and DIF_MIN <= d <= DIF_MAX and isinstance(b.get("hash"), str)
              and cumple_objetivo(b["hash"], d) and (dif_red is None or d == dif_red))
    if not pow_ok:
        errores.append("no cumple la prueba de trabajo" + (f" (la red exige dificultad {dif_red})" if dif_red else ""))
    clave = claves.get(b.get("proponente")) if isinstance(b.get("proponente"), str) else None
    datos = _hex_a_bytes(b.get("hash"))
    firma_ok = bool(clave and datos is not None and es_hex(b.get("firma_minero"), LARGO_FIRMA_HEX)
                    and verificar(clave, datos, b["firma_minero"]))
    if not firma_ok:
        errores.append("la firma del minero no corresponde al proponente")
    txs_raw = b.get("transacciones")
    txs = [_comprobar_tx(tx, i, claves) for i, tx in enumerate(txs_raw if isinstance(txs_raw, list) else [])]
    txs_ok = isinstance(txs_raw, list) and all(t["ok"] for t in txs)
    if not txs_ok:
        malas = [str(t["indice"]) for t in txs if not t["ok"]]
        errores.append("transacciones inválidas" + (f" (índices {', '.join(malas)})" if malas else ""))
    comprobaciones = {"hash": bool(hash_ok), "enlace": bool(enlace_ok), "merkle": bool(merkle_ok), "pow": bool(pow_ok),
                      "firma_minero": firma_ok, "transacciones": bool(txs_ok)}
    return {"numero": b.get("numero"), "hash": b.get("hash"), "ok": all(comprobaciones.values()),
            "comprobaciones": comprobaciones, "transacciones": txs, "errores": errores}


def verificar_cadena_detallada(cadena, hash_genesis: str) -> dict:
    """Evalúa cada comprobación de cada bloque sin detenerse. Devuelve el cuerpo de GET /verificacion (sin los
    campos que agrega la ruta). Nunca lanza excepciones por datos mal formados."""
    t0 = time.perf_counter()
    bloques, primer_error = [], None
    genesis = cadena[0] if isinstance(cadena, list) and cadena and isinstance(cadena[0], dict) else {}
    try:
        gen_hash_ok = hash_bloque(genesis) == genesis.get("hash")
    except (TypeError, ValueError):
        gen_hash_ok = False
    gen_ok = bool(gen_hash_ok and genesis.get("hash") == hash_genesis)
    cuentas = genesis.get("cuentas") if isinstance(genesis.get("cuentas"), dict) else {}
    claves = {n: c.get("clave_publica") for n, c in cuentas.items() if isinstance(c, dict)}
    params = genesis.get("parametros") if isinstance(genesis.get("parametros"), dict) else {}
    dif_red = params.get("dificultad")
    if gen_ok is False:
        primer_error = {"bloque": 0, "comprobacion": "hash", "motivo": "el génesis no es el de esta red o fue alterado"}
    if isinstance(cadena, list):
        for pos in range(1, len(cadena)):
            b, ant = cadena[pos], cadena[pos - 1]
            if not isinstance(b, dict) or not isinstance(ant, dict) or "numero" not in ant or "hash" not in ant:
                bloques.append({"numero": pos, "hash": None, "ok": False, "transacciones": [],
                                "comprobaciones": {c: False for c in COMPROBACIONES},
                                "errores": ["el bloque no es un objeto válido"]})
                continue
            info = _comprobar_bloque(b, ant, claves, dif_red)
            bloques.append(info)
            if primer_error is None and not info["ok"]:
                c = next(k for k in COMPROBACIONES if not info["comprobaciones"][k])
                primer_error = {"bloque": b.get("numero"), "comprobacion": c, "motivo": info["errores"][0]}
    otras = {"ok": True, "error": None}
    try:
        validar_cadena(cadena, hash_genesis)
    except ErrorValidacion as exc:
        otras = {"ok": False, "error": str(exc)}
    except Exception as exc:                      # datos tan rotos que ni el validador los entiende
        otras = {"ok": False, "error": f"formato inválido ({type(exc).__name__})"}
    itemizado = gen_ok and all(b["ok"] for b in bloques)
    if primer_error is None and not otras["ok"]:
        primer_error = {"bloque": None, "comprobacion": "otras_reglas", "motivo": otras["error"]}
    return {"valida": bool(itemizado and otras["ok"]), "duracion_ms": round((time.perf_counter() - t0) * 1000, 1),
            "copia_alterada": False, "alteracion": None,
            "genesis": {"hash": genesis.get("hash"), "ok": gen_ok}, "dificultad_red": dif_red,
            "bloques": bloques, "otras_reglas": otras, "primer_error": primer_error}


# ---------------------------------------------------------------- alteraciones sobre una copia
def _voltear_hex(h: str) -> str:
    """Cambia el primer carácter hexadecimal (siempre produce otro valor hexadecimal válido)."""
    return ("1" if h[0] == "0" else "0") + h[1:]


def _bloque_de(copia: list, bloque) -> dict:
    if not es_entero(bloque) or not 1 <= bloque < len(copia):
        raise ErrorEntrada(f"El bloque #{bloque} no existe o no se puede alterar "
                           f"(hay bloques del 1 al {len(copia) - 1}; el génesis no se altera).")
    return copia[bloque]


def alterar_copia(cadena: list, tipo: str, bloque: int) -> tuple[list, str]:
    """(copia alterada, descripción). `cadena` no se modifica. ErrorEntrada si el tipo no existe, el bloque no existe
    o no tiene lo necesario (p. ej. `multifirma` en un bloque sin sellos)."""
    if tipo not in TIPOS_ALTERACION:
        raise ErrorEntrada(f"El tipo de alteración debe ser uno de: {', '.join(TIPOS_ALTERACION)}.")
    copia = copy.deepcopy(cadena)
    b = _bloque_de(copia, bloque)
    n = b["numero"]
    if tipo == "transaccion":
        if not b["transacciones"]:
            raise ErrorEntrada(f"El bloque #{n} no tiene transacciones que alterar.")
        tx = b["transacciones"][0]
        if es_sello(tx):
            tx["titulo"] = tx["titulo"] + " (alterado)"
            return copia, f"se cambió el título del sello 0 del bloque #{n}"
        tx["monto"] += 1
        return copia, f"se cambió el monto de la transferencia 0 del bloque #{n} ({tx['monto'] - 1} → {tx['monto']})"
    if tipo == "firma_tx":
        if not b["transacciones"]:
            raise ErrorEntrada(f"El bloque #{n} no tiene transacciones cuya firma alterar.")
        tx = b["transacciones"][0]
        if es_sello(tx):
            if not tx.get("firmas"):
                raise ErrorEntrada(f"El sello 0 del bloque #{n} no trae firmas que alterar.")
            autor = sorted(tx["firmas"])[0]
            tx["firmas"][autor] = _voltear_hex(tx["firmas"][autor])
            return copia, f"se alteró la firma de {autor} en el sello 0 del bloque #{n}"
        tx["firma"] = _voltear_hex(tx["firma"])
        return copia, f"se alteró la firma de la transferencia 0 del bloque #{n}"
    if tipo == "hash":
        b["hash"] = _voltear_hex(b["hash"])
        return copia, f"se cambió el hash declarado del bloque #{n}"
    if tipo == "enlace":
        b["hash_anterior"] = _voltear_hex(b["hash_anterior"])
        return copia, f"se cambió hash_anterior del bloque #{n} (ya no apunta al bloque #{n - 1})"
    if tipo == "merkle":
        b["raiz_merkle"] = _voltear_hex(b["raiz_merkle"])
        return copia, f"se cambió la raíz de Merkle del bloque #{n}"
    if tipo == "firma_minero":
        b["firma_minero"] = _voltear_hex(b["firma_minero"])
        return copia, f"se alteró la firma del minero del bloque #{n}"
    if tipo == "nonce":
        b["nonce"] += 1
        return copia, f"se cambió el nonce del bloque #{n} ({b['nonce'] - 1} → {b['nonce']})"
    # multifirma
    for i, tx in enumerate(b["transacciones"]):
        if es_sello(tx) and tx.get("firmas"):
            firmas = tx["firmas"]
            quitar = max(1, len(firmas) - (tx["umbral"] - 1))     # hasta quedar por debajo del umbral
            for autor in sorted(firmas, reverse=True)[:quitar]:
                del firmas[autor]
            return copia, (f"se quitaron {quitar} firma(s) del sello {i} del bloque #{n}: quedan {len(firmas)} "
                           f"y el umbral es {tx['umbral']}")
    raise ErrorEntrada(f"El bloque #{n} no tiene sellos con firmas: no hay multifirma que alterar.")
