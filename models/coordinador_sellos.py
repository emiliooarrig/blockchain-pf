"""Coordinación de sellos multifirma entre los laboratorios de la red (contrato C7).

Un sello k-de-n no entra a pendientes hasta reunir `umbral` firmas válidas. Mientras tanto vive «en firma»:
el laboratorio que lo registra lo difunde (`SELLO_PROPUESTO`), cada co-autor lo ve como solicitud y, al firmarlo,
difunde su firma (`SELLO_FIRMA`). Quien completa el umbral lo agrega a sus pendientes (y se difunde como `TX`).

Los datos que llegan de la red nunca lanzan excepciones hacia el transporte: se descartan y quedan en la bitácora.
"""
import json
import os
import tempfile
import threading
import time

from models.bloque import ErrorValidacion
from models.cripto import es_hex
from models.errores import ErrorEntrada, ErrorEstado
from models.multifirma import (CAMPOS_SELLO, agregar_firma, firmar_sello, firmas_validas, id_sello, mensaje_sello,
                               nuevo_sello, es_sello)

CADUCIDAD = 24 * 3600.0       # un sello sin firmas suficientes se olvida a las 24 h
MAX_EN_FIRMA = 200
MAX_HUERFANAS = 200           # firmas que llegan antes que su propuesta
MARGEN_FUTURO = 600.0


class CoordinadorSellos:
    def __init__(self, nodo, dir_datos: str):
        self.nodo = nodo
        self.dir_datos = dir_datos
        self.ruta = os.path.join(dir_datos, "sellos_en_firma.json")
        self._lock = threading.RLock()
        self._servidor = None
        self._en_firma: dict[str, dict] = {}     # id -> {"sello": tx, "creado": epoch}
        self._huerfanas: dict[str, dict] = {}    # id -> {autor: firma}
        self._claves = {nid: c["clave_publica"] for nid, c in nodo.genesis["cuentas"].items()}
        self._cargar()

    # ------------------------------------------------------------------ persistencia
    def _cargar(self) -> None:
        try:
            with open(self.ruta, encoding="utf-8") as f:
                datos = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError, RecursionError):
            self.nodo.evento("sellos", "No se pudo leer sellos_en_firma.json; se empieza sin sellos en firma.")
            return
        if not isinstance(datos, dict):
            self.nodo.evento("sellos", "sellos_en_firma.json no tiene el formato esperado; se empieza sin sellos en firma.")
            return
        for sid, entrada in datos.items():
            try:
                sello = self._normalizar(entrada["sello"])
                if id_sello(sello) == sid:
                    self._en_firma[sid] = {"sello": sello, "creado": float(entrada["creado"])}
            except (ErrorEntrada, KeyError, TypeError, ValueError, OverflowError, RecursionError):
                continue

    def _guardar(self) -> None:
        """Escritura atómica; se llama con el candado propio tomado."""
        try:
            os.makedirs(self.dir_datos, exist_ok=True)
            fd, temporal = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=self.dir_datos)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._en_firma, f, separators=(",", ":"))
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporal, self.ruta)
            except BaseException:
                try:
                    os.unlink(temporal)
                except OSError:
                    pass
                raise
        except OSError as exc:
            self.nodo.evento("error", f"No se pudieron guardar los sellos en firma: {exc}")

    # ------------------------------------------------------------------ transporte
    def conectar(self, servidor) -> None:
        """Registra los manejadores en un ServidorP2P (se llama de nuevo cada vez que el nodo se desbloquea)."""
        self._servidor = servidor
        servidor.registrar_manejador("SELLO_PROPUESTO", self._al_propuesto)
        servidor.registrar_manejador("SELLO_FIRMA", self._al_firma)

    def desconectar(self) -> None:
        self._servidor = None

    def _difundir(self, tipo: str, datos: dict, excepto: str | None = None) -> None:
        servidor = self._servidor
        if servidor is None:
            return
        try:
            servidor.difundir(tipo, datos, excepto=excepto)
        except Exception as exc:   # la difusión nunca debe romper la operación local
            self.nodo.evento("sellos", f"No se pudo difundir {tipo}: {exc!r}")

    # ------------------------------------------------------------------ utilidades
    def _normalizar(self, sello) -> dict:
        """Reconstruye un sello recibido con las reglas de formato (ErrorEntrada si no sirve). No toca las firmas."""
        if not isinstance(sello, dict) or set(sello) != set(CAMPOS_SELLO) | {"firmas"} or not es_sello(sello):
            raise ErrorEntrada("el sello no tiene el formato esperado")
        if not isinstance(sello["autores"], list) or not all(isinstance(a, str) for a in sello["autores"]):
            raise ErrorEntrada("los autores del sello no son válidos")
        limpio = nuevo_sello(sello["doc_hash"], sello["titulo"], sello["investigador"], sello["laboratorio"],
                             list(sello["autores"]), sello["umbral"], sello["timestamp"])
        if limpio["autores"] != sello["autores"]:
            raise ErrorEntrada("los autores del sello no están ordenados")
        for a in limpio["autores"]:
            if a not in self._claves:
                raise ErrorEntrada(f"el autor {a} no existe en la red")
        firmas = sello["firmas"]
        if not isinstance(firmas, dict):
            raise ErrorEntrada("las firmas del sello no son un objeto")
        limpio["firmas"] = {a: f for a, f in firmas.items() if isinstance(a, str) and isinstance(f, str)}
        # sólo se conservan las firmas correctas (una inválida se descarta, no invalida el resto)
        validas = firmas_validas(limpio, self._claves)
        limpio["firmas"] = {a: limpio["firmas"][a] for a in validas}
        return limpio

    def _ya_resuelto(self, sid: str) -> bool:
        """True si el sello ya está en la cadena o en pendientes."""
        with self.nodo.lock:
            if sid in self.nodo.estado.tx_ids:
                return True
            return any(es_sello(p) and id_sello(p) == sid for p in self.nodo.pendientes)

    def _limpiar(self) -> None:
        """Quita lo caducado y lo que ya está en cadena o pendientes. Con el candado propio tomado."""
        ahora = time.time()
        cambio = False
        for sid in list(self._en_firma):
            if ahora - self._en_firma[sid]["creado"] > CADUCIDAD or self._ya_resuelto(sid):
                del self._en_firma[sid]
                cambio = True
        if cambio:
            self._guardar()

    def _completa(self, sello: dict) -> bool:
        return len(firmas_validas(sello, self._claves)) >= sello["umbral"]

    def _vista(self, sid: str, entrada: dict) -> dict:
        s = entrada["sello"]
        firmas = [a for a in s["autores"] if a in s["firmas"]]
        return {"id": sid, "doc_hash": s["doc_hash"], "titulo": s["titulo"], "investigador": s["investigador"],
                "laboratorio": s["laboratorio"], "autores": list(s["autores"]), "umbral": s["umbral"],
                "firmas": firmas, "faltan": max(0, s["umbral"] - len(firmas)), "creado": entrada["creado"]}

    def _a_pendientes(self, sello: dict, de: str = "") -> bool:
        """Intenta agregar un sello completo a pendientes (se difunde como TX). Nunca lanza."""
        sid = id_sello(sello)
        if self._ya_resuelto(sid):
            return False
        try:
            self.nodo.agregar_transaccion(sello)
            return True
        except (ErrorEntrada, ErrorValidacion) as exc:
            self.nodo.evento("sellos", f"El sello {sid[:12]}… completo no entró a pendientes: {exc}")
            return False

    # ------------------------------------------------------------------ consultas
    def en_firma(self) -> list[dict]:
        """Sellos esperando firmas: {id, doc_hash, titulo, investigador, laboratorio, autores, umbral, firmas, faltan, creado}."""
        with self._lock:
            self._limpiar()
            return [self._vista(sid, e) for sid, e in self._en_firma.items()]

    def solicitudes(self) -> list[dict]:
        """Sellos en firma donde este nodo es autor y aún no firmó."""
        yo = self.nodo.id
        return [s for s in self.en_firma() if yo in s["autores"] and yo not in s["firmas"]]

    # ------------------------------------------------------------------ acciones locales
    def proponer(self, doc_hash, titulo, investigador, autores, umbral) -> dict:
        nodo = self.nodo
        if not nodo.desbloqueado:
            raise ErrorEstado("El nodo está bloqueado: desbloquéalo con su contraseña para firmar un sello.")
        if not isinstance(autores, (list, tuple)) or not all(isinstance(a, str) for a in autores):
            raise ErrorEntrada("Los autores deben ser una lista de ids de laboratorio.")
        for a in autores:
            if a not in self._claves:
                raise ErrorEntrada(f"El autor {a[:20]!r} no es un laboratorio de esta red.")
        if nodo.id not in autores:
            raise ErrorEntrada(f"El laboratorio que registra ({nodo.id}) debe estar entre los autores.")
        sello = nuevo_sello(doc_hash, titulo, investigador, nodo.id, list(autores), umbral, time.time())
        sid = id_sello(sello)
        firma = nodo.firmar(mensaje_sello(sello))
        sello = agregar_firma(sello, nodo.id, firma, self._claves)
        if sello["umbral"] == 1:
            nodo.agregar_transaccion(sello)          # se difunde como TX por el callback del nodo
            return {"id": sid, "doc_hash": doc_hash, "estado": "pendiente", "firmas": [nodo.id], "umbral": 1}
        with self._lock:
            self._limpiar()
            if len(self._en_firma) >= MAX_EN_FIRMA:
                raise ErrorEstado(f"Hay demasiados sellos esperando firmas ({MAX_EN_FIRMA}).")
            self._en_firma[sid] = {"sello": sello, "creado": time.time()}
            self._guardar()
        nodo.evento("sellos", f"Sello {sid[:12]}… propuesto ({umbral}-de-{len(autores)}): esperando firmas.")
        self._difundir("SELLO_PROPUESTO", {"sello": sello})
        return {"id": sid, "doc_hash": doc_hash, "estado": "en_firma", "firmas": [nodo.id], "umbral": umbral}

    def firmar(self, id_del_sello) -> dict:
        nodo = self.nodo
        if not isinstance(id_del_sello, str) or not es_hex(id_del_sello, 64):
            raise ErrorEntrada("El id del sello debe ser un hash hexadecimal de 64 caracteres.")
        if not nodo.desbloqueado:
            raise ErrorEstado("El nodo está bloqueado: desbloquéalo con su contraseña para firmar un sello.")
        with self._lock:
            self._limpiar()
            entrada = self._en_firma.get(id_del_sello)
            if entrada is None:
                raise ErrorEstado("Ese sello no está esperando firmas en este nodo (ya se completó, caducó o no existe).")
            sello = entrada["sello"]
            if nodo.id not in sello["autores"]:
                raise ErrorEntrada(f"{nodo.id} no es autor de este sello; no puede firmarlo.")
            if nodo.id in sello["firmas"]:
                raise ErrorEstado("Este nodo ya firmó el sello.")
            firma = nodo.firmar(mensaje_sello(sello))
            sello = agregar_firma(sello, nodo.id, firma, self._claves)
            entrada["sello"] = sello
            completo = self._completa(sello)
            if completo:
                del self._en_firma[id_del_sello]
            self._guardar()
        self._difundir("SELLO_FIRMA", {"id_sello": id_del_sello, "autor": nodo.id, "firma": firma})
        nodo.evento("sellos", f"{nodo.id} firmó el sello {id_del_sello[:12]}… ({len(sello['firmas'])}/{sello['umbral']}).")
        estado = "en_firma"
        if completo:
            estado = "pendiente" if self._a_pendientes(sello) else "en_firma"
        return {"id": id_del_sello, "doc_hash": sello["doc_hash"], "estado": estado,
                "firmas": [a for a in sello["autores"] if a in sello["firmas"]], "umbral": sello["umbral"]}

    # ------------------------------------------------------------------ manejadores de red
    def _al_propuesto(self, par_id: str, msg: dict) -> None:
        try:
            self._procesar_propuesto(par_id, msg)
        except Exception as exc:
            self.nodo.evento("sellos", f"Propuesta de sello de {par_id} descartada ({type(exc).__name__}).")

    def _procesar_propuesto(self, par_id: str, msg: dict) -> None:
        try:
            sello = self._normalizar(msg.get("sello"))
        except ErrorEntrada as exc:
            self.nodo.evento("sellos", f"Propuesta de sello de {par_id} descartada: {exc}.")
            return
        if sello["laboratorio"] not in sello["firmas"]:
            self.nodo.evento("sellos", f"Propuesta de sello de {par_id} descartada: no trae la firma de quien la propone.")
            return
        ahora = time.time()
        if sello["timestamp"] > ahora + MARGEN_FUTURO or ahora - sello["timestamp"] > CADUCIDAD:
            self.nodo.evento("sellos", f"Propuesta de sello de {par_id} descartada: fecha fuera de rango.")
            return
        sid = id_sello(sello)
        if self._ya_resuelto(sid):
            return
        nueva = False
        with self._lock:
            self._limpiar()
            if sid in self._en_firma:
                actual = self._en_firma[sid]["sello"]
                union = {**actual["firmas"], **sello["firmas"]}
                if len(union) != len(actual["firmas"]):
                    actual["firmas"] = union
                    self._guardar()
                sello = actual
            else:
                if len(self._en_firma) >= MAX_EN_FIRMA:
                    self.nodo.evento("sellos", "Propuesta descartada: demasiados sellos esperando firmas.")
                    return
                for autor, firma in self._huerfanas.pop(sid, {}).items():
                    try:
                        sello = agregar_firma(sello, autor, firma, self._claves)
                    except ErrorEntrada:
                        pass
                self._en_firma[sid] = {"sello": sello, "creado": ahora}
                self._guardar()
                nueva = True
            completo = self._completa(sello)
            if completo:
                self._en_firma.pop(sid, None)
                self._guardar()
        if nueva:
            self.nodo.evento("sellos", f"Solicitud de firma: sello {sid[:12]}… de {sello['laboratorio']} "
                                       f"({len(sello['firmas'])}/{sello['umbral']}).")
            self._difundir("SELLO_PROPUESTO", {"sello": sello}, excepto=par_id)   # gossip: una sola vez
        if completo:
            self._a_pendientes(sello, par_id)

    def _al_firma(self, par_id: str, msg: dict) -> None:
        try:
            self._procesar_firma(par_id, msg)
        except Exception as exc:
            self.nodo.evento("sellos", f"Firma de sello de {par_id} descartada ({type(exc).__name__}).")

    def _procesar_firma(self, par_id: str, msg: dict) -> None:
        sid, autor, firma = msg.get("id_sello"), msg.get("autor"), msg.get("firma")
        if not (isinstance(sid, str) and es_hex(sid, 64) and isinstance(autor, str) and isinstance(firma, str)):
            self.nodo.evento("sellos", f"Firma de sello de {par_id} descartada: formato inválido.")
            return
        sello = None
        completo = False
        with self._lock:
            entrada = self._en_firma.get(sid)
            if entrada is None:
                # puede ser una firma adelantada a su propuesta, o de un sello que ya se resolvió
                if self._ya_resuelto(sid):
                    return
                if autor in self._claves and len(self._huerfanas) < MAX_HUERFANAS:
                    self._huerfanas.setdefault(sid, {})[autor] = firma
                return
            actual = entrada["sello"]
            if autor in actual["firmas"]:
                return                                       # ya la tenía: no se reenvía (corta el gossip)
            try:
                sello = agregar_firma(actual, autor, firma, self._claves)
            except ErrorEntrada as exc:
                self.nodo.evento("sellos", f"Firma de {par_id} descartada: {exc}")
                return
            entrada["sello"] = sello
            completo = self._completa(sello)
            if completo:
                del self._en_firma[sid]
            self._guardar()
        self.nodo.evento("sellos", f"Firma de {autor} recibida para el sello {sid[:12]}… "
                                   f"({len(sello['firmas'])}/{sello['umbral']}).")
        self._difundir("SELLO_FIRMA", {"id_sello": sid, "autor": autor, "firma": firma}, excepto=par_id)
        if completo:
            self._a_pendientes(sello, par_id)
