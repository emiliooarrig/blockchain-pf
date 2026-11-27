#!/usr/bin/env python3
"""Verificador independiente de certificados de prioridad de Sellalo.

Sólo usa la biblioteca estándar y `cryptography`; NO importa nada del proyecto, así que cualquiera puede auditarlo.
Uso:  python verificar_certificado.py certificado.json --genesis HASH [--documento ruta] [--min-confirmaciones N]
Salida: 0 certificado válido (red confirmada con --genesis), 1 inválido, 2 archivo ilegible o que no es JSON,
        3 NO CONCLUYENTE (el certificado es coherente consigo mismo pero no se indicó el génesis de la red).
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

DIF_MIN, DIF_MAX = 1, 6      # mismas cotas que exige el nodo (models/pow.py): sin dificultad 0 ni cadenas de ceros gigantes
EXCLUIDOS_HASH = ("hash", "transacciones", "firma_minero")
CAMPOS_FIRMADOS = ("tipo", "doc_hash", "titulo", "investigador", "laboratorio", "autores", "umbral", "timestamp")
CAMPOS_AJUSTE = ("tipo", "dificultad", "proponente", "timestamp")
HEX = set("0123456789abcdef")


def _sha(datos) -> str:
    return hashlib.sha256(datos.encode("utf-8") if isinstance(datos, str) else datos).hexdigest()


def _canonico(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _es_hex(v, largo) -> bool:
    return isinstance(v, str) and len(v) == largo and set(v) <= HEX


def hash_bloque(b: dict) -> str:
    datos = {k: v for k, v in b.items() if k not in EXCLUIDOS_HASH}
    return hashlib.sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()


def _firma_ok(publica, datos: bytes, firma) -> bool:
    if not (_es_hex(publica, 64) and _es_hex(firma, 128)):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(publica)).verify(bytes.fromhex(firma), datos)
        return True
    except (InvalidSignature, ValueError):
        return False


def _mensaje_sello(tx: dict) -> bytes:
    return _canonico({k: tx[k] for k in CAMPOS_FIRMADOS})


def _mensaje_ajuste(tx: dict) -> bytes:
    return _canonico({k: tx[k] for k in CAMPOS_AJUSTE})


def _revisar_ajuste(entrada, vigente, genesis: dict, cabecera: dict, vistos: set):
    """Valida un ajuste de dificultad del certificado (C9) contra la dificultad `vigente` y el génesis. Devuelve
    (nueva_dificultad, None) o (None, motivo)."""
    tx, prueba = entrada.get("tx"), entrada.get("prueba_merkle")
    if not isinstance(tx, dict) or not isinstance(prueba, dict):
        return None, "un ajuste de dificultad está mal formado"
    if set(tx) != set(CAMPOS_AJUSTE) | {"firmas"} or tx["tipo"] != "ajuste_dificultad":
        return None, "un ajuste de dificultad no tiene exactamente los campos esperados"
    dif, firmas, proponente = tx["dificultad"], tx["firmas"], tx["proponente"]
    if type(dif) is not int or not DIF_MIN <= dif <= DIF_MAX:
        return None, "un ajuste de dificultad pide una dificultad fuera de rango"
    if vigente is None:
        return None, "el génesis no fija la dificultad: no admite ajustes"
    if dif == vigente:
        return None, f"un ajuste de dificultad pide {dif}, que ya era la vigente"
    if not isinstance(firmas, dict) or _clave_de(genesis, proponente) is None or proponente not in firmas:
        return None, "el proponente de un ajuste de dificultad no está en el génesis o no lo firmó"
    mensaje = _mensaje_ajuste(tx)
    for quien, firma in firmas.items():
        if _clave_de(genesis, quien) is None:
            return None, f"un ajuste de dificultad trae la firma de {str(quien)[:20]}, que no es laboratorio del génesis"
        if not _firma_ok(_clave_de(genesis, quien), mensaje, firma):
            return None, f"la firma de {quien} en un ajuste de dificultad no es válida"
    n = len(genesis["cuentas"])
    if len(firmas) <= n / 2:
        return None, f"un ajuste de dificultad tiene {len(firmas)} firma(s) y se necesitan más de la mitad de {n} laboratorios"
    aid = _sha(mensaje)
    if aid in vistos:
        return None, "un ajuste de dificultad aparece dos veces en el certificado"
    vistos.add(aid)
    hoja = _sha(_canonico(tx))
    if prueba.get("hoja") != hoja or not _camino_ok(hoja, prueba.get("camino"), cabecera.get("raiz_merkle")):
        return None, "la prueba de Merkle de un ajuste de dificultad no lleva a la raíz de su bloque"
    return dif, None


def _camino_ok(hoja, pasos, raiz) -> bool:
    if not _es_hex(hoja, 64) or not _es_hex(raiz, 64) or not isinstance(pasos, list) or len(pasos) > 64:
        return False
    actual = hoja
    for p in pasos:
        if not isinstance(p, dict) or p.get("lado") not in ("izq", "der") or not _es_hex(p.get("hash"), 64):
            return False
        actual = _sha(p["hash"] + actual) if p["lado"] == "izq" else _sha(actual + p["hash"])
    return actual == raiz


def _fallo(motivo: str, detalle=None) -> dict:
    return {"valido": False, "concluyente": True, "genesis_confirmado": False, "motivo": motivo, "detalle": detalle or {}}


NOMBRES_PASOS = ("génesis", "encabezados", "sello", "multifirma", "merkle", "documento")


class _Pasos:
    """Registro de los pasos de la verificación (para mostrarlos paso a paso en la interfaz).
    Cada paso es {"paso", "ok", "detalle", "evaluado"}: `ok` es True/False si se evaluó y None si no se llegó a
    evaluar (un paso anterior falló) o no había datos (documento no entregado)."""

    def __init__(self):
        self.pasos = {n: {"paso": n, "ok": None, "detalle": "no evaluado: falló un paso anterior", "evaluado": False}
                      for n in NOMBRES_PASOS}
        self.merkle = None

    def ok(self, paso: str, detalle: str) -> None:
        self.pasos[paso].update(ok=True, detalle=detalle, evaluado=True)

    def omitido(self, paso: str, detalle: str) -> None:
        self.pasos[paso].update(ok=None, detalle=detalle, evaluado=False)

    def fallo(self, paso: str, motivo: str, detalle=None) -> dict:
        self.pasos[paso].update(ok=False, detalle=motivo, evaluado=True)
        return _fallo(motivo, detalle)

    def lista(self) -> list:
        return [dict(self.pasos[n]) for n in NOMBRES_PASOS]


def _clave_de(genesis: dict, nodo):
    cuentas = genesis.get("cuentas")
    if isinstance(cuentas, dict) and isinstance(nodo, str) and isinstance(cuentas.get(nodo), dict):
        return cuentas[nodo].get("clave_publica")
    return None


def _recorrer_camino(hoja, pasos, raiz) -> list:
    """Hash intermedio tras cada paso del camino de Merkle: [{"lado", "hash", "resultado"}]. Si un paso está mal
    formado se corta ahí; la comparación final con la raíz la hace `_camino_ok`."""
    salida, actual = [], hoja
    if not isinstance(pasos, list):
        return salida
    for p in pasos[:64]:
        if not isinstance(p, dict) or p.get("lado") not in ("izq", "der") or not _es_hex(p.get("hash"), 64):
            break
        actual = _sha(p["hash"] + actual) if p["lado"] == "izq" else _sha(actual + p["hash"])
        salida.append({"lado": p["lado"], "hash": p["hash"], "resultado": actual})
    return salida


def _verificar(cert, documento, genesis_esperado, reg: _Pasos) -> dict:
    if not isinstance(cert, dict):
        return reg.fallo("génesis", "el certificado no es un objeto JSON")
    if cert.get("formato") != "sellalo-certificado":
        return reg.fallo("génesis", "formato desconocido: no es un certificado de Sellalo")
    if type(cert.get("version")) is not int or cert["version"] != 1:     # True == 1 en Python: se exige un entero
        return reg.fallo("génesis", f"versión de certificado no soportada: {cert.get('version')!r}")
    genesis, encabezados = cert.get("genesis"), cert.get("encabezados")
    sello, prueba = cert.get("sello"), cert.get("prueba_merkle")
    numero_bloque, doc_hash = cert.get("numero_bloque"), cert.get("doc_hash")
    if not (isinstance(genesis, dict) and isinstance(encabezados, list) and isinstance(sello, dict)
            and isinstance(prueba, dict) and isinstance(cert.get("emitido"), (int, float))):
        return reg.fallo("génesis", "el certificado está incompleto o mal formado")
    if not _es_hex(doc_hash, 64):
        return reg.fallo("génesis", "el hash del documento del certificado no es válido")
    if type(numero_bloque) is not int or numero_bloque < 1:
        return reg.fallo("génesis", "el número de bloque del certificado no es válido")
    if not encabezados or not all(isinstance(h, dict) for h in encabezados):
        return reg.fallo("encabezados", "los encabezados del certificado no son válidos")
    ajustes = cert.get("ajustes", [])
    if not isinstance(ajustes, list) or not all(isinstance(a, dict) and type(a.get("bloque")) is int for a in ajustes) \
            or len({a["bloque"] for a in ajustes}) != len(ajustes):
        return reg.fallo("encabezados", "los ajustes de dificultad del certificado no son válidos "
                                        "(deben ser una lista con un ajuste como máximo por bloque)")
    ajustes_por_bloque = {a["bloque"]: a for a in ajustes}

    # 1. Génesis
    try:
        hash_genesis = hash_bloque(genesis)
    except (TypeError, ValueError):
        return reg.fallo("génesis", "el bloque génesis no se puede serializar")
    if genesis.get("hash") != hash_genesis:
        return reg.fallo("génesis", "el hash del génesis no coincide con su contenido")
    if genesis_esperado is not None and genesis_esperado != "" and hash_genesis != genesis_esperado.strip().lower():
        return reg.fallo("génesis", "el génesis del certificado no es el esperado (red distinta)",
                         {"genesis": hash_genesis, "esperado": genesis_esperado})
    if not isinstance(genesis.get("cuentas"), dict):
        return reg.fallo("génesis", "el génesis no contiene cuentas")

    parametros = genesis.get("parametros")
    dif_red = parametros.get("dificultad") if isinstance(parametros, dict) else None
    if isinstance(parametros, dict) and "dificultad" in parametros and (
            type(dif_red) is not int or not DIF_MIN <= dif_red <= DIF_MAX):
        return reg.fallo("génesis", "el génesis fija una dificultad de red inválida")
    confirmado_esp = isinstance(genesis_esperado, str) and bool(genesis_esperado.strip())
    reg.ok("génesis", f"hash {hash_genesis[:16]}… coincide con su contenido"
           + ("; es el génesis esperado de la red" if confirmado_esp else
              "; no se indicó el génesis esperado, la red no está confirmada"))

    # 2. Encabezados (la dificultad vigente parte de la del génesis y sólo cambia por un ajuste co-firmado probado)
    anterior, previo_num, vigente, vistos_ajustes, aplicados = hash_genesis, 0, dif_red, set(), 0
    for h in encabezados:
        num = h.get("numero")
        if type(num) is not int:
            return reg.fallo("encabezados", "un encabezado no tiene número de bloque válido")
        try:
            recalculado = hash_bloque(h)
        except (TypeError, ValueError):
            return reg.fallo("encabezados", f"el encabezado {num} no se puede serializar")
        if h.get("hash") != recalculado:
            return reg.fallo("encabezados", f"el hash del bloque {num} no coincide con su contenido")
        if h.get("hash_anterior") != anterior:
            return reg.fallo("encabezados", f"el bloque {num} no enlaza con el bloque anterior")
        if num != previo_num + 1:
            return reg.fallo("encabezados", f"la numeración de los bloques no es consecutiva en el bloque {num}")
        dif = h.get("dificultad")
        if type(dif) is not int or not DIF_MIN <= dif <= DIF_MAX or not h["hash"].startswith("0" * dif):
            return reg.fallo("encabezados", f"el bloque {num} no cumple la prueba de trabajo")
        if vigente is not None and dif != vigente:
            return reg.fallo("encabezados", f"el bloque {num} usa dificultad {dif} y la vigente es {vigente} "
                                            f"(la del génesis o la de un ajuste co-firmado probado)")
        clave = _clave_de(genesis, h.get("proponente"))
        if clave is None:
            return reg.fallo("encabezados", f"el proponente del bloque {num} no está en el génesis")
        if not _firma_ok(clave, bytes.fromhex(h["hash"]), h.get("firma_minero")):
            return reg.fallo("encabezados", f"la firma del minero del bloque {num} no es válida")
        if num in ajustes_por_bloque:        # rige desde el bloque siguiente
            nueva, motivo = _revisar_ajuste(ajustes_por_bloque[num], vigente, genesis, h, vistos_ajustes)
            if motivo:
                return reg.fallo("encabezados", f"bloque {num}: {motivo}")
            vigente, aplicados = nueva, aplicados + 1
        anterior, previo_num = h["hash"], num
    if len(ajustes_por_bloque) != aplicados:
        return reg.fallo("encabezados", "el certificado trae ajustes de dificultad de bloques que no están en los encabezados")
    punta = previo_num
    if numero_bloque > punta:
        return reg.fallo("encabezados", "el bloque del sello no está en los encabezados del certificado")
    cabecera = encabezados[numero_bloque - 1]
    reg.ok("encabezados", f"{punta} encabezado(s): hash recalculado, enlace, prueba de trabajo y firma del minero "
                          f"correctos hasta la punta (bloque {punta})"
           + (f"; {aplicados} ajuste(s) de dificultad co-firmado(s) probado(s)" if aplicados else ""))

    # 3. Sello
    if set(sello) != set(CAMPOS_FIRMADOS) | {"firmas"}:
        return reg.fallo("sello", "el sello no tiene exactamente los campos esperados")
    if sello["tipo"] != "sello":
        return reg.fallo("sello", "la transacción no es un sello")
    if sello["doc_hash"] != doc_hash:
        return reg.fallo("sello", "el sello no corresponde al documento del certificado")
    autores, umbral, firmas = sello["autores"], sello["umbral"], sello["firmas"]
    if not (isinstance(autores, list) and autores and all(isinstance(a, str) for a in autores)
            and type(umbral) is int and isinstance(firmas, dict)):
        return reg.fallo("sello", "los autores, el umbral o las firmas del sello no son válidos")
    if not 1 <= umbral <= len(autores):
        return reg.fallo("sello", "el umbral del sello no es válido")
    for a in autores:
        if _clave_de(genesis, a) is None:
            return reg.fallo("sello", f"el autor {a} no está registrado en el génesis")
    reg.ok("sello", f"sello del documento {doc_hash[:12]}… con {len(autores)} autor(es) registrados en el génesis "
                    f"y umbral {umbral}")

    # 3b. Multifirma
    try:
        mensaje = _mensaje_sello(sello)
    except (TypeError, ValueError):
        return reg.fallo("multifirma", "el sello no se puede serializar")
    for quien, firma in firmas.items():
        if quien not in autores:
            return reg.fallo("multifirma", f"el sello trae una firma de {quien}, que no es autor")
        if not _firma_ok(_clave_de(genesis, quien), mensaje, firma):
            return reg.fallo("multifirma", f"la firma de {quien} en el sello no es válida")
    if len(firmas) < umbral:
        return reg.fallo("multifirma", f"el sello tiene {len(firmas)} firma(s) válida(s) y el umbral exige {umbral}")
    reg.ok("multifirma", f"{len(firmas)} firma(s) válida(s) ({', '.join(sorted(firmas))}) y el umbral exige {umbral}")

    # 4. Merkle
    hoja = _sha(_canonico(sello))
    camino = _recorrer_camino(hoja, prueba.get("camino"), cabecera.get("raiz_merkle"))
    reg.merkle = {"hoja": hoja, "raiz": cabecera.get("raiz_merkle"), "camino": camino}
    if prueba.get("hoja") != hoja:
        return reg.fallo("merkle", "la hoja de la prueba de Merkle no corresponde al sello")
    if not _camino_ok(hoja, prueba.get("camino"), cabecera.get("raiz_merkle")):
        return reg.fallo("merkle", "la prueba de Merkle no lleva a la raíz del bloque")
    reg.ok("merkle", f"la hoja del sello sube por {len(camino)} paso(s) hasta la raíz del bloque {numero_bloque}")

    # 5. Documento
    if documento is not None and hashlib.sha256(documento).hexdigest() != doc_hash:
        return reg.fallo("documento", "el documento no coincide con el hash sellado")
    if documento is None:
        reg.omitido("documento", "no se entregó el documento: no se comprobó su SHA-256")
    else:
        reg.ok("documento", "el SHA-256 del documento coincide con el hash sellado")

    fecha = datetime.fromtimestamp(cabecera["timestamp"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    confirmado = confirmado_esp
    return {"valido": confirmado, "concluyente": confirmado, "genesis_confirmado": confirmado,
            "motivo": "certificado válido" if confirmado else
            "NO CONCLUYENTE: el certificado es coherente consigo mismo, pero no se indicó el hash del génesis de la "
            "red; cualquiera puede fabricar una red propia", "detalle": {
        "fecha": fecha, "titulo": sello["titulo"], "investigador": sello["investigador"],
        "laboratorio": sello["laboratorio"], "autores": list(autores), "umbral": umbral,
        "bloque": numero_bloque, "confirmaciones": punta - numero_bloque, "genesis": hash_genesis,
        "doc_hash": doc_hash, "documento_comprobado": documento is not None}}


def verificar(cert: dict, documento: bytes | None = None, genesis_esperado: str | None = None) -> dict:
    """Verifica un certificado ya cargado. Nunca lanza excepciones por datos mal formados.

    Semántica (AUD-005): `valido` sólo es True si el certificado es íntegro Y se dio `genesis_esperado` y coincide con
    el génesis del certificado (`genesis_confirmado`). Sin `genesis_esperado` el resultado es `valido=False`,
    `concluyente=False` (coherente pero de red no confirmada); el detalle conserva los datos del sello.

    Además devuelve `pasos` (génesis, encabezados, sello, multifirma, merkle, documento: cada uno con `ok`,
    `detalle` y `evaluado`; ok es None si no se evaluó) y `merkle` ({hoja, raiz, camino: [{lado, hash, resultado}]},
    None si no se llegó a ese paso). No cambian `valido`, `motivo`, `detalle` ni `genesis_confirmado`."""
    reg = _Pasos()
    try:
        resultado = _verificar(cert, documento, genesis_esperado, reg)
    except Exception as e:  # datos inesperados: se reporta como inválido, nunca como traceback
        resultado = _fallo(f"el certificado está mal formado ({type(e).__name__})")
        primero = next((p for p in reg.pasos.values() if not p["evaluado"]), None)
        if primero is not None:
            primero.update(ok=False, evaluado=True, detalle=resultado["motivo"])
    resultado["pasos"] = reg.lista()
    resultado["merkle"] = reg.merkle
    return resultado


def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Verifica un certificado de prioridad de Sellalo sin conexión.")
    ap.add_argument("certificado")
    ap.add_argument("--documento", help="archivo original para comprobar su SHA-256")
    ap.add_argument("--genesis", help="hash del génesis de la red (necesario para concluir que es VÁLIDO)")
    args = ap.parse_args(argv)
    try:
        with open(args.certificado, "r", encoding="utf-8") as f:
            cert = json.load(f)
    except (OSError, ValueError) as e:
        print(f"No se pudo leer el certificado como JSON: {e}")
        return 2
    documento = None
    if args.documento:
        try:
            with open(args.documento, "rb") as f:
                documento = f.read()
        except OSError as e:
            print(f"No se pudo leer el documento: {e}")
            return 2
    r = verificar(cert, documento, args.genesis)
    if not r["valido"] and r["concluyente"]:
        print(f"CERTIFICADO NO VÁLIDO: {r['motivo']}")
        return 1
    d = r["detalle"]
    print("CERTIFICADO VÁLIDO" if r["valido"] else "CERTIFICADO: NO CONCLUYENTE")
    if not r["valido"]:
        print(r["motivo"])
        print("Repita con --genesis HASH_DEL_GENESIS_DE_LA_RED (publicado por la red) para confirmar la red.")
    print(f"Fecha del bloque: {d['fecha']}")
    print(f"Título: {d['titulo']}")
    print(f"Investigador: {d['investigador']}")
    print(f"Laboratorio: {d['laboratorio']}")
    print(f"Autores: {', '.join(d['autores'])} (umbral {d['umbral']} de {len(d['autores'])})")
    print(f"Bloque: {d['bloque']}  Confirmaciones: {d['confirmaciones']}")
    print(f"Génesis: {d['genesis']}")
    print("Documento: " + ("coincide con el hash sellado" if d["documento_comprobado"]
                           else "no se comprobó (use --documento)"))
    return 0 if r["valido"] else 3


if __name__ == "__main__":
    sys.exit(main())
