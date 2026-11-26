"""Versión 2: Proof of Stake con comité de validadores, apuestas, sorteo ponderado y votación.

Ronda como máquina de estados:
    APUESTAS → SORTEO → CANDIDATO → VOTACION → ACEPTADO
                  ↑                         ↘ RECHAZADO (castigo al proponente; nuevo sorteo con los restantes)
                  └──────────────────────────┘           ↘ FALLIDA (ya no quedan validadores)

Todo lo que ocurre en la ronda queda en el bloque aceptado (validadores y apuestas, intento, excluidos,
castigos, firma del proponente y votos firmados), así cualquier nodo puede volver a comprobar el sorteo,
los castigos y el umbral de 2/3 al validar la cadena completa.
"""
import hashlib

from models import merkle
from models.bloque import (CAMPOS_POS, MAX_TX_POR_BLOQUE, MONTO_MAX, ErrorValidacion, copiar, es_entero, hash_bloque,
                           nueva_transaccion)
from models.cripto import LARGO_FIRMA_HEX, canonico, es_hex, sha256_hex, verificar
from models.errores import ErrorEntrada, ErrorEstado

REGLAS_CASTIGO = ("A", "B")
FRAUDES = ("firma", "gasto")
CONFIG_INICIAL = {"tam_comite": 0, "regla": "A", "alfa_pct": 50, "fraude": "firma"}
ESTADOS_ACTIVOS = ("APUESTAS", "SORTEO", "CANDIDATO", "VOTACION", "RECHAZADO")
CAMPOS_CASTIGO = ("validador", "apuesta", "valor_transacciones", "regla", "alfa_pct", "monto", "motivo", "hash_propuesta")
# AUD-007: cada castigo trae la prueba del fraude: el candidato rechazado (sin hash ni votos) con la firma de su proponente.
CAMPOS_CASTIGO_PRUEBA = CAMPOS_CASTIGO + ("propuesta",)
CAMPOS_VOTO = ("validador", "peso", "a_favor", "firma")


# ---------------------------------------------------------------- reglas (sin estado)
def sortear(validadores: list, hash_anterior: str, numero: int, intento: int):
    """Sorteo ponderado con semilla pública y reproducible: P(i) = a_i / A (intervalos acumulados).
    `validadores` es una lista de {"id", "apuesta"} en orden fijo (por id)."""
    semilla = f"{hash_anterior}|{numero}|{intento}".encode()
    total = sum(v["apuesta"] for v in validadores)
    if total <= 0:
        return None, None
    r = int(hashlib.sha256(semilla).hexdigest(), 16) % total
    acumulado = 0
    for v in validadores:
        acumulado += v["apuesta"]
        if r < acumulado:
            return v, r
    return None, None


def comite_derivado(candidatos: list, hash_anterior: str, numero: int, tam: int) -> list:
    """Comité reproducible (AUD-006): con `tam` >= nodos con saldo, todos; si no, los `tam` nodos cuyo
    SHA-256(`hash_anterior|numero|id`) es menor. Depende sólo de la cadena y de `tam`; nadie lo elige a mano."""
    candidatos = sorted(candidatos)
    if tam >= len(candidatos):
        return candidatos
    clave = lambda nid: hashlib.sha256(f"{hash_anterior}|{numero}|{nid}".encode()).hexdigest()
    return sorted(sorted(candidatos, key=clave)[:tam])


def calcular_castigo(regla: str, apuesta: int, valor_transacciones: int, alfa_pct: int) -> int:
    """(A) c = a_p      (B) c = min(a_p, ⌈α · valor de las transacciones⌉), con α = alfa_pct / 100 y c ≥ 1."""
    if regla == "A":
        return apuesta
    return min(apuesta, max(1, -(-alfa_pct * valor_transacciones // 100)))


def mensaje_propuesta(bloque: dict) -> bytes:
    """Lo que firma el proponente: el bloque candidato sin votos, sin hash y sin su propia firma.
    Las pruebas de fraude de los castigos (`propuesta`) no entran: se verifican aparte y así una prueba puede
    guardarse sin las pruebas anidadas de sus propios castigos (si no, el tamaño crecería exponencialmente)."""
    datos = {k: v for k, v in bloque.items() if k not in ("hash", "votos", "firma_proponente")}
    if isinstance(datos.get("castigos"), list):
        datos["castigos"] = [{k: v for k, v in c.items() if k != "propuesta"} if isinstance(c, dict) else c
                             for c in datos["castigos"]]
    return canonico(datos)


def prueba_de_propuesta(candidato: dict) -> dict:
    """Copia del candidato rechazado para usarla como prueba: sin pruebas anidadas (no se firman, ver arriba)."""
    p = copiar(candidato)
    p["castigos"] = [{k: v for k, v in c.items() if k != "propuesta"} for c in p["castigos"]]
    return p


def mensaje_voto(hash_propuesta: str, validador: str, a_favor: bool) -> bytes:
    return canonico({"propuesta": hash_propuesta, "validador": validador, "a_favor": a_favor})


def _revisar_prueba(base, bloque: dict, c: dict, k: int | None = None) -> None:
    """AUD-007: el castigo sólo vale si trae el candidato rechazado, firmado por el castigado, y ese candidato
    resulta INVÁLIDO al revalidarlo contra el estado previo. `k` = posición en `excluidos` (castigos de esta ronda)."""
    from models.validacion import validar_bloque
    p = c["propuesta"]
    if not isinstance(p, dict) or set(p) != set(CAMPOS_POS):
        raise ErrorValidacion(f"el castigo de {c['validador']} no trae la propuesta rechazada (prueba de fraude)")
    try:
        mensaje = mensaje_propuesta(p)
        hp = sha256_hex(mensaje)
        valor = sum(tx["monto"] for tx in p["transacciones"])
        apuesta = next((v["apuesta"] for v in p["validadores"] if v["id"] == c["validador"]), None)
        firma_ok = es_hex(p["firma_proponente"], LARGO_FIRMA_HEX) and verificar(
            base.claves[c["validador"]], mensaje, p["firma_proponente"])
    except (TypeError, KeyError, ValueError, AttributeError):
        raise ErrorValidacion(f"la prueba del castigo de {c['validador']} es ilegible") from None
    if p["hash"] != "" or p["votos"] != []:
        raise ErrorValidacion("la prueba debe ser la propuesta sin hash ni votos")
    if p["proponente"] != c["validador"] or p["numero"] != bloque["numero"]             or p["hash_anterior"] != bloque["hash_anterior"]:
        raise ErrorValidacion(f"la prueba del castigo de {c['validador']} no corresponde a este bloque ni a su proponente")
    if hp != c["hash_propuesta"] or valor != c["valor_transacciones"] or apuesta != c["apuesta"]:
        raise ErrorValidacion(f"la prueba del castigo de {c['validador']} no coincide con el registro del castigo")
    if not firma_ok:
        raise ErrorValidacion(f"la firma del proponente en la prueba del castigo de {c['validador']} es inválida")
    if k is not None and (p["intento"] != k or p["excluidos"] != bloque["excluidos"][:k]):
        raise ErrorValidacion(f"la prueba del castigo de {c['validador']} no es del intento {k} de esta ronda")
    try:
        validar_bloque(base.copia(), p, propuesta=True, sin_pruebas=True)
    except ErrorValidacion:
        return                                   # la propuesta era inválida: el fraude está probado
    except (TypeError, KeyError, ValueError, AttributeError):
        return
    raise ErrorValidacion(f"castigo sin fundamento: la propuesta de {c['validador']} es válida")


def _revisar_castigo(estado, c, con_prueba: bool = True) -> None:
    if not isinstance(c, dict) or set(c) != set(CAMPOS_CASTIGO_PRUEBA if con_prueba else CAMPOS_CASTIGO):
        raise ErrorValidacion("registro de castigo con formato inválido (¿falta la prueba de fraude?)"
                              if con_prueba else "registro de castigo con formato inválido")
    if c["validador"] not in estado.claves:
        raise ErrorValidacion(f"castigo a un nodo inexistente ({c['validador']!r})")
    if not es_entero(c["apuesta"]) or c["apuesta"] <= 0 or not es_entero(c["valor_transacciones"]) \
            or c["valor_transacciones"] < 0 or c["regla"] not in REGLAS_CASTIGO \
            or not es_entero(c["alfa_pct"]) or not 1 <= c["alfa_pct"] <= 100 or not isinstance(c["motivo"], str) \
            or not es_hex(c["hash_propuesta"], 64):
        raise ErrorValidacion("registro de castigo con valores inválidos")
    esperado = calcular_castigo(c["regla"], c["apuesta"], c["valor_transacciones"], c["alfa_pct"])
    if c["monto"] != esperado:
        raise ErrorValidacion(f"castigo de {c['validador']} por {c['monto']!r}, pero la regla {c['regla']} da {esperado}")
    if estado.saldos[c["validador"]] < c["apuesta"]:
        raise ErrorValidacion(f"castigo sobre una apuesta ({c['apuesta']}) mayor al saldo de {c['validador']}")
    estado.saldos[c["validador"]] -= c["monto"]


def verificar_pos(estado, bloque: dict, con_votos: bool = True, sin_pruebas: bool = False) -> None:
    """Regla de consenso PoS. Modifica `estado` aplicando los castigos registrados en el bloque.
    `sin_pruebas=True` sólo se usa al revalidar una propuesta aportada como prueba de fraude (sus castigos
    anidados no llevan prueba; ver mensaje_propuesta)."""
    base = estado.copia()
    validadores, excluidos, castigos = bloque["validadores"], bloque["excluidos"], bloque["castigos"]
    if not isinstance(validadores, list) or not validadores:
        raise ErrorValidacion("el bloque no registra validadores")
    if not isinstance(excluidos, list) or not isinstance(castigos, list) or not isinstance(bloque["votos"], list):
        raise ErrorValidacion("excluidos, castigos o votos con formato inválido")
    ids = []
    for v in validadores:
        if not isinstance(v, dict) or set(v) != {"id", "apuesta"} or v["id"] not in estado.claves:
            raise ErrorValidacion("validador con formato inválido o inexistente")
        if not es_entero(v["apuesta"]) or v["apuesta"] <= 0:
            raise ErrorValidacion(f"apuesta inválida de {v['id']} ({v['apuesta']!r}); debe ser mayor que cero")
        ids.append(v["id"])
    if ids != sorted(set(ids)):
        raise ErrorValidacion("validadores repetidos o fuera de orden")
    apuesta_de = {v["id"]: v["apuesta"] for v in validadores}
    if len(set(excluidos)) != len(excluidos) or any(e not in apuesta_de for e in excluidos):
        raise ErrorValidacion("lista de excluidos inválida")
    if len(castigos) < len(excluidos):
        raise ErrorValidacion("hay validadores excluidos sin su castigo registrado")

    # 1) castigos de rondas anteriores que fallaron por completo
    corte = len(castigos) - len(excluidos)
    for c in castigos[:corte]:
        _revisar_castigo(estado, c, not sin_pruebas)
        if not sin_pruebas:
            _revisar_prueba(base, bloque, c)
    # 1b) el comité debe ser derivable del estado: todos los nodos con saldo, o el subconjunto reproducible de su tamaño
    con_saldo = [nid for nid in estado.claves if estado.saldos[nid] > 0]
    esperado = comite_derivado(con_saldo, bloque["hash_anterior"], bloque["numero"], len(ids))
    if ids != esperado:
        raise ErrorValidacion("el comité de validadores no es el que se deriva del estado de la cadena "
                              "(todos los nodos con saldo o el subconjunto reproducible de ese tamaño)")
    # 2) las apuestas de esta ronda no pueden superar el saldo
    for v in validadores:
        if v["apuesta"] > estado.saldos[v["id"]]:
            raise ErrorValidacion(f"apuesta de {v['id']} ({v['apuesta']}) mayor a su saldo ({estado.saldos[v['id']]})")
    # 3) castigos de esta ronda: uno por cada proponente rechazado, en orden
    for k, (c, ex) in enumerate(zip(castigos[corte:], excluidos)):
        if not isinstance(c, dict) or c.get("validador") != ex or c.get("apuesta") != apuesta_de[ex]:
            raise ErrorValidacion(f"el castigo de {ex} no corresponde a su apuesta en esta ronda")
        _revisar_castigo(estado, c, not sin_pruebas)
        if not sin_pruebas:
            _revisar_prueba(base, bloque, c, k)
    # 4) el sorteo se repite con los validadores restantes y debe dar los mismos resultados
    if bloque["intento"] != len(excluidos):
        raise ErrorValidacion("el número de intento no coincide con los proponentes rechazados")
    restantes = list(validadores)
    for k, ex in enumerate(excluidos):
        elegido, _ = sortear(restantes, bloque["hash_anterior"], bloque["numero"], k)
        if elegido is None or elegido["id"] != ex:
            raise ErrorValidacion(f"el sorteo del intento {k} no eligió a {ex}")
        restantes.remove(elegido)
    elegido, _ = sortear(restantes, bloque["hash_anterior"], bloque["numero"], bloque["intento"])
    if elegido is None or elegido["id"] != bloque["proponente"]:
        raise ErrorValidacion(f"{bloque['proponente']} no es el proponente que dicta el sorteo ponderado")
    # 5) el proponente firmó el bloque candidato
    if not es_hex(bloque["firma_proponente"], LARGO_FIRMA_HEX) or not verificar(
            estado.claves[bloque["proponente"]], mensaje_propuesta(bloque), bloque["firma_proponente"]):
        raise ErrorValidacion(f"firma del proponente {bloque['proponente']} inválida")
    if con_votos:
        verificar_votos(estado, bloque, restantes)


def verificar_votos(estado, bloque: dict, restantes: list) -> None:
    peso_de = {v["id"]: v["apuesta"] for v in restantes}
    total = sum(peso_de.values())
    hp = sha256_hex(mensaje_propuesta(bloque))
    a_favor, vistos = 0, set()
    for voto in bloque["votos"]:
        if not isinstance(voto, dict) or set(voto) != set(CAMPOS_VOTO):
            raise ErrorValidacion("voto con formato inválido")
        quien = voto["validador"]
        if quien not in peso_de:
            raise ErrorValidacion(f"voto de {quien!r}, que no es validador en esta ronda")
        if quien in vistos:
            raise ErrorValidacion(f"{quien} votó dos veces")
        vistos.add(quien)
        if voto["peso"] != peso_de[quien]:
            raise ErrorValidacion(f"el peso del voto de {quien} ({voto['peso']!r}) no coincide con su apuesta ({peso_de[quien]})")
        if type(voto["a_favor"]) is not bool:
            raise ErrorValidacion(f"voto de {quien} sin sentido válido")
        if not verificar(estado.claves[quien], mensaje_voto(hp, quien, voto["a_favor"]), voto["firma"]):
            raise ErrorValidacion(f"firma del voto de {quien} inválida")
        if voto["a_favor"]:
            a_favor += voto["peso"]
    if 3 * a_favor < 2 * total:
        raise ErrorValidacion(f"votos insuficientes: {a_favor} de {total} a favor (se requieren al menos 2/3)")


# ---------------------------------------------------------------- motor
class MotorPoS:
    def __init__(self, red):
        self.red = red
        self.config = dict(CONFIG_INICIAL)
        self.ronda = None
        self.castigos_pendientes = []   # castigos de rondas fallidas; se registran en el siguiente bloque aceptado
        self.contador = 0

    # ---------- utilidades ----------
    def activa(self) -> bool:
        return self.ronda is not None and self.ronda["estado"] in ESTADOS_ACTIVOS

    def _exigir(self, *estados) -> dict:
        if self.ronda is None or self.ronda["estado"] not in ESTADOS_ACTIVOS:
            raise ErrorEstado("No hay una ronda PoS en curso; inicia una ronda primero.")
        if self.ronda["estado"] not in estados:
            raise ErrorEstado(f"Acción no permitida en la etapa {self.ronda['estado']} "
                              f"(se requiere {' o '.join(estados)}).")
        return self.ronda

    def retenido(self, nodo_id: str) -> int:
        """Saldo que el nodo no puede gastar: apuesta bloqueada en la ronda y castigos aún no registrados."""
        total = sum(c["monto"] for c in self.castigos_pendientes if c["validador"] == nodo_id)
        if self.activa():
            total += self.ronda["apuestas"].get(nodo_id) or 0
        return total

    def _restantes(self) -> list:
        r = self.ronda
        return [v for v in r["comite"] if v["id"] not in r["excluidos"]]

    def detener(self) -> None:
        pass

    # ---------- configuración ----------
    def configurar(self, tam_comite: int, regla: str, alfa_pct: int, fraude: str) -> str:
        n = len(self.red.nodos)
        if not es_entero(tam_comite) or not (tam_comite == 0 or 1 <= tam_comite <= n):
            raise ErrorEntrada(f"El tamaño del comité debe ser 0 (todos los nodos con saldo) o un entero entre 1 y {n}.")
        if regla not in REGLAS_CASTIGO:
            raise ErrorEntrada("La regla de castigo debe ser A o B.")
        if not es_entero(alfa_pct) or not 1 <= alfa_pct <= 100:
            raise ErrorEntrada("α debe ser un porcentaje entero entre 1 y 100.")
        if fraude not in FRAUDES:
            raise ErrorEntrada("El fraude del nodo deshonesto debe ser «firma» o «gasto».")
        with self.red.lock:
            if self.activa():
                raise ErrorEstado("No se puede cambiar la configuración con una ronda en curso.")
            self.config = {"tam_comite": tam_comite, "regla": regla, "alfa_pct": alfa_pct, "fraude": fraude}
            regla_txt = "A (c = apuesta completa)" if regla == "A" else f"B (c = min(apuesta, {alfa_pct}% del valor))"
            self.red.evento("pos", f"Configuración PoS: comité {'de todos los nodos con saldo' if not tam_comite else f'de {tam_comite} nodos'}, "
                                   f"castigo {regla_txt}, fraude del deshonesto: {fraude}.")
        return "Configuración de PoS guardada."

    # ---------- etapas ----------
    def iniciar_ronda(self) -> str:
        red = self.red
        with red.lock:
            if self.activa():
                raise ErrorEstado(f"Ya hay una ronda en curso (etapa {self.ronda['estado']}).")
            if not red.pendientes:
                raise ErrorEstado("No hay transacciones pendientes: el proponente no tendría nada que proponer. "
                                  "Crea al menos una transacción.")
            ref = red.referencia()
            if not any(red.saldo_disponible(n.id) > 0 for n in red.nodos):
                raise ErrorEstado("Ningún nodo tiene saldo disponible: no hay validadores posibles para la ronda.")
            self.contador += 1
            # El comité se deriva igual que lo exige la validación (AUD-006): nodos con saldo (tras castigos pendientes).
            con_saldo = [n.id for n in red.nodos
                         if ref.estado.saldos[n.id] - sum(c["monto"] for c in self.castigos_pendientes
                                                          if c["validador"] == n.id) > 0]
            tam = self.config["tam_comite"]
            con_saldo = comite_derivado(con_saldo, ref.ultimo_hash, ref.altura + 1, tam or len(con_saldo))
            self.ronda = {
                "id": self.contador, "estado": "APUESTAS", "numero": ref.altura + 1, "hash_anterior": ref.ultimo_hash,
                "validadores": con_saldo, "apuestas": {}, "comite": [], "excluidos": [], "castigos": [],
                "intento": 0, "proponente": None, "sorteo": None, "candidato": None, "hash_propuesta": None,
                "evaluaciones": {}, "votos": {}, "historial": [], "mensaje": "",
            }
            red.evento("pos", f"Ronda {self.contador} para el bloque #{ref.altura + 1}: {len(con_saldo)} validadores "
                              f"elegidos ({', '.join(con_saldo)}). Etapa APUESTAS.")
            return f"Ronda iniciada con {len(con_saldo)} validadores. Registra las apuestas."

    def apostar(self, nodo_id: str, monto: int) -> str:
        red = self.red
        with red.lock:
            r = self._exigir("APUESTAS")
            red.nodo(nodo_id)
            if nodo_id not in r["validadores"]:
                raise ErrorEntrada(f"{nodo_id} no es validador en esta ronda; no puede apostar.")
            if not es_entero(monto) or monto <= 0:
                raise ErrorEntrada("La apuesta debe ser un entero mayor que cero.")
            disponible = red.saldo_disponible(nodo_id) + (r["apuestas"].get(nodo_id) or 0)
            if monto > disponible:
                raise ErrorEntrada(f"Apuesta mayor al saldo: {nodo_id} sólo tiene {disponible} disponible.")
            r["apuestas"][nodo_id] = monto
            red.evento("pos", f"{nodo_id} apuesta {monto} (queda bloqueado durante la ronda).")
            return f"Apuesta de {nodo_id} registrada: {monto}."

    def apuestas_automaticas(self) -> str:
        red = self.red
        with red.lock:
            r = self._exigir("APUESTAS")
            rng = red.rng_derivado(f"apuestas|{r['hash_anterior']}|{r['id']}")
            hechas = 0
            for nid in r["validadores"]:
                if r["apuestas"].get(nid):
                    continue
                disponible = red.saldo_disponible(nid)
                if disponible <= 0:
                    continue
                r["apuestas"][nid] = rng.randint(max(1, disponible // 4), disponible)
                hechas += 1
            red.evento("pos", f"Apuestas automáticas: {hechas} validadores apostaron "
                              f"(total en juego: {sum(r['apuestas'].values())}).")
            return f"{hechas} apuestas automáticas registradas."

    def sortear_proponente(self) -> str:
        red = self.red
        with red.lock:
            r = self._exigir("APUESTAS", "SORTEO", "RECHAZADO")
            if r["estado"] == "APUESTAS":
                # Quien tiene todo su saldo comprometido en transacciones pendientes no puede apostar más: el comité
                # derivado lo incluye igual (AUD-006), así que participa con la apuesta mínima de 1.
                for nid in r["validadores"]:
                    if not r["apuestas"].get(nid) and red.saldo_disponible(nid) <= 0:
                        r["apuestas"][nid] = 1
                        red.evento("pos", f"{nid} no tiene saldo libre: participa con la apuesta mínima de 1.")
                comite = [{"id": nid, "apuesta": r["apuestas"][nid]} for nid in r["validadores"] if r["apuestas"].get(nid)]
                if not comite:
                    raise ErrorEstado("Ningún validador ha apostado; registra al menos una apuesta antes del sorteo.")
                sin_apuesta = [nid for nid in r["validadores"] if not r["apuestas"].get(nid)]
                if sin_apuesta:
                    raise ErrorEstado(f"Faltan las apuestas de {', '.join(sin_apuesta)}: el comité lo forman todos los "
                                      f"validadores derivados de la cadena y cada uno debe apostar (AUD-006).")
                r["comite"] = comite
            restantes = self._restantes()
            r["estado"] = "SORTEO"
            elegido, aleatorio = sortear(restantes, r["hash_anterior"], r["numero"], r["intento"])
            total = sum(v["apuesta"] for v in restantes)
            r["proponente"] = elegido["id"]
            r["sorteo"] = {"r": aleatorio, "A": total, "intento": r["intento"],
                           "probabilidad": round(100 * elegido["apuesta"] / total, 2)}
            r["candidato"], r["hash_propuesta"], r["votos"], r["evaluaciones"] = None, None, {}, {}
            r["estado"] = "CANDIDATO"
            red.evento("pos", f"Sorteo (intento {r['intento']}): semilla = hash_anterior|{r['numero']}|{r['intento']}, "
                              f"r = {aleatorio} mod A={total} → proponente {elegido['id']} "
                              f"(apuesta {elegido['apuesta']}, probabilidad {r['sorteo']['probabilidad']}%).")
            return f"Proponente sorteado: {elegido['id']}."

    def construir_candidato(self) -> str:
        red = self.red
        with red.lock:
            r = self._exigir("CANDIDATO")
            if red.referencia().ultimo_hash != r["hash_anterior"]:
                self._cerrar_ronda("CANCELADA", "La cadena cambió durante la ronda; se canceló.")
                raise ErrorEstado("La cadena cambió durante la ronda; se canceló. Inicia una nueva.")
            if not red.pendientes:
                raise ErrorEstado("La lista de transacciones pendientes está vacía: el proponente no puede construir "
                                  "un bloque. Crea una transacción y vuelve a intentarlo.")
            vigentes = [c for c in self.castigos_pendientes if c["propuesta"]["hash_anterior"] == r["hash_anterior"]]
            if len(vigentes) != len(self.castigos_pendientes):
                red.evento("pos", f"Se descartan {len(self.castigos_pendientes) - len(vigentes)} castigos pendientes "
                                  f"de rondas sobre otra cadena: su prueba ya no corresponde a este bloque.")
                self.castigos_pendientes = vigentes
            proponente = red.nodo(r["proponente"])
            bloque = {
                "numero": r["numero"], "timestamp": red.reloj(),
                "transacciones": copiar(red.pendientes[:MAX_TX_POR_BLOQUE]),
                "hash_anterior": r["hash_anterior"], "raiz_merkle": "", "nonce": 0, "proponente": proponente.id,
                "recompensa": red.referencia().estado.params["recompensa"],
                "validadores": copiar(r["comite"]), "intento": r["intento"], "excluidos": list(r["excluidos"]),
                "castigos": copiar(self.castigos_pendientes) + copiar(r["castigos"]),
                "firma_proponente": "", "votos": [], "hash": "",
            }
            fraude = ""
            if proponente.deshonesto:
                fraude = self._cometer_fraude(bloque, proponente)
            bloque["raiz_merkle"] = merkle.raiz_transacciones(bloque["transacciones"])
            bloque["firma_proponente"] = proponente.claves.firmar(mensaje_propuesta(bloque))
            r["candidato"] = bloque
            r["hash_propuesta"] = sha256_hex(mensaje_propuesta(bloque))
            r["estado"] = "VOTACION"
            valor = sum(tx["monto"] for tx in bloque["transacciones"])
            red.evento("pos", f"{proponente.id} construye y firma el bloque candidato #{r['numero']} con "
                              f"{len(bloque['transacciones'])} transacciones (valor {valor}).{fraude} Etapa VOTACION.")
            return f"Bloque candidato construido por {proponente.id}." + (" ⚠ Es deshonesto." if fraude else "")

    def _cometer_fraude(self, bloque: dict, proponente) -> str:
        red = self.red
        if self.config["fraude"] == "firma":
            tx = bloque["transacciones"][0]
            tx["firma"] = tx["firma"][:-1] + ("0" if tx["firma"][-1] != "0" else "1")
            return f" ⚠ {proponente.id} es deshonesto: alteró la firma de una transacción."
        saldo = red.referencia().estado.saldos[proponente.id]
        receptor = next(n.id for n in red.nodos if n.id != proponente.id)
        monto = min(MONTO_MAX, saldo + 1000)
        bloque["transacciones"] = bloque["transacciones"][:MAX_TX_POR_BLOQUE - 1]
        bloque["transacciones"].append(nueva_transaccion(proponente.id, receptor, monto, red.reloj(), proponente.claves))
        return f" ⚠ {proponente.id} es deshonesto: se transfiere {monto} teniendo sólo {saldo}."

    def votar(self, nodo_id: str, a_favor: bool, registrar: bool = True) -> str:
        red = self.red
        with red.lock:
            r = self._exigir("VOTACION")
            red.nodo(nodo_id)
            if type(a_favor) is not bool:
                raise ErrorEntrada("El voto debe ser a favor (true) o en contra (false).")
            if nodo_id in r["excluidos"]:
                raise ErrorEntrada(f"{nodo_id} fue castigado en esta ronda y ya no puede votar.")
            pesos = {v["id"]: v["apuesta"] for v in self._restantes()}
            if nodo_id not in pesos:
                raise ErrorEntrada(f"{nodo_id} no es validador en esta ronda; su voto no se acepta.")
            if nodo_id in r["votos"]:
                raise ErrorEntrada(f"{nodo_id} ya votó en esta ronda; no puede votar dos veces.")
            nodo = red.nodo(nodo_id)
            r["votos"][nodo_id] = {"validador": nodo_id, "peso": pesos[nodo_id], "a_favor": a_favor,
                                   "firma": nodo.claves.firmar(mensaje_voto(r["hash_propuesta"], nodo_id, a_favor))}
            if registrar:
                red.evento("voto", f"{nodo_id} vota {'a favor' if a_favor else 'en contra'} con peso {pesos[nodo_id]}.")
            return f"Voto de {nodo_id} registrado ({'a favor' if a_favor else 'en contra'})."

    def votacion_automatica(self) -> str:
        """Cada validador que no ha votado revisa el candidato contra SU copia de la cadena.
        Los honestos votan según el resultado; los deshonestos votan a favor de todo."""
        red = self.red
        with red.lock:
            r = self._exigir("VOTACION")
            favor = contra = 0
            for v in self._restantes():
                if v["id"] in r["votos"]:
                    continue
                nodo = red.nodo(v["id"])
                if nodo.deshonesto:
                    a_favor, motivo = True, "deshonesto: vota a favor sin revisar"
                else:
                    a_favor, motivo = nodo.evaluar_propuesta(r["candidato"])
                r["evaluaciones"][v["id"]] = motivo
                self.votar(v["id"], a_favor, registrar=False)
                favor, contra = favor + a_favor, contra + (not a_favor)
            motivos = {m for m in r["evaluaciones"].values() if m != "válido"}
            extra = f" Motivo de los votos en contra: {'; '.join(sorted(motivos))}." if contra and motivos else ""
            red.evento("pos", f"Votación automática: {favor} a favor, {contra} en contra.{extra}")
            return f"Votación automática: {favor} a favor, {contra} en contra."

    def cerrar_votacion(self) -> str:
        red = self.red
        with red.lock:
            r = self._exigir("VOTACION")
            restantes = self._restantes()
            total = sum(v["apuesta"] for v in restantes)
            votos = [r["votos"][k] for k in sorted(r["votos"])]
            a_favor = sum(v["peso"] for v in votos if v["a_favor"])
            texto_votos = f"{a_favor} de {total} a favor ({100 * a_favor / total:.1f}%; umbral 2/3 ≈ 66.7%)"
            if 3 * a_favor >= 2 * total:
                bloque = {**r["candidato"], "votos": votos}
                bloque["hash"] = hash_bloque(bloque)
                nodo = red.nodo(r["proponente"])
                ok, motivo = nodo.recibir_cadena(nodo.cadena + [bloque])
                if ok:
                    return self._aceptar(bloque, texto_votos)
                return self._rechazar(f"alcanzó los votos ({texto_votos}) pero el bloque es inválido: {motivo}")
            return self._rechazar(f"votos insuficientes: {texto_votos}")

    def _aceptar(self, bloque: dict, texto_votos: str) -> str:
        red, r = self.red, self.ronda
        nodo = red.nodo(bloque["proponente"])
        r["historial"].append({"intento": r["intento"], "proponente": nodo.id, "resultado": "ACEPTADO", "motivo": texto_votos})
        red.evento("bloque", f"Bloque #{bloque['numero']} ACEPTADO: {texto_votos}. Proponente {nodo.id}.")
        red.difundir(nodo, f"el bloque #{bloque['numero']}")
        red.evento("recompensa", f"Recompensa de {bloque['recompensa']} pagada a {nodo.id}. "
                                 f"Se liberan las apuestas de {len(r['comite'])} validadores.")
        if self.castigos_pendientes:
            red.evento("pos", f"Se registraron en la cadena {len(self.castigos_pendientes)} castigos de rondas fallidas.")
            self.castigos_pendientes = []
        self._cerrar_ronda("ACEPTADO", f"Bloque #{bloque['numero']} aceptado ({texto_votos}).")
        red.tras_bloque(bloque)
        return self.ronda["mensaje"]

    def _rechazar(self, motivo: str) -> str:
        from models.validacion import validar_bloque
        red, r = self.red, self.ronda
        cand = r["candidato"]
        proponente = r["proponente"]
        apuesta = next(v["apuesta"] for v in r["comite"] if v["id"] == proponente)
        valor = sum(tx["monto"] for tx in cand["transacciones"])
        cfg = self.config
        monto = calcular_castigo(cfg["regla"], apuesta, valor, cfg["alfa_pct"])
        # AUD-007: sólo se castiga con prueba de fraude; un candidato válido que los votos tumbaron no se castiga.
        prueba = prueba_de_propuesta(cand)
        try:
            validar_bloque(red.referencia().estado.copia(), copiar(prueba), propuesta=True, sin_pruebas=True)
            valida = True
        except (ErrorValidacion, TypeError, KeyError, ValueError, AttributeError):
            valida = False
        if valida:
            self._cerrar_ronda("CANCELADA", f"El candidato de {proponente} es válido ({motivo}); sin prueba de fraude no "
                                            f"se castiga ni se excluye a nadie. Ronda cancelada.")
            return self.ronda["mensaje"]
        r["castigos"].append({"validador": proponente, "apuesta": apuesta, "valor_transacciones": valor,
                              "regla": cfg["regla"], "alfa_pct": cfg["alfa_pct"], "monto": monto,
                              "motivo": motivo[:300], "hash_propuesta": r["hash_propuesta"], "propuesta": prueba})
        r["excluidos"].append(proponente)
        r["historial"].append({"intento": r["intento"], "proponente": proponente, "resultado": "RECHAZADO",
                               "motivo": motivo, "castigo": monto})
        r["intento"] += 1
        r["estado"] = "RECHAZADO"
        red.evento("castigo", f"Bloque candidato de {proponente} RECHAZADO ({motivo}). Castigo regla {cfg['regla']}: "
                              f"pierde {monto} de su apuesta de {apuesta}.")
        if not self._restantes():
            self._cerrar_ronda("FALLIDA", "Todos los validadores del comité fueron castigados; la ronda termina sin bloque.")
            return self.ronda["mensaje"]
        r["mensaje"] = (f"Bloque de {proponente} rechazado; castigo de {monto}. "
                        f"Repite el sorteo con los {len(self._restantes())} validadores restantes.")
        return r["mensaje"]

    def _cerrar_ronda(self, estado: str, mensaje: str) -> None:
        r = self.ronda
        if estado != "ACEPTADO" and r["castigos"]:
            # Los castigos ya aplicados no se pierden: se registrarán en el próximo bloque aceptado.
            self.castigos_pendientes.extend(r["castigos"])
        r["estado"] = estado
        r["mensaje"] = mensaje
        self.red.evento("pos", f"Ronda {r['id']}: {estado}. {mensaje}")

    def cancelar_ronda(self) -> str:
        with self.red.lock:
            self._exigir(*ESTADOS_ACTIVOS)
            self._cerrar_ronda("CANCELADA", "Ronda cancelada por el usuario; se liberan las apuestas.")
            return self.ronda["mensaje"]

    def ronda_automatica(self) -> str:
        """Ejecuta (o termina) una ronda completa: apuestas, sorteos, candidato y votación hasta aceptar o fallar."""
        with self.red.lock:
            if not self.activa():
                self.iniciar_ronda()
            if self.ronda["estado"] == "APUESTAS":
                self.apuestas_automaticas()
            for _ in range(3 * len(self.red.nodos) + 3):  # cada intento: sorteo, candidato y votación
                estado = self.ronda["estado"]
                if estado in ("APUESTAS", "SORTEO", "RECHAZADO"):
                    self.sortear_proponente()
                elif estado == "CANDIDATO":
                    self.construir_candidato()
                elif estado == "VOTACION":
                    self.votacion_automatica()
                    self.cerrar_votacion()
                else:
                    break
            return self.ronda["mensaje"] or f"Ronda en etapa {self.ronda['estado']}."

    # ---------- vista ----------
    def publico(self) -> dict:
        r = self.ronda
        datos = {"config": self.config, "castigos_pendientes": self.castigos_pendientes, "ronda": None,
                 "estados": ["APUESTAS", "SORTEO", "CANDIDATO", "VOTACION", "ACEPTADO", "RECHAZADO"]}
        if r is None:
            return datos
        restantes = {v["id"]: v["apuesta"] for v in self._restantes()} if r["comite"] else {}
        total_restante = sum(restantes.values())
        a_favor = sum(v["peso"] for v in r["votos"].values() if v["a_favor"])
        filas = []
        for nid in r["validadores"]:
            apuesta = r["apuestas"].get(nid)
            if nid in r["excluidos"]:
                papel = "castigado"
            elif r["comite"] and nid not in restantes:
                papel = "sin apuesta"
            elif nid == r["proponente"] and r["estado"] in ("CANDIDATO", "VOTACION", "ACEPTADO"):
                papel = "proponente"
            else:
                papel = "validador"
            voto = r["votos"].get(nid)
            filas.append({
                "id": nid, "apuesta": apuesta, "papel": papel,
                "probabilidad": round(100 * restantes[nid] / total_restante, 2) if nid in restantes and total_restante else None,
                "voto": None if voto is None else voto["a_favor"],
                "evaluacion": r["evaluaciones"].get(nid),
                "castigo": next((c["monto"] for c in r["castigos"] if c["validador"] == nid), None),
                "disponible": self.red.saldo_disponible(nid),
            })
        cand = r["candidato"]
        datos["ronda"] = {
            "id": r["id"], "estado": r["estado"], "numero": r["numero"], "intento": r["intento"],
            "proponente": r["proponente"], "sorteo": r["sorteo"], "mensaje": r["mensaje"],
            "validadores": filas, "historial": r["historial"],
            "votacion": {"a_favor": a_favor, "total": total_restante,
                         "emitidos": len(r["votos"]), "esperados": len(restantes),
                         "umbral": -(-2 * total_restante // 3)},
            "candidato": None if cand is None else {
                "transacciones": cand["transacciones"], "castigos": len(cand["castigos"]),
                "hash_propuesta": r["hash_propuesta"], "firma_proponente": cand["firma_proponente"],
            },
        }
        return datos
