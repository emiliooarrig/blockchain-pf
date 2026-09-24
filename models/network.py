"""Conexión TCP/IP entre las dos PCs (Alice y Bob).

Cada PC abre un servidor TCP (por defecto en el puerto 5050) y una de ellas se
conecta a la IP de la otra dentro de la red local. Los mensajes viajan como
JSON, uno por línea, sobre una sola conexión persistente:

    HELLO / HELLO_ACK / HELLO_REJECT   saludo con identidad, cadena y pendientes
    PING / PONG                        latencia y detección de caídas
    ENTRY / PENDING / CHAIN_SYNC       sincronización de entradas y de la cadena
    MINE_START / MINE_ACK              inicio coordinado del minado
    PROGRESS / BLOCK_FOUND / MINE_STOP carrera de minado
    BYE                                desconexión voluntaria
"""
import ipaddress
import json
import socket
import threading
import time
import uuid
from collections import deque
from datetime import datetime

from models.blockchain import Blockchain
from models.mining import MINERS, MiningRace

PROTOCOL = "labchain/1"
DEFAULT_PEER_PORT = 5050
CONNECT_TIMEOUT = 5
HEARTBEAT_EVERY = 3
HEARTBEAT_TIMEOUT = 12
MAX_MESSAGE = 16 * 1024 * 1024  # 16 MB por mensaje


def local_ips() -> list[str]:
    """IPs IPv4 de esta PC en la red local (la de la interfaz de salida primero)."""
    ips = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))  # UDP no envía paquetes: solo elige la interfaz de salida
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


class PeerNode:
    def __init__(self, blockchain: Blockchain, race: MiningRace, port: int = DEFAULT_PEER_PORT,
                 host: str = "0.0.0.0", identity: str | None = None):
        self.blockchain = blockchain
        self.race = race
        self.host = host
        self.port = port
        self.identity = identity if identity in MINERS else None
        self.lock = threading.RLock()
        self.send_lock = threading.Lock()
        self.conn: socket.socket | None = None
        self.rfile = None
        self.connecting = False
        self.peer: dict = {}
        self.connected_at = ""
        self.last_seen = 0.0
        self.latency_ms: float | None = None
        self.last_error = ""
        self.listening = False
        self.listen_error = ""
        self.events: deque = deque(maxlen=14)
        self.requests: dict[str, dict] = {}
        race.attach_network(self)

    # ---------- registro ----------
    def log(self, text: str) -> None:
        self.events.appendleft({"time": datetime.now().strftime("%H:%M:%S"), "text": text})

    @property
    def connected(self) -> bool:
        return self.conn is not None

    @property
    def remote_identity(self) -> str | None:
        return self.peer.get("name") if self.connected else None

    # ---------- servidor ----------
    def start(self) -> None:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.host, self.port))
            srv.listen(2)
        except OSError as exc:
            self.listen_error = f"No se pudo abrir el puerto TCP {self.port}: {exc.strerror or exc}"
            self.log(self.listen_error)
            return
        self.listening = True
        self.log(f"Servidor TCP escuchando en {self.host}:{self.port}.")
        threading.Thread(target=self._accept_loop, args=(srv,), daemon=True, name="peer-accept").start()

    def _accept_loop(self, srv: socket.socket) -> None:
        while True:
            try:
                conn, addr = srv.accept()
            except OSError:
                return
            threading.Thread(target=self._handle_incoming, args=(conn, addr), daemon=True,
                             name="peer-handshake").start()

    # ---------- utilidades de socket ----------
    @staticmethod
    def _encode(msg: dict) -> bytes:
        return json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"

    @staticmethod
    def _read(rfile) -> dict:
        line = rfile.readline(MAX_MESSAGE + 1)
        if not line:
            raise ConnectionError("conexión cerrada")
        if len(line) > MAX_MESSAGE or not line.endswith(b"\n"):
            raise ValueError("mensaje demasiado grande o incompleto")
        msg = json.loads(line)
        if not isinstance(msg, dict):
            raise ValueError("mensaje inválido")
        return msg

    def _hello(self, kind: str) -> dict:
        return {"type": kind, "protocol": PROTOCOL, "identity": self.identity, "listen_port": self.port,
                "chain": self.blockchain.chain_snapshot(), "pending": self.blockchain.pending_snapshot()}

    @staticmethod
    def _close(conn: socket.socket) -> None:
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        conn.close()

    # ---------- identidad ----------
    def set_identity(self, name: str) -> None:
        if name not in MINERS:
            raise ValueError("Identidad inválida.")
        with self.lock:
            if self.connected:
                raise RuntimeError("Desconéctate antes de cambiar la identidad.")
            self.identity = name
        self.log(f"Esta PC ahora es {name}.")

    # ---------- conexión saliente ----------
    def connect(self, ip: str, port: int) -> None:
        try:
            ip = str(ipaddress.ip_address(ip.strip()))
        except ValueError:
            raise ValueError("La IP no es válida (ejemplo: 192.168.1.20).")
        if not 1 <= port <= 65535:
            raise ValueError("El puerto debe estar entre 1 y 65535.")
        with self.lock:
            if self.connected:
                raise RuntimeError("Ya hay una conexión activa.")
            if not self.identity:
                raise RuntimeError("Elige si esta PC es Alice o Bob antes de conectar.")
            if self.connecting:
                raise RuntimeError("Ya hay un intento de conexión en curso.")
            self.connecting = True
        try:
            self._connect(ip, port)
        finally:
            self.connecting = False

    def _connect(self, ip: str, port: int) -> None:
        self.log(f"Abriendo conexión TCP con {ip}:{port}…")
        try:
            conn = socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT)
        except OSError as exc:
            self.last_error = f"No se pudo conectar con {ip}:{port} ({exc.strerror or exc})."
            self.log(self.last_error)
            raise ConnectionError(self.last_error + " Verifica la IP, que la app esté abierta en la otra PC "
                                                    "y que el firewall permita el puerto.")
        self.log("Conexión TCP establecida. Enviando HELLO…")
        try:
            conn.settimeout(CONNECT_TIMEOUT)
            rfile = conn.makefile("rb")
            conn.sendall(self._encode(self._hello("HELLO")))
            reply = self._read(rfile)
        except (OSError, ValueError, ConnectionError):
            self._close(conn)
            self.last_error = "La otra PC no respondió al saludo (¿es una instancia de esta app?)."
            self.log(self.last_error)
            raise ConnectionError(self.last_error)

        if reply.get("type") == "HELLO_REJECT":
            self._close(conn)
            self.last_error = f"Conexión rechazada: {reply.get('reason', 'sin motivo')}"
            self.log(self.last_error)
            raise ConnectionError(self.last_error)
        remote = reply.get("identity")
        if reply.get("type") != "HELLO_ACK" or reply.get("protocol") != PROTOCOL or remote not in MINERS \
                or remote == self.identity:
            self._close(conn)
            self.last_error = "Respuesta de saludo inválida o identidad repetida."
            self.log(self.last_error)
            raise ConnectionError(self.last_error)
        self._attach(conn, rfile, remote, ip, port, "saliente", reply)

    # ---------- conexión entrante ----------
    def _handle_incoming(self, conn: socket.socket, addr) -> None:
        ip = addr[0]
        try:
            conn.settimeout(CONNECT_TIMEOUT)
            rfile = conn.makefile("rb")
            hello = self._read(rfile)
        except (OSError, ValueError, ConnectionError):
            self._close(conn)
            return
        if hello.get("type") != "HELLO" or hello.get("protocol") != PROTOCOL:
            self._close(conn)
            return

        remote = hello.get("identity")
        reason = None
        with self.lock:
            if self.connected or self.connecting:
                reason = "La otra PC ya tiene una conexión activa."
            elif remote not in MINERS:
                reason = "Identidad desconocida."
            elif self.identity == remote:
                reason = f"Ambas PCs eligieron ser {remote}. Cambien la identidad en una de ellas."
            else:
                if not self.identity:
                    self.identity = next(n for n in MINERS if n != remote)
                    self.log(f"Identidad asignada automáticamente: esta PC es {self.identity}.")
                self.connecting = True
        if reason:
            self.log(f"Conexión entrante de {ip} rechazada: {reason}")
            try:
                conn.sendall(self._encode({"type": "HELLO_REJECT", "reason": reason}))
            except OSError:
                pass
            self._close(conn)
            return

        self.log(f"Conexión entrante de {ip} ({remote}). Respondiendo HELLO_ACK…")
        try:
            conn.sendall(self._encode(self._hello("HELLO_ACK")))
            port = hello.get("listen_port") if type(hello.get("listen_port")) is int else addr[1]
            self._attach(conn, rfile, remote, ip, port, "entrante", hello)
        except (OSError, RuntimeError):
            self._close(conn)
        finally:
            self.connecting = False

    # ---------- sesión ----------
    def _attach(self, conn, rfile, name, ip, port, direction, hello) -> None:
        with self.lock:
            if self.connected:
                self._close(conn)
                raise RuntimeError("Ya hay una conexión activa.")
            conn.settimeout(None)
            self.conn, self.rfile = conn, rfile
            self.peer = {"name": name, "ip": ip, "port": port, "direction": direction}
            self.connected_at = datetime.now().strftime("%H:%M:%S")
            self.last_seen = time.monotonic()
            self.latency_ms = None
            self.last_error = ""
        self.log(f"Handshake completado: {self.identity} ⇄ {name} ({ip}:{port}).")
        self.log(self.blockchain.sync_with(hello.get("chain")))
        added = self.blockchain.merge_pending(hello.get("pending"))
        if added:
            self.log(f"Se recibieron {added} entrada(s) pendiente(s) de {name}.")
        threading.Thread(target=self._reader, args=(conn, rfile), daemon=True, name="peer-reader").start()
        threading.Thread(target=self._heartbeat, args=(conn,), daemon=True, name="peer-heartbeat").start()
        # Tras sincronizar, se reenvían las pendientes (incluye entradas que quedaron huérfanas).
        self.send({"type": "PENDING", "entries": self.blockchain.pending_snapshot()})

    def send(self, msg: dict) -> bool:
        conn = self.conn
        if conn is None:
            return False
        try:
            data = self._encode(msg)
            with self.send_lock:
                conn.sendall(data)
            return True
        except OSError:
            self._drop("Error al enviar datos; se cerró la conexión.", conn)
            return False

    def request(self, msg: dict, timeout: float = CONNECT_TIMEOUT) -> dict | None:
        """Envía un mensaje y espera su respuesta (`reply_to`)."""
        rid = uuid.uuid4().hex
        slot = {"event": threading.Event(), "reply": None}
        self.requests[rid] = slot
        try:
            if not self.send({**msg, "request_id": rid}):
                return None
            slot["event"].wait(timeout)
            return slot["reply"]
        finally:
            self.requests.pop(rid, None)

    def resync(self) -> None:
        self.send({"type": "CHAIN_SYNC", "chain": self.blockchain.chain_snapshot(),
                   "pending": self.blockchain.pending_snapshot()})

    def broadcast_entry(self, entry: dict) -> None:
        self.send({"type": "ENTRY", "entry": entry})

    def disconnect(self) -> None:
        if self.connected:
            self.send({"type": "BYE"})
            self._drop("Desconectado por el usuario.")

    def _drop(self, reason: str, conn=None) -> None:
        with self.lock:
            if self.conn is None or (conn is not None and conn is not self.conn):
                return
            old, self.conn, self.rfile = self.conn, None, None
            self.latency_ms = None
            if reason != "Desconectado por el usuario.":
                self.last_error = reason
        self.log(reason)
        self._close(old)
        for slot in list(self.requests.values()):
            slot["event"].set()
        self.race.on_disconnect()

    # ---------- hilos de la sesión ----------
    def _reader(self, conn, rfile) -> None:
        try:
            while True:
                msg = self._read(rfile)
                self.last_seen = time.monotonic()
                self._dispatch(msg)
        except (OSError, ValueError, ConnectionError):
            pass
        self._drop("La otra PC cerró la conexión.", conn)

    def _heartbeat(self, conn) -> None:
        while self.conn is conn:
            time.sleep(HEARTBEAT_EVERY)
            if self.conn is not conn:
                return
            if time.monotonic() - self.last_seen > HEARTBEAT_TIMEOUT:
                self._drop("Sin respuesta de la otra PC (tiempo de espera agotado).", conn)
                return
            self.send({"type": "PING", "t": time.perf_counter()})

    def _dispatch(self, msg: dict) -> None:
        kind = msg.get("type")
        name = self.peer.get("name", "La otra PC")

        if isinstance(msg.get("reply_to"), str):
            slot = self.requests.get(msg["reply_to"])
            if slot:
                slot["reply"] = msg
                slot["event"].set()
            return

        if kind == "PING":
            self.send({"type": "PONG", "t": msg.get("t")})
        elif kind == "PONG":
            if isinstance(msg.get("t"), (int, float)):
                self.latency_ms = round((time.perf_counter() - msg["t"]) * 1000, 1)
        elif kind == "PROGRESS":
            self.race.on_remote_progress(msg.get("miner"))
        elif kind == "MINE_START":
            reply = self.race.on_remote_start(msg.get("template"))
            self.send({"type": "MINE_ACK", "reply_to": msg.get("request_id"), **reply})
            self.log(f"{name} inició el minado." if reply.get("ok") else
                     f"Se rechazó el minado de {name}: {reply.get('reason')}")
        elif kind == "BLOCK_FOUND":
            self.log(f"{name} anunció un bloque encontrado.")
            self.race.on_remote_block(msg.get("block"))
        elif kind == "MINE_STOP":
            self.log(f"{name} detuvo el minado.")
            self.race.on_remote_stop()
        elif kind == "ENTRY":
            if self.blockchain.merge_pending([msg.get("entry")]):
                self.log(f"Nueva entrada pendiente recibida de {name}.")
        elif kind == "PENDING":
            added = self.blockchain.merge_pending(msg.get("entries"))
            if added:
                self.log(f"Se sincronizaron {added} entrada(s) pendiente(s) de {name}.")
        elif kind == "CHAIN_SYNC":
            self.log(self.blockchain.sync_with(msg.get("chain")))
            self.blockchain.merge_pending(msg.get("pending"))
            if not msg.get("reply"):
                self.send({"type": "CHAIN_SYNC", "reply": True, "chain": self.blockchain.chain_snapshot(),
                           "pending": self.blockchain.pending_snapshot()})
        elif kind == "BYE":
            self._drop(f"{name} se desconectó.")

    # ---------- estado para la vista ----------
    def status(self) -> dict:
        connected = self.connected
        return {
            "connected": connected,
            "connecting": self.connecting,
            "identity": self.identity,
            "remote_identity": self.remote_identity,
            "peer": dict(self.peer) if connected else {},
            "latency_ms": self.latency_ms if connected else None,
            "connected_since": self.connected_at if connected else "",
            "local_ips": local_ips(),
            "listen_port": self.port,
            "default_peer_port": DEFAULT_PEER_PORT,
            "listening": self.listening,
            "listen_error": self.listen_error,
            "last_error": "" if connected else self.last_error,
            "events": list(self.events),
        }
