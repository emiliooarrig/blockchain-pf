"""Crea el bloque génesis compartido de la red Sellalo a partir de las claves públicas de los laboratorios.

Uso:
    python scripts/inicializar_red.py --lab LAB-A=data/LAB-A/clave.json --lab LAB-B=data/LAB-B/clave.json \
        --salida red/genesis.json [--saldo 100] [--recompensa 10] [--dificultad 4] [--nombre "Red Sellalo"] [--forzar]

Sólo se leen las claves públicas (no hace falta ninguna contraseña). El archivo resultante se copia a todas las PCs.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.bloque import crear_genesis  # noqa: E402
from models.errores import ErrorEntrada  # noqa: E402
from models.keystore import leer_publica  # noqa: E402
from models.pow import DIF_MAX, DIF_MIN  # noqa: E402
from models.validacion import revisar_genesis  # noqa: E402

CONFIRMACIONES = 6
DIFICULTAD = 4   # dificultad PoW fija de la red (AUD-004): todo bloque debe usar exactamente esta


def construir_genesis(labs: list[str], saldo: int, recompensa: int, nombre: str, timestamp: float | None = None,
                     dificultad: int = DIFICULTAD) -> dict:
    """`labs` = lista de «ID=ruta_del_almacen». Devuelve el génesis o lanza ErrorEntrada."""
    cuentas = {}
    for item in labs:
        if "=" not in item:
            raise ErrorEntrada(f"--lab debe tener la forma ID=ruta (recibido: {item!r}).")
        nodo_id, ruta = item.split("=", 1)
        nodo_id = nodo_id.strip()
        if nodo_id in cuentas:
            raise ErrorEntrada(f"El laboratorio {nodo_id} está repetido.")
        id_archivo, publica = leer_publica(ruta.strip())
        if id_archivo != nodo_id:
            raise ErrorEntrada(f"El archivo {ruta} es de «{id_archivo}», no de «{nodo_id}».")
        if any(c["clave_publica"] == publica for c in cuentas.values()):
            raise ErrorEntrada(f"{nodo_id} usa una clave pública que ya tiene otro laboratorio.")
        cuentas[nodo_id] = {"clave_publica": publica, "saldo": saldo}
    if len(cuentas) < 2:
        raise ErrorEntrada("Hacen falta al menos 2 laboratorios (--lab ID=ruta).")
    if saldo < 0 or recompensa < 0:
        raise ErrorEntrada("El saldo y la recompensa no pueden ser negativos.")
    if type(dificultad) is not int or not DIF_MIN <= dificultad <= DIF_MAX:
        raise ErrorEntrada(f"La dificultad debe ser un entero entre {DIF_MIN} y {DIF_MAX}.")
    parametros = {"consenso": "pow", "recompensa": recompensa, "confirmaciones": CONFIRMACIONES, "red": "sellalo",
                  "nombre": nombre, "dificultad": dificultad}
    genesis = crear_genesis(cuentas, parametros, time.time() if timestamp is None else timestamp)
    revisar_genesis(genesis, genesis["hash"])
    return genesis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crea el génesis compartido de la red Sellalo.")
    parser.add_argument("--lab", action="append", default=[], metavar="ID=RUTA",
                        help="laboratorio y su archivo de claves (repetir al menos 2 veces)")
    parser.add_argument("--salida", required=True, help="archivo del génesis (p. ej. red/genesis.json)")
    parser.add_argument("--saldo", type=int, default=100, help="saldo inicial de cada laboratorio (100)")
    parser.add_argument("--recompensa", type=int, default=10, help="recompensa por bloque (10)")
    parser.add_argument("--dificultad", type=int, default=DIFICULTAD,
                        help=f"dificultad PoW fija de la red, ceros hexadecimales iniciales ({DIFICULTAD})")
    parser.add_argument("--nombre", default="Red Sellalo", help="nombre de la red")
    parser.add_argument("--forzar", action="store_true", help="sobrescribir el archivo de salida si existe")
    args = parser.parse_args(argv)
    try:
        if os.path.exists(args.salida) and not args.forzar:
            raise ErrorEntrada(f"{args.salida} ya existe; usa --forzar para sobrescribirlo.")
        genesis = construir_genesis(args.lab, args.saldo, args.recompensa, args.nombre,
                                   dificultad=args.dificultad)
        carpeta = os.path.dirname(os.path.abspath(args.salida))
        os.makedirs(carpeta, exist_ok=True)
        with open(args.salida, "w", encoding="utf-8") as f:
            json.dump(genesis, f, indent=2, ensure_ascii=False)
    except ErrorEntrada as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Génesis creado en {args.salida} con {len(genesis['cuentas'])} laboratorios: {', '.join(genesis['cuentas'])}")
    print(f"Dificultad fija de la red: {genesis['parametros']['dificultad']}")
    print(f"Hash del génesis: {genesis['hash']}")
    print("Copia este archivo a todas las PCs de la red.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
