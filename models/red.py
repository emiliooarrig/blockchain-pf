"""Red simulada en memoria: nodos con su propia copia de la cadena, difusión y transacciones pendientes.

Cada nodo tiene un identificador, un par de claves Ed25519, su propia copia de la cadena y el estado
de cuentas que resulta de validarla. Cuando un nodo difunde su cadena, cada uno de los demás la valida
completa (desde el génesis) y sólo la adopta si es válida y más larga que la suya.
"""
import json
import random
import threading
import time
from collections import deque

from models.bloque import (MAX_TX_POR_BLOQUE, MONTO_MAX, Estado, ErrorValidacion, crear_genesis, es_entero,
                           id_transaccion, nueva_transaccion, revisar_transaccion)
from models.cripto import ParClaves
from models.errores import ErrorEntrada, ErrorEstado
from models.pos import MotorPoS
from models.pow import MotorPoW
from models.validacion import validar_bloque, validar_cadena

N_MIN, N_MAX = 10, 20
SALDO_MIN, SALDO_MAX = 1, 1_000_000
RECOMPENSA_MIN, RECOMPENSA_MAX = 1, 10_000
SEMILLA_MAX = 2**63 - 1
CONFIRMACIONES_POW = 6
MAX_PENDIENTES = 200
INICIO_RELOJ_SIMULADO = 1_767_225_600.0  # 2026-01-01 00:00:00 UTC

PARAMETROS_INICIALES = {
    "pow": {"n": 10, "semilla": 2026, "saldo_inicial": 100, "recompensa": 50, "reproducible": False},
    "pos": {"n": 10, "semilla": 2026, "saldo_inicial": 100, "recompensa": 10, "reproducible": False},
}


class RelojReal:
    """Hora real con microsegundos, estrictamente creciente."""

    def __init__(self):
        self._ultimo = 0.0
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            t = round(max(time.time(), self._ultimo + 0.000001), 6)
            self._ultimo = t
            return t


class RelojSimulado:
    """Reloj lógico: cada lectura avanza un segundo. Con la misma semilla, la simulación se repite idéntica."""

    def __init__(self, inicio: float = INICIO_RELOJ_SIMULADO):
        self._t = inicio
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            self._t += 1.0
            return self._t


def _copia_json(obj):
    """Copia profunda que además garantiza que el contenido es JSON puro (como si viajara por la red)."""
    return json.loads(json.dumps(obj))


class Nodo:
    def __init__(self, indice: int, nodo_id: str, claves: ParClaves, genesis: dict):
        self.indice = indice
        self.id = nodo_id
        self.claves = claves
        self.cadena = [_copia_json(genesis)]
        self.estado = Estado(self.cadena[0])
        self.deshonesto = False
        self.ultimo_rechazo = ""

    @property
    def altura(self) -> int:
        return len(self.cadena) - 1

    @property
    def ultimo_hash(self) -> str:
        return self.cadena[-1]["hash"]

    def recibir_cadena(self, cadena) -> tuple[bool, str]:
        """Valida la cadena COMPLETA recibida; la adopta sólo si es válida y más larga que la propia."""
        try:
            copia = _copia_json(cadena)
        except (TypeError, ValueError):
            return self._rechazar("la cadena recibida no es serializable")
        try:
            estado = validar_cadena(copia, self.cadena[0]["hash"])
        except ErrorValidacion as exc:
            return self._rechazar(str(exc))
        if len(copia) <= len(self.cadena):
            return self._rechazar(f"la cadena recibida (altura {len(copia) - 1}) no es más larga que la propia "
                                  f"(altura {self.altura})")
        self.cadena, self.estado = copia, estado
        self.ultimo_rechazo = ""
        return True, "aceptada"

    def _rechazar(self, motivo: str) -> tuple[bool, str]:
        self.ultimo_rechazo = motivo
        return False, motivo

    def evaluar_propuesta(self, candidato: dict) -> tuple[bool, str]:
        """Revisión que hace un validador PoS honesto antes de votar (contra su propia copia de la cadena)."""
        try:
            validar_bloque(self.estado.copia(), _copia_json(candidato), propuesta=True)
            return True, "válido"
        except ErrorValidacion as exc:
            return False, str(exc)
        except (TypeError, KeyError, ValueError, AttributeError):
            return False, "bloque con formato inválido"


class Red:
    def __init__(self, consenso: str, n: int, semilla: int, saldo_inicial: int, recompensa: int,
                 reproducible: bool = False):
        if consenso not in ("pow", "pos"):
            raise ErrorEntrada("El consenso debe ser «pow» o «pos».")
        _rango(n, N_MIN, N_MAX, "El número de nodos N")
        _rango(semilla, 0, SEMILLA_MAX, "La semilla")
        _rango(saldo_inicial, SALDO_MIN, SALDO_MAX, "El saldo inicial")
        _rango(recompensa, RECOMPENSA_MIN, RECOMPENSA_MAX, "La recompensa por bloque")
        self.consenso = consenso
        self.parametros = {"n": n, "semilla": semilla, "saldo_inicial": saldo_inicial, "recompensa": recompensa,
                           "reproducible": bool(reproducible)}
        self.lock = threading.RLock()
        self.reloj = RelojSimulado() if reproducible else RelojReal()
        self.rng = random.Random(f"{semilla}|{consenso}|transacciones")
        self.bitacora = deque(maxlen=400)
        self._secuencia = 0
        self.revision = 0
        self.pendientes: list[dict] = []

        claves = [ParClaves(f"{semilla}|{consenso}|nodo|{i}") for i in range(n)]
        ids = [f"N{i:02d}" for i in range(n)]
        cuentas = {nid: {"clave_publica": c.publica, "saldo": saldo_inicial} for nid, c in zip(ids, claves)}
        parametros = {"consenso": consenso, "recompensa": recompensa,
                      "confirmaciones": CONFIRMACIONES_POW if consenso == "pow" else 0}
        genesis = crear_genesis(cuentas, parametros, self.reloj())
        self.nodos = [Nodo(i, nid, c, genesis) for i, (nid, c) in enumerate(zip(ids, claves))]
        self.motor = MotorPoW(self) if consenso == "pow" else MotorPoS(self)
        nombre = "Proof of Work" if consenso == "pow" else "Proof of Stake"
        self.evento("red", f"Simulación {nombre} creada: {n} nodos, saldo inicial {saldo_inicial}, recompensa "
                           f"{recompensa}, semilla {semilla}{' (reloj simulado: reproducible)' if reproducible else ''}.")

    # ---------- utilidades ----------
    def evento(self, tipo: str, texto: str) -> None:
        self._secuencia += 1
        self.bitacora.append({"n": self._secuencia, "t": time.time(), "tipo": tipo, "texto": texto})

    def rng_derivado(self, etiqueta: str) -> random.Random:
        """Generador reproducible: depende sólo de la semilla de la simulación y de la etiqueta."""
        return random.Random(f"{self.parametros['semilla']}|{self.consenso}|{etiqueta}")

    def nodo(self, nodo_id) -> Nodo:
        if not isinstance(nodo_id, str) or not nodo_id.strip():
            raise ErrorEntrada("Indica un nodo.")
        for n in self.nodos:
            if n.id == nodo_id.strip():
                return n
        raise ErrorEntrada(f"El nodo «{str(nodo_id)[:20]}» no existe (los nodos van de {self.nodos[0].id} a {self.nodos[-1].id}).")

    def referencia(self) -> Nodo:
        """Nodo con la cadena más larga (todos coinciden cuando la red está sincronizada)."""
        return max(self.nodos, key=lambda n: (n.altura, -n.indice))

    def compromisos(self, nodo_id: str) -> int:
        salida = sum(tx["monto"] for tx in self.pendientes if tx["emisor"] == nodo_id)
        return salida + self.motor.retenido(nodo_id)

    def saldo_disponible(self, nodo_id: str) -> int:
        return self.referencia().estado.saldos[nodo_id] - self.compromisos(nodo_id)

    # ---------- transacciones ----------
    def crear_transaccion(self, emisor, receptor, monto) -> dict:
        with self.lock:
            e, r = self.nodo(emisor), self.nodo(receptor)
            if e.id == r.id:
                raise ErrorEntrada("El emisor y el receptor no pueden ser el mismo nodo.")
            if not es_entero(monto) or monto <= 0:
                raise ErrorEntrada("El monto debe ser un entero mayor que cero.")
            if monto > MONTO_MAX:
                raise ErrorEntrada(f"El monto no puede ser mayor que {MONTO_MAX:,}.")
            tx = nueva_transaccion(e.id, r.id, monto, self.reloj(), e.claves)
            return self.agregar_pendiente(tx)

    def agregar_pendiente(self, tx, origen: str = "") -> dict:
        """Cualquier transacción que llega a la lista de pendientes se valida igual que en un bloque."""
        with self.lock:
            if len(self.pendientes) >= MAX_PENDIENTES:
                raise ErrorEstado(f"La lista de pendientes está llena ({MAX_PENDIENTES}); mina o propone un bloque.")
            try:
                tid = revisar_transaccion(self.referencia().estado, tx)
            except ErrorValidacion as exc:
                self.evento("rechazo", f"Transacción rechazada{origen}: {exc}.")
                raise ErrorEntrada(f"Transacción rechazada: {exc}.") from None
            if any(id_transaccion(p) == tid for p in self.pendientes):
                self.evento("rechazo", f"Transacción rechazada{origen}: ya está en la lista de pendientes.")
                raise ErrorEntrada("Transacción rechazada: ya está en la lista de pendientes (doble gasto).")
            disponible = self.saldo_disponible(tx["emisor"])
            if tx["monto"] > disponible:
                comprometido = self.compromisos(tx["emisor"])
                detalle = f" ({comprometido} ya comprometido en pendientes o apuestas)" if comprometido else ""
                self.evento("rechazo", f"Transacción rechazada{origen}: saldo insuficiente de {tx['emisor']} "
                                       f"(disponible {disponible}, monto {tx['monto']}).")
                raise ErrorEntrada(f"Saldo insuficiente: {tx['emisor']} tiene {disponible} disponible{detalle} "
                                   f"e intenta enviar {tx['monto']}.")
            self.pendientes.append(_copia_json(tx))
            self.evento("tx", f"Transacción firmada {tx['emisor']} → {tx['receptor']} por {tx['monto']} "
                              f"(firma {tx['firma'][:10]}… verificada){origen}.")
            return tx

    def transaccion_aleatoria(self) -> dict | None:
        with self.lock:
            candidatos = [n for n in self.nodos if self.saldo_disponible(n.id) > 0]
            if not candidatos:
                return None
            e = self.rng.choice(candidatos)
            r = self.rng.choice([n for n in self.nodos if n is not e])
            monto = self.rng.randint(1, max(1, min(self.saldo_disponible(e.id), 25)))
            tx = nueva_transaccion(e.id, r.id, monto, self.reloj(), e.claves)
            return self.agregar_pendiente(tx, origen=" (automática)")

    # ---------- difusión ----------
    def difundir(self, origen: Nodo, descripcion: str, cadena=None) -> dict:
        """Envía la cadena de `origen` (o `cadena`) a todos los demás nodos; cada uno la valida."""
        cadena = origen.cadena if cadena is None else cadena
        aceptaron, rechazos = [], {}
        for n in self.nodos:
            if n is origen:
                continue
            ok, motivo = n.recibir_cadena(cadena)
            if ok:
                aceptaron.append(n.id)
            else:
                rechazos.setdefault(motivo, []).append(n.id)
        if aceptaron:
            self.revision += 1
        total = len(self.nodos) - 1
        if not rechazos:
            self.evento("difusion", f"{origen.id} difunde {descripcion}: los {total} nodos restantes validaron la "
                                    f"cadena completa y la aceptaron.")
        else:
            detalle = "; ".join(f"{len(ids)} nodo(s): {m}" for m, ids in rechazos.items())
            tipo = "difusion" if aceptaron else "rechazo"
            self.evento(tipo, f"{origen.id} difunde {descripcion}: {len(aceptaron)}/{total} la aceptaron. "
                              f"Rechazada por {detalle}.")
        return {"aceptaron": aceptaron, "rechazos": [{"motivo": m, "nodos": ids} for m, ids in rechazos.items()]}

    def tras_bloque(self, bloque: dict) -> None:
        """Limpia pendientes ya incluidos (o que quedaron inválidos) y anuncia recompensas maduradas."""
        ref = self.referencia()
        incluidas = ref.estado.tx_ids
        restantes, descartadas = [], 0
        for tx in self.pendientes:
            if id_transaccion(tx) in incluidas:
                continue
            restantes.append(tx)
        self.pendientes = []
        for tx in restantes:
            try:
                revisar_transaccion(ref.estado, tx)
                if tx["monto"] > self.saldo_disponible(tx["emisor"]):
                    raise ErrorValidacion("saldo insuficiente")
                self.pendientes.append(tx)
            except ErrorValidacion:
                descartadas += 1
        if descartadas:
            self.evento("rechazo", f"{descartadas} transacción(es) pendiente(s) quedaron inválidas y se descartaron.")
        conf = ref.estado.params["confirmaciones"]
        if conf and bloque["numero"] - conf >= 1:
            madura = ref.cadena[bloque["numero"] - conf]
            self.evento("recompensa", f"Recompensa del bloque #{madura['numero']} ({madura['recompensa']}) acreditada a "
                                      f"{madura['proponente']} tras {conf} confirmaciones (altura {bloque['numero']}).")

    # ---------- vista ----------
    def publico(self) -> dict:
        ref = self.referencia()
        nodos = []
        for n in self.nodos:
            saldo = ref.estado.saldos[n.id]
            nodos.append({
                "id": n.id, "indice": n.indice, "altura": n.altura, "ultimo_hash": n.ultimo_hash,
                "sincronizado": n.ultimo_hash == ref.ultimo_hash, "saldo": saldo,
                "disponible": saldo - self.compromisos(n.id), "retenido": self.motor.retenido(n.id),
                "pendiente_recompensa": ref.estado.pendiente_de(n.id), "deshonesto": n.deshonesto,
                "clave_publica": n.claves.publica, "ultimo_rechazo": n.ultimo_rechazo,
            })
        return {
            "consenso": self.consenso,
            "parametros": self.parametros,
            "revision": self.revision,
            "altura": ref.altura,
            "ultimo_hash": ref.ultimo_hash,
            "sincronizados": sum(1 for x in nodos if x["sincronizado"]),
            "nodos": nodos,
            "pendientes": [{**tx, "id": id_transaccion(tx)} for tx in self.pendientes],
            "max_tx_por_bloque": MAX_TX_POR_BLOQUE,
            "recompensas": self.recompensas(),
            "motor": self.motor.publico(),
            "bitacora": list(self.bitacora)[-150:],
        }

    def recompensas(self, nodo_id: str | None = None) -> list:
        """Recompensas por bloque con su número de confirmaciones (PoW: maduran a las 6)."""
        ref = self.referencia()
        conf = ref.estado.params["confirmaciones"]
        filas = []
        for b in ref.cadena[1:]:
            if nodo_id and b["proponente"] != nodo_id:
                continue
            confirmaciones = ref.altura - b["numero"]
            filas.append({"numero": b["numero"], "nodo": b["proponente"], "monto": b["recompensa"],
                          "confirmaciones": min(confirmaciones, conf) if conf else 0, "requeridas": conf,
                          "estado": "acreditada" if confirmaciones >= conf else "pendiente"})
        return filas[-60:]

    def cadena_publica(self, nodo_id: str | None = None, ultimos: int = 40) -> dict:
        nodo = self.nodo(nodo_id) if nodo_id else self.referencia()
        inicio = max(0, len(nodo.cadena) - ultimos)
        return {"nodo": nodo.id, "altura": nodo.altura, "revision": self.revision, "desde": inicio,
                "bloques": nodo.cadena[inicio:]}


def _rango(valor, minimo: int, maximo: int, nombre: str) -> None:
    if not es_entero(valor) or not minimo <= valor <= maximo:
        raise ErrorEntrada(f"{nombre} debe ser un entero entre {minimo} y {maximo} (recibido: {valor!r}).")
