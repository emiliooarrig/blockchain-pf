"""Carrera de minado (prueba de trabajo) entre Alice y Bob.

Cada minero corre en su propio hilo y busca un nonce tal que el SHA-256 de la
cabecera empiece con `difficulty` ceros. El primero que lo encuentra toma el
candado, registra el bloque y activa un `threading.Event` que detiene a ambos.
"""
import threading
import time

from models.block import Block
from models.blockchain import Blockchain
from models.crypto import utc_timestamp

MINERS = ("Alice", "Bob")
REPORT_EVERY = 2_000  # cada cuántos intentos se publica el progreso


class MinerState:
    def __init__(self, name: str):
        self.name = name
        self.reset()

    def reset(self):
        self.status = "inactivo"  # inactivo | minando | ganador | detenido
        self.nonce = 0
        self.attempts = 0
        self.last_hash = ""
        self.hash_rate = 0.0

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "nonce": self.nonce, "attempts": self.attempts,
                "last_hash": self.last_hash, "hash_rate": round(self.hash_rate)}


class MiningRace:
    def __init__(self, blockchain: Blockchain):
        self.blockchain = blockchain
        self.miners = {name: MinerState(name) for name in MINERS}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []
        self.running = False
        self.difficulty = 0
        self.started_at = 0.0
        self.elapsed = 0.0
        self.winner: str | None = None
        self.winning_block: Block | None = None
        self.message = ""

    def start(self, difficulty: int) -> None:
        with self.lock:
            if self.running:
                raise RuntimeError("Ya hay un minado en curso.")
            entries = self.blockchain.pending_snapshot()
            if not entries:
                raise ValueError("No hay entradas pendientes para sellar.")
            last = self.blockchain.last_block
            timestamp = utc_timestamp()  # mismo sello de tiempo para ambos: competencia justa

            self.stop_event = threading.Event()
            self.running = True
            self.difficulty = difficulty
            self.winner = None
            self.winning_block = None
            self.message = ""
            self.started_at = time.perf_counter()
            self.elapsed = 0.0
            self.threads = []
            for name, state in self.miners.items():
                state.reset()
                state.status = "minando"
                template = Block(index=last.index + 1, timestamp=timestamp, entries=entries,
                                 previous_hash=last.hash, difficulty=difficulty, miner=name)
                t = threading.Thread(target=self._mine, args=(state, template), daemon=True, name=f"miner-{name}")
                self.threads.append(t)
            for t in self.threads:
                t.start()

    def stop(self) -> None:
        """Detención manual de la carrera."""
        with self.lock:
            if not self.running:
                return
            self.stop_event.set()
            self.running = False
            self.elapsed = time.perf_counter() - self.started_at
            self.message = "Minado detenido manualmente."
            for s in self.miners.values():
                if s.status == "minando":
                    s.status = "detenido"

    def _mine(self, state: MinerState, block: Block) -> None:
        stop = self.stop_event
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
                self._claim_victory(state, block, nonce, digest, time.perf_counter() - t0)
                return
            nonce += 1
            if nonce % REPORT_EVERY == 0:
                state.nonce, state.attempts, state.last_hash = nonce, nonce, digest
                state.hash_rate = nonce / max(time.perf_counter() - t0, 1e-9)

    def _claim_victory(self, state: MinerState, block: Block, nonce: int, digest: str, seconds: float) -> None:
        with self.lock:
            if self.winner is not None or self.stop_event.is_set():
                return  # el otro minero llegó primero
            self.stop_event.set()  # detiene a ambos mineros
            self.elapsed = time.perf_counter() - self.started_at
            block.nonce, block.hash = nonce, digest
            block.attempts, block.mining_seconds = nonce + 1, round(seconds, 3)
            block.extra = {"race": {n: s.attempts for n, s in self.miners.items()}}
            if self.blockchain.append_block(block):
                self.winner = state.name
                self.winning_block = block
                state.status = "ganador"
                self.message = f"¡{state.name} encontró el bloque #{block.index} primero!"
            else:
                state.status = "detenido"
                self.message = "El bloque minado ya no enlaza con la cadena actual; se descartó."
            for s in self.miners.values():
                if s is not state:
                    s.status = "detenido"
            self.running = False

    def status(self) -> dict:
        elapsed = time.perf_counter() - self.started_at if self.running else self.elapsed
        return {
            "running": self.running,
            "difficulty": self.difficulty,
            "elapsed": round(elapsed, 2),
            "winner": self.winner,
            "message": self.message,
            "block_index": self.winning_block.index if self.winning_block else None,
            "block_hash": self.winning_block.hash if self.winning_block else None,
            "miners": [s.to_dict() for s in self.miners.values()],
        }
