"""Lectura y validación de las entradas de cada petición (JSON o formulario).

La interfaz también valida, pero el servidor nunca confía en ella: cualquier petición directa con
datos faltantes, de tipo incorrecto o fuera de rango recibe un 400 con un mensaje claro.
"""
import math

from flask import request

from models.errores import ErrorEntrada

VERDADERO = {"true", "1", "si", "sí", "on", "a_favor", "favor"}
FALSO = {"false", "0", "no", "off", "en_contra", "contra"}


def datos() -> dict:
    if request.is_json:
        cuerpo = request.get_json(silent=True)
        if cuerpo is None:
            raise ErrorEntrada("El cuerpo de la petición no es JSON válido.")
    elif request.form:
        cuerpo = request.form.to_dict()
    elif request.get_data(cache=True).strip():
        raise ErrorEntrada("Formato no soportado: envía JSON (Content-Type: application/json) o un formulario.")
    else:
        cuerpo = {}
    if not isinstance(cuerpo, dict):
        raise ErrorEntrada("Se esperaba un objeto JSON con los campos de la petición.")
    return cuerpo


def _vacio(valor) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def entero(d: dict, campo: str, nombre: str, minimo: int, maximo: int, defecto: int | None = None) -> int:
    valor = d.get(campo)
    if _vacio(valor):
        if defecto is not None:
            return defecto
        raise ErrorEntrada(f"{nombre} es obligatorio.")
    if isinstance(valor, bool):
        raise ErrorEntrada(f"{nombre} debe ser un número entero.")
    if isinstance(valor, int):
        n = valor
    elif isinstance(valor, float):
        if not math.isfinite(valor) or not valor.is_integer():
            raise ErrorEntrada(f"{nombre} debe ser un número entero (recibido: {valor}).")
        n = int(valor)
    elif isinstance(valor, str):
        texto = valor.strip()
        if len(texto) > 30:
            raise ErrorEntrada(f"{nombre} está fuera de rango.")
        try:
            n = int(texto)
        except ValueError:
            try:
                f = float(texto)
            except ValueError:
                raise ErrorEntrada(f"{nombre} debe ser numérico (recibido: «{texto[:20]}»).") from None
            if not math.isfinite(f) or not f.is_integer():
                raise ErrorEntrada(f"{nombre} debe ser un número entero (recibido: «{texto[:20]}»).") from None
            n = int(f)
    else:
        raise ErrorEntrada(f"{nombre} debe ser un número entero.")
    if n < minimo or n > maximo:
        if minimo == 1 and n <= 0:
            raise ErrorEntrada(f"{nombre} debe ser mayor que cero (recibido: {n}).")
        raise ErrorEntrada(f"{nombre} debe estar entre {minimo:,} y {maximo:,} (recibido: {n:,}).")
    return n


def texto(d: dict, campo: str, nombre: str, obligatorio: bool = True) -> str | None:
    valor = d.get(campo)
    if _vacio(valor):
        if obligatorio:
            raise ErrorEntrada(f"{nombre} es obligatorio.")
        return None
    if not isinstance(valor, str):
        raise ErrorEntrada(f"{nombre} debe ser texto.")
    return valor.strip()[:40]


def booleano(d: dict, campo: str, nombre: str, defecto: bool | None = None) -> bool:
    valor = d.get(campo)
    if _vacio(valor):
        if defecto is not None:
            return defecto
        raise ErrorEntrada(f"{nombre} es obligatorio.")
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str) and valor.strip().lower() in VERDADERO:
        return True
    if isinstance(valor, str) and valor.strip().lower() in FALSO:
        return False
    raise ErrorEntrada(f"{nombre} debe ser verdadero o falso.")


def opcion(d: dict, campo: str, nombre: str, opciones: tuple, defecto: str | None = None) -> str:
    valor = d.get(campo)
    if _vacio(valor) and defecto is not None:
        return defecto
    if not isinstance(valor, str) or valor.strip() not in opciones:
        raise ErrorEntrada(f"{nombre} debe ser una de: {', '.join(opciones)}.")
    return valor.strip()
