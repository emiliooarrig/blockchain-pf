"""Carrera de minado distribuida (prueba de trabajo) entre Alice y Bob.

Cada PC mina en un hilo con SU minero y busca un nonce tal que el SHA-256 de la
cabecera empiece con `difficulty` ceros. El progreso de cada minero se envía al
otro por TCP. El primero que encuentra el nonce registra el bloque, detiene su
minero y envía BLOCK_FOUND; el otro lo valida, se detiene y lo agrega. Si ambos
lo encuentran casi al mismo tiempo, las dos PCs se quedan con el de hash menor.
"""
import threading
import time

from models.block import Block
from models.blockchain import Blockchain, parse_block, parse_entry
from models.crypto import utc_timestamp

MINERS = ("Alice", "Bob")
MIN_DIFFICULTY, MAX_DIFFICULTY = 3, 6
REPORT_EVERY = 2_000       # cada cuántos intentos se actualiza el progreso local
PROGRESS_INTERVAL = 0.25   # cada cuántos segundos se envía el progreso al par


class MinerState:
    def __init__(self, name: str):
        self.name = name
        self.location = ""  # "local" | "remoto"
        self.reset()

    def reset(self):
        self.status = "inactivo"  # inactivo | minando | ganador | detenido
        self.nonce = 0
        self.attempts = 0
        self.last_hash = ""
        self.hash_rate = 0.0

    def to_dict(self) -> dict:
        return {"name": self.name, "location": self.location, "status": self.status, "nonce": self.nonce,
                "attempts": self.attempts, "last_hash": self.last_hash, "hash_rate": round(self.hash_rate)}

    def update_progress(self, data: dict):
        for key in ("nonce", "attempts", "hash_rate"):
            if isinstance(data.get(key), (int, float)):
                setattr(self, key, data[key])
        if isinstance(data.get("last_hash"), str):
            self.last_hash = data["last_hash"][:64]


class MiningRace:
    def __init__(self, blockchain: Blockchain):
        self.blockchain = blockchain
        self.network = None  # PeerNode; se asigna en attach_network
        self.miners = {name: MinerState(name) for name in MINERS}
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.running = False
        self.difficulty = 0
        self.started_at = 0.0
        self.elapsed = 0.0
        self.winner: str | None = None
        self.winning_block: Block | None = None
        self.message = ""
        self.started_by = ""

    def attach_network(self, node) -> None:
        self.network = node

    # ---------- identidades ----------
    @property
    def local_name(self) -> str | None:
        return self.network.identity if self.network else None

    @property
    def remote_name(self) -> str | None:
        local = self.local_name
        return next((n for n in MINERS if n != local), None) if local else None

    def _local(self) -> MinerState:
        return self.miners[self.local_name]

    def _remote(self) -> MinerState:
        return self.miners[self.remote_name]

    # ---------- inicio ----------
    def start(self, difficulty: int) -> None:
        """Inicia la carrera desde esta PC: envía la plantilla al par y, si la acepta, empieza a minar."""
        if not self.network or not self.network.connected:
            raise RuntimeError("Conecta con la otra PC antes de minar.")
        with self.lock:
            if self.running:
                raise RuntimeError("Ya hay un minado en curso.")
        if not self.blockchain.pending_snapshot():
            raise ValueError("No hay entradas pendientes para sellar.")
        template = self.blockchain.block_template(difficulty, miner="")
        reply = self.network.request({"type": "MINE_START", "template": self._template_dict(template)},
                                     timeout=5)
        if not reply or not reply.get("ok"):
            reason = (reply or {}).get("reason") or "La otra PC no respondió."
            if (reply or {}).get("resync"):
                self.network.resync()
                reason += " Se resincronizaron las cadenas; intenta de nuevo."
            raise RuntimeError(f"La otra PC rechazó el minado: {reason}")
        with self.lock:
            # Si el par ya encontró el bloque antes de recibir la confirmación, no hay nada que minar.
            if self.blockchain.last_block.hash == template.previous_hash and not self.running:
                self._begin(template, started_by=self.local_name)

    @staticmethod
    def _template_dict(block: Block) -> dict:
        return {"index": block.index, "timestamp": block.timestamp, "entries": block.entries,
                "previous_hash": block.previous_hash, "difficulty": block.difficulty}

    def on_remote_start(self, data) -> dict:
        """El par pidió iniciar la carrera: se valida la plantilla y se empieza a minar."""
        if not isinstance(data, dict):
            return {"ok": False, "reason": "Plantilla inválida."}
        with self.lock:
            if self.running:
                return {"ok": False, "reason": "Ya hay un minado en curso en la otra PC."}
            tip = self.blockchain.last_block
            if data.get("previous_hash") != tip.hash or data.get("index") != tip.index + 1:
                return {"ok": False, "resync": True, "reason": "Las cadenas de ambas PCs no coinciden."}
            difficulty = data.get("difficulty")
            if type(difficulty) is not int or not MIN_DIFFICULTY <= difficulty <= MAX_DIFFICULTY:
                return {"ok": False, "reason": "Dificultad fuera de rango."}
            entries = [parse_entry(e) for e in data.get("entries") or []]
            if not entries or any(e is None for e in entries) or not isinstance(data.get("timestamp"), str):
                return {"ok": False, "reason": "Entradas o sello de tiempo inválidos."}
            template = Block(index=tip.index + 1, timestamp=data["timestamp"], entries=entries,
                             previous_hash=tip.hash, difficulty=difficulty, miner="")
            self._begin(template, started_by=self.remote_name)
        return {"ok": True}

    def _begin(self, template: Block, started_by: str) -> None:
        with self.lock:
            self.stop_event = threading.Event()
            self.running = True
            self.difficulty = template.difficulty
            self.winner = None
            self.winning_block = None
            self.started_by = started_by
            self.message = f"Minado iniciado por {started_by}."
            self.started_at = time.perf_counter()
            self.elapsed = 0.0
            for name, state in self.miners.items():
                state.reset()
                state.status = "minando"
                state.location = "local" if name == self.local_name else "remoto"
            block = Block(index=template.index, timestamp=template.timestamp, entries=template.entries,
                          previous_hash=template.previous_hash, difficulty=template.difficulty,
                          miner=self.local_name)
            stop = self.stop_event
            threading.Thread(target=self._mine, args=(self._local(), block, stop), daemon=True,
                             name=f"miner-{self.local_name}").start()
            threading.Thread(target=self._report_progress, args=(stop,), daemon=True,
                             name="miner-progress").start()

    # ---------- minado local ----------
    def _mine(self, state: MinerState, block: Block, stop: threading.Event) -> None:
        base = block.hasher()
        target = "0" * block.difficulty
        nonce = 0
        t0 = time.perf_counter()
        while not stop.is_set():
            h = base.copy()
            h.update(str(nonce).encode())
            digest = h.hexdigest()
            if digest.startswith(target):
                state.nonce, state.attempts, state.last_hash = nonce, nonce + 1, digest
                self._claim_local(state, block, nonce, digest, time.perf_counter() - t0, stop)
                return
            nonce += 1
            if nonce % REPORT_EVERY == 0:
                state.nonce, state.attempts, state.last_hash = nonce, nonce, digest
                state.hash_rate = nonce / max(time.perf_counter() - t0, 1e-9)

    def _report_progress(self, stop: threading.Event) -> None:
        """Envía al par el progreso del minero local mientras dura la carrera (y una vez al final)."""
        while not stop.wait(PROGRESS_INTERVAL):
            self._send_progress()
        self._send_progress()

    def _send_progress(self) -> None:
        if self.network and self.local_name:
            self.network.send({"type": "PROGRESS", "miner": self._local().to_dict()})

    def _claim_local(self, state, block, nonce, digest, seconds, stop) -> None:
        with self.lock:
            if stop is not self.stop_event or stop.is_set() or self.winner is not None:
                return  # el par ganó primero o la carrera se detuvo
            stop.set()
            self.elapsed = time.perf_counter() - self.started_at
            block.nonce, block.hash = nonce, digest
            block.attempts, block.mining_seconds = nonce + 1, round(seconds, 3)
            block.extra = {"race": {n: s.attempts for n, s in self.miners.items()}}
            error = self.blockchain.append_block(block)
            if error:
                self._finish(None, f"El bloque minado se descartó: {error}.")
                return
            self._finish(state.name, f"¡{state.name} encontró el bloque #{block.index} primero!", block)
        if self.network:
            self.network.send({"type": "BLOCK_FOUND", "block": block.to_dict()})

    # ---------- eventos del par ----------
    def on_remote_progress(self, data) -> None:
        if isinstance(data, dict) and self.remote_name:
            self._remote().update_progress(data)

    def on_remote_block(self, data) -> None:
        """El par encontró un bloque: se valida y, si gana, se detiene el minero local."""
        block = parse_block(data)
        if block is None or block.miner != self.remote_name:
            return
        with self.lock:
            remote = self._remote()
            remote.update_progress({"nonce": block.nonce, "attempts": block.attempts, "last_hash": block.hash})
            if self.winning_block and self.winning_block.index == block.index:
                # Ambos encontraron un bloque de la misma altura: gana el de hash menor en las dos PCs.
                if block.hash < self.winning_block.hash and not self.blockchain.replace_last(block):
                    self._finish(remote.name, f"¡Empate técnico! Ambos encontraron el bloque #{block.index}; "
                                              f"se conserva el de {remote.name} por tener el hash menor.", block)
                elif self.winner == self.local_name:
                    self.message = (f"¡Empate técnico! Ambos encontraron el bloque #{block.index}; "
                                    f"se conserva el de {self.local_name} por tener el hash menor.")
                return
            error = self.blockchain.append_block(block)
            if error:
                if self.running:
                    self.message = f"Se rechazó el bloque de {remote.name}: {error}."
                return
            if self.running:
                self.stop_event.set()
                self.elapsed = time.perf_counter() - self.started_at
            self._finish(remote.name, f"¡{remote.name} encontró el bloque #{block.index} primero!", block)

    def on_remote_stop(self) -> None:
        self.stop(propagate=False, message="La otra PC detuvo el minado.")

    def on_disconnect(self) -> None:
        self.stop(propagate=False, message="Se perdió la conexión con la otra PC; minado detenido.")

    # ---------- fin ----------
    def _finish(self, winner: str | None, message: str, block: Block | None = None) -> None:
        self.running = False
        self.winner = winner
        self.winning_block = block if winner else None
        self.message = message
        for name, s in self.miners.items():
            s.status = "ganador" if name == winner else "detenido"
        if winner and block is not None:
            s = self.miners[winner]
            s.nonce, s.attempts, s.last_hash = block.nonce, block.attempts, block.hash

    def stop(self, propagate: bool = True, message: str = "Minado detenido manualmente.") -> None:
        with self.lock:
            if not self.running:
                return
            self.stop_event.set()
            self.running = False
            self.elapsed = time.perf_counter() - self.started_at
            self.message = message
            for s in self.miners.values():
                if s.status == "minando":
                    s.status = "detenido"
        if propagate and self.network:
            self.network.send({"type": "MINE_STOP"})

    def clear(self) -> None:
        """Olvida el resultado de la última carrera (p. ej. al reiniciar la cadena)."""
        with self.lock:
            if self.running:
                return
            self.difficulty = 0
            self.elapsed = 0.0
            self.winner = None
            self.winning_block = None
            self.message = ""
            self.started_by = ""
            for s in self.miners.values():
                s.reset()

    def status(self) -> dict:
        elapsed = time.perf_counter() - self.started_at if self.running else self.elapsed
        local = self.local_name
        miners = []
        for s in self.miners.values():
            d = s.to_dict()
            d["location"] = ("local" if s.name == local else "remoto") if local else ""
            miners.append(d)
        return {
            "running": self.running,
            "difficulty": self.difficulty,
            "elapsed": round(elapsed, 2),
            "winner": self.winner,
            "message": self.message,
            "started_by": self.started_by,
            "block_index": self.winning_block.index if self.winning_block else None,
            "block_hash": self.winning_block.hash if self.winning_block else None,
            "miners": miners,
        }
