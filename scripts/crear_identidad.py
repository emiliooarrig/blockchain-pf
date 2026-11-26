"""Crea el almacén de claves cifrado de un nodo Sellalo.

Uso:
    python scripts/crear_identidad.py LAB-A --salida data/LAB-A/clave.json
    python scripts/crear_identidad.py LAB-A --salida data/LAB-A/clave.json --contrasena-env SELLALO_CLAVE

Sólo se muestran el id y la clave pública; la clave privada queda cifrada en el archivo.
"""
import argparse
import getpass
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.errores import ErrorEntrada  # noqa: E402
from models.keystore import CONTRASENA_MIN, crear_almacen  # noqa: E402

ID_VALIDO = re.compile(r"^[A-Z0-9-]{2,16}$")


def _pedir_contrasena(variable: str | None) -> str:
    if variable:
        valor = os.environ.get(variable)
        if not valor:
            raise ErrorEntrada(f"La variable de entorno {variable} no existe o está vacía.")
        return valor
    primera = getpass.getpass(f"Contraseña (mínimo {CONTRASENA_MIN} caracteres): ")
    if getpass.getpass("Repite la contraseña: ") != primera:
        raise ErrorEntrada("Las contraseñas no coinciden.")
    return primera


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crea la identidad (par de claves cifrado) de un nodo Sellalo.")
    parser.add_argument("id", help="id del nodo: 2 a 16 caracteres, mayúsculas, números y guiones (p. ej. LAB-A)")
    parser.add_argument("--salida", required=True, help="ruta del archivo de claves (p. ej. data/LAB-A/clave.json)")
    parser.add_argument("--contrasena-env", metavar="VAR", help="leer la contraseña de esta variable de entorno")
    args = parser.parse_args(argv)
    try:
        if not ID_VALIDO.fullmatch(args.id):
            raise ErrorEntrada("El id debe tener de 2 a 16 caracteres: letras mayúsculas, números y guiones.")
        contrasena = _pedir_contrasena(args.contrasena_env)
        publica = crear_almacen(args.salida, args.id, contrasena)
    except ErrorEntrada as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Identidad creada en {args.salida}")
    print(f"  id:            {args.id}")
    print(f"  clave pública: {publica}")
    print("Guarda la contraseña: sin ella la clave no se puede recuperar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
