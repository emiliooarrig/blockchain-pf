"""Modelo de bloque y de entrada de cuaderno de laboratorio."""
import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict

from models.crypto import sha256_hex, merkle_root, utc_timestamp


def new_entry(researcher: str, title: str, content: str) -> dict:
    """Crea una entrada de cuaderno con el SHA-256 de su contenido y su sello de tiempo."""
    return {
        "id": uuid.uuid4().hex,
        "researcher": researcher,
        "title": title,
        "content": content,
        "content_hash": sha256_hex(content),
        "submitted_at": utc_timestamp(),
    }


def entry_hash(entry: dict) -> str:
    """Hash de una entrada completa (autor, título, hash del contenido y fecha de envío)."""
    payload = json.dumps(
        {k: entry[k] for k in ("researcher", "title", "content_hash", "submitted_at")},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return sha256_hex(payload)


@dataclass
class Block:
    index: int
    timestamp: str
    entries: list[dict]
    previous_hash: str
    difficulty: int
    miner: str
    merkle_root: str = ""
    nonce: int = 0
    hash: str = ""
    attempts: int = 0
    mining_seconds: float = 0.0
    extra: dict = field(default_factory=dict)  # metadatos fuera del hash (p. ej. resultados de la carrera)

    def __post_init__(self):
        if not self.merkle_root:
            self.merkle_root = self.compute_merkle_root()

    def compute_merkle_root(self) -> str:
        return merkle_root([entry_hash(e) for e in self.entries])

    def header_bytes(self) -> bytes:
        """Cabecera canónica (sin nonce) que se firma con SHA-256."""
        header = {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "merkle_root": self.merkle_root,
            "difficulty": self.difficulty,
            "miner": self.miner,
        }
        return json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def hasher(self):
        """Objeto SHA-256 precargado con la cabecera, para minar de forma eficiente con .copy()."""
        return hashlib.sha256(self.header_bytes())

    def compute_hash(self, nonce: int | None = None) -> str:
        h = self.hasher()
        h.update(str(self.nonce if nonce is None else nonce).encode())
        return h.hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        return cls(**data)

    @classmethod
    def genesis(cls) -> "Block":
        block = cls(
            index=0,
            timestamp=utc_timestamp(),
            entries=[],
            previous_hash="0" * 64,
            difficulty=0,
            miner="Génesis",
        )
        block.hash = block.compute_hash()
        return block
