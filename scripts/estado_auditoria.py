#!/usr/bin/env python3
"""Genera docs/auditoria/estado.json: el estado de cada hallazgo de la auditoría con IA.

Fuentes (todas versionadas en el repositorio):
  docs/auditoria/HALLAZGOS.md   tabla maestra (id, categoría, severidad, grupo, descripción) y fichas (título)
  docs/auditoria/TRIAJE.md      decisión de cada hallazgo (C, CP, RE, NA, D) y qué se hace
  git log                       commits cuyo asunto empieza con `fix(AUD-0NN)`
  tests/                        pruebas `test_aud_0NN_*` en tests/test_auditoria_g*.py (y las que cite el triaje)

Estado de cada hallazgo:
  resuelto_por_eliminacion  decisión RE (o el triaje dice «resuelto por eliminación»)
  justificado               decisión NA o D (no se corrige; la justificación está en el triaje)
  corregido                 decisión C o CP y existe al menos un commit `fix(AUD-0NN)`
  pendiente                 cualquier otro caso (p. ej. decisión C sin commit de corrección)

Uso:  python scripts/estado_auditoria.py [--salida docs/auditoria/estado.json] [--raiz .]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RE_ID = re.compile(r"^AUD-\d{3}$")
RE_COMMIT = re.compile(r"^fix\((AUD-\d{3}(?:\s*,\s*AUD-\d{3})*)\)")
DECISIONES = {"C", "CP", "RE", "NA", "D"}


def _leer(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def _corta(texto: str, maximo: int = 240) -> str:
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto) <= maximo:
        return texto
    corte = texto.rfind(". ", 0, maximo)
    return texto[:corte + 1] if corte > 60 else texto[:maximo - 1].rstrip() + "…"


def leer_tabla_maestra(texto: str) -> dict:
    """{id: {categoria, severidad, grupo, descripcion}} de la tabla `## 3. Tabla maestra`. Las columnas fijas se
    toman desde los dos extremos porque la descripción puede contener «|» dentro de código."""
    inicio = texto.index("## 3. Tabla maestra")
    fin = texto.index("## 4. Fichas")
    filas = {}
    for linea in texto[inicio:fin].splitlines():
        if not linea.startswith("| AUD-"):
            continue
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if len(celdas) < 11 or not RE_ID.match(celdas[0]):
            continue
        medio = "|".join(celdas[4:-5]).strip()          # `archivo:línea` + descripción
        m = re.match(r"^`[^`]*`\s*\|\s*(.*)$", medio)
        filas[celdas[0]] = {"categoria": celdas[1], "severidad": celdas[2], "grupo": celdas[3],
                            "descripcion": _corta(m.group(1) if m else medio)}
    return filas


def leer_titulos(texto: str) -> dict:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^### (AUD-\d{3}) · (.+)$", texto, re.M)}


def leer_triaje(texto: str) -> dict:
    """{id: {decision, accion}} de las tablas del triaje (`| AUD-0NN | C | Qué se hace |`)."""
    salida = {}
    for linea in texto.splitlines():
        m = re.match(r"^\|\s*(AUD-\d{3})\s*\|\s*([A-Z]{1,2})\s*\|\s*(.*?)\s*\|\s*$", linea)
        if m and m.group(2) in DECISIONES:
            salida[m.group(1)] = {"decision": m.group(2), "accion": _corta(m.group(3).replace("**", ""), 400),
                                  "texto": m.group(3)}
    return salida


def leer_commits(raiz: str) -> tuple[dict, str | None]:
    """({id: [hashes cortos, del más antiguo al más reciente]}, advertencia)."""
    try:
        r = subprocess.run(["git", "log", "--format=%h%x09%s", "--reverse"], cwd=raiz, capture_output=True,
                           text=True, encoding="utf-8", check=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return {}, f"no se pudo leer git log ({type(exc).__name__}): los commits quedan vacíos"
    commits: dict = {}
    for linea in r.stdout.splitlines():
        corto, _, asunto = linea.partition("\t")
        m = RE_COMMIT.match(asunto)
        if m:
            for aud in re.findall(r"AUD-\d{3}", m.group(1)):
                commits.setdefault(aud, []).append(corto)
    return commits, None


def buscar_pruebas(raiz: str, triaje: dict) -> dict:
    """{id: ["tests/archivo.py::test_nombre", ...]}: `test_aud_0NN_*` en tests/test_auditoria_g*.py y, si el
    triaje cita explícitamente una prueba existente (`test_...`), esa."""
    carpeta = os.path.join(raiz, "tests")
    pruebas: dict = {}
    todas: dict = {}
    for nombre in sorted(os.listdir(carpeta)):
        if not (nombre.startswith("test_") and nombre.endswith(".py")):
            continue
        for m in re.finditer(r"^def (test_\w+)", _leer(os.path.join(carpeta, nombre)), re.M):
            todas.setdefault(m.group(1), f"tests/{nombre}")
            a = re.match(r"^test_aud_(\d{3})_", m.group(1))
            if a and nombre.startswith("test_auditoria_g"):
                pruebas.setdefault(f"AUD-{a.group(1)}", []).append(f"tests/{nombre}::{m.group(1)}")
    for aud, t in triaje.items():
        if aud not in pruebas:
            citadas = [n for n in re.findall(r"`(test_\w+)`", t["texto"]) if n in todas]
            if citadas:
                pruebas[aud] = [f"{todas[n]}::{n}" for n in citadas]
    return pruebas


def estado_de(decision: str | None, accion_texto: str, commits: list) -> str:
    if decision == "RE" or "resuelto por eliminación" in accion_texto.lower():
        return "resuelto_por_eliminacion"
    if decision in ("NA", "D"):
        return "justificado"
    if decision in ("C", "CP") and commits:
        return "corregido"
    return "pendiente"


def generar(raiz: str = RAIZ) -> dict:
    hallazgos_md = _leer(os.path.join(raiz, "docs", "auditoria", "HALLAZGOS.md"))
    tabla, titulos = leer_tabla_maestra(hallazgos_md), leer_titulos(hallazgos_md)
    triaje = leer_triaje(_leer(os.path.join(raiz, "docs", "auditoria", "TRIAJE.md")))
    commits, aviso = leer_commits(raiz)
    pruebas = buscar_pruebas(raiz, triaje)
    if aviso:
        print("Aviso:", aviso, file=sys.stderr)
    hallazgos = []
    for aud in sorted(tabla):
        fila, tri = tabla[aud], triaje.get(aud, {})
        decision = tri.get("decision")
        estado = estado_de(decision, tri.get("texto", ""), commits.get(aud, []))
        hallazgos.append({
            "id": aud, "titulo": titulos.get(aud, fila["descripcion"]), "descripcion": fila["descripcion"],
            "severidad": fila["severidad"], "categoria": fila["categoria"], "grupo": fila["grupo"],
            "decision": decision, "accion": tri.get("accion"), "estado": estado,
            "commits": commits.get(aud, []), "prueba": (pruebas.get(aud) or [None])[0],
            "pruebas": pruebas.get(aud, [])})
    resumen = {"total": len(hallazgos),
               "por_decision": dict(sorted(Counter(h["decision"] or "sin_decision" for h in hallazgos).items())),
               "por_severidad": dict(Counter(h["severidad"] for h in hallazgos)),
               "por_estado": dict(sorted(Counter(h["estado"] for h in hallazgos).items()))}
    return {"generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "resumen": resumen,
            "hallazgos": hallazgos}


def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Genera docs/auditoria/estado.json desde HALLAZGOS.md, TRIAJE.md y git.")
    ap.add_argument("--raiz", default=RAIZ, help="raíz del repositorio")
    ap.add_argument("--salida", help="archivo de salida (por defecto docs/auditoria/estado.json)")
    args = ap.parse_args(argv)
    try:
        datos = generar(args.raiz)
    except (OSError, ValueError) as exc:
        print(f"No se pudo generar el estado de la auditoría: {exc}", file=sys.stderr)
        return 1
    salida = args.salida or os.path.join(args.raiz, "docs", "auditoria", "estado.json")
    with open(salida, "w", encoding="utf-8", newline="\n") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
        f.write("\n")
    r = datos["resumen"]
    print(f"{salida}: {r['total']} hallazgos · por estado {r['por_estado']} · por decisión {r['por_decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
