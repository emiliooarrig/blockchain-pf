"""Sellos multifirma k-de-n: un documento se registra con la firma de al menos `umbral` de sus co-autores.

Un sello es una transacción de tipo "sello" que no mueve saldos. Cada autor firma el mismo mensaje canónico
(todos los campos salvo `firmas`), así que ninguna firma se puede reutilizar en otro sello ni en otro documento.
"""
from models.bloque import ErrorValidacion, es_entero, es_numero
from models.cripto import LARGO_FIRMA_HEX, canonico, es_hex, sha256_hex, verificar
from models.errores import ErrorEntrada

CAMPOS_SELLO = ("tipo", "doc_hash", "titulo", "investigador", "laboratorio", "autores", "umbral", "timestamp")
UMBRAL_MAX_AUTORES = 5
TITULO_MAX, INVESTIGADOR_MAX = 120, 80


def es_sello(tx) -> bool:
    return isinstance(tx, dict) and tx.get("tipo") == "sello"


def mensaje_sello(tx) -> bytes:
    return canonico({k: tx[k] for k in CAMPOS_SELLO})


def id_sello(tx) -> str:
    return sha256_hex(mensaje_sello(tx))


def firmar_sello(tx, claves) -> str:
    return claves.firmar(mensaje_sello(tx))


def _problema_formato(doc_hash, titulo, investigador, laboratorio, autores, umbral, timestamp) -> str | None:
    """Reglas de formato comunes a la creación y a la validación en cadena. Devuelve el motivo o None."""
    if not es_hex(doc_hash, 64):
        return "doc_hash debe ser el SHA-256 del documento (64 caracteres hexadecimales en minúsculas)"
    if not isinstance(titulo, str) or not titulo.strip() or len(titulo) > TITULO_MAX or not titulo.isprintable():
        return f"el título debe tener de 1 a {TITULO_MAX} caracteres, sin caracteres de control"
    if not isinstance(investigador, str) or not investigador.strip() or len(investigador) > INVESTIGADOR_MAX \
            or not investigador.isprintable():
        return f"el investigador debe tener de 1 a {INVESTIGADOR_MAX} caracteres, sin caracteres de control"
    if not isinstance(autores, list) or not autores or not all(isinstance(a, str) and a for a in autores):
        return "autores debe ser una lista no vacía de ids de nodo"
    if len(autores) > UMBRAL_MAX_AUTORES:
        return f"un sello admite como máximo {UMBRAL_MAX_AUTORES} autores"
    if len(set(autores)) != len(autores):
        return "autores contiene ids repetidos"
    if autores != sorted(autores):
        return "autores debe estar ordenado alfabéticamente"
    if not isinstance(laboratorio, str) or laboratorio not in autores:
        return "el laboratorio que registra debe estar entre los autores"
    if not es_entero(umbral) or not 1 <= umbral <= len(autores):
        return f"el umbral debe ser un entero entre 1 y {len(autores)} (el número de autores)"
    if not es_numero(timestamp) or timestamp < 0:
        return "timestamp inválido"
    return None


def nuevo_sello(doc_hash, titulo, investigador, laboratorio, autores, umbral, timestamp) -> dict:
    """Sello sin firmas. Los autores se ordenan; lo demás se valida (ErrorEntrada)."""
    if isinstance(autores, (list, tuple)):
        autores = sorted(autores) if all(isinstance(a, str) for a in autores) else list(autores)
    motivo = _problema_formato(doc_hash, titulo, investigador, laboratorio, autores, umbral, timestamp)
    if motivo:
        raise ErrorEntrada(f"Sello inválido: {motivo}.")
    return {"tipo": "sello", "doc_hash": doc_hash, "titulo": titulo, "investigador": investigador,
            "laboratorio": laboratorio, "autores": autores, "umbral": umbral, "timestamp": timestamp, "firmas": {}}


def _firma_correcta(tx, autor, firma, claves_publicas) -> bool:
    clave = claves_publicas.get(autor)
    return clave is not None and es_hex(firma, LARGO_FIRMA_HEX) and verificar(clave, mensaje_sello(tx), firma)


def agregar_firma(tx, autor, firma, claves_publicas) -> dict:
    """Copia del sello con la firma agregada. Una firma inválida o de alguien que no es autor se descarta."""
    if not isinstance(tx, dict) or not isinstance(tx.get("autores"), list):
        raise ErrorEntrada("El sello no tiene el formato esperado.")
    if not isinstance(autor, str) or autor not in tx["autores"]:
        raise ErrorEntrada(f"{str(autor)[:20]!r} no es autor de este sello; su firma se descartó.")
    if not _firma_correcta(tx, autor, firma, claves_publicas):
        raise ErrorEntrada(f"La firma de {autor} no es válida para este sello; se descartó.")
    nuevo = {**tx, "firmas": {**tx.get("firmas", {}), autor: firma}}
    return nuevo


def firmas_validas(tx, claves_publicas) -> list[str]:
    """Autores (en el orden del sello) cuya firma es correcta."""
    firmas = tx.get("firmas")
    if not isinstance(firmas, dict) or not isinstance(tx.get("autores"), list):
        return []
    return [a for a in tx["autores"] if a in firmas and _firma_correcta(tx, a, firmas[a], claves_publicas)]


def revisar_sello(estado, tx, vistos: set | None = None) -> str:
    """Reglas estrictas de un sello dentro de un bloque. Devuelve su id o lanza ErrorValidacion."""
    if not isinstance(tx, dict):
        raise ErrorValidacion("el sello no es un objeto")
    if set(tx) != set(CAMPOS_SELLO) | {"firmas"}:
        raise ErrorValidacion("el sello debe tener exactamente tipo, doc_hash, titulo, investigador, laboratorio, "
                              "autores, umbral, timestamp y firmas")
    if tx["tipo"] != "sello":
        raise ErrorValidacion("tipo de transacción desconocido")
    motivo = _problema_formato(*(tx[k] for k in CAMPOS_SELLO[1:]))
    if motivo:
        raise ErrorValidacion(f"sello inválido: {motivo}")
    for a in tx["autores"]:
        if a not in estado.claves:
            raise ErrorValidacion(f"sello inválido: el autor {a!r} no existe en la red")
    firmas = tx["firmas"]
    if not isinstance(firmas, dict):
        raise ErrorValidacion("sello inválido: firmas debe ser un objeto {autor: firma}")
    for autor, firma in firmas.items():
        if autor not in tx["autores"]:
            raise ErrorValidacion(f"sello inválido: {str(autor)[:20]!r} firmó pero no es autor")
        if not _firma_correcta(tx, autor, firma, estado.claves):
            raise ErrorValidacion(f"sello inválido: la firma de {autor} no corresponde a este sello")
    if len(firmas) < tx["umbral"]:
        raise ErrorValidacion(f"sello sin firmas suficientes: tiene {len(firmas)} y el umbral es {tx['umbral']} "
                              f"de {len(tx['autores'])}")
    sid = id_sello(tx)
    if sid in estado.tx_ids:
        raise ErrorValidacion(f"el sello {sid[:12]}… ya está en la cadena")
    if vistos is not None and sid in vistos:
        raise ErrorValidacion(f"el sello {sid[:12]}… aparece dos veces en el bloque")
    return sid


def registrar_sello(estado, tx, sid: str, numero: int | None, indice: int) -> None:
    """Anota el sello en estado.sellos (orden de cadena: el primero de cada documento tiene la prioridad)."""
    estado.sellos.setdefault(tx["doc_hash"], []).append({
        "id": sid, "numero": numero, "indice": indice, "timestamp": tx["timestamp"], "laboratorio": tx["laboratorio"],
        "autores": list(tx["autores"]), "titulo": tx["titulo"], "investigador": tx["investigador"]})
