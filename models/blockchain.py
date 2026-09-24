"""Modelo de la cadena de bloques con persistencia en JSON."""
import json
import os
import threading
from dataclasses import fields

from models.block import Block, new_entry, entry_hash
from models.crypto import sha256_hex, safe_equals, utc_timestamp

ENTRY_KEYS = ("id", "researcher", "title", "content", "content_hash", "submitted_at")
BLOCK_KEYS = {f.name for f in fields(Block)}


def validate_blocks(blocks: list[Block]) -> list[dict]:
    """Valida una lista de bloques y devuelve los errores de cada uno."""
    results = []
    broken = False
    for i, block in enumerate(blocks):
        errors = []
        for e in block.entries:
            if not safe_equals(sha256_hex(e["content"]), e["content_hash"]):
                errors.append(f"El contenido de «{e['title']}» no coincide con su SHA-256.")
        if block.compute_merkle_root() != block.merkle_root:
            errors.append("La raíz de Merkle no coincide con las entradas.")
        if not safe_equals(block.compute_hash(), block.hash):
            errors.append("El hash del bloque no coincide con su contenido.")
        if i > 0:
            prev = blocks[i - 1]
            if not block.hash.startswith("0" * block.difficulty):
                errors.append("El hash no cumple la dificultad (prueba de trabajo).")
            if block.previous_hash != prev.hash:
                errors.append("El hash previo no enlaza con el bloque anterior.")
            if block.timestamp < prev.timestamp:
                errors.append("El sello de tiempo es anterior al del bloque previo.")
        if broken and not errors:
            errors.append("Depende de un bloque anterior inválido.")
        broken = broken or bool(errors)
        results.append({"index": block.index, "valid": not errors, "errors": errors})
    return results


def parse_entry(data) -> dict | None:
    """Valida una entrada recibida de la red; None si es inválida."""
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) for k in ENTRY_KEYS):
        return None
    entry = {k: data[k] for k in ENTRY_KEYS}
    if not safe_equals(sha256_hex(entry["content"]), entry["content_hash"]):
        return None
    return entry


def parse_block(data) -> Block | None:
    """Reconstruye un bloque recibido de la red; None si su estructura es inválida."""
    try:
        if not isinstance(data, dict) or set(data) - BLOCK_KEYS:
            return None
        ints = ("index", "difficulty", "nonce", "attempts")
        strs = ("timestamp", "previous_hash", "miner", "merkle_root", "hash")
        if not all(type(data.get(k)) is int for k in ints) or not all(isinstance(data.get(k), str) for k in strs):
            return None
        if not isinstance(data.get("entries"), list) or not 0 <= data["difficulty"] <= 16:
            return None
        block = Block(**data)
        entries = [parse_entry(e) for e in block.entries]
        if any(e is None for e in entries):
            return None
        block.entries = entries
        if not isinstance(block.extra, dict):
            block.extra = {}
        return block
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


def chain_rank(blocks: list[Block]) -> tuple:
    """Criterio determinista para elegir cadena: válida > más larga > hash de la punta menor."""
    valid = all(r["valid"] for r in validate_blocks(blocks))
    return (valid, len(blocks), [-ord(c) for c in blocks[-1].hash])


class Blockchain:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.lock = threading.RLock()
        self.chain: list[Block] = []
        self.pending: list[dict] = []
        self.revision = 0  # aumenta con cada cambio; la vista lo usa para saber si recargar
        self._load()

    # ---------- persistencia ----------
    def _load(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, encoding="utf-8") as f:
                data = json.load(f)
            self.chain = [Block.from_dict(b) for b in data.get("chain", [])]
            self.pending = data.get("pending", [])
        if not self.chain:
            self.chain = [Block.genesis()]
            self._save()

    def _save(self):
        self.revision += 1
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        tmp = self.storage_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"chain": [b.to_dict() for b in self.chain], "pending": self.pending},
                      f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.storage_path)

    # ---------- operaciones ----------
    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    def add_entry(self, researcher: str, title: str, content: str) -> dict:
        entry = new_entry(researcher, title, content)
        with self.lock:
            self.pending.append(entry)
            self._save()
        return entry

    def pending_snapshot(self) -> list[dict]:
        with self.lock:
            return [dict(e) for e in self.pending]

    def chain_snapshot(self) -> list[dict]:
        with self.lock:
            return [b.to_dict() for b in self.chain]

    def block_template(self, difficulty: int, miner: str) -> Block:
        """Cabecera del siguiente bloque con las entradas pendientes y un nuevo sello de tiempo."""
        with self.lock:
            return Block(index=self.last_block.index + 1, timestamp=utc_timestamp(),
                         entries=self.pending_snapshot(), previous_hash=self.last_block.hash,
                         difficulty=difficulty, miner=miner)

    def _block_errors(self, block: Block, prev: Block) -> str | None:
        if block.previous_hash != prev.hash or block.index != prev.index + 1:
            return "no enlaza con la punta de la cadena"
        if block.timestamp < prev.timestamp:
            return "sello de tiempo anterior al bloque previo"
        if any(not safe_equals(sha256_hex(e["content"]), e["content_hash"]) for e in block.entries):
            return "contenido que no coincide con su SHA-256"
        if block.compute_merkle_root() != block.merkle_root:
            return "raíz de Merkle incorrecta"
        if not safe_equals(block.compute_hash(), block.hash) or not block.hash.startswith("0" * block.difficulty):
            return "hash o prueba de trabajo inválidos"
        return None

    def _drop_mined_from_pending(self, block: Block):
        mined_ids = {e["id"] for e in block.entries}
        self.pending = [e for e in self.pending if e["id"] not in mined_ids]

    def append_block(self, block: Block) -> str | None:
        """Agrega un bloque minado. Devuelve None si se aceptó o el motivo del rechazo."""
        with self.lock:
            error = self._block_errors(block, self.last_block)
            if error:
                return error
            self.chain.append(block)
            self._drop_mined_from_pending(block)
            self._save()
            return None

    def replace_last(self, block: Block) -> str | None:
        """Sustituye la punta por un bloque competidor de la misma altura (empate en la carrera)."""
        with self.lock:
            if len(self.chain) < 2:
                return "no hay bloque que sustituir"
            error = self._block_errors(block, self.chain[-2])
            if error:
                return error
            old = self.chain[-1]
            self.chain[-1] = block
            known = {e["id"] for e in self.pending} | {e["id"] for e in block.entries}
            self.pending.extend(e for e in old.entries if e["id"] not in known)
            self._drop_mined_from_pending(block)
            self._save()
            return None

    def reset(self):
        with self.lock:
            self.chain = [Block.genesis()]
            self.pending = []
            self._save()

    def tamper(self, index: int) -> bool:
        """Simula una alteración maliciosa del contenido de un bloque (sin volver a minarlo)."""
        with self.lock:
            if not (0 < index < len(self.chain)) or not self.chain[index].entries:
                return False
            entry = self.chain[index].entries[0]
            entry["content"] += " [ALTERADO]"
            self._save()
            return True

    # ---------- sincronización con el par ----------
    def merge_pending(self, entries: list) -> int:
        """Agrega entradas del par que no se conocían. Devuelve cuántas se agregaron."""
        added = 0
        with self.lock:
            known = {e["id"] for e in self.pending} | {e["id"] for b in self.chain for e in b.entries}
            for raw in entries if isinstance(entries, list) else []:
                entry = parse_entry(raw)
                if entry and entry["id"] not in known:
                    self.pending.append(entry)
                    known.add(entry["id"])
                    added += 1
            if added:
                self.pending.sort(key=lambda e: e["submitted_at"])
                self._save()
        return added

    def sync_with(self, remote_chain: list) -> str:
        """Adopta la cadena del par si gana según `chain_rank`; las entradas huérfanas vuelven a pendientes."""
        remote = [parse_block(b) for b in remote_chain] if isinstance(remote_chain, list) else []
        if not remote or any(b is None for b in remote):
            return "La cadena recibida del par no tiene un formato válido; se conserva la local."
        with self.lock:
            if remote[-1].hash == self.last_block.hash and len(remote) == len(self.chain):
                return "Las cadenas ya coinciden."
            if chain_rank(remote) <= chain_rank(self.chain):
                return f"Se conserva la cadena local ({len(self.chain)} bloques)."
            in_remote = {e["id"] for b in remote for e in b.entries}
            orphans = [e for b in self.chain for e in b.entries if e["id"] not in in_remote]
            self.chain = remote
            known = {e["id"] for e in self.pending}
            self.pending = [e for e in self.pending if e["id"] not in in_remote]
            self.pending.extend(e for e in orphans if e["id"] not in known)
            self._save()
            return f"Se adoptó la cadena del par ({len(remote)} bloques)."

    # ---------- validación ----------
    def validate(self) -> list[dict]:
        with self.lock:
            return validate_blocks(self.chain)

    def is_valid(self) -> bool:
        return all(r["valid"] for r in self.validate())

    # ---------- prueba de prioridad ----------
    def find_content(self, content: str) -> dict:
        """Busca el SHA-256 de un documento en la cadena y en las entradas pendientes."""
        digest = sha256_hex(content)
        with self.lock:
            for block in self.chain:
                for e in block.entries:
                    if safe_equals(e["content_hash"], digest):
                        return {"hash": digest, "status": "sellado", "entry": e, "block": block,
                                "entry_hash": entry_hash(e)}
            for e in self.pending:
                if safe_equals(e["content_hash"], digest):
                    return {"hash": digest, "status": "pendiente", "entry": e}
        return {"hash": digest, "status": "no_encontrado"}
