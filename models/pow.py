"""Versión 1: Proof of Work simulado por rondas (ticks).

En cada ronda cada uno de los N mineros prueba k nonces. El minero i prueba únicamente
i, i+N, i+2N, ... (nonces disjuntos). Una ronda representa un intervalo de tiempo en el que
todos trabajan en paralelo: si dos o más mineros encuentran un nonce válido en la misma ronda,
gana el hash menor (desempate determinista). Al haber ganador todos se detienen; el ganador
agrega el bloque a su cadena y la difunde para que los demás nodos la validen.
"""
import threading
import time

from models.bloque import MAX_TX_POR_BLOQUE, ErrorValidacion, copiar, es_entero, hash_bloque, preparar_hasher
from models.errores import ErrorEntrada, ErrorEstado

DIF_MIN, DIF_MAX = 1, 6
K_MIN, K_MAX = 1, 5000
RONDAS_MIN, RONDAS_MAX = 1, 100_000
SERIE_MIN, SERIE_MAX = 1, 50
PAUSA_MIN, PAUSA_MAX = 0, 2000
PAUSA_TRAS_BLOQUE = 0.9  # segundos que se muestra al ganador antes del siguiente bloque de una serie

CONFIG_INICIAL = {"dificultad": 3, "nonces_por_ronda": 100, "max_rondas": 2000, "bloques": 1,
                  "pausa_ms": 120, "auto_transacciones": True}


# ---------------------------------------------------------------- reglas (sin estado)
def cumple_objetivo(h: str, dificultad: int) -> bool:
    return h.startswith("0" * dificultad)


def verificar_pow(bloque: dict) -> None:
    d = bloque["dificultad"]
    if not es_entero(d) or not DIF_MIN <= d <= DIF_MAX:
        raise ErrorValidacion(f"dificultad fuera de rango ({d!r}); debe estar entre {DIF_MIN} y {DIF_MAX}")
    if not cumple_objetivo(bloque["hash"], d):
        raise ErrorValidacion(f"el hash no cumple la prueba de trabajo (requiere {d} ceros iniciales)")


class Minero:
    def __init__(self, indice: int, nodo_id: str, hasher):
        self.indice = indice
        self.id = nodo_id
        self.hasher = hasher
        self.nonce = indice      # primer nonce: i
        self.intentos = 0
        self.ultimo_hash = ""
        self.estado = "minando"  # minando | ganador | detenido

    def publico(self) -> dict:
        return {"id": self.id, "indice": self.indice, "nonce": self.nonce, "intentos": self.intentos,
                "ultimo_hash": self.ultimo_hash, "estado": self.estado}


def ronda_pow(mineros: list, n: int, k: int, d: int) -> list:
    """Una ronda: cada minero prueba hasta k nonces de su secuencia i, i+N, i+2N, ...
    Devuelve los mineros que encontraron un nonce válido, ordenados por hash (el menor gana)."""
    ganadores = []
    for m in mineros:
        for _ in range(k):
            h = m.hasher(m.nonce)
            m.intentos += 1
            m.ultimo_hash = h
            if cumple_objetivo(h, d):
                ganadores.append((h, m))
                break            # este minero conserva su nonce ganador
            m.nonce += n
    ganadores.sort(key=lambda par: par[0])
    return ganadores


# ---------------------------------------------------------------- motor
class MotorPoW:
    def __init__(self, red):
        self.red = red
        self.config = dict(CONFIG_INICIAL)
        self.minando = False
        self.mineros: list[Minero] = []
        self.ronda = 0
        self.base = None            # bloque en minado (sin proponente, nonce ni hash)
        self.serie_total = 0
        self.serie_hecha = 0
        self.mensaje = ""
        self.ultimo = None          # resultado del último bloque minado
        self._siguiente = False     # en una serie, preparar el siguiente bloque en el próximo tick
        self._cancelar = threading.Event()
        self._hilo = None

    def retenido(self, nodo_id: str) -> int:
        return 0

    # ---------- control ----------
    def iniciar(self, dificultad: int, nonces_por_ronda: int, max_rondas: int, bloques: int = 1,
                pausa_ms: int = 120, auto_transacciones: bool = False, en_hilo: bool = True) -> str:
        _rango(dificultad, DIF_MIN, DIF_MAX, "La dificultad")
        _rango(nonces_por_ronda, K_MIN, K_MAX, "Los nonces por ronda")
        _rango(max_rondas, RONDAS_MIN, RONDAS_MAX, "El límite de rondas")
        _rango(bloques, SERIE_MIN, SERIE_MAX, "El número de bloques")
        _rango(pausa_ms, PAUSA_MIN, PAUSA_MAX, "La pausa entre rondas")
        red = self.red
        with red.lock:
            if self.minando:
                raise ErrorEstado("Ya hay un minado en curso; espera a que termine o cancélalo.")
            if not red.pendientes:
                if not auto_transacciones:
                    raise ErrorEstado("No hay transacciones pendientes: crea al menos una antes de minar "
                                      "(o activa «generar transacciones automáticas» para minar en serie).")
                self._generar_transacciones()
            self.config = {"dificultad": dificultad, "nonces_por_ronda": nonces_por_ronda, "max_rondas": max_rondas,
                           "bloques": bloques, "pausa_ms": pausa_ms, "auto_transacciones": bool(auto_transacciones)}
            self.serie_total, self.serie_hecha = bloques, 0
            self.ultimo = None
            self._siguiente = False
            self._preparar_bloque()
            self._cancelar = threading.Event()
            self.minando = True
            serie = f" (serie de {bloques} bloques)" if bloques > 1 else ""
            red.evento("pow", f"Inicia el minado del bloque #{self.base['numero']}{serie}: {len(self.mineros)} mineros, "
                              f"dificultad {dificultad}, {nonces_por_ronda} nonces por minero y ronda.")
            if en_hilo:
                self._hilo = threading.Thread(target=self._bucle, args=(self._cancelar,), daemon=True, name="pow")
                self._hilo.start()
        return f"Minado iniciado: bloque #{self.base['numero']} con dificultad {dificultad}{serie}."

    def cancelar(self) -> str:
        with self.red.lock:
            if not self.minando:
                raise ErrorEstado("No hay ningún minado en curso que cancelar.")
            self._terminar(f"Minado cancelado por el usuario en la ronda {self.ronda}.")
            return self.mensaje

    def detener(self) -> None:
        """Detiene el hilo sin registrar eventos (al reiniciar la simulación)."""
        self._cancelar.set()
        self.minando = False

    # ---------- ciclo ----------
    def _bucle(self, cancelar: threading.Event) -> None:
        while not cancelar.is_set():
            pausa = self.config["pausa_ms"] / 1000
            with self.red.lock:
                if cancelar.is_set() or not self.minando:
                    return
                if self.tick():
                    pausa = max(pausa, PAUSA_TRAS_BLOQUE)
            cancelar.wait(pausa)

    def tick(self) -> bool:
        """Ejecuta una ronda. Devuelve True si en esta ronda se encontró un bloque."""
        with self.red.lock:
            if not self.minando:
                return False
            if self._siguiente:
                self._siguiente = False
                self._siguiente_bloque()
                return False
            if self.red.referencia().ultimo_hash != self.base["hash_anterior"]:
                self._terminar("La cadena cambió durante el minado; se detuvo la ronda.")
                return False
            self.ronda += 1
            cfg = self.config
            ganadores = ronda_pow(self.mineros, len(self.mineros), cfg["nonces_por_ronda"], cfg["dificultad"])
            if ganadores:
                self._resolver(ganadores)
                return True
            if self.ronda >= cfg["max_rondas"]:
                self._terminar(f"Se alcanzó el límite de {cfg['max_rondas']} rondas sin encontrar un nonce válido; "
                               f"minado cancelado. Baja la dificultad o aumenta el límite de rondas.")
            return False

    def _preparar_bloque(self) -> None:
        red = self.red
        ref = red.referencia()
        self.base = {
            "numero": ref.altura + 1,
            "timestamp": red.reloj(),
            "transacciones": copiar(red.pendientes[:MAX_TX_POR_BLOQUE]),
            "hash_anterior": ref.ultimo_hash,
            "nonce": 0,
            "proponente": "",
            "recompensa": ref.estado.params["recompensa"],
            "dificultad": self.config["dificultad"],
        }
        # Cada minero mina el bloque con SU identificador como proponente (así nadie puede robar el nonce ajeno).
        self.mineros = [Minero(i, nodo.id, preparar_hasher({**self.base, "proponente": nodo.id}))
                        for i, nodo in enumerate(red.nodos)]
        self.ronda = 0
        self.mensaje = f"Minando el bloque #{self.base['numero']}…"

    def _resolver(self, ganadores: list) -> None:
        red = self.red
        h, ganador = ganadores[0]
        for m in self.mineros:
            m.estado = "ganador" if m is ganador else "detenido"
        bloque = {**self.base, "proponente": ganador.id, "nonce": ganador.nonce}
        bloque["hash"] = hash_bloque(bloque)
        total = sum(m.intentos for m in self.mineros)
        empate = ""
        if len(ganadores) > 1:
            otros = ", ".join(m.id for _, m in ganadores[1:])
            empate = f" Empate en la ronda: también encontraron nonce válido {otros}; gana {ganador.id} por tener el hash menor."
            red.evento("pow", f"Ronda {self.ronda}: {len(ganadores)} mineros encontraron un nonce válido a la vez "
                              f"({', '.join(m.id for _, m in ganadores)}). Desempate: gana el hash menor → {ganador.id}.")
        nodo = red.nodo(ganador.id)
        ok, motivo = nodo.recibir_cadena(nodo.cadena + [bloque])
        if not ok:
            self._terminar(f"{ganador.id} descartó su propio bloque: {motivo}")
            return
        red.evento("bloque", f"Bloque #{bloque['numero']} minado por {ganador.id} en la ronda {self.ronda} "
                             f"(nonce {ganador.nonce:,}, {total:,} intentos en total). Todos los mineros se detienen.")
        red.difundir(nodo, f"el bloque #{bloque['numero']}")
        red.tras_bloque(bloque)
        self.serie_hecha += 1
        self.ultimo = {"numero": bloque["numero"], "hash": bloque["hash"], "ganador": ganador.id,
                       "nonce": ganador.nonce, "ronda": self.ronda, "intentos": total, "empate": len(ganadores) > 1}
        self.mensaje = f"¡{ganador.id} encontró el bloque #{bloque['numero']} en la ronda {self.ronda}!{empate}"
        if self.serie_hecha < self.serie_total:
            # El siguiente bloque se prepara en el próximo tick, para que el ganador se vea un momento.
            self._siguiente = True
            self.mensaje += f" Serie: {self.serie_hecha}/{self.serie_total} bloques."
            return
        self.minando = False
        self._cancelar.set()

    def _siguiente_bloque(self) -> None:
        if not self.red.pendientes and self.config["auto_transacciones"]:
            self._generar_transacciones()
        if not self.red.pendientes:
            self._terminar(f"La serie se detuvo tras {self.serie_hecha} bloques: no hay transacciones pendientes.")
            return
        self._preparar_bloque()

    def _generar_transacciones(self) -> None:
        tx = self.red.transaccion_aleatoria()
        if tx is None:
            self.red.evento("pow", "No se pudo generar una transacción automática: ningún nodo tiene saldo disponible.")

    def _terminar(self, mensaje: str) -> None:
        self._cancelar.set()
        self.minando = False
        self.mensaje = mensaje
        for m in self.mineros:
            if m.estado == "minando":
                m.estado = "detenido"
        self.red.evento("pow", mensaje)

    def publico(self) -> dict:
        return {
            "minando": self.minando,
            "config": self.config,
            "ronda": self.ronda,
            "bloque": self.base["numero"] if self.base else None,
            "serie": {"total": self.serie_total, "hechos": self.serie_hecha},
            "mensaje": self.mensaje,
            "ultimo": self.ultimo,
            "mineros": [m.publico() for m in self.mineros],
            "limites": {"dificultad": [DIF_MIN, DIF_MAX], "nonces_por_ronda": [K_MIN, K_MAX],
                        "max_rondas": [RONDAS_MIN, RONDAS_MAX], "bloques": [SERIE_MIN, SERIE_MAX],
                        "pausa_ms": [PAUSA_MIN, PAUSA_MAX]},
        }


def _rango(valor, minimo: int, maximo: int, nombre: str) -> None:
    if not es_entero(valor) or not minimo <= valor <= maximo:
        raise ErrorEntrada(f"{nombre} debe ser un entero entre {minimo} y {maximo} (recibido: {valor!r}).")
