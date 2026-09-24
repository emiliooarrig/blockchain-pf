"""Modelo de la cadena de bloques con persistencia en JSON."""
import json
import os
import threading

from models.block import Block, new_entry, entry_hash
from models.crypto import sha256_hex, safe_equals


class Blockchain:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.lock = threading.RLock()
        self.chain: list[Block] = []
        self.pending: list[dict] = []
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

    def append_block(self, block: Block) -> bool:
        """Agrega un bloque minado si enlaza con la punta actual y cumple la prueba de trabajo."""
        with self.lock:
            if block.previous_hash != self.last_block.hash or block.index != len(self.chain):
                return False
            if block.compute_hash() != block.hash or not block.hash.startswith("0" * block.difficulty):
                return False
            self.chain.append(block)
            mined_ids = {e["id"] for e in block.entries}
            self.pending = [e for e in self.pending if e["id"] not in mined_ids]
            self._save()
            return True

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

    # ---------- validación ----------
    def validate(self) -> list[dict]:
        """Valida cada bloque y devuelve la lista de errores por bloque."""
        results = []
        broken = False
        with self.lock:
            for i, block in enumerate(self.chain):
                errors = []
                for e in block.entries:
                    if not safe_equals(sha256_hex(e["content"]), e["content_hash"]):
                        errors.append(f"El contenido de «{e['title']}» no coincide con su SHA-256.")
                if block.compute_merkle_root() != block.merkle_root:
                    errors.append("La raíz de Merkle no coincide con las entradas.")
                if not safe_equals(block.compute_hash(), block.hash):
                    errors.append("El hash del bloque no coincide con su contenido.")
                if i > 0:
                    prev = self.chain[i - 1]
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
