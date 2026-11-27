"""Ataques de demostración contra la red Sellalo (contrato C7, ruta /ataques).

Cada ataque fabrica una manipulación sobre una COPIA de la cadena del nodo y la entrega al propio nodo (`local`) o la
envía además a sus pares (`red`). Ninguna honrada cambia: los nodos validan y rechazan, y aquí se informa el motivo.
Las manipulaciones se firman con la clave del propio nodo (por eso debe estar desbloqueado), de modo que el rechazo
sea por la regla que se quiere mostrar (prueba de trabajo, firma, multifirma, Merkle) y no por una firma ajena.
"""
import time

from models import merkle
from models.bloque import copiar, hash_bloque, nueva_transaccion
from models.cripto import sha256_hex
from models.errores import ErrorEntrada, ErrorEstado
from models.multifirma import agregar_firma, es_sello, mensaje_sello, nuevo_sello
from models.pow import cumple_objetivo

LIMITE_MINADO = 3_000_000
DIF_REMINADO_MAX = 4          # al alterar un bloque ya minado se vuelve a minar sólo si es barato

TIPOS = {
    "sello_alterado": "Cambiar el título de un sello ya minado (y rehacer raíz, hash y firma)",
    "firma_falsa": "Transferencia con la firma alterada",
    "merkle_falsa": "Bloque cuya raíz de Merkle no corresponde a sus transacciones",
    "cadena_corta": "Cadena más corta que la honrada",
    "multifirma_incompleta": "Bloque con un sello 2-de-2 que sólo trae una firma",
    "firma_minero_ajena": "Bloque que dice ser de otro laboratorio pero lo firma este nodo",
}
DESTINOS = ("local", "red")


class _Firmador:
    """Adapta nodo.firmar a la interfaz que espera nueva_transaccion (objeto con .firmar)."""

    def __init__(self, nodo):
        self.nodo = nodo

    def firmar(self, datos: bytes) -> str:
        return self.nodo.firmar(datos)


def _minar(bloque: dict, dificultad: int) -> None:
    bloque["dificultad"] = dificultad
    bloque["nonce"] = 0
    while True:
        h = hash_bloque(bloque)
        if cumple_objetivo(h, dificultad):
            bloque["hash"] = h
            return
        bloque["nonce"] += 1
        if bloque["nonce"] > LIMITE_MINADO:
            raise ErrorEstado("No se pudo preparar el ataque (la prueba de trabajo exigida es demasiado alta).")


def _firmar_bloque(nodo, bloque: dict) -> None:
    bloque["firma_minero"] = nodo.firmar(bytes.fromhex(bloque["hash"]))


def _bloque_sobre(nodo, cadena: list, txs: list, proponente: str | None = None, raiz: str | None = None) -> dict:
    anterior = cadena[-1]
    b = {"numero": anterior["numero"] + 1, "timestamp": max(time.time(), anterior["timestamp"]),
         "transacciones": txs, "hash_anterior": anterior["hash"],
         "raiz_merkle": raiz or merkle.raiz_transacciones(txs), "nonce": 0,
         "proponente": proponente or nodo.id, "recompensa": nodo.genesis["parametros"]["recompensa"]}
    _minar(b, 1)
    _firmar_bloque(nodo, b)
    return b


def _sello_propio(nodo, autores: list, umbral: int, firmar_todos: bool = True) -> dict:
    claves = {nid: c["clave_publica"] for nid, c in nodo.genesis["cuentas"].items()}
    sello = nuevo_sello(sha256_hex(f"ataque|{nodo.id}|{time.time()}"), "Sello de demostración (ataque)",
                        "Atacante", nodo.id, autores, umbral, time.time())
    return agregar_firma(sello, nodo.id, nodo.firmar(mensaje_sello(sello)), claves)


def _otro_lab(nodo) -> str:
    for nid in sorted(nodo.genesis["cuentas"]):
        if nid != nodo.id:
            return nid
    raise ErrorEstado("La red sólo tiene un laboratorio; no hay contra quién atacar.")


# ---------------------------------------------------------------- fábricas: devuelven (tipo_entrega, objeto, descripción)
def _sello_alterado(nodo, cadena):
    k = next((i for i in range(len(cadena) - 1, 0, -1)
              if any(es_sello(t) for t in cadena[i]["transacciones"])), None)
    if k is None:
        raise ErrorEstado("No hay ningún sello minado que alterar: sella un documento y mina un bloque primero.")
    cadena = cadena[:k + 1]
    bloque = cadena[k]
    sello = next(t for t in bloque["transacciones"] if es_sello(t))
    sello["titulo"] = (sello["titulo"] + " [ALTERADO]")[:120]
    bloque["raiz_merkle"] = merkle.raiz_transacciones(bloque["transacciones"])
    if bloque["dificultad"] <= DIF_REMINADO_MAX:
        _minar(bloque, bloque["dificultad"])
    else:
        bloque["hash"] = hash_bloque(bloque)
    if bloque["proponente"] == nodo.id:
        _firmar_bloque(nodo, bloque)
    return "cadena", cadena, (f"se cambió el título de un sello del bloque #{bloque['numero']} y se recalcularon "
                              f"raíz de Merkle, hash y firma del minero")


def _firma_falsa(nodo, cadena):
    tx = nueva_transaccion(nodo.id, _otro_lab(nodo), 1, time.time(), _Firmador(nodo))
    tx["firma"] = ("1" if tx["firma"][0] == "0" else "0") + tx["firma"][1:]
    return "tx", tx, "transferencia con un carácter de la firma cambiado"


def _merkle_falsa(nodo, cadena):
    sello = _sello_propio(nodo, [nodo.id], 1)
    b = _bloque_sobre(nodo, cadena, [sello], raiz=sha256_hex("raiz de Merkle falsa"))
    return "bloque", b, "bloque nuevo con una raíz de Merkle inventada (recalculando hash y firma)"


def _cadena_corta(nodo, cadena):
    if len(cadena) < 2:
        raise ErrorEstado("La cadena sólo tiene el génesis: mina al menos un bloque para poder acortarla.")
    return "cadena", cadena[:-1], f"la cadena honrada sin su último bloque (#{cadena[-1]['numero']})"


def _multifirma_incompleta(nodo, cadena):
    sello = _sello_propio(nodo, sorted([nodo.id, _otro_lab(nodo)]), 2)
    b = _bloque_sobre(nodo, cadena, [sello])
    return "bloque", b, "bloque con un sello 2-de-2 que sólo trae la firma del laboratorio que lo registra"


def _firma_minero_ajena(nodo, cadena):
    ajeno = _otro_lab(nodo)
    b = _bloque_sobre(nodo, cadena, [_sello_propio(nodo, [nodo.id], 1)], proponente=ajeno)
    return "bloque", b, f"bloque que dice ser minado por {ajeno} pero firmado con la clave de {nodo.id}"


_FABRICAS = {"sello_alterado": _sello_alterado, "firma_falsa": _firma_falsa, "merkle_falsa": _merkle_falsa,
             "cadena_corta": _cadena_corta, "multifirma_incompleta": _multifirma_incompleta,
             "firma_minero_ajena": _firma_minero_ajena}


def catalogo() -> list[dict]:
    return [{"id": k, "nombre": v} for k, v in TIPOS.items()]


def ejecutar(nodo, servidor, tipo: str, destino: str) -> dict:
    """Fabrica y entrega el ataque. Devuelve {rechazado, motivos, mensaje, ...}."""
    if tipo not in TIPOS:
        raise ErrorEntrada(f"Ataque desconocido: {str(tipo)[:40]!r}. Opciones: {', '.join(TIPOS)}.")
    if destino not in DESTINOS:
        raise ErrorEntrada("El destino debe ser local o red.")
    if not nodo.desbloqueado:
        raise ErrorEstado("Desbloquea el nodo para lanzar un ataque: la manipulación se firma con la clave propia.")
    if destino == "red" and (servidor is None or not servidor.activo):
        raise ErrorEstado("No hay conexión P2P: desbloquea el nodo y conéctalo a otros laboratorios para atacar la red.")
    with nodo.lock:
        cadena = copiar(nodo.cadena)          # copia profunda: la cadena honrada nunca se toca
        punta = nodo.punta
    forma, objeto, descripcion = _FABRICAS[tipo](nodo, cadena)

    if forma == "cadena":
        aceptada, motivo = nodo.recibir_cadena(objeto, de="atacante")
        motivos = [motivo]
        rechazado = not aceptada
        pieza = ("BLOQUE", {"bloque": objeto[-1]})
    elif forma == "bloque":
        estado, motivo = nodo.recibir_bloque(objeto, de="atacante")
        motivos = [motivo]
        rechazado = estado != "aceptado"
        pieza = ("BLOQUE", {"bloque": objeto})
    else:
        try:
            nodo.agregar_transaccion(objeto, origen="atacante")
            motivos, rechazado = ["la transacción fue aceptada"], False
        except ErrorEntrada as exc:
            motivos, rechazado = [str(exc)], True
        pieza = ("TX", {"tx": objeto})

    enviados = 0
    if destino == "red":
        enviados = servidor.difundir(*pieza)
    with nodo.lock:
        intacta = nodo.punta == punta or not rechazado
    nombre = TIPOS[tipo]
    if rechazado:
        mensaje = (f"{nombre}: {descripcion}. {'Se envió a ' + str(enviados) + ' par(es); ' if destino == 'red' else ''}"
                   f"el nodo la rechazó y conserva su cadena. Motivo: {motivos[0]}")
    else:
        mensaje = f"ATENCIÓN: la manipulación fue aceptada ({descripcion})."
    return {"tipo": tipo, "destino": destino, "rechazado": rechazado, "motivos": motivos, "enviados": enviados,
            "cadena_intacta": intacta, "mensaje": mensaje}
