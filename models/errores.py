"""Errores que el núcleo comunica a la interfaz con un mensaje claro."""


class ErrorEntrada(Exception):
    """Dato de entrada inválido (HTTP 400)."""
    status = 400


class ErrorEstado(ErrorEntrada):
    """Acción válida pero no permitida en el estado actual de la simulación (HTTP 409)."""
    status = 409
