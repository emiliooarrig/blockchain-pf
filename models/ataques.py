"""Laboratorio de casos: un nodo atacante fabrica una cadena o transacción inválida y la envía a la red.

Ningún ataque modifica la cadena real de ningún nodo: se trabaja sobre una copia y cada nodo receptor
la valida y la rechaza con el motivo correspondiente.
"""
from models.bloque import MAX_TX_POR_BLOQUE, copiar, hash_bloque, nueva_transaccion, preparar_hasher
from models.cripto import sha256_hex
from models.errores import ErrorEntrada, ErrorEstado
from models.pos import mensaje_propuesta, mensaje_voto
from models.pow import cumple_objetivo

LIMITE_MINADO_ATAQUE = 3_000_000

ATAQUES_CADENA = {
    "hash_alterado": ("Bloque con hash alterado", None),
    "hash_anterior_alterado": ("Bloque con hash_anterior alterado", None),
    "bloque_intermedio": ("Manipular un bloque intermedio", None),
    "cadena_corta": ("Cadena más corta", None),
    "cadena_mal_formada": ("Cadena con un bloque mal formado", None),
    "recompensa_falsa": ("Bloque con recompensa falsa", "pow"),
    "doble_gasto_bloque": ("Doble gasto dentro de un bloque", "pow"),
    "voto_no_validador": ("Voto de un nodo que no es validador", "pos"),
    "voto_doble": ("Un validador vota dos veces", "pos"),
}
ATAQUES_TX = {
    "firma_alterada": "Transacción con firma alterada",
    "otra_clave": "Transacción firmada con la clave de otro nodo",
    "repetida": "Reenviar una transacción ya minada (doble gasto entre bloques)",
    "doble_gasto": "Gastar dos veces el mismo saldo",
}


def catalogo(consenso: str) -> dict:
    return {
        "cadena": [{"id": k, "nombre": n} for k, (n, solo) in ATAQUES_CADENA.items() if solo in (None, consenso)],
        "transaccion": [{"id": k, "nombre": n} for k, n in ATAQUES_TX.items()],
    }


# ---------------------------------------------------------------- ataques a la cadena
def atacar_cadena(red, tipo: str, atacante_id: str | None) -> dict:
    if tipo not in ATAQUES_CADENA or ATAQUES_CADENA[tipo][1] not in (None, red.consenso):
        raise ErrorEntrada(f"Ataque desconocido para esta versión: {str(tipo)[:40]!r}.")
    nombre = ATAQUES_CADENA[tipo][0]
    with red.lock:
        atacante = red.nodo(atacante_id) if atacante_id else red.nodos[-1]
        cadena = copiar(atacante.cadena)
        altura = len(cadena) - 1
        descripcion = _FABRICAS[tipo](red, atacante, cadena, altura)
        resultado = red.difundir(atacante, f"una cadena manipulada ({nombre.lower()})", cadena=cadena)
    rechazos = sum(len(r["nodos"]) for r in resultado["rechazos"])
    total = len(red.nodos) - 1
    motivos = "; ".join(r["motivo"] for r in resultado["rechazos"])
    if resultado["aceptaron"]:
        return {"rechazado": False, "mensaje": f"⚠ {len(resultado['aceptaron'])} nodos aceptaron la cadena: {descripcion}"}
    return {"rechazado": True, "detalle": resultado,
            "mensaje": f"{nombre}: {descripcion} Los {rechazos}/{total} nodos la rechazaron y conservan su cadena. "
                       f"Motivo: {motivos}."}


def _exigir_altura(altura: int, minimo: int) -> None:
    if altura < minimo:
        raise ErrorEstado(f"Este caso necesita al menos {minimo} bloque(s) además del génesis; agrega bloques primero.")


def _f_hash_alterado(red, atacante, cadena, altura):
    _exigir_altura(altura, 1)
    b = cadena[-1]
    b["hash"] = ("1" if b["hash"][0] == "0" else "0") + b["hash"][1:]
    return f"{atacante.id} cambió el hash del bloque #{altura} sin cambiar su contenido."


def _f_hash_anterior(red, atacante, cadena, altura):
    _exigir_altura(altura, 1)
    b = cadena[-1]
    b["hash_anterior"] = sha256_hex("bloque previo falso")
    b["hash"] = hash_bloque(b)
    return f"{atacante.id} cambió el hash_anterior del bloque #{altura} y recalculó su hash."


def _f_bloque_intermedio(red, atacante, cadena, altura):
    _exigir_altura(altura, 2)
    k = altura // 2
    b = cadena[k]
    if red.consenso == "pow":
        # Se roba el bloque: cambia el proponente (y su recompensa) y lo vuelve a minar. El bloque k queda
        # válido por sí solo, pero el hash_anterior del bloque k+1 ya no coincide → se rechaza toda la cadena.
        nuevo = next(n.id for n in red.nodos if n.id != b["proponente"])
        b["proponente"] = nuevo
        _minar(b)
        return (f"{atacante.id} reescribió el bloque intermedio #{k} (proponente → {nuevo}) y lo volvió a minar; "
                f"el bloque #{k + 1} ya no enlaza con él.")
    tx = b["transacciones"][0]
    tx["monto"] += 1
    b["hash"] = hash_bloque(b)
    return f"{atacante.id} subió en 1 el monto de una transacción del bloque intermedio #{k} y recalculó su hash."


def _f_cadena_corta(red, atacante, cadena, altura):
    _exigir_altura(altura, 1)
    del cadena[-1]
    return f"{atacante.id} envió su cadena sin el último bloque (altura {altura - 1})."


def _f_mal_formada(red, atacante, cadena, altura):
    cadena.append({"numero": altura + 1, "datos": "esto no es un bloque", "hash": 42})
    return f"{atacante.id} agregó un bloque #{altura + 1} con campos inválidos."


def _bloque_pow_sobre(red, atacante, cadena, transacciones, recompensa) -> dict:
    tope = cadena[-1]
    b = {"numero": tope["numero"] + 1, "timestamp": red.reloj(), "transacciones": transacciones,
         "hash_anterior": tope["hash"], "nonce": 0, "proponente": atacante.id, "recompensa": recompensa,
         "dificultad": red.motor.config["dificultad"]}
    _minar(b)
    cadena.append(b)
    return b


def _f_recompensa_falsa(red, atacante, cadena, altura):
    establecida = red.referencia().estado.params["recompensa"]
    txs = copiar(red.pendientes[:MAX_TX_POR_BLOQUE]) or [_tx_valida(red)]
    falsa = establecida * 10
    b = _bloque_pow_sobre(red, atacante, cadena, txs, falsa)
    return (f"{atacante.id} minó el bloque #{b['numero']} (prueba de trabajo válida) reclamando una recompensa de "
            f"{falsa} en lugar de {establecida}.")


def _f_doble_gasto_bloque(red, atacante, cadena, altura):
    estado = red.referencia().estado
    emisor = max(red.nodos, key=lambda n: estado.saldos[n.id])
    saldo = estado.saldos[emisor.id]
    if saldo <= 0:
        raise ErrorEstado("Ningún nodo tiene saldo para intentar un doble gasto.")
    otros = [n for n in red.nodos if n is not emisor]
    txs = [nueva_transaccion(emisor.id, otros[0].id, saldo, red.reloj(), emisor.claves),
           nueva_transaccion(emisor.id, otros[1].id, saldo, red.reloj(), emisor.claves)]
    b = _bloque_pow_sobre(red, atacante, cadena, txs, estado.params["recompensa"])
    return (f"{atacante.id} minó el bloque #{b['numero']} con dos transacciones de {emisor.id} por {saldo} cada una "
            f"(su saldo es {saldo}).")


def _ultimo_bloque_pos(cadena, altura) -> dict:
    _exigir_altura(altura, 1)
    return cadena[-1]


def _f_voto_no_validador(red, atacante, cadena, altura):
    b = _ultimo_bloque_pos(cadena, altura)
    en_comite = {v["id"] for v in b["validadores"]}
    intruso = next((n for n in red.nodos if n.id not in en_comite), None)
    hp = sha256_hex(mensaje_propuesta(b))
    if intruso is None:
        # Todos los nodos estaban en el comité: el atacante inventa un votante ajeno y firma por él.
        falso = "N99"
        b["votos"].append({"validador": falso, "peso": 1, "a_favor": True,
                           "firma": atacante.claves.firmar(mensaje_voto(hp, falso, True))})
        b["hash"] = hash_bloque(b)
        return f"{atacante.id} agregó al bloque #{altura} un voto de {falso}, que no pertenece al comité de validadores."
    b["votos"].append({"validador": intruso.id, "peso": 1, "a_favor": True,
                       "firma": intruso.claves.firmar(mensaje_voto(hp, intruso.id, True))})
    b["hash"] = hash_bloque(b)
    return f"{atacante.id} agregó al bloque #{altura} un voto firmado por {intruso.id}, que no era validador."


def _f_voto_doble(red, atacante, cadena, altura):
    b = _ultimo_bloque_pos(cadena, altura)
    b["votos"].append(copiar(b["votos"][0]))
    b["hash"] = hash_bloque(b)
    return f"{atacante.id} duplicó en el bloque #{altura} el voto de {b['votos'][0]['validador']}."


_FABRICAS = {
    "hash_alterado": _f_hash_alterado,
    "hash_anterior_alterado": _f_hash_anterior,
    "bloque_intermedio": _f_bloque_intermedio,
    "cadena_corta": _f_cadena_corta,
    "cadena_mal_formada": _f_mal_formada,
    "recompensa_falsa": _f_recompensa_falsa,
    "doble_gasto_bloque": _f_doble_gasto_bloque,
    "voto_no_validador": _f_voto_no_validador,
    "voto_doble": _f_voto_doble,
}


def _minar(bloque: dict) -> None:
    calcular = preparar_hasher(bloque)
    for nonce in range(LIMITE_MINADO_ATAQUE):
        h = calcular(nonce)
        if cumple_objetivo(h, bloque["dificultad"]):
            bloque["nonce"], bloque["hash"] = nonce, h
            return
    raise ErrorEstado(f"El atacante no logró minar el bloque falso con dificultad {bloque['dificultad']} "
                      f"en {LIMITE_MINADO_ATAQUE:,} intentos; usa una dificultad menor.")


def _tx_valida(red) -> dict:
    estado = red.referencia().estado
    emisor = max(red.nodos, key=lambda n: estado.saldos[n.id])
    receptor = next(n for n in red.nodos if n is not emisor)
    return nueva_transaccion(emisor.id, receptor.id, 1, red.reloj(), emisor.claves)


# ---------------------------------------------------------------- ataques con transacciones
def atacar_transaccion(red, tipo: str, emisor_id: str | None) -> dict:
    if tipo not in ATAQUES_TX:
        raise ErrorEntrada(f"Caso de transacción desconocido: {str(tipo)[:40]!r}.")
    with red.lock:
        emisor = red.nodo(emisor_id) if emisor_id else max(red.nodos, key=lambda n: red.saldo_disponible(n.id))
        receptor = next(n for n in red.nodos if n is not emisor)
        disponible = red.saldo_disponible(emisor.id)
        if tipo == "repetida":
            minada = next((tx for b in reversed(red.referencia().cadena[1:]) for tx in b["transacciones"]), None)
            if minada is None:
                raise ErrorEstado("Todavía no hay transacciones minadas que reenviar; agrega un bloque primero.")
            return _enviar(red, copiar(minada), f"Se reenvió la transacción ya minada {minada['emisor']} → "
                                                f"{minada['receptor']} por {minada['monto']}.")
        if disponible <= 0:
            raise ErrorEstado(f"{emisor.id} no tiene saldo disponible para este caso; elige otro nodo.")
        if tipo == "firma_alterada":
            tx = nueva_transaccion(emisor.id, receptor.id, 1, red.reloj(), emisor.claves)
            tx["monto"] = disponible  # se cambia el monto después de firmar
            return _enviar(red, tx, f"{emisor.id} firmó un envío de 1 a {receptor.id} y luego el monto se cambió a "
                                    f"{disponible} sin volver a firmar.")
        if tipo == "otra_clave":
            impostor = next(n for n in red.nodos if n is not emisor and n is not receptor)
            tx = nueva_transaccion(emisor.id, impostor.id, 1, red.reloj(), impostor.claves)
            return _enviar(red, tx, f"{impostor.id} intentó gastar fondos de {emisor.id} firmando con su propia clave.")
        # doble_gasto: el primer gasto es válido y entra a pendientes; el segundo, sobre el mismo saldo, no.
        primera = nueva_transaccion(emisor.id, receptor.id, disponible, red.reloj(), emisor.claves)
        red.agregar_pendiente(primera, origen=" (caso doble gasto, primer envío)")
        otro = next(n for n in red.nodos if n is not emisor and n is not receptor)
        segunda = nueva_transaccion(emisor.id, otro.id, disponible, red.reloj(), emisor.claves)
        return _enviar(red, segunda, f"{emisor.id} envió {disponible} a {receptor.id} (aceptada) y luego intentó "
                                     f"enviar los mismos {disponible} a {otro.id}.")


def _enviar(red, tx, descripcion: str) -> dict:
    try:
        red.agregar_pendiente(tx, origen=" (caso de prueba)")
    except ErrorEntrada as exc:
        return {"rechazado": True, "mensaje": f"{descripcion} {exc}"}
    return {"rechazado": False, "mensaje": f"⚠ {descripcion} La transacción fue aceptada."}
