#!/usr/bin/env python3
"""Verificador independiente de certificados de prioridad de Sellalo.

Sólo usa la biblioteca estándar y `cryptography`; NO importa nada del proyecto, así que cualquiera puede auditarlo.
Uso:  python verificar_certificado.py certificado.json [--documento ruta] [--genesis HASH]
Salida: 0 certificado válido, 1 inválido, 2 archivo ilegible o que no es JSON.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

EXCLUIDOS_HASH = ("hash", "transacciones", "firma_minero")
CAMPOS_FIRMADOS = ("tipo", "doc_hash", "titulo", "investigador", "laboratorio", "autores", "umbral", "timestamp")
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
    return {"valido": False, "motivo": motivo, "detalle": detalle or {}}


def _clave_de(genesis: dict, nodo):
    cuentas = genesis.get("cuentas")
    if isinstance(cuentas, dict) and isinstance(nodo, str) and isinstance(cuentas.get(nodo), dict):
        return cuentas[nodo].get("clave_publica")
    return None


def _verificar(cert, documento, genesis_esperado) -> dict:
    if not isinstance(cert, dict):
        return _fallo("el certificado no es un objeto JSON")
    if cert.get("formato") != "sellalo-certificado":
        return _fallo("formato desconocido: no es un certificado de Sellalo")
    if cert.get("version") != 1:
        return _fallo(f"versión de certificado no soportada: {cert.get('version')!r}")
    genesis, encabezados = cert.get("genesis"), cert.get("encabezados")
    sello, prueba = cert.get("sello"), cert.get("prueba_merkle")
    numero_bloque, doc_hash = cert.get("numero_bloque"), cert.get("doc_hash")
    if not (isinstance(genesis, dict) and isinstance(encabezados, list) and isinstance(sello, dict)
            and isinstance(prueba, dict) and isinstance(cert.get("emitido"), (int, float))):
        return _fallo("el certificado está incompleto o mal formado")
    if not _es_hex(doc_hash, 64):
        return _fallo("el hash del documento del certificado no es válido")
    if type(numero_bloque) is not int or numero_bloque < 1:
        return _fallo("el número de bloque del certificado no es válido")
    if not encabezados or not all(isinstance(h, dict) for h in encabezados):
        return _fallo("los encabezados del certificado no son válidos")

    # 1. Génesis
    try:
        hash_genesis = hash_bloque(genesis)
    except (TypeError, ValueError):
        return _fallo("el bloque génesis no se puede serializar")
    if genesis.get("hash") != hash_genesis:
        return _fallo("el hash del génesis no coincide con su contenido")
    if genesis_esperado is not None and hash_genesis != genesis_esperado.strip().lower():
        return _fallo("el génesis del certificado no es el esperado (red distinta)",
                      {"genesis": hash_genesis, "esperado": genesis_esperado})
    if not isinstance(genesis.get("cuentas"), dict):
        return _fallo("el génesis no contiene cuentas")

    # 2. Encabezados
    anterior, previo_num = hash_genesis, 0
    for h in encabezados:
        num = h.get("numero")
        if type(num) is not int:
            return _fallo("un encabezado no tiene número de bloque válido")
        try:
            recalculado = hash_bloque(h)
        except (TypeError, ValueError):
            return _fallo(f"el encabezado {num} no se puede serializar")
        if h.get("hash") != recalculado:
            return _fallo(f"el hash del bloque {num} no coincide con su contenido")
        if h.get("hash_anterior") != anterior:
            return _fallo(f"el bloque {num} no enlaza con el bloque anterior")
        if num != previo_num + 1:
            return _fallo(f"la numeración de los bloques no es consecutiva en el bloque {num}")
        dif = h.get("dificultad")
        if type(dif) is not int or dif < 0 or not h["hash"].startswith("0" * dif):
            return _fallo(f"el bloque {num} no cumple la prueba de trabajo")
        clave = _clave_de(genesis, h.get("proponente"))
        if clave is None:
            return _fallo(f"el proponente del bloque {num} no está en el génesis")
        if not _firma_ok(clave, bytes.fromhex(h["hash"]), h.get("firma_minero")):
            return _fallo(f"la firma del minero del bloque {num} no es válida")
        anterior, previo_num = h["hash"], num
    punta = previo_num
    if numero_bloque > punta:
        return _fallo("el bloque del sello no está en los encabezados del certificado")
    cabecera = encabezados[numero_bloque - 1]

    # 3. Sello
    if set(sello) != set(CAMPOS_FIRMADOS) | {"firmas"}:
        return _fallo("el sello no tiene exactamente los campos esperados")
    if sello["tipo"] != "sello":
        return _fallo("la transacción no es un sello")
    if sello["doc_hash"] != doc_hash:
        return _fallo("el sello no corresponde al documento del certificado")
    autores, umbral, firmas = sello["autores"], sello["umbral"], sello["firmas"]
    if not (isinstance(autores, list) and autores and all(isinstance(a, str) for a in autores)
            and type(umbral) is int and isinstance(firmas, dict)):
        return _fallo("los autores, el umbral o las firmas del sello no son válidos")
    if not 1 <= umbral <= len(autores):
        return _fallo("el umbral del sello no es válido")
    for a in autores:
        if _clave_de(genesis, a) is None:
            return _fallo(f"el autor {a} no está registrado en el génesis")
    try:
        mensaje = _mensaje_sello(sello)
    except (TypeError, ValueError):
        return _fallo("el sello no se puede serializar")
    for quien, firma in firmas.items():
        if quien not in autores:
            return _fallo(f"el sello trae una firma de {quien}, que no es autor")
        if not _firma_ok(_clave_de(genesis, quien), mensaje, firma):
            return _fallo(f"la firma de {quien} en el sello no es válida")
    if len(firmas) < umbral:
        return _fallo(f"el sello tiene {len(firmas)} firma(s) válida(s) y el umbral exige {umbral}")

    # 4. Merkle
    hoja = _sha(_canonico(sello))
    if prueba.get("hoja") != hoja:
        return _fallo("la hoja de la prueba de Merkle no corresponde al sello")
    if not _camino_ok(hoja, prueba.get("camino"), cabecera.get("raiz_merkle")):
        return _fallo("la prueba de Merkle no lleva a la raíz del bloque")

    # 5. Documento
    if documento is not None and hashlib.sha256(documento).hexdigest() != doc_hash:
        return _fallo("el documento no coincide con el hash sellado")

    fecha = datetime.fromtimestamp(cabecera["timestamp"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return {"valido": True, "motivo": "certificado válido", "detalle": {
        "fecha": fecha, "titulo": sello["titulo"], "investigador": sello["investigador"],
        "laboratorio": sello["laboratorio"], "autores": list(autores), "umbral": umbral,
        "bloque": numero_bloque, "confirmaciones": punta - numero_bloque, "genesis": hash_genesis,
        "doc_hash": doc_hash, "documento_comprobado": documento is not None}}


def verificar(cert: dict, documento: bytes | None = None, genesis_esperado: str | None = None) -> dict:
    """Verifica un certificado ya cargado. Nunca lanza excepciones por datos mal formados."""
    try:
        return _verificar(cert, documento, genesis_esperado)
    except Exception as e:  # datos inesperados: se reporta como inválido, nunca como traceback
        return _fallo(f"el certificado está mal formado ({type(e).__name__})")


def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Verifica un certificado de prioridad de Sellalo sin conexión.")
    ap.add_argument("certificado")
    ap.add_argument("--documento", help="archivo original para comprobar su SHA-256")
    ap.add_argument("--genesis", help="hash del génesis esperado (para confirmar la red)")
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
    if not r["valido"]:
        print(f"CERTIFICADO NO VÁLIDO: {r['motivo']}")
        return 1
    d = r["detalle"]
    print("CERTIFICADO VÁLIDO")
    print(f"Fecha del bloque: {d['fecha']}")
    print(f"Título: {d['titulo']}")
    print(f"Investigador: {d['investigador']}")
    print(f"Laboratorio: {d['laboratorio']}")
    print(f"Autores: {', '.join(d['autores'])} (umbral {d['umbral']} de {len(d['autores'])})")
    print(f"Bloque: {d['bloque']}  Confirmaciones: {d['confirmaciones']}")
    print(f"Génesis: {d['genesis']}")
    print("Documento: " + ("coincide con el hash sellado" if d["documento_comprobado"]
                           else "no se comprobó (use --documento)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
