"""Certificado de prioridad verificable offline (contrato C6).

El certificado reúne lo mínimo para que un tercero, sin la red ni este proyecto, compruebe que un documento fue
sellado: el sello completo, su prueba de Merkle, el génesis y los encabezados de la cadena hasta la punta.
La verificación la hace `verificar_certificado.py`, que no importa nada de `models/`.
"""
import copy
import time
from datetime import datetime, timezone

from models import merkle
from models.cripto import es_hex
from models.errores import ErrorEntrada

FORMATO = "sellalo-certificado"
VERSION = 1


def _buscar_sello(cadena: list, doc_hash: str):
    """Sello más antiguo: menor número de bloque y, dentro del bloque, menor índice."""
    for posicion, bloque in enumerate(cadena):
        for indice, tx in enumerate(bloque.get("transacciones", [])):
            if isinstance(tx, dict) and tx.get("tipo") == "sello" and tx.get("doc_hash") == doc_hash:
                return posicion, indice
    return None


def _ajustes_de_dificultad(cadena: list) -> list:
    """Cada ajuste de dificultad de la cadena con su número de bloque y su prueba de Merkle (C9): el verificador los
    necesita para saber qué dificultad rige en cada encabezado."""
    salida = []
    for bloque in cadena[1:]:
        txs = bloque.get("transacciones", [])
        for indice, tx in enumerate(txs):
            if isinstance(tx, dict) and tx.get("tipo") == "ajuste_dificultad":
                hojas = [merkle.hoja_tx(t) for t in txs]
                salida.append({"bloque": bloque["numero"], "tx": copy.deepcopy(tx),
                               "prueba_merkle": {"hoja": hojas[indice], "indice": indice,
                                                 "camino": merkle.camino(hojas, indice)}})
    return salida


def generar_certificado(cadena: list, doc_hash: str, emitido: float | None = None) -> dict:
    if not es_hex(doc_hash, 64):
        raise ErrorEntrada("el hash del documento debe ser SHA-256 en hexadecimal minúscula (64 caracteres)")
    if not cadena:
        raise ErrorEntrada("la cadena está vacía")
    hallado = _buscar_sello(cadena, doc_hash)
    if hallado is None:
        raise ErrorEntrada("el documento no está sellado en esta cadena")
    posicion, indice = hallado
    bloque = cadena[posicion]
    hojas = [merkle.hoja_tx(tx) for tx in bloque["transacciones"]]
    return {
        "formato": FORMATO,
        "version": VERSION,
        "emitido": float(time.time() if emitido is None else emitido),
        "doc_hash": doc_hash,
        "sello": copy.deepcopy(bloque["transacciones"][indice]),
        "prueba_merkle": {"hoja": hojas[indice], "indice": indice, "camino": merkle.camino(hojas, indice)},
        "numero_bloque": bloque["numero"],
        "ajustes": _ajustes_de_dificultad(cadena),
        "genesis": copy.deepcopy(cadena[0]),
        "encabezados": [copy.deepcopy({k: v for k, v in b.items() if k != "transacciones"}) for b in cadena[1:]],
    }


def resumen_certificado(cert: dict) -> dict:
    """Datos legibles del certificado para la interfaz (no lo verifica)."""
    sello = cert.get("sello", {})
    numero = cert.get("numero_bloque")
    encabezados = cert.get("encabezados", [])
    fecha, punta = "", numero
    for h in encabezados:
        if h.get("numero") == numero:
            fecha = datetime.fromtimestamp(h["timestamp"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if encabezados:
        punta = encabezados[-1].get("numero", numero)
    return {
        "doc_hash": cert.get("doc_hash"),
        "titulo": sello.get("titulo"),
        "investigador": sello.get("investigador"),
        "laboratorio": sello.get("laboratorio"),
        "autores": sello.get("autores"),
        "umbral": sello.get("umbral"),
        "bloque": numero,
        "fecha": fecha,
        "confirmaciones": (punta - numero) if isinstance(punta, int) and isinstance(numero, int) else None,
    }
