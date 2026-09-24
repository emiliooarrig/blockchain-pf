"""Utilidades criptográficas basadas en hashlib (SHA-256) y hmac."""
import hashlib
import hmac
from datetime import datetime, timezone


def sha256_hex(data) -> str:
    """SHA-256 en hexadecimal de un str o bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def safe_equals(a: str, b: str) -> bool:
    """Comparación de hashes en tiempo constante."""
    return hmac.compare_digest(a.encode(), b.encode())


def merkle_root(hashes: list[str]) -> str:
    """Raíz de Merkle de una lista de hashes SHA-256 (duplica el último si es impar)."""
    if not hashes:
        return sha256_hex(b"")
    level = list(hashes)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [sha256_hex(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def utc_timestamp() -> str:
    """Sello de tiempo ISO-8601 en UTC con microsegundos."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def format_timestamp(ts: str) -> str:
    """Formato legible de un sello de tiempo ISO-8601 UTC."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.strftime("%d/%m/%Y %H:%M:%S.%f")[:-3] + " UTC"
