"""Prepara (y opcionalmente lanza) una red Sellalo local de N laboratorios en una sola PC.

Uso:
    python scripts/lanzar_red_local.py --labs 3 [--carpeta data/demo] [--contrasena-env VAR] [--lanzar]

Crea (si no existen) las identidades LAB-A, LAB-B, ... con su almacén de claves cifrado y el génesis compartido, e
imprime el comando que arranca cada nodo. Con --lanzar arranca un proceso por laboratorio (`app.py --modo nodo`) y
los termina todos con Ctrl+C.
La contraseña se pide una vez (o se lee de --contrasena-env) y se usa para todas las identidades de la demo.
"""
import argparse
import getpass
import json
import os
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from models.errores import ErrorEntrada  # noqa: E402
from models.keystore import CONTRASENA_MIN, crear_almacen  # noqa: E402
from scripts.inicializar_red import construir_genesis  # noqa: E402

PUERTO_HTTP, PUERTO_P2P = 5001, 6001
MAX_LABS = 10


def nombre_lab(i: int) -> str:
    return f"LAB-{chr(ord('A') + i)}"


def preparar(n: int, carpeta: str, contrasena: str | None) -> tuple[str, list[dict]]:
    """Crea identidades y génesis que falten. Devuelve (ruta del génesis, lista de nodos con sus datos)."""
    if not 2 <= n <= MAX_LABS:
        raise ErrorEntrada(f"--labs debe estar entre 2 y {MAX_LABS}.")
    nodos = []
    for i in range(n):
        nid = nombre_lab(i)
        datos = os.path.join(carpeta, nid)
        clave = os.path.join(datos, "clave.json")
        if not os.path.exists(clave):
            if contrasena is None:
                raise ErrorEntrada("Falta la contraseña para crear las identidades (usa --contrasena-env).")
            crear_almacen(clave, nid, contrasena)
        nodos.append({"id": nid, "datos": datos, "clave": clave, "http": PUERTO_HTTP + i, "p2p": PUERTO_P2P + i})
    ruta_genesis = os.path.join(carpeta, "genesis.json")
    if not os.path.exists(ruta_genesis):
        genesis = construir_genesis([f"{x['id']}={x['clave']}" for x in nodos], 100, 10, "Red Sellalo (demo local)")
        with open(ruta_genesis, "w", encoding="utf-8") as f:
            json.dump(genesis, f, indent=2, ensure_ascii=False)
    for x in nodos:
        x["pares"] = ",".join(f"127.0.0.1:{y['p2p']}" for y in nodos if y is not x)
    return ruta_genesis, nodos


def comando(x: dict, genesis: str) -> list[str]:
    return [sys.executable, "app.py", "--modo", "nodo", "--nodo", x["id"], "--datos", x["datos"], "--genesis", genesis,
            "--puerto", str(x["http"]), "--puerto-p2p", str(x["p2p"]), "--pares", x["pares"]]


def lanzar(nodos: list[dict], genesis: str) -> int:
    """Arranca un proceso por laboratorio, imprime sus URLs y los termina a todos con Ctrl+C."""
    procesos = []
    try:
        for x in nodos:
            procesos.append(subprocess.Popen(comando(x, genesis), cwd=RAIZ))
        print(f"\n{len(procesos)} nodos lanzados (cada uno arranca bloqueado; desbloquéalo con su contraseña):")
        for x in nodos:
            print(f"  {x['id']}: http://127.0.0.1:{x['http']}  (P2P {x['p2p']})")
        print("Ctrl+C para detenerlos.")
        while procesos and any(p.poll() is None for p in procesos):
            time.sleep(0.5)
        print("Todos los nodos terminaron.")
    except KeyboardInterrupt:
        print("\nDeteniendo los nodos…")
    except OSError as exc:
        print(f"No se pudo lanzar un nodo: {exc}", file=sys.stderr)
        return 1
    finally:
        for p in procesos:
            if p.poll() is None:
                p.terminate()
        for p in procesos:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepara una red Sellalo local de varios laboratorios.")
    parser.add_argument("--labs", type=int, default=3, help="número de laboratorios (3)")
    parser.add_argument("--carpeta", default="data/demo", help="carpeta de la demo (data/demo)")
    parser.add_argument("--contrasena-env", metavar="VAR", help="leer la contraseña de esta variable de entorno")
    parser.add_argument("--lanzar", action="store_true", help="arrancar un proceso por laboratorio")
    args = parser.parse_args(argv)
    try:
        contrasena = None
        if args.contrasena_env:
            contrasena = os.environ.get(args.contrasena_env)
            if not contrasena:
                raise ErrorEntrada(f"La variable de entorno {args.contrasena_env} no existe o está vacía.")
        elif not os.path.exists(os.path.join(args.carpeta, nombre_lab(0), "clave.json")) and sys.stdin.isatty():
            contrasena = getpass.getpass(f"Contraseña para las identidades de la demo (mínimo {CONTRASENA_MIN}): ")
        genesis, nodos = preparar(args.labs, args.carpeta, contrasena)
    except ErrorEntrada as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Red local preparada en {args.carpeta} con {len(nodos)} laboratorios. Génesis: {genesis}\n")
    print("Comandos para arrancar cada nodo (uno por terminal; cada nodo se desbloquea desde la interfaz):")
    for x in nodos:
        print(f"  [{x['id']}]  http://127.0.0.1:{x['http']}\n    " + " ".join(comando(x, genesis)))
    if args.lanzar:
        return lanzar(nodos, genesis)
    return 0


if __name__ == "__main__":
    sys.exit(main())
