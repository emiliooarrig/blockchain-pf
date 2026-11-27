"""Ajuste de dificultad co-firmado (contrato C9).

Una transacción `ajuste_dificultad` cambia la dificultad de la red cuando la firman más de la mitad de los
laboratorios del génesis. No mueve saldos. La nueva dificultad rige desde el bloque siguiente al que la contiene.
Cada firmante firma el mismo mensaje canónico (todos los campos salvo `firmas`), y el id es el SHA-256 de ese mensaje.
"""
from models.bloque import ErrorValidacion, es_entero, es_numero
from models.cripto import LARGO_FIRMA_HEX, canonico, es_hex, sha256_hex, verificar
from models.errores import ErrorEntrada
from models.pow import DIF_MAX, DIF_MIN

CAMPOS_AJUSTE = ("tipo", "dificultad", "proponente", "timestamp")


def es_ajuste(tx) -> bool:
    return isinstance(tx, dict) and tx.get("tipo") == "ajuste_dificultad"


def mensaje_ajuste(tx) -> bytes:
    return canonico({k: tx[k] for k in CAMPOS_AJUSTE})


def id_ajuste(tx) -> str:
    return sha256_hex(mensaje_ajuste(tx))


def mayoria(n: int) -> int:
    """Firmas necesarias: más de la mitad de los n laboratorios del génesis."""
    return n // 2 + 1


def nuevo_ajuste(dificultad, proponente, timestamp) -> dict:
    """Ajuste sin firmas; ErrorEntrada si el formato no sirve."""
    if not es_entero(dificultad) or not DIF_MIN <= dificultad <= DIF_MAX:
        raise ErrorEntrada(f"La dificultad debe ser un entero entre {DIF_MIN} y {DIF_MAX}.")
    if not isinstance(proponente, str) or not proponente:
        raise ErrorEntrada("El proponente del ajuste no es válido.")
    if not es_numero(timestamp) or timestamp < 0:
        raise ErrorEntrada("timestamp inválido.")
    return {"tipo": "ajuste_dificultad", "dificultad": dificultad, "proponente": proponente,
            "timestamp": timestamp, "firmas": {}}


def _firma_correcta(tx, lab, firma, claves) -> bool:
    clave = claves.get(lab) if isinstance(lab, str) else None
    return clave is not None and es_hex(firma, LARGO_FIRMA_HEX) and verificar(clave, mensaje_ajuste(tx), firma)


def agregar_firma(tx, lab, firma, claves) -> dict:
    """Copia del ajuste con la firma agregada; una firma inválida o de quien no es laboratorio se descarta."""
    if not isinstance(lab, str) or lab not in claves:
        raise ErrorEntrada(f"{str(lab)[:20]!r} no es un laboratorio de esta red; su firma se descartó.")
    if not _firma_correcta(tx, lab, firma, claves):
        raise ErrorEntrada(f"La firma de {lab} no es válida para este ajuste; se descartó.")
    return {**tx, "firmas": {**tx.get("firmas", {}), lab: firma}}


def firmas_validas(tx, claves) -> list[str]:
    """Laboratorios (ordenados) cuya firma es correcta."""
    firmas = tx.get("firmas")
    if not isinstance(firmas, dict):
        return []
    return sorted(l for l in firmas if _firma_correcta(tx, l, firmas[l], claves))


def problema_formato(tx) -> str | None:
    """Reglas de campos que no dependen del estado (None si todo bien)."""
    if not isinstance(tx, dict):
        return "el ajuste no es un objeto"
    if set(tx) != set(CAMPOS_AJUSTE) | {"firmas"}:
        return "el ajuste debe tener exactamente tipo, dificultad, proponente, timestamp y firmas"
    if tx["tipo"] != "ajuste_dificultad":
        return "tipo de transacción desconocido"
    if not es_entero(tx["dificultad"]) or not DIF_MIN <= tx["dificultad"] <= DIF_MAX:
        return f"la dificultad debe ser un entero entre {DIF_MIN} y {DIF_MAX}"
    if not isinstance(tx["proponente"], str) or not tx["proponente"]:
        return "el proponente no es válido"
    if not es_numero(tx["timestamp"]) or tx["timestamp"] < 0:
        return "timestamp inválido"
    if not isinstance(tx["firmas"], dict):
        return "firmas debe ser un objeto {laboratorio: firma}"
    return None


def revisar_ajuste(estado, tx, vistos: set | None = None) -> str:
    """Reglas estrictas de un ajuste dentro de un bloque. Devuelve su id o lanza ErrorValidacion."""
    motivo = problema_formato(tx)
    if motivo:
        raise ErrorValidacion(f"ajuste de dificultad inválido: {motivo}")
    if estado.dificultad_vigente is None:
        raise ErrorValidacion("ajuste de dificultad inválido: esta red no fija la dificultad en el génesis")
    if tx["dificultad"] == estado.dificultad_vigente:
        raise ErrorValidacion(f"ajuste de dificultad inválido: la dificultad {tx['dificultad']} ya es la vigente")
    if tx["proponente"] not in estado.claves:
        raise ErrorValidacion(f"ajuste de dificultad inválido: el proponente {tx['proponente'][:20]!r} no es laboratorio")
    for lab, firma in tx["firmas"].items():
        if lab not in estado.claves:
            raise ErrorValidacion(f"ajuste de dificultad inválido: {str(lab)[:20]!r} firmó pero no es laboratorio")
        if not _firma_correcta(tx, lab, firma, estado.claves):
            raise ErrorValidacion(f"ajuste de dificultad inválido: la firma de {lab} no corresponde a este ajuste")
    if tx["proponente"] not in tx["firmas"]:
        raise ErrorValidacion("ajuste de dificultad inválido: el proponente no lo firmó")
    n = len(estado.claves)
    if len(tx["firmas"]) < mayoria(n):
        raise ErrorValidacion(f"ajuste de dificultad sin mayoría: tiene {len(tx['firmas'])} firma(s) y se necesitan "
                              f"más de la mitad de {n} laboratorios ({mayoria(n)})")
    tid = id_ajuste(tx)
    if tid in estado.tx_ids:
        raise ErrorValidacion(f"el ajuste {tid[:12]}… ya está en la cadena")
    if vistos is not None and tid in vistos:
        raise ErrorValidacion(f"el ajuste {tid[:12]}… aparece dos veces en el bloque")
    return tid


def registrar_ajuste(estado, tx, tid: str, numero: int | None) -> None:
    """Anota el ajuste; la nueva dificultad rige desde el bloque siguiente (el bloque actual ya se validó)."""
    estado.ajustes.append({"numero": numero, "dificultad_anterior": estado.dificultad_vigente,
                           "dificultad": tx["dificultad"], "proponente": tx["proponente"],
                           "firmantes": sorted(tx["firmas"]), "id": tid})
    estado.dificultad_vigente = tx["dificultad"]
