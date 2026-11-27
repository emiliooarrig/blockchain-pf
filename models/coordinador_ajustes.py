"""Coordinación del ajuste de dificultad entre los laboratorios de la red (contrato C9).

Mismo patrón que `coordinador_sellos`: un ajuste no entra a pendientes hasta reunir la mayoría (más de la mitad de los
laboratorios del génesis). Mientras tanto vive «en firma»: quien lo propone lo difunde (`AJUSTE_PROPUESTO`), cada otro
laboratorio lo ve como solicitud y, al firmarlo, difunde su firma (`AJUSTE_FIRMA`). Quien completa la mayoría lo agrega
a sus pendientes (y se difunde como `TX`). Se guarda en `<datos>/ajustes_en_firma.json` y caduca a las 24 h.

Los datos que llegan de la red nunca lanzan excepciones hacia el transporte: se descartan y quedan en la bitácora.
"""
import json
import os
import tempfile
import threading
import time

from models.ajuste_dificultad import (agregar_firma, es_ajuste, firmas_validas, id_ajuste, mayoria, mensaje_ajuste,
                                      nuevo_ajuste, problema_formato)
from models.bloque import ErrorValidacion
from models.cripto import es_hex
from models.errores import ErrorEntrada, ErrorEstado
from models.pow import DIF_MAX, DIF_MIN

CADUCIDAD = 24 * 3600.0
MAX_EN_FIRMA = 50
MAX_HUERFANAS = 100
MARGEN_FUTURO = 600.0


class CoordinadorAjustes:
    def __init__(self, nodo, dir_datos: str):
        self.nodo = nodo
        self.dir_datos = dir_datos
        self.ruta = os.path.join(dir_datos, "ajustes_en_firma.json")
        self._lock = threading.RLock()
        self._servidor = None
        self._en_firma: dict[str, dict] = {}     # id -> {"ajuste": tx, "creado": epoch}
        self._huerfanas: dict[str, dict] = {}    # id -> {lab: firma} (firmas que llegan antes que su propuesta)
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
            self.nodo.evento("dificultad", "No se pudo leer ajustes_en_firma.json; se empieza sin ajustes en firma.")
            return
        if not isinstance(datos, dict):
            self.nodo.evento("dificultad", "ajustes_en_firma.json no tiene el formato esperado; se ignora.")
            return
        for aid, entrada in datos.items():
            try:
                ajuste = self._normalizar(entrada["ajuste"])
                if id_ajuste(ajuste) == aid:
                    self._en_firma[aid] = {"ajuste": ajuste, "creado": float(entrada["creado"])}
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
            self.nodo.evento("error", f"No se pudieron guardar los ajustes en firma: {exc}")

    # ------------------------------------------------------------------ transporte
    def conectar(self, servidor) -> None:
        self._servidor = servidor
        servidor.registrar_manejador("AJUSTE_PROPUESTO", self._al_propuesto)
        servidor.registrar_manejador("AJUSTE_FIRMA", self._al_firma)

    def desconectar(self) -> None:
        self._servidor = None

    def _difundir(self, tipo: str, datos: dict, excepto: str | None = None) -> None:
        servidor = self._servidor
        if servidor is None:
            return
        try:
            servidor.difundir(tipo, datos, excepto=excepto)
        except Exception as exc:
            self.nodo.evento("dificultad", f"No se pudo difundir {tipo}: {exc!r}")

    # ------------------------------------------------------------------ utilidades
    def _normalizar(self, ajuste) -> dict:
        """Reconstruye un ajuste recibido (ErrorEntrada si no sirve) conservando sólo las firmas correctas."""
        if not es_ajuste(ajuste):
            raise ErrorEntrada("el ajuste no tiene el formato esperado")
        motivo = problema_formato(ajuste)
        if motivo:
            raise ErrorEntrada(motivo)
        if ajuste["proponente"] not in self._claves:
            raise ErrorEntrada(f"el proponente {ajuste['proponente'][:20]} no es laboratorio de la red")
        limpio = {k: ajuste[k] for k in ("tipo", "dificultad", "proponente", "timestamp")}
        limpio["firmas"] = {l: f for l, f in ajuste["firmas"].items() if isinstance(l, str) and isinstance(f, str)}
        validas = firmas_validas(limpio, self._claves)
        limpio["firmas"] = {l: limpio["firmas"][l] for l in validas}
        return limpio

    def _vigente(self):
        return self.nodo.estado.dificultad_vigente

    def _ya_resuelto(self, aid: str) -> bool:
        with self.nodo.lock:
            if aid in self.nodo.estado.tx_ids:
                return True
            return any(es_ajuste(p) and id_ajuste(p) == aid for p in self.nodo.pendientes)

    def _obsoleto(self, ajuste: dict) -> bool:
        """Ya no sirve: pide justo la dificultad vigente (otro ajuste la dejó así) o la red no la fija."""
        vigente = self._vigente()
        return vigente is None or ajuste["dificultad"] == vigente

    def _limpiar(self) -> None:
        ahora = time.time()
        cambio = False
        for aid in list(self._en_firma):
            e = self._en_firma[aid]
            if ahora - e["creado"] > CADUCIDAD or self._ya_resuelto(aid) or self._obsoleto(e["ajuste"]):
                del self._en_firma[aid]
                cambio = True
        if cambio:
            self._guardar()

    def _completa(self, ajuste: dict) -> bool:
        return len(firmas_validas(ajuste, self._claves)) >= mayoria(len(self._claves))

    def _vista(self, aid: str, entrada: dict) -> dict:
        a = entrada["ajuste"]
        firmas = sorted(a["firmas"])
        umbral = mayoria(len(self._claves))
        return {"id": aid, "dificultad": a["dificultad"], "proponente": a["proponente"], "firmas": firmas,
                "umbral": umbral, "faltan": max(0, umbral - len(firmas)), "creado": entrada["creado"],
                "firmado_por_mi": self.nodo.id in a["firmas"]}

    def _reemplazar_del_proponente(self, proponente: str, conservar: str) -> None:
        """Una propuesta nueva reemplaza a la pendiente del mismo proponente. Con el candado propio tomado."""
        for aid in [i for i, e in self._en_firma.items() if e["ajuste"]["proponente"] == proponente and i != conservar]:
            del self._en_firma[aid]

    def _a_pendientes(self, ajuste: dict) -> bool:
        aid = id_ajuste(ajuste)
        if self._ya_resuelto(aid):
            return False
        try:
            self.nodo.agregar_transaccion(ajuste)
            return True
        except (ErrorEntrada, ErrorValidacion) as exc:
            self.nodo.evento("dificultad", f"El ajuste {aid[:12]}… completo no entró a pendientes: {exc}")
            return False

    # ------------------------------------------------------------------ consultas
    def en_firma(self) -> list[dict]:
        with self._lock:
            self._limpiar()
            return [self._vista(aid, e) for aid, e in self._en_firma.items()]

    def solicitudes(self) -> list[dict]:
        """Ajustes en firma que este nodo aún no firmó."""
        return [a for a in self.en_firma() if not a["firmado_por_mi"]]

    def umbral(self) -> int:
        return mayoria(len(self._claves))

    # ------------------------------------------------------------------ acciones locales
    def proponer(self, dificultad) -> dict:
        nodo = self.nodo
        if not nodo.desbloqueado:
            raise ErrorEstado("El nodo está bloqueado: desbloquéalo con su contraseña para firmar un ajuste.")
        vigente = self._vigente()
        if vigente is None:
            raise ErrorEstado("Esta red no fija la dificultad en el génesis: cada minero la elige, no hay nada que ajustar.")
        if type(dificultad) is not int or not DIF_MIN <= dificultad <= DIF_MAX:
            raise ErrorEntrada(f"La dificultad debe ser un entero entre {DIF_MIN} y {DIF_MAX}.")
        if dificultad == vigente:
            raise ErrorEstado(f"La dificultad {dificultad} ya es la vigente de la red.")
        if nodo.id not in self._claves:
            raise ErrorEstado(f"{nodo.id} no es un laboratorio de esta red.")
        ajuste = nuevo_ajuste(dificultad, nodo.id, time.time())
        aid = id_ajuste(ajuste)
        ajuste = agregar_firma(ajuste, nodo.id, nodo.firmar(mensaje_ajuste(ajuste)), self._claves)
        if self._completa(ajuste):                  # red de un solo laboratorio
            nodo.agregar_transaccion(ajuste)
            return {"id": aid, "dificultad": dificultad, "estado": "pendiente", "firmas": [nodo.id],
                    "umbral": self.umbral()}
        with self._lock:
            self._limpiar()
            self._reemplazar_del_proponente(nodo.id, aid)
            if len(self._en_firma) >= MAX_EN_FIRMA:
                raise ErrorEstado(f"Hay demasiados ajustes esperando firmas ({MAX_EN_FIRMA}).")
            self._en_firma[aid] = {"ajuste": ajuste, "creado": time.time()}
            self._guardar()
        nodo.evento("dificultad", f"Ajuste {aid[:12]}… propuesto (dificultad {vigente} → {dificultad}): esperando firmas.")
        self._difundir("AJUSTE_PROPUESTO", {"ajuste": ajuste})
        return {"id": aid, "dificultad": dificultad, "estado": "en_firma", "firmas": [nodo.id], "umbral": self.umbral()}

    def firmar(self, id_del_ajuste) -> dict:
        nodo = self.nodo
        if not isinstance(id_del_ajuste, str) or not es_hex(id_del_ajuste, 64):
            raise ErrorEntrada("El id del ajuste debe ser un hash hexadecimal de 64 caracteres.")
        if not nodo.desbloqueado:
            raise ErrorEstado("El nodo está bloqueado: desbloquéalo con su contraseña para firmar un ajuste.")
        with self._lock:
            self._limpiar()
            entrada = self._en_firma.get(id_del_ajuste)
            if entrada is None:
                raise ErrorEstado("Ese ajuste no está esperando firmas en este nodo (ya se completó, caducó, quedó "
                                  "obsoleto o no existe).")
            ajuste = entrada["ajuste"]
            if nodo.id not in self._claves:
                raise ErrorEstado(f"{nodo.id} no es un laboratorio de esta red; no puede firmar.")
            if nodo.id in ajuste["firmas"]:
                raise ErrorEstado("Este nodo ya firmó el ajuste.")
            firma = nodo.firmar(mensaje_ajuste(ajuste))
            ajuste = agregar_firma(ajuste, nodo.id, firma, self._claves)
            entrada["ajuste"] = ajuste
            completo = self._completa(ajuste)
            if completo:
                del self._en_firma[id_del_ajuste]
            self._guardar()
        self._difundir("AJUSTE_FIRMA", {"id_ajuste": id_del_ajuste, "lab": nodo.id, "firma": firma})
        nodo.evento("dificultad", f"{nodo.id} firmó el ajuste {id_del_ajuste[:12]}… "
                                  f"({len(ajuste['firmas'])}/{self.umbral()}).")
        estado = "en_firma"
        if completo:
            estado = "pendiente" if self._a_pendientes(ajuste) else "en_firma"
        return {"id": id_del_ajuste, "dificultad": ajuste["dificultad"], "estado": estado,
                "firmas": sorted(ajuste["firmas"]), "umbral": self.umbral()}

    # ------------------------------------------------------------------ manejadores de red
    def _al_propuesto(self, par_id: str, msg: dict) -> None:
        try:
            self._procesar_propuesto(par_id, msg)
        except Exception as exc:
            self.nodo.evento("dificultad", f"Propuesta de ajuste de {par_id} descartada ({type(exc).__name__}).")

    def _procesar_propuesto(self, par_id: str, msg: dict) -> None:
        try:
            ajuste = self._normalizar(msg.get("ajuste"))
        except ErrorEntrada as exc:
            self.nodo.evento("dificultad", f"Propuesta de ajuste de {par_id} descartada: {exc}.")
            return
        if ajuste["proponente"] not in ajuste["firmas"]:
            self.nodo.evento("dificultad", f"Propuesta de ajuste de {par_id} descartada: no trae la firma de quien la propone.")
            return
        ahora = time.time()
        if ajuste["timestamp"] > ahora + MARGEN_FUTURO or ahora - ajuste["timestamp"] > CADUCIDAD:
            self.nodo.evento("dificultad", f"Propuesta de ajuste de {par_id} descartada: fecha fuera de rango.")
            return
        if self._obsoleto(ajuste):
            self.nodo.evento("dificultad", f"Propuesta de ajuste de {par_id} descartada: la dificultad pedida ya es la "
                                           f"vigente o la red no la fija.")
            return
        aid = id_ajuste(ajuste)
        if self._ya_resuelto(aid):
            return
        nueva = False
        with self._lock:
            self._limpiar()
            if aid in self._en_firma:
                actual = self._en_firma[aid]["ajuste"]
                union = {**actual["firmas"], **ajuste["firmas"]}
                if len(union) != len(actual["firmas"]):
                    actual["firmas"] = union
                    self._guardar()
                ajuste = actual
            else:
                previa = [e for e in self._en_firma.values() if e["ajuste"]["proponente"] == ajuste["proponente"]]
                if any(e["ajuste"]["timestamp"] >= ajuste["timestamp"] for e in previa):
                    return                       # ya tengo una propuesta más reciente del mismo proponente
                self._reemplazar_del_proponente(ajuste["proponente"], aid)
                if len(self._en_firma) >= MAX_EN_FIRMA:
                    self.nodo.evento("dificultad", "Propuesta descartada: demasiados ajustes esperando firmas.")
                    return
                for lab, firma in self._huerfanas.pop(aid, {}).items():
                    try:
                        ajuste = agregar_firma(ajuste, lab, firma, self._claves)
                    except ErrorEntrada:
                        pass
                self._en_firma[aid] = {"ajuste": ajuste, "creado": ahora}
                self._guardar()
                nueva = True
            completo = self._completa(ajuste)
            if completo:
                self._en_firma.pop(aid, None)
                self._guardar()
        if nueva:
            self.nodo.evento("dificultad", f"Solicitud de firma: ajuste {aid[:12]}… de {ajuste['proponente']} a "
                                           f"dificultad {ajuste['dificultad']} ({len(ajuste['firmas'])}/{self.umbral()}).")
            self._difundir("AJUSTE_PROPUESTO", {"ajuste": ajuste}, excepto=par_id)
        if completo:
            self._a_pendientes(ajuste)

    def _al_firma(self, par_id: str, msg: dict) -> None:
        try:
            self._procesar_firma(par_id, msg)
        except Exception as exc:
            self.nodo.evento("dificultad", f"Firma de ajuste de {par_id} descartada ({type(exc).__name__}).")

    def _procesar_firma(self, par_id: str, msg: dict) -> None:
        aid, lab, firma = msg.get("id_ajuste"), msg.get("lab"), msg.get("firma")
        if not (isinstance(aid, str) and es_hex(aid, 64) and isinstance(lab, str) and isinstance(firma, str)):
            self.nodo.evento("dificultad", f"Firma de ajuste de {par_id} descartada: formato inválido.")
            return
        with self._lock:
            entrada = self._en_firma.get(aid)
            if entrada is None:
                if self._ya_resuelto(aid):
                    return
                if lab in self._claves and len(self._huerfanas) < MAX_HUERFANAS:
                    self._huerfanas.setdefault(aid, {})[lab] = firma
                return
            actual = entrada["ajuste"]
            if lab in actual["firmas"]:
                return                                       # ya la tenía: no se reenvía (corta el gossip)
            try:
                ajuste = agregar_firma(actual, lab, firma, self._claves)
            except ErrorEntrada as exc:
                self.nodo.evento("dificultad", f"Firma de {par_id} descartada: {exc}")
                return
            entrada["ajuste"] = ajuste
            completo = self._completa(ajuste)
            if completo:
                del self._en_firma[aid]
            self._guardar()
        self.nodo.evento("dificultad", f"Firma de {lab} recibida para el ajuste {aid[:12]}… "
                                       f"({len(ajuste['firmas'])}/{self.umbral()}).")
        self._difundir("AJUSTE_FIRMA", {"id_ajuste": aid, "lab": lab, "firma": firma}, excepto=par_id)
        if completo:
            self._a_pendientes(ajuste)
