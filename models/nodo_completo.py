"""Nodo completo de la red Sellalo: cadena persistente, pendientes, minado PoW real y selección de cadena.

Reglas (contrato C5 / C5.1):
- Selección de cadena: válida -> mayor trabajo acumulado (suma de 16**dificultad) -> hash de la punta menor.
- Reorganización: las transacciones de los bloques descartados que no estén en la nueva cadena vuelven a pendientes
  si siguen siendo válidas.
- Persistencia atómica en `dir_datos` (`cadena.json`, `pendientes.json`); la cadena se revalida completa al arrancar.
- La clave privada sólo existe en memoria mientras el nodo está desbloqueado; nunca sale en `publico()` ni en la bitácora.

Los callbacks de `al_cambiar` reciben `(tipo, dato)` y se invocan SIEMPRE fuera del candado del nodo:
    "bloque"          bloque minado localmente (difundir)         "tx"          transacción creada localmente (difundir)
    "bloque_recibido" bloque aceptado de un par (ya lo difunde el transporte)   "tx_recibida"  tx aceptada de un par
    "cadena"          se adoptó una cadena completa              "bloqueado"   el nodo se bloqueó (detener el servidor P2P)
    "minado"          cambió el estado del minado
"""
import json
import os
import tempfile
import threading
import time
from collections import deque

from models.bloque import (CAMPOS_POW, MAX_TX_POR_BLOQUE, Estado, ErrorValidacion, aplicar_transacciones, copiar,
                           es_entero, es_numero, hash_bloque, id_transaccion, preparar_hasher, revisar_campos,
                           revisar_transaccion)
from models import merkle
from models.errores import ErrorEntrada, ErrorEstado
from models.keystore import ErrorClave, abrir_almacen, leer_publica
from models.multifirma import es_sello, id_sello, revisar_sello
from models.pow import DIF_MAX, DIF_MIN, cumple_objetivo
from models.validacion import revisar_genesis, validar_bloque, validar_cadena

MAX_PENDIENTES = 200
MARGEN_FUTURO = 120.0       # segundos que se tolera un bloque "del futuro" respecto al reloj local
LOTE_HASHES = 2048          # intentos entre revisiones de cancelación / cambio de punta
ULTIMOS_BLOQUES_UI = 15
MAX_MAXIMO_BLOQUES = 100


def trabajo(cadena) -> int:
    """Trabajo acumulado: suma de 16**dificultad de los bloques que declaran dificultad."""
    total = 0
    for b in cadena:
        d = b.get("dificultad") if isinstance(b, dict) else None
        if es_entero(d) and 0 <= d <= 64:
            total += 16 ** d
    return total


def _id_tx(tx) -> str:
    return id_sello(tx) if es_sello(tx) else id_transaccion(tx)


def _json_puro(obj):
    """Copia profunda que además garantiza que el contenido es JSON puro (como si viniera de la red)."""
    return json.loads(json.dumps(obj))


def _escribir_atomico(ruta: str, datos) -> None:
    carpeta = os.path.dirname(os.path.abspath(ruta))
    os.makedirs(carpeta, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=carpeta)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, ruta)
    except BaseException:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise


class NodoCompleto:
    def __init__(self, dir_datos: str, genesis: dict, nodo_id: str, ruta_clave: str | None = None):
        try:
            revisar_genesis(genesis, genesis.get("hash") if isinstance(genesis, dict) else None)
        except (ErrorValidacion, TypeError, KeyError, AttributeError) as exc:
            raise ErrorEntrada(f"El bloque génesis no es válido: {exc}.") from None
        if genesis["parametros"].get("consenso") != "pow":
            raise ErrorEntrada("La red Sellalo usa consenso PoW; el génesis indica otro consenso.")
        if not isinstance(nodo_id, str) or nodo_id not in genesis["cuentas"]:
            raise ErrorEntrada(f"El nodo «{str(nodo_id)[:20]}» no existe en el génesis de la red.")
        if ruta_clave and os.path.exists(ruta_clave):
            id_archivo, publica = leer_publica(ruta_clave)
            if id_archivo != nodo_id:
                raise ErrorEntrada(f"El almacén de claves es de «{id_archivo}», no de «{nodo_id}».")
            if publica != genesis["cuentas"][nodo_id]["clave_publica"]:
                raise ErrorEntrada(f"La clave pública del almacén no coincide con la de {nodo_id} en el génesis.")

        self.id = nodo_id
        self.genesis = _json_puro(genesis)
        self.hash_genesis = self.genesis["hash"]
        self.dir_datos = dir_datos
        self.ruta_clave = ruta_clave
        self.lock = threading.RLock()
        self.al_cambiar: list = []
        self.bitacora = deque(maxlen=400)
        self._secuencia = 0
        self.revision = 0
        self._claves = None
        # minado
        self._hilo = None
        self._cancelar = threading.Event()
        self._despertar = threading.Event()
        self._version = 0           # sube cada vez que cambia la punta: reinicia la plantilla de minado
        self._minando = False
        self._stats = self._stats_vacias()

        self.cadena = [self.genesis]
        self.estado = Estado(self.genesis)
        self.pendientes: list[dict] = []
        self._hashes = {self.genesis["hash"]}
        self._trabajo = 0
        os.makedirs(dir_datos, exist_ok=True)
        self._cargar()

    # ------------------------------------------------------------------ utilidades
    @property
    def ruta_cadena(self) -> str:
        return os.path.join(self.dir_datos, "cadena.json")

    @property
    def ruta_pendientes(self) -> str:
        return os.path.join(self.dir_datos, "pendientes.json")

    def evento(self, tipo: str, texto: str) -> None:
        with self.lock:
            self._secuencia += 1
            self.bitacora.append({"n": self._secuencia, "t": time.time(), "tipo": str(tipo), "texto": str(texto)})

    def _emitir(self, eventos: list) -> None:
        """Avisa a los callbacks. Siempre se llama con el candado libre para no provocar interbloqueos."""
        for tipo, dato in eventos:
            for fn in list(self.al_cambiar):
                try:
                    fn(tipo, dato)
                except Exception as exc:
                    self.evento("error", f"Falló un callback ({tipo}): {exc!r}")

    @property
    def altura(self) -> int:
        return len(self.cadena) - 1

    @property
    def punta(self) -> str:
        return self.cadena[-1]["hash"]

    # ------------------------------------------------------------------ persistencia
    def _cargar(self) -> None:
        ruta = self.ruta_cadena
        if os.path.exists(ruta):
            motivo = None
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    cadena = json.load(f)
                if not isinstance(cadena, list) or not cadena or cadena[0].get("hash") != self.hash_genesis:
                    raise ErrorValidacion("la cadena guardada no pertenece a esta red")
                estado = validar_cadena(cadena, self.hash_genesis)
                cadena[0] = self.genesis
                self.cadena, self.estado = cadena, estado
            except (OSError, ValueError, ErrorValidacion, AttributeError, TypeError) as exc:
                motivo = str(exc) or type(exc).__name__
            if motivo:
                destino = f"{ruta}.corrupto-{int(time.time())}"
                try:
                    os.replace(ruta, destino)
                except OSError:
                    destino = "(no se pudo renombrar)"
                self.evento("corrupto", f"La cadena guardada no es válida ({motivo}); se movió a {os.path.basename(destino)} "
                                        f"y el nodo empieza desde el génesis.")
        self._hashes = {b["hash"] for b in self.cadena}
        self._trabajo = trabajo(self.cadena)
        cargadas = []
        try:
            with open(self.ruta_pendientes, "r", encoding="utf-8") as f:
                cargadas = json.load(f)
            if not isinstance(cargadas, list):
                cargadas = []
        except (OSError, ValueError):
            cargadas = []
        if cargadas:
            self.pendientes = self._depurar(cargadas[:MAX_PENDIENTES])
            if len(self.pendientes) != len(cargadas):
                self.evento("rechazo", f"{len(cargadas) - len(self.pendientes)} transacción(es) pendiente(s) guardada(s) "
                                       f"ya no son válidas y se descartaron.")
        self.evento("nodo", f"Nodo {self.id} cargado: altura {self.altura}, {len(self.pendientes)} pendiente(s).")

    def _guardar_cadena(self) -> None:
        try:
            _escribir_atomico(self.ruta_cadena, self.cadena)
        except OSError as exc:
            self.evento("error", f"No se pudo guardar la cadena: {exc}")

    def _guardar_pendientes(self) -> None:
        try:
            _escribir_atomico(self.ruta_pendientes, self.pendientes)
        except OSError as exc:
            self.evento("error", f"No se pudieron guardar los pendientes: {exc}")

    # ------------------------------------------------------------------ claves
    @property
    def desbloqueado(self) -> bool:
        return self._claves is not None

    def desbloquear(self, contrasena: str) -> None:
        if not self.ruta_clave:
            raise ErrorEstado("Este nodo no tiene un almacén de claves configurado.")
        with self.lock:
            if self._claves is not None:
                raise ErrorEstado("El nodo ya está desbloqueado.")
            claves = abrir_almacen(self.ruta_clave, contrasena)      # ErrorClave sube con su mensaje
            if claves.publica != self.genesis["cuentas"][self.id]["clave_publica"]:
                raise ErrorClave("La clave del almacén no coincide con la de este nodo en el génesis.")
            self._claves = claves
        self.evento("clave", f"Nodo {self.id} desbloqueado.")
        self._emitir([("desbloqueado", None)])

    def bloquear(self) -> None:
        self.detener_minado()
        with self.lock:
            era = self._claves is not None
            self._claves = None
        if era:
            self.evento("clave", f"Nodo {self.id} bloqueado: la clave se olvidó de la memoria.")
        self._emitir([("bloqueado", None)])

    def firmar(self, datos: bytes) -> str:
        claves = self._claves
        if claves is None:
            raise ErrorEstado("El nodo está bloqueado: desbloquéalo con su contraseña para firmar.")
        return claves.firmar(datos)

    def clave_publica_de(self, nodo_id) -> str | None:
        cuenta = self.genesis["cuentas"].get(nodo_id) if isinstance(nodo_id, str) else None
        return cuenta["clave_publica"] if cuenta else None

    # ------------------------------------------------------------------ interfaz del transporte
    def resumen(self) -> dict:
        with self.lock:
            return {"altura": self.altura, "trabajo": self._trabajo, "punta": self.punta}

    def bloques_desde(self, numero: int, maximo: int = MAX_MAXIMO_BLOQUES) -> list:
        if not es_entero(numero) or not es_entero(maximo):
            return []
        numero, maximo = max(1, numero), max(0, min(maximo, MAX_MAXIMO_BLOQUES))
        with self.lock:
            return list(self.cadena[numero:numero + maximo])

    # ------------------------------------------------------------------ pendientes
    def _depurar(self, candidatas: list, estado: Estado | None = None) -> list:
        """Devuelve las transacciones que siguen siendo válidas contra `estado`, sin duplicados y sin gastar de más."""
        estado = estado or self.estado
        vistos, comprometido, salida = set(), {}, []
        for tx in candidatas:
            try:
                if es_sello(tx):
                    tid = revisar_sello(estado, tx)
                else:
                    tid = revisar_transaccion(estado, tx)
                    gastado = comprometido.get(tx["emisor"], 0)
                    if tx["monto"] > estado.saldos[tx["emisor"]] - gastado:
                        continue
                    comprometido[tx["emisor"]] = gastado + tx["monto"]
            except (ErrorValidacion, KeyError, TypeError, ValueError, AttributeError):
                continue
            if tid in vistos:
                continue
            vistos.add(tid)
            salida.append(tx)
        return salida

    def agregar_transaccion(self, tx, origen: str = "") -> str:
        if not isinstance(tx, dict):
            raise ErrorEntrada("Transacción rechazada: no es un objeto.")
        try:
            tx = _json_puro(tx)
        except (TypeError, ValueError):
            raise ErrorEntrada("Transacción rechazada: no se puede serializar.") from None
        de = f" (de {origen})" if origen else ""
        with self.lock:
            if len(self.pendientes) >= MAX_PENDIENTES:
                raise ErrorEstado(f"La lista de pendientes está llena ({MAX_PENDIENTES}); mina un bloque primero.")
            try:
                if es_sello(tx):
                    tid = revisar_sello(self.estado.copia(), tx)
                else:
                    tid = revisar_transaccion(self.estado, tx)
            except ErrorValidacion as exc:
                self.evento("rechazo", f"Transacción rechazada{de}: {exc}.")
                raise ErrorEntrada(f"Transacción rechazada: {exc}.") from None
            except (KeyError, TypeError, ValueError, AttributeError):
                self.evento("rechazo", f"Transacción rechazada{de}: formato inválido.")
                raise ErrorEntrada("Transacción rechazada: formato inválido.") from None
            if any(_id_tx(p) == tid for p in self.pendientes):
                self.evento("rechazo", f"Transacción rechazada{de}: ya está en la lista de pendientes.")
                raise ErrorEntrada("Transacción rechazada: ya está en la lista de pendientes (duplicada).")
            if not es_sello(tx):
                disponible = self._disponible(tx["emisor"])
                if tx["monto"] > disponible:
                    self.evento("rechazo", f"Transacción rechazada{de}: saldo insuficiente de {tx['emisor']} "
                                           f"(disponible {disponible}, monto {tx['monto']}).")
                    raise ErrorEntrada(f"Saldo insuficiente: {tx['emisor']} tiene {disponible} disponible "
                                       f"e intenta enviar {tx['monto']}.")
            self.pendientes.append(tx)
            self._guardar_pendientes()
            if es_sello(tx):
                self.evento("sello", f"Sello de {tx['doc_hash'][:12]}… ({tx['laboratorio']}, "
                                     f"{len(tx['firmas'])}/{len(tx['autores'])} firmas){de}.")
            else:
                self.evento("tx", f"Transacción {tx['emisor']} → {tx['receptor']} por {tx['monto']}{de}.")
        self._despertar.set()
        self._emitir([("tx" if not origen else "tx_recibida", tx)])
        return tid

    def _disponible(self, nodo_id: str) -> int:
        comprometido = sum(p["monto"] for p in self.pendientes if not es_sello(p) and p["emisor"] == nodo_id)
        return self.estado.saldos[nodo_id] - comprometido

    # ------------------------------------------------------------------ cambios de cadena
    def _adoptar_bloque(self, bloque: dict, estado: Estado) -> None:
        """Bajo candado: agrega un bloque ya validado y deja todo consistente."""
        self.cadena.append(bloque)
        self.estado = estado
        self._hashes.add(bloque["hash"])
        self._trabajo = trabajo(self.cadena)
        antes = len(self.pendientes)
        self.pendientes = self._depurar(self.pendientes)
        self._guardar_cadena()
        self._guardar_pendientes()
        self._version += 1
        self.revision += 1
        self._despertar.set()
        quitadas = antes - len(self.pendientes)
        if quitadas:
            self.evento("tx", f"{quitadas} pendiente(s) salieron de la lista (incluidas en el bloque o ya inválidas).")

    def _futuro(self, ts) -> bool:
        return es_numero(ts) and ts > time.time() + MARGEN_FUTURO

    def recibir_bloque(self, bloque, de: str = "") -> tuple[str, str]:
        origen = f" de {de}" if de else ""
        try:
            return self._recibir_bloque(bloque, origen)
        except Exception as exc:  # nunca debe escapar una excepción por datos externos
            self.evento("rechazo", f"Bloque{origen} rechazado por error de formato ({type(exc).__name__}).")
            return "rechazado", f"bloque con formato inválido ({type(exc).__name__})"

    def _recibir_bloque(self, bloque, origen: str) -> tuple[str, str]:
        if not isinstance(bloque, dict) or not isinstance(bloque.get("hash"), str):
            return "rechazado", "el bloque no es un objeto con hash"
        eventos = []
        with self.lock:
            if bloque["hash"] in self._hashes:
                return "duplicado", "ya lo tengo"
            numero = bloque.get("numero")
            if not es_entero(numero):
                return "rechazado", "número de bloque inválido"
            if self._futuro(bloque.get("timestamp")):
                self.evento("rechazo", f"Bloque #{numero}{origen} rechazado: su timestamp está en el futuro.")
                return "rechazado", f"timestamp más de {MARGEN_FUTURO:g} s en el futuro"
            enlaza = numero == self.altura + 1 and bloque.get("hash_anterior") == self.punta
            if enlaza:
                bloque = _json_puro(bloque)
                estado = self.estado.copia()
                try:
                    validar_bloque(estado, bloque)
                except ErrorValidacion as exc:
                    self.evento("rechazo", f"Bloque #{numero}{origen} rechazado: {exc}.")
                    return "rechazado", str(exc)
                self._adoptar_bloque(bloque, estado)
                self.evento("bloque", f"Bloque #{numero} aceptado{origen} (proponente {bloque['proponente']}).")
                eventos.append(("bloque_recibido", bloque))
            elif numero < self.altura or (numero == self.altura and bloque["hash"] > self.punta):
                return "duplicado", "rama alterna de menor altura o de igual altura y hash mayor"
            elif numero == self.altura:
                # misma altura y hash menor: puede ganar el desempate; se pide la cadena (la decide recibir_cadena)
                try:
                    self._chequeo_ligero(bloque)
                except ErrorValidacion as exc:
                    self.evento("rechazo", f"Bloque #{numero}{origen} rechazado: {exc}.")
                    return "rechazado", str(exc)
                return "sincronizar", "rama alterna con hash menor: hay que comparar cadenas"
            else:
                try:
                    self._chequeo_ligero(bloque)
                except ErrorValidacion as exc:
                    self.evento("rechazo", f"Bloque #{numero}{origen} rechazado: {exc}.")
                    return "rechazado", str(exc)
                return "sincronizar", "no enlaza con mi punta: hay que pedir la cadena"
        self._emitir(eventos)
        return "aceptado", "ok"

    def _chequeo_ligero(self, bloque: dict) -> None:
        """Revisión barata de un bloque que no enlaza: formato, hash propio y prueba de trabajo."""
        revisar_campos(bloque, CAMPOS_POW)
        if hash_bloque(bloque) != bloque["hash"]:
            raise ErrorValidacion("el hash no coincide con el contenido del bloque (fue alterado)")
        d = bloque["dificultad"]
        if not es_entero(d) or not DIF_MIN <= d <= DIF_MAX or not cumple_objetivo(bloque["hash"], d):
            raise ErrorValidacion("el bloque no cumple la prueba de trabajo")

    def recibir_cadena(self, cadena, de: str = "") -> tuple[bool, str]:
        origen = f" de {de}" if de else ""
        try:
            return self._recibir_cadena(cadena, origen)
        except Exception as exc:
            self.evento("rechazo", f"Cadena{origen} rechazada por error ({type(exc).__name__}).")
            return False, f"cadena con formato inválido ({type(exc).__name__})"

    def _recibir_cadena(self, cadena, origen: str) -> tuple[bool, str]:
        try:
            copia = _json_puro(cadena)
        except (TypeError, ValueError):
            return False, "la cadena recibida no es serializable"
        try:
            estado = validar_cadena(copia, self.hash_genesis)
        except ErrorValidacion as exc:
            self.evento("rechazo", f"Cadena{origen} rechazada: {exc}.")
            return False, str(exc)
        if any(self._futuro(b["timestamp"]) for b in copia[1:]):
            self.evento("rechazo", f"Cadena{origen} rechazada: contiene bloques con timestamp en el futuro.")
            return False, f"contiene bloques con timestamp más de {MARGEN_FUTURO:g} s en el futuro"
        copia[0] = self.genesis
        nuevo_trabajo = trabajo(copia)
        eventos = []
        with self.lock:
            propia = self._trabajo
            if nuevo_trabajo < propia:
                return False, f"la cadena recibida tiene menos trabajo ({nuevo_trabajo} contra {propia})"
            if nuevo_trabajo == propia:
                if copia[-1]["hash"] == self.punta:
                    return False, "ya tengo esa cadena"
                if copia[-1]["hash"] > self.punta:
                    return False, "mismo trabajo y la punta de la cadena recibida tiene un hash mayor"
            vieja = self.cadena
            nuevos = {b["hash"] for b in copia}
            huerfanas = [tx for b in vieja[1:] if b["hash"] not in nuevos for tx in b["transacciones"]]
            self.cadena, self.estado = copia, estado
            self._hashes = nuevos
            self._trabajo = nuevo_trabajo
            devueltas = self._depurar(huerfanas + self.pendientes)
            recuperadas = len([t for t in devueltas if t not in self.pendientes])
            self.pendientes = devueltas[:MAX_PENDIENTES]
            self._guardar_cadena()
            self._guardar_pendientes()
            self._version += 1
            self.revision += 1
            self._despertar.set()
            descartados = len([b for b in vieja[1:] if b["hash"] not in nuevos])
            self.evento("bloque", f"Cadena{origen} adoptada: altura {self.altura}, trabajo {nuevo_trabajo}"
                                  f"{f', {descartados} bloque(s) propios descartados' if descartados else ''}"
                                  f"{f', {recuperadas} transacción(es) vuelven a pendientes' if recuperadas else ''}.")
            eventos.append(("cadena", None))
        self._emitir(eventos)
        return True, "adoptada"

    # ------------------------------------------------------------------ minado real
    @staticmethod
    def _stats_vacias() -> dict:
        return {"intentos": 0, "hashes_por_s": 0.0, "nonce": 0, "dificultad": 0, "bloque": 0, "inicio": 0.0,
                "bloques_minados": 0}

    @property
    def minando(self) -> bool:
        return self._minando

    def iniciar_minado(self, dificultad: int, continuo: bool = False) -> str:
        if not es_entero(dificultad) or not DIF_MIN <= dificultad <= DIF_MAX:
            raise ErrorEntrada(f"La dificultad debe ser un entero entre {DIF_MIN} y {DIF_MAX}.")
        with self.lock:
            if self._claves is None:
                raise ErrorEstado("El nodo está bloqueado: desbloquéalo con su contraseña para minar.")
            if self._minando:
                raise ErrorEstado("Ya hay un minado en curso; detenlo primero.")
            if not self._seleccionar()[0] and not continuo:
                raise ErrorEstado("No hay transacciones pendientes válidas: crea al menos una antes de minar.")
            self._cancelar = threading.Event()
            self._stats = {**self._stats_vacias(), "dificultad": dificultad, "inicio": time.monotonic()}
            self._minando = True
            self._hilo = threading.Thread(target=self._bucle_minado, args=(self._cancelar, dificultad, continuo),
                                          daemon=True, name=f"minado-{self.id}")
            self._hilo.start()
            self.evento("pow", f"Inicia el minado con dificultad {dificultad}{' (continuo)' if continuo else ''}.")
        self._emitir([("minado", True)])
        return f"Minado iniciado con dificultad {dificultad}."

    def detener_minado(self) -> None:
        with self.lock:
            hilo, cancelar = self._hilo, self._cancelar
            cancelar.set()
        self._despertar.set()
        if hilo is not None and hilo is not threading.current_thread():
            hilo.join(timeout=5)

    def _seleccionar(self) -> tuple[list, Estado]:
        """Bajo candado: hasta MAX_TX_POR_BLOQUE pendientes que se aplican limpiamente en orden."""
        numero = self.altura + 1
        estado, elegidas = self.estado.copia(), []
        for tx in self.pendientes:
            if len(elegidas) >= MAX_TX_POR_BLOQUE:
                break
            intento = estado.copia()
            try:
                aplicar_transacciones(intento, [tx], numero)
            except ErrorValidacion:
                continue
            estado = intento
            elegidas.append(tx)
        return elegidas, estado

    def _plantilla(self, dificultad: int) -> dict | None:
        with self.lock:
            txs, _ = self._seleccionar()
            if not txs:
                return None
            return {"numero": self.altura + 1, "timestamp": max(round(time.time(), 6), self.estado.ultimo_ts),
                    "transacciones": copiar(txs), "hash_anterior": self.punta,
                    "raiz_merkle": merkle.raiz_transacciones(txs), "nonce": 0, "dificultad": dificultad,
                    "proponente": self.id, "recompensa": self.estado.params["recompensa"], "_version": self._version}

    def _bucle_minado(self, cancelar: threading.Event, dificultad: int, continuo: bool) -> None:
        try:
            while not cancelar.is_set():
                plantilla = self._plantilla(dificultad)
                if plantilla is None:
                    if not continuo:
                        self.evento("pow", "Se acabaron las transacciones pendientes; el minado se detiene.")
                        break
                    self._despertar.clear()
                    if self._plantilla_hay():
                        continue
                    self._despertar.wait(1.0)
                    continue
                version = plantilla.pop("_version")
                resultado = self._buscar_nonce(plantilla, dificultad, cancelar, version)
                if resultado is None:
                    continue
                plantilla["nonce"], plantilla["hash"] = resultado
                if self._cerrar_bloque(plantilla, version, cancelar) and not continuo:
                    break
        except Exception as exc:
            self.evento("error", f"El hilo de minado terminó por un error: {exc!r}")
        finally:
            with self.lock:
                if self._cancelar is cancelar:
                    self._minando = False
            self.evento("pow", "Minado detenido.")
            self._emitir([("minado", False)])

    def _plantilla_hay(self) -> bool:
        with self.lock:
            return bool(self._seleccionar()[0])

    def _buscar_nonce(self, plantilla: dict, dificultad: int, cancelar: threading.Event, version: int):
        calcular = preparar_hasher(plantilla)
        prefijo = "0" * dificultad
        st = self._stats
        st["bloque"] = plantilla["numero"]
        nonce, t0 = 0, time.monotonic()
        base = st["intentos"]
        while True:
            for _ in range(LOTE_HASHES):
                h = calcular(nonce)
                if h.startswith(prefijo):
                    self._actualizar_stats(st, base, nonce + 1, nonce, t0)
                    return nonce, h
                nonce += 1
            self._actualizar_stats(st, base, nonce, nonce, t0)
            if cancelar.is_set() or self._version != version:
                return None

    @staticmethod
    def _actualizar_stats(st: dict, base: int, intentos: int, nonce: int, t0: float) -> None:
        dt = max(time.monotonic() - t0, 1e-6)
        st["intentos"] = base + intentos
        st["nonce"] = nonce
        st["hashes_por_s"] = round(intentos / dt, 1)

    def _cerrar_bloque(self, bloque: dict, version: int, cancelar: threading.Event) -> bool:
        """Firma, valida y agrega el bloque minado si la punta no cambió. Devuelve True si se agregó."""
        with self.lock:
            if cancelar.is_set() or self._version != version or self._claves is None:
                return False
            bloque["firma_minero"] = self._claves.firmar(bytes.fromhex(bloque["hash"]))
            estado = self.estado.copia()
            try:
                validar_bloque(estado, bloque)
            except ErrorValidacion as exc:
                self.evento("error", f"El bloque minado no pasó la validación local: {exc}.")
                return False
            self._adoptar_bloque(bloque, estado)
            self._stats["bloques_minados"] += 1
            self.evento("bloque", f"Bloque #{bloque['numero']} minado (nonce {bloque['nonce']}, "
                                  f"hash {bloque['hash'][:12]}…).")
        self._emitir([("bloque", bloque)])
        return True

    # ------------------------------------------------------------------ consultas
    def prioridad(self, doc_hash: str) -> list:
        """Sellos del documento en orden de cadena: el primero tiene la prioridad."""
        with self.lock:
            sellos = self.estado.sellos.get(doc_hash) if isinstance(doc_hash, str) else None
            if not sellos:
                return []
            conf = self.estado.params["confirmaciones"]
            salida = []
            for i, s in enumerate(sellos):
                bloque = self.cadena[s["numero"]]
                confirmaciones = self.altura - s["numero"]
                salida.append({**s, "doc_hash": doc_hash, "prioritario": i == 0, "fecha_bloque": bloque["timestamp"],
                               "hash_bloque": bloque["hash"], "confirmaciones": confirmaciones,
                               "requeridas": conf, "confirmado": confirmaciones >= conf})
            return salida

    def publico(self) -> dict:
        """Vista para la UI. Nunca incluye claves privadas ni contraseñas."""
        with self.lock:
            est, conf = self.estado, self.estado.params["confirmaciones"]
            pendientes = []
            for tx in self.pendientes:
                if es_sello(tx):
                    pendientes.append({"id": id_sello(tx), "tipo": "sello", "doc_hash": tx["doc_hash"],
                                       "titulo": tx["titulo"], "laboratorio": tx["laboratorio"],
                                       "firmas": len(tx["firmas"]), "umbral": tx["umbral"]})
                else:
                    pendientes.append({"id": id_transaccion(tx), "tipo": "transferencia", "emisor": tx["emisor"],
                                       "receptor": tx["receptor"], "monto": tx["monto"]})
            cuentas = [{"id": nid, "saldo": est.saldos[nid], "disponible": self._disponible(nid),
                        "pendiente_recompensa": est.pendiente_de(nid)} for nid in est.claves]
            ultimos = [{"numero": b["numero"], "hash": b["hash"], "proponente": b["proponente"],
                        "dificultad": b.get("dificultad"), "transacciones": len(b["transacciones"]),
                        "timestamp": b["timestamp"], "confirmaciones": self.altura - b["numero"]}
                       for b in self.cadena[-ULTIMOS_BLOQUES_UI:]][::-1]
            return {"id": self.id, "altura": self.altura, "punta": self.punta, "trabajo": self._trabajo,
                    "revision": self.revision, "hash_genesis": self.hash_genesis, "desbloqueado": self.desbloqueado,
                    "minando": self._minando, "estadisticas": dict(self._stats), "confirmaciones": conf,
                    "recompensa": est.params["recompensa"], "max_tx_por_bloque": MAX_TX_POR_BLOQUE,
                    "max_pendientes": MAX_PENDIENTES, "pendientes": pendientes, "cuentas": cuentas,
                    "ultimos_bloques": ultimos, "bitacora": list(self.bitacora)[-100:]}


def conectar_nodo_y_servidor(nodo: NodoCompleto, servidor):
    """Une un nodo con su ServidorP2P: difunde lo creado localmente y detiene el servidor al bloquear el nodo.
    Devuelve el callback registrado (por si se quiere quitar de `nodo.al_cambiar`)."""
    def al_cambiar(tipo, dato):
        if tipo == "bloque":
            servidor.difundir("BLOQUE", {"bloque": dato})
        elif tipo == "tx":
            servidor.difundir("TX", {"tx": dato})
        elif tipo == "bloqueado":
            servidor.detener()
    nodo.al_cambiar.append(al_cambiar)
    return al_cambiar
