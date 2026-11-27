"""Árbol de Merkle de las transacciones de un bloque y pruebas de inclusión.

Regla (igual en el nodo y en el verificador independiente `verificar_certificado.py`):
- hoja = SHA-256 hex del JSON canónico de la transacción COMPLETA (incluidas sus firmas);
- padre = SHA-256 hex de la concatenación de los dos hijos en hexadecimal (texto, no bytes);
- si un nivel tiene un número impar de nodos, el último se duplica;
- la raíz de una lista vacía es SHA-256(b"").
"""
from models.cripto import canonico, es_hex, sha256_hex

RAIZ_VACIA = sha256_hex(b"")


def hoja_tx(tx: dict) -> str:
    """Hash de la hoja de una transacción (compromete también sus firmas)."""
    return sha256_hex(canonico(tx))


def raiz(hojas: list[str]) -> str:
    if not hojas:
        return RAIZ_VACIA
    nivel = list(hojas)
    while len(nivel) > 1:
        if len(nivel) % 2:
            nivel.append(nivel[-1])
        nivel = [sha256_hex(nivel[i] + nivel[i + 1]) for i in range(0, len(nivel), 2)]
    return nivel[0]


def raiz_transacciones(transacciones: list) -> str:
    return raiz([hoja_tx(tx) for tx in transacciones])


def camino(hojas: list[str], indice: int) -> list[dict]:
    """Prueba de inclusión de la hoja `indice`: lista de hermanos desde la hoja hasta la raíz.
    `lado` indica dónde está el hermano: "izq" → padre = H(hermano + actual); "der" → padre = H(actual + hermano)."""
    if not 0 <= indice < len(hojas):
        raise IndexError("índice de hoja fuera de rango")
    pasos, nivel, i = [], list(hojas), indice
    while len(nivel) > 1:
        if len(nivel) % 2:
            nivel.append(nivel[-1])
        if i % 2:
            pasos.append({"lado": "izq", "hash": nivel[i - 1]})
        else:
            pasos.append({"lado": "der", "hash": nivel[i + 1]})
        nivel = [sha256_hex(nivel[j] + nivel[j + 1]) for j in range(0, len(nivel), 2)]
        i //= 2
    return pasos


def verificar_camino(hoja: str, pasos, raiz_esperada: str) -> bool:
    if not es_hex(hoja, 64) or not es_hex(raiz_esperada, 64) or not isinstance(pasos, list) or len(pasos) > 64:
        return False
    actual = hoja
    for paso in pasos:
        if not isinstance(paso, dict) or paso.get("lado") not in ("izq", "der") or not es_hex(paso.get("hash"), 64):
            return False
        actual = sha256_hex(paso["hash"] + actual) if paso["lado"] == "izq" else sha256_hex(actual + paso["hash"])
    return actual == raiz_esperada
