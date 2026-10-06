"""Validación de bloques y de cadenas completas (común a PoW y PoS).

Un nodo acepta una cadena recibida sólo si:
  (a) cada hash coincide con el recalculado y cada hash_anterior con el del bloque previo;
  (b) todas las firmas son válidas y nadie gasta más de lo que tiene (incluido el doble gasto);
  (c) se cumple la regla del consenso (PoW: hash bajo el objetivo; PoS: sorteo, castigos y 2/3 de los votos);
  (d) es más larga que la propia (esto lo revisa el nodo, en red.py).
"""
from models.bloque import (CAMPOS_GENESIS, CAMPOS_POS, CAMPOS_POW, MAX_TX_POR_BLOQUE, Estado, ErrorValidacion,
                           aplicar_transacciones, es_entero, es_numero, hash_bloque, revisar_campos)
from models.cripto import LARGO_CLAVE_HEX, es_hex
from models.pos import verificar_pos
from models.pow import verificar_pow


def validar_bloque(estado: Estado, bloque, propuesta: bool = False) -> list:
    """Valida `bloque` como sucesor del estado y lo aplica sobre `estado`.
    Devuelve las recompensas que maduraron con este bloque.
    Con propuesta=True (votación PoS) se omiten el hash final y los votos, que aún no existen."""
    pos = estado.params["consenso"] == "pos"
    if propuesta:
        if not isinstance(bloque, dict) or bloque.get("hash") != "" or bloque.get("votos") != []:
            raise ErrorValidacion("la propuesta debe llegar sin hash ni votos")
        revisar_campos({**bloque, "hash": "0" * 64}, CAMPOS_POS)
    else:
        revisar_campos(bloque, CAMPOS_POS if pos else CAMPOS_POW)
    if bloque["numero"] != estado.altura + 1:
        raise ErrorValidacion(f"número de bloque {bloque['numero']} cuando se esperaba {estado.altura + 1}")
    if bloque["hash_anterior"] != estado.ultimo_hash:
        raise ErrorValidacion("hash_anterior no coincide con el hash del bloque previo")
    if not propuesta and hash_bloque(bloque) != bloque["hash"]:
        raise ErrorValidacion("el hash no coincide con el contenido del bloque (fue alterado)")
    if bloque["timestamp"] < estado.ultimo_ts:
        raise ErrorValidacion("timestamp anterior al del bloque previo")
    if bloque["proponente"] not in estado.claves:
        raise ErrorValidacion(f"proponente desconocido ({bloque['proponente']!r})")
    if bloque["recompensa"] != estado.params["recompensa"]:
        raise ErrorValidacion(f"recompensa falsa: el bloque reclama {bloque['recompensa']} y la establecida es "
                              f"{estado.params['recompensa']}")
    if not bloque["transacciones"]:
        raise ErrorValidacion("el bloque no contiene transacciones de usuarios")
    if len(bloque["transacciones"]) > MAX_TX_POR_BLOQUE:
        raise ErrorValidacion(f"demasiadas transacciones (máximo {MAX_TX_POR_BLOQUE})")

    if pos:
        if bloque["nonce"] != 0:
            raise ErrorValidacion("en PoS el nonce debe ser 0")
        verificar_pos(estado, bloque, con_votos=not propuesta)
    else:
        verificar_pow(bloque)
    aplicar_transacciones(estado, bloque["transacciones"])

    estado.recompensas.append({"numero": bloque["numero"], "nodo": bloque["proponente"], "monto": bloque["recompensa"]})
    estado.altura = bloque["numero"]
    estado.ultimo_hash = bloque["hash"]
    estado.ultimo_ts = bloque["timestamp"]
    return estado.madurar()


def revisar_genesis(genesis, hash_esperado: str) -> None:
    revisar_campos(genesis, CAMPOS_GENESIS)
    if genesis["numero"] != 0 or hash_bloque(genesis) != genesis["hash"]:
        raise ErrorValidacion("el bloque génesis fue alterado")
    if genesis["hash"] != hash_esperado:
        raise ErrorValidacion("el bloque génesis no es el de esta red")
    cuentas, params = genesis["cuentas"], genesis["parametros"]
    if not isinstance(cuentas, dict) or not isinstance(params, dict):
        raise ErrorValidacion("génesis con formato inválido")
    for c in cuentas.values():
        if not isinstance(c, dict) or not es_hex(c.get("clave_publica"), LARGO_CLAVE_HEX) or not es_entero(c.get("saldo")):
            raise ErrorValidacion("génesis con cuentas inválidas")
    if params.get("consenso") not in ("pow", "pos") or not es_entero(params.get("recompensa")) \
            or not es_entero(params.get("confirmaciones")):
        raise ErrorValidacion("génesis con parámetros inválidos")
    if not es_numero(genesis["timestamp"]):
        raise ErrorValidacion("génesis con timestamp inválido")


def validar_cadena(cadena, hash_genesis: str) -> Estado:
    """Revalida la cadena completa desde el génesis. Devuelve el estado final o lanza ErrorValidacion."""
    if not isinstance(cadena, list) or not cadena:
        raise ErrorValidacion("la cadena está vacía o no es una lista de bloques")
    try:
        revisar_genesis(cadena[0], hash_genesis)
        estado = Estado(cadena[0])
        for i, bloque in enumerate(cadena[1:], 1):
            try:
                validar_bloque(estado, bloque)
            except ErrorValidacion as exc:
                raise ErrorValidacion(f"bloque #{i}: {exc}") from None
    except (TypeError, KeyError, ValueError, AttributeError) as exc:
        raise ErrorValidacion(f"la cadena tiene un formato inválido ({type(exc).__name__})") from None
    return estado
