"""Demostración automática (plan B) del guion §3.7 de Sellalo contra una red de 3 procesos reales.

Uso:
    python scripts/demo_e2e.py                      # lanza 3 nodos locales, recorre el guion y los cierra
    python scripts/demo_e2e.py --dejar-abiertos     # igual, pero deja los nodos corriendo al terminar
    python scripts/demo_e2e.py --urls http://127.0.0.1:5001,http://127.0.0.1:5002,http://127.0.0.1:5003 \
        --contrasena-env SELLALO_CLAVE              # usa nodos ya lanzados (todos con la misma contraseña)

Cada paso imprime la evidencia (alturas, puntas, motivo de cada rechazo, resultado del verificador). Si algo no se
cumple, el programa termina con código 1 y explica qué paso falló. Este mismo guion lo usa tests/test_e2e_red.py.
"""
import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from models.keystore import crear_almacen  # noqa: E402
from scripts.inicializar_red import construir_genesis  # noqa: E402

IDS = ("LAB-A", "LAB-B", "LAB-C")


# ---------------------------------------------------------------- utilidades
def puerto_libre(preferido: int) -> int:
    """`preferido` si está libre; si no, un puerto libre que asigne el sistema."""
    for candidato in (preferido, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", candidato))
                return s.getsockname()[1]
            except OSError:
                continue
    raise OSError("no hay puertos libres")


def esperar(cond, limite: float = 15.0, paso: float = 0.1):
    """Repite `cond()` hasta que devuelva algo verdadero o venza `limite`. Devuelve el último valor."""
    fin = time.monotonic() + limite
    valor = cond()
    while not valor and time.monotonic() < fin:
        time.sleep(paso)
        valor = cond()
    return valor


def multipart(campos: dict, archivos: dict) -> tuple[bytes, str]:
    """Cuerpo multipart/form-data armado a mano. archivos = {campo: (nombre, bytes)}."""
    frontera = "----sellalo" + uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f'--{frontera}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, (nombre, contenido) in archivos.items():
        partes.append((f'--{frontera}\r\nContent-Disposition: form-data; name="{k}"; filename="{nombre}"\r\n'
                       f'Content-Type: application/octet-stream\r\n\r\n').encode() + contenido + b"\r\n")
    partes.append(f"--{frontera}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={frontera}"


class Cliente:
    """Cliente HTTP mínimo (urllib) de un nodo."""

    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def pedir(self, metodo: str, ruta: str, cuerpo: bytes | None = None, tipo: str | None = None, timeout: float = 30):
        req = urllib.request.Request(self.url + ruta, data=cuerpo, method=metodo)
        if tipo:
            req.add_header("Content-Type", tipo)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def json(self, metodo: str, ruta: str, datos: dict | None = None, timeout: float = 30) -> tuple[int, dict]:
        cuerpo = json.dumps(datos).encode() if datos is not None else None
        estado, crudo = self.pedir(metodo, ruta, cuerpo, "application/json" if datos is not None else None, timeout)
        try:
            return estado, json.loads(crudo)
        except ValueError:
            return estado, {"ok": False, "error": crudo[:200].decode("utf-8", "replace")}

    def subir(self, ruta: str, campos: dict, archivos: dict) -> tuple[int, dict]:
        cuerpo, tipo = multipart(campos, archivos)
        estado, crudo = self.pedir("POST", ruta, cuerpo, tipo)
        return estado, json.loads(crudo)


class NodoRed:
    """Un nodo de la red (proceso propio o ya lanzado) visto desde el cliente HTTP."""

    def __init__(self, nid: str, url: str, host_p2p: str, puerto_p2p: int, datos: str | None = None):
        self.id, self.url, self.host_p2p, self.p2p, self.datos = nid, url, host_p2p, puerto_p2p, datos
        self.c = Cliente(url)
        self.proceso: subprocess.Popen | None = None
        self.log: str | None = None

    def estado(self) -> dict:
        return self.c.json("GET", "/api/sellalo/estado")[1]

    def nodo(self) -> dict:
        return self.estado()["nodo"]

    def resumen(self) -> tuple[int, str]:
        n = self.nodo()
        return n["altura"], n["punta"]

    def pares(self) -> list[str]:
        return sorted(p["id"] for p in self.estado()["pares"])

    def pendientes(self) -> list[dict]:
        return self.nodo()["pendientes"]

    def bitacora(self) -> list[dict]:
        return self.nodo()["bitacora"]

    def llamar(self, metodo: str, ruta: str, datos: dict | None = None) -> dict:
        estado, cuerpo = self.c.json(metodo, "/api/sellalo" + ruta, datos)
        if estado != 200:
            raise AssertionError(f"{self.id} {metodo} {ruta} -> HTTP {estado}: {cuerpo.get('error')}")
        return cuerpo


class RedLocal:
    """Prepara (identidades cifradas + génesis) y lanza una red de procesos reales `app.py --modo nodo`."""

    def __init__(self, carpeta: str, contrasena: str, ids=IDS, http_base: int = 5201, p2p_base: int = 6201,
                 limite_total: float | None = None):
        self.carpeta, self.contrasena, self.ids = carpeta, contrasena, tuple(ids)
        self.nodos: dict[str, NodoRed] = {}
        self.puede_reiniciar = True
        self._guardian = None
        self._limite_total = limite_total
        os.makedirs(os.path.join(carpeta, "logs"), exist_ok=True)
        claves = {}
        for nid in self.ids:
            datos = os.path.join(carpeta, nid)
            claves[nid] = os.path.join(datos, "clave.json")
            crear_almacen(claves[nid], nid, contrasena)
        self.ruta_genesis = os.path.join(carpeta, "genesis.json")
        genesis = construir_genesis([f"{nid}={claves[nid]}" for nid in self.ids], 100, 10, "Red Sellalo (e2e)")
        with open(self.ruta_genesis, "w", encoding="utf-8") as f:
            json.dump(genesis, f, indent=2, ensure_ascii=False)
        usados = set()
        for i, nid in enumerate(self.ids):
            http, p2p = puerto_libre(http_base + i), puerto_libre(p2p_base + i)
            while http in usados or p2p in usados:
                http, p2p = puerto_libre(0), puerto_libre(0)
            usados |= {http, p2p}
            n = NodoRed(nid, f"http://127.0.0.1:{http}", "127.0.0.1", p2p, os.path.join(carpeta, nid))
            n.log = os.path.join(carpeta, "logs", f"{nid}.log")
            self.nodos[nid] = n

    def comando(self, nid: str) -> list[str]:
        n = self.nodos[nid]
        pares = ",".join(f"127.0.0.1:{o.p2p}" for o in self.nodos.values() if o is not n)
        return [sys.executable, "-u", "app.py", "--modo", "nodo", "--nodo", nid, "--datos", n.datos,
                "--genesis", self.ruta_genesis, "--puerto", n.url.rsplit(":", 1)[1], "--puerto-p2p", str(n.p2p),
                "--pares", pares, "--laboratorio-ataques"]

    def lanzar(self, nid: str) -> NodoRed:
        n = self.nodos[nid]
        if self._guardian is None and self._limite_total:
            self._guardian = threading.Timer(self._limite_total, self.cerrar)
            self._guardian.daemon = True
            self._guardian.start()
        salida = open(n.log, "ab")
        n.proceso = subprocess.Popen(self.comando(nid), cwd=RAIZ, stdout=salida, stderr=subprocess.STDOUT)
        salida.close()
        arriba = esperar(lambda: n.proceso.poll() is None and self._responde(n), 30, 0.2)
        if not arriba:
            raise AssertionError(f"El nodo {nid} no arrancó; log: {n.log}")
        return n

    @staticmethod
    def _responde(n: NodoRed) -> bool:
        try:
            return n.c.json("GET", "/api/sellalo/estado", timeout=2)[0] == 200
        except OSError:
            return False

    def lanzar_todos(self) -> None:
        for nid in self.ids:
            self.lanzar(nid)

    def matar(self, nid: str) -> None:
        """Termina el proceso de golpe (como una caída), sin cerrar nada ordenadamente."""
        p = self.nodos[nid].proceso
        if p is not None and p.poll() is None:
            p.kill()
            p.wait(timeout=10)

    def cerrar(self) -> None:
        if self._guardian is not None:
            self._guardian.cancel()
        for n in self.nodos.values():
            p = n.proceso
            if p is not None and p.poll() is None:
                p.terminate()
        for n in self.nodos.values():
            p = n.proceso
            if p is not None:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=10)

    def logs(self) -> str:
        texto = []
        for n in self.nodos.values():
            if n.log and os.path.exists(n.log):
                with open(n.log, "rb") as f:
                    texto.append(f.read().decode("utf-8", "replace"))
        return "\n".join(texto)


class RedExterna:
    """Nodos ya lanzados por el usuario (modo --urls). No se pueden matar ni reiniciar."""

    puede_reiniciar = False

    def __init__(self, urls: list[str]):
        self.nodos: dict[str, NodoRed] = {}
        for url in urls:
            c = Cliente(url)
            est = c.json("GET", "/api/sellalo/estado")[1]
            host = url.split("//")[-1].rsplit(":", 1)[0]
            n = NodoRed(est["nodo"]["id"], url, host, est["red"]["puerto_p2p"])
            self.nodos[n.id] = n
        self.ids = tuple(self.nodos)

    def cerrar(self) -> None:
        pass


# ---------------------------------------------------------------- guion §3.7
class Guion:
    """Recorre los 9 pasos del guion. Cada paso imprime evidencia y afirma lo que debe cumplirse."""

    def __init__(self, red, contrasena: str, carpeta: str, salida=print, documento: bytes | None = None):
        self.red, self.contrasena, self.carpeta, self.say = red, contrasena, carpeta, salida
        self.documento = documento or (b"Resultado experimental: la proteina X inhibe la via Y. " * 40
                                       + secrets.token_hex(8).encode())
        self.doc_hash = hashlib.sha256(self.documento).hexdigest()
        self.ev: dict = {}
        ids = list(red.ids)
        self.a, self.b, self.c = (red.nodos[i] for i in ids[:3])
        self.todos = [self.a, self.b, self.c]
        os.makedirs(carpeta, exist_ok=True)

    # ---- ayudas
    def titulo(self, n: int, texto: str) -> None:
        self.say(f"\n=== Paso {n}: {texto} ===")

    def exigir(self, cond, texto: str) -> None:
        if not cond:
            raise AssertionError(texto)

    def esperar(self, cond, texto: str, limite: float = 20.0):
        valor = esperar(cond, limite)
        self.exigir(valor, f"Tiempo agotado esperando: {texto}")
        return valor

    def resumenes(self, nodos=None) -> dict:
        return {n.id: n.resumen() for n in (nodos or self.todos)}

    def converger(self, altura: int, texto: str, nodos=None, limite: float = 25.0) -> tuple[int, str]:
        nodos = nodos or self.todos

        def listo():
            r = [n.resumen() for n in nodos]
            return len(set(r)) == 1 and r[0][0] == altura
        self.esperar(listo, texto, limite)
        a, p = nodos[0].resumen()
        for n in nodos:
            self.say(f"    {n.id}: altura {n.resumen()[0]}  punta {n.resumen()[1][:16]}…")
        return a, p

    def minar(self, n: NodoRed, altura: int, dificultad: int = 2) -> None:
        n.llamar("POST", "/minar", {"dificultad": dificultad})
        self.esperar(lambda: n.nodo()["altura"] >= altura and not n.nodo()["minando"], f"{n.id} minando bloque {altura}")

    def tipos_pendientes(self, n: NodoRed) -> list[str]:
        return [f"{p['tipo']}:{p.get('doc_hash', p.get('emisor', ''))[:8]}" for p in n.pendientes()]

    # ---- pasos
    def paso1_desbloquear(self) -> None:
        self.titulo(1, "Inicializar la red: desbloquear los 3 nodos y formar la malla P2P")
        for n in self.todos:
            try:
                r = n.llamar("POST", "/desbloquear", {"contrasena": self.contrasena})
                self.say(f"  {n.id}: {r['mensaje']}")
            except AssertionError as exc:
                if "ya está desbloqueado" not in str(exc):
                    raise
                self.say(f"  {n.id}: ya estaba desbloqueado")
        if not self.red.puede_reiniciar:         # nodos lanzados por fuera: se completa la malla a mano
            for n in self.todos:
                for o in self.todos:
                    if o is not n and o.id not in n.pares():
                        try:
                            n.llamar("POST", "/pares", {"ip": o.host_p2p, "puerto": o.p2p})
                        except AssertionError:
                            pass
        for n in self.todos:
            esperados = sorted(o.id for o in self.todos if o is not n)
            self.esperar(lambda n=n, e=esperados: n.pares() == e, f"{n.id} conectado con {esperados}", 30)
            self.say(f"  {n.id} ve a sus pares: {', '.join(n.pares())}")
        h = {n.nodo()["hash_genesis"] for n in self.todos}
        self.exigir(len(h) == 1, "los nodos no comparten el génesis")
        self.say(f"  Génesis común: {h.pop()[:16]}…  (alturas: "
                 f"{', '.join(str(n.resumen()[0]) for n in self.todos)})")
        self.ev["altura_inicial"] = self.a.resumen()[0]

    def paso2_sellar(self) -> None:
        self.titulo(2, "Lab A sella resultado.pdf (autores A+B+C, umbral 2-de-3)")
        r = self.a.c.subir("/api/sellalo/sellos",
                           {"titulo": "Inhibicion de la via Y", "investigador": "Dra. A. Prueba",
                            "autores": ",".join(n.id for n in self.todos), "umbral": "2"},
                           {"archivo": ("resultado.pdf", self.documento)})
        self.exigir(r[0] == 200 and r[1]["sello"]["estado"] == "en_firma", f"el sello no quedó en firma: {r}")
        self.sello_id = r[1]["sello"]["id"]
        self.say(f"  {r[1]['mensaje']}")
        self.say(f"  doc_hash (sólo el hash sale del nodo): {self.doc_hash[:24]}…  id del sello: {self.sello_id[:16]}…")
        self.exigir(not self.a.pendientes(), "el sello no debe estar en pendientes antes de reunir las firmas")
        for n in (self.b, self.c):
            self.esperar(lambda n=n: any(s["id"] == self.sello_id for s in n.estado()["solicitudes"]),
                         f"{n.id} recibe la solicitud de firma")
            self.say(f"  {n.id} tiene una solicitud de firma para el sello (1/2 firmas)")

    def paso3_cofirmar(self) -> None:
        self.titulo(3, "Lab B co-firma: el sello alcanza 2-de-3 y pasa a pendientes en toda la red")
        r = self.b.llamar("POST", f"/sellos/{self.sello_id}/firmar")
        self.say(f"  {r['mensaje']}")
        for n in self.todos:
            self.esperar(lambda n=n: any(p["tipo"] == "sello" and p["doc_hash"] == self.doc_hash for p in n.pendientes()),
                         f"{n.id} tiene el sello pendiente")
            sellos = [p for p in n.pendientes() if p["tipo"] == "sello"]
            self.exigir(len(sellos) == 1, f"{n.id} tiene {len(sellos)} copias del sello pendiente (debe ser 1)")
            self.say(f"  {n.id}: pendientes = {self.tipos_pendientes(n)}  (firmas {sellos[0]['firmas']}/{sellos[0]['umbral']})")

    def paso4_minar(self) -> None:
        self.titulo(4, "Minado PoW real en Lab A; el bloque se replica")
        base = self.ev["altura_inicial"]
        self.minar(self.a, base + 1)
        altura, punta = self.converger(base + 1, "los 3 nodos con el mismo bloque")
        self.ev["altura_sello"], self.ev["punta_sello"] = altura, punta
        self.say(f"  Los 3 nodos tienen altura {altura} y la misma punta {punta[:16]}…")

    def paso5_certificado(self) -> None:
        self.titulo(5, "Descargar el certificado y verificarlo offline con verificar_certificado.py")
        estado, crudo = self.c.c.pedir("GET", f"/api/sellalo/certificado/{self.doc_hash}")
        self.exigir(estado == 200, f"el certificado no se pudo descargar (HTTP {estado})")
        self.ruta_cert = os.path.join(self.carpeta, f"certificado-{self.doc_hash[:8]}.json")
        self.ruta_doc = os.path.join(self.carpeta, "resultado.pdf")
        with open(self.ruta_cert, "wb") as f:
            f.write(crudo)
        with open(self.ruta_doc, "wb") as f:
            f.write(self.documento)
        self.say(f"  Certificado descargado de {self.c.id}: {os.path.basename(self.ruta_cert)} ({len(crudo)} bytes)")
        codigo, texto = self.verificador(self.ruta_cert, self.ruta_doc)
        self.exigir(codigo == 0 and "CERTIFICADO VÁLIDO" in texto, f"el verificador rechazó el certificado: {texto}")
        self.ev["verificador_valido"] = texto
        for linea in texto.strip().splitlines():
            self.say(f"    | {linea}")
        self.say(f"  verificar_certificado.py terminó con código {codigo} (certificado válido, documento coincide)")
        r = self.b.c.subir("/api/sellalo/certificado/verificar", {},
                           {"certificado": ("c.json", crudo), "documento": ("resultado.pdf", self.documento)})[1]
        self.exigir(r["valido"] and r["misma_red"], f"la verificación vía API falló: {r}")
        self.say(f"  La API de {self.b.id} también lo valida (misma_red={r['misma_red']}).")

    def verificador(self, cert: str, documento: str | None) -> tuple[int, str]:
        cmd = [sys.executable, "verificar_certificado.py", cert]
        if documento:
            cmd += ["--documento", documento]
        p = subprocess.run(cmd, cwd=RAIZ, capture_output=True, timeout=60)
        return p.returncode, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")

    def paso6_alterar(self) -> None:
        self.titulo(6, "Alterar un byte del PDF: la verificación debe fallar con motivo claro")
        alterado = bytearray(self.documento)
        alterado[10] ^= 0x01
        ruta = os.path.join(self.carpeta, "resultado-alterado.pdf")
        with open(ruta, "wb") as f:
            f.write(alterado)
        codigo, texto = self.verificador(self.ruta_cert, ruta)
        self.exigir(codigo == 1 and "el documento no coincide con el hash sellado" in texto,
                    f"el verificador debía rechazar el documento alterado: {codigo} {texto}")
        self.ev["verificador_invalido"] = texto
        self.say(f"  1 byte distinto -> código {codigo}: {texto.strip()}")

    def paso7_prioridad(self) -> None:
        self.titulo(7, "Disputa de prioridad: Lab C sella el mismo documento después")
        r = self.c.llamar("POST", "/sellos", {"doc_hash": self.doc_hash, "titulo": "Mismo resultado (C)",
                                              "investigador": "Dr. C. Posterior", "autores": self.c.id, "umbral": 1})
        self.say(f"  {self.c.id}: {r['mensaje']}")
        base = self.ev["altura_sello"]
        self.minar(self.c, base + 1)
        self.converger(base + 1, "la red acepta el registro posterior")
        for n in self.todos:
            sellos = n.llamar("POST", "/prioridad", {"doc_hash": self.doc_hash})["sellos"]
            self.exigir(len(sellos) == 2, f"{n.id} ve {len(sellos)} sellos (deben ser 2)")
            self.exigir(sellos[0]["laboratorio"] == self.a.id and sellos[0]["prioritario"]
                        and sellos[0]["numero"] == base, f"{n.id}: la prioridad no es del sello más antiguo: {sellos}")
            self.exigir(sellos[1]["laboratorio"] == self.c.id and not sellos[1]["prioritario"], "orden incorrecto")
            self.say(f"  {n.id}: prioridad -> {sellos[0]['laboratorio']} (bloque #{sellos[0]['numero']}, "
                     f"{sellos[0]['hash_bloque'][:12]}…); posterior: {sellos[1]['laboratorio']} (bloque #{sellos[1]['numero']})")
        self.ev["altura_prioridad"] = base + 1

    def paso8_ataque(self) -> None:
        self.titulo(8, "Ataque a la red: Lab A difunde un bloque con raíz de Merkle falsa")
        antes = self.resumenes()
        for tipo in ("merkle_falsa", "sello_alterado"):
            r = self.a.llamar("POST", "/ataques", {"tipo": tipo, "destino": "red"})
            self.exigir(r["rechazado"] and r["cadena_intacta"], f"el ataque {tipo} no fue rechazado: {r}")
            self.say(f"  [{tipo}] enviado a {r['enviados']} par(es). Rechazo local: {r['motivos'][0]}")
            self.ev.setdefault("ataques", {})[tipo] = r["motivos"][0]
        time.sleep(0.8)
        for n in (self.b, self.c):
            rechazos = [e["texto"] for e in n.bitacora() if e["tipo"] == "rechazo" and "Bloque" in e["texto"]]
            self.exigir(rechazos, f"{n.id} no registró el rechazo en su bitácora")
            self.say(f"  {n.id} bitácora: {rechazos[-1]}")
        despues = self.resumenes()
        self.exigir(antes == despues, f"el ataque alteró alturas/puntas: {antes} -> {despues}")
        for nid, (alt, punta) in despues.items():
            self.say(f"  {nid}: altura {alt} y punta {punta[:16]}… intactas")
        self.ev["rechazos_bitacora"] = True

    def paso9_particion(self) -> None:
        self.titulo(9, "Partición: aislar a Lab C, minar a ambos lados y reconectar")
        base = self.ev["altura_prioridad"]
        for o in (self.a, self.b):
            self.c.llamar("POST", f"/pares/{o.id}/desconectar")
        self.esperar(lambda: self.c.pares() == [] and self.a.pares() == [self.b.id] and self.b.pares() == [self.a.id],
                     "Lab C aislado de A y B")
        self.say(f"  {self.c.id} desconectado (pares: {self.c.pares()}); {self.a.id} y {self.b.id} siguen unidos.")
        self.a.llamar("POST", "/transferencias", {"receptor": self.b.id, "monto": 5})
        self.minar(self.a, base + 1, dificultad=2)
        self.converger(base + 1, "A y B con el mismo bloque", [self.a, self.b])
        self.c.llamar("POST", "/transferencias", {"receptor": self.a.id, "monto": 7})
        self.minar(self.c, base + 1, dificultad=1)
        rama_ab, rama_c = self.a.resumen(), self.c.resumen()
        self.exigir(rama_ab[0] == rama_c[0] and rama_ab[1] != rama_c[1], "las dos ramas deberían divergir")
        self.say(f"  Ramas divergentes a la altura {base + 1}: A/B punta {rama_ab[1][:12]}… (dificultad 2) "
                 f"contra C punta {rama_c[1][:12]}… (dificultad 1)")
        for o in (self.a, self.b):
            self.c.llamar("POST", "/pares", {"ip": o.host_p2p, "puerto": o.p2p})
        altura, punta = self.converger(base + 1, "convergencia tras reconectar", limite=30)
        self.exigir(punta == rama_ab[1], "debió ganar la rama de A con más trabajo")
        self.say(f"  Reconectados: los 3 adoptan la rama con más trabajo (la de A), punta {punta[:16]}…")
        perdida = [p for p in self.c.pendientes() if p["tipo"] == "transferencia" and p["emisor"] == self.c.id]
        self.exigir(perdida, f"la transferencia de la rama perdida no volvió a pendientes de {self.c.id}")
        self.say(f"  La transacción de la rama perdida volvió a pendientes de {self.c.id}: C->{perdida[0]['receptor']} "
                 f"por {perdida[0]['monto']}")
        self.minar(self.c, base + 2, dificultad=1)
        self.converger(base + 2, "la tx recuperada entra en un bloque de la cadena ganadora")
        self.exigir(not self.c.pendientes(), "quedaron pendientes después de minar la tx recuperada")
        saldos = {n.id: sorted((c["id"], c["saldo"]) for c in n.nodo()["cuentas"]) for n in self.todos}
        self.exigir(len({json.dumps(s) for s in saldos.values()}) == 1, f"los saldos difieren: {saldos}")
        self.say("  Ningún sello ni transacción se perdió; saldos idénticos en los 3 nodos.")
        self.ev["altura_particion"] = base + 2

    def paso10_reinicio(self) -> None:
        self.titulo("extra", "Reinicio: se mata el proceso de Lab B y se vuelve a arrancar con los mismos datos")
        if not self.red.puede_reiniciar:
            self.say("  (omitido: los nodos fueron lanzados por fuera de este programa)")
            return
        base = self.ev["altura_particion"]
        antes = self.b.resumen()
        self.red.matar(self.b.id)
        self.say(f"  {self.b.id} detenido en la altura {antes[0]}.")
        self.esperar(lambda: self.b.id not in self.a.pares(), f"{self.a.id} nota la caída de {self.b.id}")
        self.a.llamar("POST", "/transferencias", {"receptor": self.c.id, "monto": 3})
        self.minar(self.a, base + 1)
        self.say(f"  Mientras {self.b.id} está caído, {self.a.id} mina el bloque #{base + 1}.")
        self.red.lanzar(self.b.id)
        est = self.b.nodo()
        self.exigir(not est["desbloqueado"], "tras reiniciar el nodo debe volver bloqueado")
        self.exigir((est["altura"], est["punta"]) == antes,
                    f"{self.b.id} no recargó su cadena del disco: {antes} -> {(est['altura'], est['punta'])}")
        cargado = [e for e in est["bitacora"] if e["tipo"] == "nodo" and "cargado" in e["texto"]]
        self.exigir(cargado and not any(e["tipo"] == "corrupto" for e in est["bitacora"]),
                    "la bitácora no muestra una carga limpia")
        self.say(f"  {self.b.id} recargó y revalidó su cadena desde disco: altura {est['altura']} (bloqueado). "
                 f"Bitácora: {cargado[-1]['texto']}")
        self.b.llamar("POST", "/desbloquear", {"contrasena": self.contrasena})
        self.converger(base + 1, "B se resincroniza tras el reinicio", limite=40)
        self.say(f"  {self.b.id} se resincronizó con la red (altura {base + 1}).")
        self.ev["altura_final"] = base + 1

    def ejecutar(self) -> dict:
        t0 = time.monotonic()
        self.paso1_desbloquear()
        self.paso2_sellar()
        self.paso3_cofirmar()
        self.paso4_minar()
        self.paso5_certificado()
        self.paso6_alterar()
        self.paso7_prioridad()
        self.paso8_ataque()
        self.paso9_particion()
        self.paso10_reinicio()
        self.ev["segundos"] = round(time.monotonic() - t0, 1)
        self.say(f"\nGuion completo en {self.ev['segundos']} s: todos los pasos se cumplieron.")
        return self.ev


# ---------------------------------------------------------------- programa
def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Demostración automática del guion §3.7 de Sellalo (plan B).")
    ap.add_argument("--carpeta", help="carpeta de trabajo (por defecto una temporal)")
    ap.add_argument("--urls", help="URLs de 3 nodos ya lanzados, separadas por comas (en vez de lanzarlos)")
    ap.add_argument("--contrasena-env", metavar="VAR", help="variable de entorno con la contraseña de los nodos")
    ap.add_argument("--dejar-abiertos", action="store_true", help="no cerrar los nodos al terminar")
    ap.add_argument("--http-base", type=int, default=5101, help="primer puerto HTTP (5101)")
    ap.add_argument("--p2p-base", type=int, default=6101, help="primer puerto P2P (6101)")
    args = ap.parse_args(argv)

    carpeta = args.carpeta or os.path.join(os.environ.get("TEMP", "/tmp"), f"sellalo-demo-{secrets.token_hex(3)}")
    contrasena = os.environ.get(args.contrasena_env, "") if args.contrasena_env else ""
    if args.urls:
        if not contrasena:
            print("Error: con --urls hace falta --contrasena-env con la contraseña de los nodos.", file=sys.stderr)
            return 2
        urls = [u.strip() for u in args.urls.split(",") if u.strip()]
        if len(urls) != 3:
            print("Error: --urls debe traer exactamente 3 nodos.", file=sys.stderr)
            return 2
        red = RedExterna(urls)
    else:
        contrasena = contrasena or ("demo-" + secrets.token_hex(8))
        print(f"Preparando 3 identidades cifradas y el génesis en {carpeta} …")
        red = RedLocal(carpeta, contrasena, http_base=args.http_base, p2p_base=args.p2p_base)
        red.lanzar_todos()
        print("Nodos lanzados: " + ", ".join(f"{n.id} {n.url} (P2P {n.p2p})" for n in red.nodos.values()))
    codigo = 0
    try:
        Guion(red, contrasena, os.path.join(carpeta, "evidencia")).ejecutar()
    except AssertionError as exc:
        print(f"\nFALLÓ EL GUION: {exc}", file=sys.stderr)
        codigo = 1
    finally:
        if args.dejar_abiertos and not args.urls:
            print("\nNodos abiertos (Ctrl+C para cerrarlos):")
            for n in red.nodos.values():
                print(f"  {n.id}: {n.url}")
            try:
                while any(n.proceso and n.proceso.poll() is None for n in red.nodos.values()):
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        red.cerrar()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
