"""Red P2P de Sellalo: malla de N pares sobre TCP (JSON por línea, protocolo v2, contrato C5).

Un hilo acepta conexiones y cada par tiene su hilo de lectura (el mismo que hace PING/PONG y vigila el tiempo límite).
El saludo es HELLO -> HELLO_ACK -> AUTH con un reto aleatorio firmado con Ed25519, de modo que cada extremo prueba que
posee la clave que el génesis asigna a su identidad. Sólo después se aceptan BLOQUE, TX, GET_BLOQUES, etc.

Este módulo sólo depende de la interfaz que el nodo ofrece (`firmar`, `clave_publica_de`, `resumen`, ...), nunca de
las claves privadas.
"""
import ipaddress
import json
import os
import queue
import select
import socket
import threading
import time
from collections import OrderedDict

from models.cripto import canonico, es_hex, sha256_hex, verificar
from models.errores import ErrorEntrada, ErrorEstado

VERSION = 2
MAX_LINEA = 1024 * 1024          # 1 MiB por línea
MAX_BLOQUES_PAGINA = 100
MAX_BLOQUES_SYNC = 200_000       # tope de seguridad al armar una cadena ajena
FALTAS_PARA_VETO = 5
TIPOS_SALUDO = ("HELLO", "HELLO_ACK", "AUTH", "HELLO_REJECT")
TIPOS_BASE = ("PING", "PONG", "GET_BLOQUES", "BLOQUES", "BLOQUE", "TX", "BYE")


class _Cierre(Exception):
    """Fin ordenado de la conexión (no es un error del par)."""


class _Falta(Exception):
    """Falta del par: se suma al contador y, si es grave, se cierra la conexión."""

    def __init__(self, motivo: str, cerrar: bool = False):
        super().__init__(motivo)
        self.motivo = motivo
        self.cerrar = cerrar


class _Lector:
    """Lee mensajes JSON delimitados por salto de línea con búfer propio y tiempo límite."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = bytearray()

    def leer(self, espera: float):
        """Devuelve un dict, o None si venció `espera` sin mensaje completo. Lanza _Cierre o _Falta."""
        limite = time.monotonic() + espera
        while True:
            i = self.buf.find(b"\n")
            if i >= 0:
                linea = bytes(self.buf[:i])
                del self.buf[:i + 1]
                if len(linea) > MAX_LINEA:
                    raise _Falta("línea mayor a 1 MiB", cerrar=True)
                if not linea.strip():
                    continue
                try:
                    msg = json.loads(linea.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    raise _Falta("JSON inválido")
                if not isinstance(msg, dict) or not isinstance(msg.get("tipo"), str):
                    raise _Falta("mensaje sin campo 'tipo'")
                return msg
            if len(self.buf) > MAX_LINEA:
                self.buf.clear()
                raise _Falta("línea mayor a 1 MiB", cerrar=True)
            resto = limite - time.monotonic()
            if resto <= 0:
                return None
            try:
                listo, _, _ = select.select([self.sock], [], [], resto)
                if not listo:
                    return None
                datos = self.sock.recv(65536)
            except (OSError, ValueError):
                raise _Cierre("conexión perdida")
            if not datos:
                raise _Cierre("el par cerró la conexión")
            self.buf += datos


class _Par:
    def __init__(self, sock: socket.socket, ip: str, saliente: bool):
        self.sock = sock
        self.lector = _Lector(sock)
        self.ip = ip
        self.saliente = saliente
        self.id = ""
        self.direccion = ip
        self.altura = 0
        self.punta = ""
        self.trabajo = 0
        self.latencia_ms = None
        self.desde = 0.0
        self.autenticado = False
        self.activo = True
        self.ultimo_rx = time.monotonic()
        self.ultimo_ping = 0.0
        self.sincronizando = False
        self.cola_bloques = queue.Queue()
        self.lock_envio = threading.Lock()


class ServidorP2P:
    def __init__(self, nodo, host="0.0.0.0", puerto=6000, *, intervalo_ping=3.0, tiempo_sin_respuesta=12.0,
                 tiempo_saludo=5.0, tiempo_sync=10.0, segundos_veto=60.0, max_vistos=10_000):
        self.nodo = nodo
        self.host = host
        self.puerto = puerto
        self.intervalo_ping = intervalo_ping
        self.tiempo_sin_respuesta = tiempo_sin_respuesta
        self.tiempo_saludo = tiempo_saludo
        self.tiempo_sync = tiempo_sync
        self.segundos_veto = segundos_veto
        self.max_vistos = max_vistos
        self._lock = threading.RLock()
        self._pares: dict[str, _Par] = {}
        self._conexiones: set[_Par] = set()      # incluye las que aún no terminan el saludo
        self._manejadores: dict[str, object] = {}
        self._vistos: OrderedDict = OrderedDict()
        self._faltas: dict[str, int] = {}
        self._vetos: dict[str, float] = {}
        self._hilos: list[threading.Thread] = []
        self._escucha: socket.socket | None = None
        self._corriendo = False

    # ---------- utilidades ----------
    def _evento(self, tipo: str, texto: str) -> None:
        try:
            self.nodo.evento(tipo, texto)
        except Exception:
            pass

    @property
    def activo(self) -> bool:
        return self._corriendo

    def _exigir_desbloqueado(self) -> None:
        if not self.nodo.desbloqueado:
            raise ErrorEstado("El nodo está bloqueado: desbloquéalo para unirte a la red.")

    def _lanzar(self, destino, *args, nombre="p2p") -> None:
        h = threading.Thread(target=destino, args=args, daemon=True, name=nombre)
        with self._lock:
            self._hilos = [t for t in self._hilos if t.is_alive()]
            self._hilos.append(h)
        h.start()

    def faltas_de(self, clave: str) -> int:
        with self._lock:
            return self._faltas.get(clave, 0)

    def vetado(self, clave: str) -> bool:
        with self._lock:
            hasta = self._vetos.get(clave)
            if hasta is None:
                return False
            if time.monotonic() >= hasta:
                del self._vetos[clave]
                return False
            return True

    def _sumar_falta(self, clave: str, motivo: str) -> bool:
        """Suma una falta a `clave` (id del par o IP). Devuelve True si quedó vetado."""
        with self._lock:
            n = self._faltas.get(clave, 0) + 1
            veto = n >= FALTAS_PARA_VETO
            if veto:
                self._faltas.pop(clave, None)
                self._vetos[clave] = time.monotonic() + self.segundos_veto
            else:
                self._faltas[clave] = n
        self._evento("p2p", f"Falta de {clave}: {motivo} ({n}/{FALTAS_PARA_VETO})")
        if veto:
            self._evento("p2p", f"{clave} vetado {self.segundos_veto:g} s por faltas repetidas.")
        return veto

    def _visto(self, clave: str) -> bool:
        """Marca `clave` como vista; devuelve True si ya lo estaba."""
        with self._lock:
            if clave in self._vistos:
                self._vistos.move_to_end(clave)
                return True
            self._vistos[clave] = True
            while len(self._vistos) > self.max_vistos:
                self._vistos.popitem(last=False)
            return False

    @staticmethod
    def _clave_dedup(msg_tipo: str, obj) -> str:
        if isinstance(obj, dict):
            if msg_tipo == "BLOQUE" and isinstance(obj.get("hash"), str):
                return "B:" + obj["hash"]
            if msg_tipo == "TX" and isinstance(obj.get("id"), str):
                return "T:" + obj["id"]
        try:
            return msg_tipo + ":" + sha256_hex(canonico(obj))
        except (TypeError, ValueError):
            return msg_tipo + ":" + repr(obj)[:200]

    # ---------- envío ----------
    def _enviar(self, par: _Par, msg: dict) -> bool:
        try:
            datos = json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            with par.lock_envio:
                par.sock.sendall(datos)
            return True
        except (OSError, ValueError, TypeError):
            self._cerrar(par, "error al enviar")
            return False

    def _cerrar(self, par: _Par, motivo: str = "", avisar: bool = False) -> None:
        with self._lock:
            if not par.activo:
                return
            par.activo = False
            self._conexiones.discard(par)
            if par.id and self._pares.get(par.id) is par:
                del self._pares[par.id]
        if avisar:
            try:
                with par.lock_envio:
                    par.sock.sendall(b'{"tipo":"BYE"}\n')
            except OSError:
                pass
        for f in (lambda: par.sock.shutdown(socket.SHUT_RDWR), par.sock.close):
            try:
                f()
            except OSError:
                pass
        if par.autenticado and motivo:
            self._evento("p2p", f"Desconectado de {par.id}: {motivo}")

    # ---------- ciclo de vida ----------
    def iniciar(self) -> None:
        self._exigir_desbloqueado()
        with self._lock:
            if self._corriendo:
                raise ErrorEstado("El servidor P2P ya está iniciado.")
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                srv.bind((self.host, self.puerto))
                srv.listen(16)
            except OSError as exc:
                srv.close()
                raise ErrorEstado(f"No se pudo abrir el puerto TCP {self.puerto}: {exc.strerror or exc}")
            srv.settimeout(0.3)
            self.puerto = srv.getsockname()[1]
            self._escucha = srv
            self._corriendo = True
        self._lanzar(self._aceptar, srv, nombre="p2p-aceptar")
        self._evento("p2p", f"Escuchando pares en {self.host}:{self.puerto}.")

    def detener(self) -> None:
        with self._lock:
            if not self._corriendo and not self._conexiones:
                return
            self._corriendo = False
            srv, self._escucha = self._escucha, None
            conexiones = list(self._conexiones)
        if srv:
            try:
                srv.close()
            except OSError:
                pass
        for par in conexiones:
            self._cerrar(par, "servidor detenido", avisar=par.autenticado)
        with self._lock:
            hilos = list(self._hilos)
        for h in hilos:
            if h is not threading.current_thread():
                h.join(timeout=3)
        self._evento("p2p", "Servidor P2P detenido.")

    def _aceptar(self, srv: socket.socket) -> None:
        while self._corriendo:
            try:
                sock, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if self.vetado(addr[0]):
                sock.close()
                continue
            self._lanzar(self._atender_entrante, sock, addr[0], nombre="p2p-par")

    # ---------- saludo ----------
    def _hello(self, tipo: str, reto: str) -> dict:
        r = self.nodo.resumen()
        return {"tipo": tipo, "version": VERSION, "nodo": self.nodo.id, "genesis": self.nodo.hash_genesis,
                "altura": r["altura"], "trabajo": r["trabajo"], "punta": r["punta"], "reto": reto,
                "puerto": self.puerto}

    def _firma_reto(self, reto: str) -> str:
        return self.nodo.firmar(f"{reto}|{self.nodo.id}".encode("utf-8"))

    def _validar_datos_hello(self, msg: dict) -> tuple[str, bool] | None:
        """Valida forma y reglas del HELLO/HELLO_ACK ajeno. Devuelve (motivo, es_falta) o None si es válido."""
        def entero(v):
            return isinstance(v, int) and not isinstance(v, bool) and v >= 0
        if msg.get("version") != VERSION:
            return "versión de protocolo no soportada", True
        pid = msg.get("nodo")
        if not isinstance(pid, str) or not 0 < len(pid) <= 64:
            return "identidad inválida", True
        if not (entero(msg.get("altura")) and entero(msg.get("trabajo")) and isinstance(msg.get("punta"), str)
                and len(msg["punta"]) <= 128 and es_hex(msg.get("reto"), 32)):
            return "campos del saludo inválidos", True
        if not isinstance(msg.get("genesis"), str):
            return "génesis ausente", True
        if msg["genesis"] != self.nodo.hash_genesis:
            return "génesis distinto: no es la misma red", False
        if pid == self.nodo.id:
            return "identidad igual a la propia", False
        if self.nodo.clave_publica_de(pid) is None:
            return "identidad desconocida en el génesis", False
        if self.vetado(pid):
            return "par vetado temporalmente", False
        with self._lock:
            if pid in self._pares:
                return "par ya conectado", False
        return None

    def _registrar(self, par: _Par, msg: dict, puerto) -> str | None:
        with self._lock:
            if par.id in self._pares:
                return "par ya conectado"
            par.altura, par.trabajo, par.punta = msg["altura"], msg["trabajo"], msg["punta"]
            if isinstance(puerto, int) and not isinstance(puerto, bool) and 0 < puerto < 65536:
                par.direccion = f"{par.ip}:{puerto}"
            par.autenticado = True
            par.desde = time.time()
            self._pares[par.id] = par
        return None

    def _rechazar(self, par: _Par, motivo: str) -> None:
        self._enviar(par, {"tipo": "HELLO_REJECT", "motivo": motivo})
        self._cerrar(par, motivo)

    def _atender_entrante(self, sock: socket.socket, ip: str) -> None:
        sock.settimeout(10)
        par = _Par(sock, ip, saliente=False)
        with self._lock:
            if not self._corriendo:
                sock.close()
                return
            self._conexiones.add(par)
        try:
            if not self._saludo_entrante(par):
                return
            self._bucle(par)
        except Exception as exc:  # nada de lo que mande un par puede tumbar el hilo ni el servidor
            self._evento("p2p", f"Error con {par.id or ip}: {exc!r}")
        finally:
            self._cerrar(par, "fin de la conexión")

    def _leer_saludo(self, par: _Par, esperado: str):
        """Lee el siguiente mensaje del saludo. Devuelve el dict o None si hubo que cerrar."""
        try:
            msg = par.lector.leer(self.tiempo_saludo)
        except _Falta as f:
            self._sumar_falta(par.id or par.ip, f"saludo: {f.motivo}")
            self._rechazar(par, f"saludo inválido: {f.motivo}")
            return None
        except _Cierre:
            return None
        if msg is None:
            self._sumar_falta(par.id or par.ip, "saludo con tiempo agotado")
            self._rechazar(par, "tiempo de saludo agotado")
            return None
        if msg["tipo"] == "HELLO_REJECT":
            self._evento("p2p", f"{par.id or par.ip} rechazó el saludo: {str(msg.get('motivo'))[:120]}")
            self._cerrar(par)
            return None
        if msg["tipo"] != esperado:
            self._sumar_falta(par.id or par.ip, f"{msg['tipo'][:30]} antes de completar el saludo")
            self._rechazar(par, f"se esperaba {esperado} y llegó otro mensaje")
            return None
        return msg

    def _saludo_entrante(self, par: _Par) -> bool:
        msg = self._leer_saludo(par, "HELLO")
        if msg is None:
            return False
        problema = self._validar_datos_hello(msg)
        if problema:
            motivo, falta = problema
            if falta:
                self._sumar_falta(par.ip, f"HELLO inválido: {motivo}")
            self._rechazar(par, motivo)
            return False
        par.id = msg["nodo"]
        reto_propio = os.urandom(16).hex()
        try:
            ack = self._hello("HELLO_ACK", reto_propio)
            ack["firma_reto"] = self._firma_reto(msg["reto"])
        except Exception as exc:
            self._rechazar(par, f"no puedo firmar: {exc}")
            return False
        if not self._enviar(par, ack):
            return False
        auth = self._leer_saludo(par, "AUTH")
        if auth is None:
            return False
        pub = self.nodo.clave_publica_de(par.id)
        if not verificar(pub, f"{reto_propio}|{par.id}".encode("utf-8"), auth.get("firma_reto")):
            self._sumar_falta(par.id, "firma de reto inválida")
            self._rechazar(par, "firma del reto inválida")
            return False
        motivo = self._registrar(par, msg, msg.get("puerto"))
        if motivo:
            self._rechazar(par, motivo)
            return False
        self._evento("p2p", f"Par {par.id} autenticado (entrante, {par.direccion}).")
        self._tras_saludo(par)
        return True

    def conectar(self, ip: str, puerto) -> str:
        self._exigir_desbloqueado()
        if not self._corriendo:
            raise ErrorEstado("Inicia el servidor P2P antes de conectar con otros pares.")
        try:
            direccion = str(ipaddress.ip_address(str(ip).strip()))
        except ValueError:
            raise ErrorEntrada("IP inválida: escribe una dirección IPv4 o IPv6 válida, por ejemplo 192.168.1.20.")
        if isinstance(puerto, bool) or not isinstance(puerto, (int, str)):
            raise ErrorEntrada("Puerto inválido: debe ser un entero entre 1 y 65535.")
        try:
            puerto = int(puerto)
        except ValueError:
            raise ErrorEntrada("Puerto inválido: debe ser un entero entre 1 y 65535.")
        if not 1 <= puerto <= 65535:
            raise ErrorEntrada("Puerto inválido: debe estar entre 1 y 65535.")
        if self.vetado(direccion):
            raise ErrorEstado(f"{direccion} está vetado temporalmente.")
        try:
            sock = socket.create_connection((direccion, puerto), timeout=5)
        except OSError as exc:
            raise ErrorEstado(f"No se pudo conectar con {direccion}:{puerto}: {exc.strerror or exc}")
        sock.settimeout(10)
        par = _Par(sock, direccion, saliente=True)
        par.direccion = f"{direccion}:{puerto}"
        with self._lock:
            self._conexiones.add(par)
        try:
            reto = os.urandom(16).hex()
            if not self._enviar(par, self._hello("HELLO", reto)):
                raise ErrorEstado("No se pudo enviar el saludo.")
            msg = self._leer_saludo_saliente(par)
            problema = self._validar_datos_hello(msg)
            if problema:
                self._rechazar(par, problema[0])
                raise ErrorEstado(f"Saludo rechazado: {problema[0]}.")
            par.id = msg["nodo"]
            pub = self.nodo.clave_publica_de(par.id)
            if not verificar(pub, f"{reto}|{par.id}".encode("utf-8"), msg.get("firma_reto")):
                self._sumar_falta(par.id, "firma de reto inválida")
                self._rechazar(par, "firma del reto inválida")
                raise ErrorEstado("El par no pudo probar su identidad (firma del reto inválida).")
            auth = {"tipo": "AUTH", "firma_reto": self._firma_reto(msg["reto"])}
            motivo = self._registrar(par, msg, puerto)
            if motivo:
                self._rechazar(par, motivo)
                raise ErrorEstado(f"Saludo rechazado: {motivo}.")
            if not self._enviar(par, auth):
                raise ErrorEstado("Se perdió la conexión durante el saludo.")
        except BaseException:
            self._cerrar(par, "saludo fallido")
            raise
        self._evento("p2p", f"Par {par.id} autenticado (saliente, {par.direccion}).")
        self._tras_saludo(par)
        self._lanzar(self._bucle_seguro, par, nombre=f"p2p-par-{par.id}")
        return par.id

    def _leer_saludo_saliente(self, par: _Par) -> dict:
        try:
            msg = par.lector.leer(self.tiempo_saludo)
        except _Falta as f:
            raise ErrorEstado(f"Respuesta de saludo inválida: {f.motivo}.")
        except _Cierre:
            raise ErrorEstado("El par cerró la conexión durante el saludo.")
        if msg is None:
            raise ErrorEstado("El par no respondió al saludo a tiempo.")
        if msg["tipo"] == "HELLO_REJECT":
            raise ErrorEstado(f"El par rechazó el saludo: {str(msg.get('motivo'))[:120]}.")
        if msg["tipo"] != "HELLO_ACK":
            raise ErrorEstado("El par respondió con un mensaje inesperado al saludo.")
        return msg

    def _tras_saludo(self, par: _Par) -> None:
        if par.trabajo > self.nodo.resumen()["trabajo"]:
            self._iniciar_sync(par)

    # ---------- lectura ----------
    def _bucle_seguro(self, par: _Par) -> None:
        try:
            self._bucle(par)
        except Exception as exc:
            self._evento("p2p", f"Error con {par.id}: {exc!r}")
        finally:
            self._cerrar(par, "fin de la conexión")

    def _bucle(self, par: _Par) -> None:
        tick = max(0.05, min(0.25, self.intervalo_ping / 2))
        while par.activo and self._corriendo:
            try:
                msg = par.lector.leer(tick)
            except _Cierre as c:
                self._cerrar(par, str(c))
                return
            except _Falta as f:
                veto = self._sumar_falta(par.id, f.motivo)
                if f.cerrar or veto:
                    self._cerrar(par, f.motivo, avisar=True)
                    return
                continue
            ahora = time.monotonic()
            if msg is None:
                if ahora - par.ultimo_rx > self.tiempo_sin_respuesta:
                    self._cerrar(par, "sin respuesta (PING sin PONG)")
                    return
                if ahora - par.ultimo_ping >= self.intervalo_ping:
                    par.ultimo_ping = ahora
                    self._enviar(par, {"tipo": "PING", "t": time.time()})
                continue
            par.ultimo_rx = ahora
            try:
                self._despachar(par, msg)
            except _Cierre as c:
                self._cerrar(par, str(c))
                return
            except _Falta as f:
                veto = self._sumar_falta(par.id, f.motivo)
                if f.cerrar or veto:
                    self._cerrar(par, f.motivo, avisar=True)
                    return
            except Exception as exc:
                veto = self._sumar_falta(par.id, f"error procesando {str(msg.get('tipo'))[:30]}: {exc!r}")
                if veto:
                    self._cerrar(par, "demasiadas faltas", avisar=True)
                    return

    def _despachar(self, par: _Par, msg: dict) -> None:
        tipo = msg["tipo"]
        if tipo == "PING":
            self._enviar(par, {"tipo": "PONG", "t": msg.get("t")})
        elif tipo == "PONG":
            t = msg.get("t")
            if isinstance(t, (int, float)) and not isinstance(t, bool):
                par.latencia_ms = round(max(0.0, (time.time() - t) * 1000), 2)
        elif tipo == "BYE":
            raise _Cierre("el par se despidió (BYE)")
        elif tipo == "GET_BLOQUES":
            self._responder_bloques(par, msg)
        elif tipo == "BLOQUES":
            lote = msg.get("bloques")
            if not isinstance(lote, list) or len(lote) > MAX_BLOQUES_PAGINA or not all(isinstance(b, dict) for b in lote):
                raise _Falta("BLOQUES mal formado")
            if par.sincronizando:
                par.cola_bloques.put(lote)
        elif tipo == "BLOQUE":
            self._recibir_bloque(par, msg)
        elif tipo == "TX":
            self._recibir_tx(par, msg)
        elif tipo in TIPOS_SALUDO:
            raise _Falta(f"{tipo} fuera del saludo")
        else:
            with self._lock:
                fn = self._manejadores.get(tipo)
            if fn is None:
                raise _Falta(f"tipo de mensaje desconocido: {tipo[:30]}")
            try:
                fn(par.id, msg)
            except Exception as exc:
                self._evento("p2p", f"Error en el manejador de {tipo}: {exc!r}")

    def _responder_bloques(self, par: _Par, msg: dict) -> None:
        desde = msg.get("desde")
        if not isinstance(desde, int) or isinstance(desde, bool) or desde < 1:
            raise _Falta("GET_BLOQUES con 'desde' inválido")
        bloques = list(self.nodo.bloques_desde(desde, MAX_BLOQUES_PAGINA))[:MAX_BLOQUES_PAGINA]
        while True:
            datos = {"tipo": "BLOQUES", "desde": desde, "bloques": bloques}
            tamano = len(json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            if tamano < MAX_LINEA - 4096 or len(bloques) <= 1:
                break
            bloques = bloques[:max(1, len(bloques) // 2)]  # la página no cabe en una línea: se envía en trozos
        self._enviar(par, datos)

    def _recibir_bloque(self, par: _Par, msg: dict) -> None:
        bloque = msg.get("bloque")
        if not isinstance(bloque, dict):
            raise _Falta("BLOQUE sin objeto 'bloque'")
        if self._visto(self._clave_dedup("BLOQUE", bloque)):
            return
        if isinstance(bloque.get("numero"), int) and not isinstance(bloque["numero"], bool):
            par.altura = max(par.altura, bloque["numero"])
        if isinstance(bloque.get("hash"), str):
            par.punta = bloque["hash"][:128]
        estado, motivo = self.nodo.recibir_bloque(bloque, de=par.id)
        if estado == "aceptado":
            self.difundir("BLOQUE", {"bloque": bloque}, excepto=par.id)
        elif estado == "sincronizar":
            self._iniciar_sync(par)
        elif estado == "rechazado":
            raise _Falta(f"bloque rechazado: {str(motivo)[:120]}")

    def _recibir_tx(self, par: _Par, msg: dict) -> None:
        tx = msg.get("tx")
        if not isinstance(tx, dict):
            raise _Falta("TX sin objeto 'tx'")
        if self._visto(self._clave_dedup("TX", tx)):
            return
        try:
            self.nodo.agregar_transaccion(tx, origen=par.id)
        except (ErrorEntrada, ErrorEstado) as exc:
            raise _Falta(f"transacción rechazada: {str(exc)[:120]}")
        self.difundir("TX", {"tx": tx}, excepto=par.id)

    # ---------- sincronización ----------
    def _iniciar_sync(self, par: _Par) -> None:
        with self._lock:
            if par.sincronizando or not par.activo:
                return
            par.sincronizando = True
        while not par.cola_bloques.empty():
            par.cola_bloques.get_nowait()
        self._lanzar(self._sincronizar, par, nombre=f"p2p-sync-{par.id}")

    def _sincronizar(self, par: _Par) -> None:
        try:
            acumulado: list[dict] = []
            while par.activo and len(acumulado) < MAX_BLOQUES_SYNC:
                if not self._enviar(par, {"tipo": "GET_BLOQUES", "desde": len(acumulado) + 1}):
                    return
                try:
                    lote = par.cola_bloques.get(timeout=self.tiempo_sync)
                except queue.Empty:
                    self._evento("p2p", f"{par.id} no respondió a GET_BLOQUES.")
                    return
                if not lote:
                    break
                acumulado += lote
                if len(acumulado) >= par.altura:
                    break
            if not acumulado or not par.activo:
                return
            ok, motivo = self.nodo.recibir_cadena([self.nodo.genesis] + acumulado, de=par.id)
            self._evento("p2p", f"Sincronización con {par.id} ({len(acumulado)} bloques): "
                                f"{'cadena adoptada' if ok else 'no adoptada'} - {motivo}")
            if not ok and par.trabajo > self.nodo.resumen()["trabajo"]:
                self._sumar_falta(par.id, f"cadena anunciada no válida: {str(motivo)[:100]}")
        except Exception as exc:
            self._evento("p2p", f"Error sincronizando con {par.id}: {exc!r}")
        finally:
            par.sincronizando = False

    # ---------- API pública ----------
    def registrar_manejador(self, tipo: str, fn) -> None:
        if not isinstance(tipo, str) or not tipo or tipo in TIPOS_BASE or tipo in TIPOS_SALUDO:
            raise ErrorEntrada(f"No se puede registrar un manejador para '{tipo}'.")
        if not callable(fn):
            raise ErrorEntrada("El manejador debe ser invocable.")
        with self._lock:
            self._manejadores[tipo] = fn

    def difundir(self, tipo: str, datos: dict, excepto: str | None = None) -> int:
        """Envía {tipo, **datos} a todos los pares autenticados salvo `excepto`. Devuelve cuántos lo recibieron."""
        msg = {**datos, "tipo": tipo}
        if tipo in ("BLOQUE", "TX"):
            clave = "bloque" if tipo == "BLOQUE" else "tx"
            if clave in datos:
                self._visto(self._clave_dedup(tipo, datos[clave]))
        with self._lock:
            destinos = [p for p in self._pares.values() if p.id != excepto and p.activo]
        return sum(1 for p in destinos if self._enviar(p, msg))

    def desconectar(self, nodo_id: str) -> bool:
        with self._lock:
            par = self._pares.get(nodo_id)
        if par is None:
            return False
        self._cerrar(par, "desconectado por el usuario", avisar=True)
        return True

    def pares_publico(self) -> list[dict]:
        with self._lock:
            pares = list(self._pares.values())
        return [{"id": p.id, "direccion": p.direccion, "altura": p.altura, "punta": p.punta, "trabajo": p.trabajo,
                 "latencia_ms": p.latencia_ms, "estado": "sincronizando" if p.sincronizando else "conectado",
                 "conectado_desde": p.desde, "saliente": p.saliente} for p in pares]
