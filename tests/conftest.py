import os
import sys
from functools import lru_cache

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
import models.red as modulo_red  # noqa: E402
from models.keystore import derivar_claves  # noqa: E402
from models.red import Red  # noqa: E402

CONTRASENA_PRUEBA = "contrasena-de-prueba-123"   # fixture de prueba: no protege ninguna clave real
# scrypt es lento a propósito; en las pruebas se memoriza para no recalcular las mismas claves una y otra vez.
modulo_red.derivar_claves = lru_cache(maxsize=None)(derivar_claves)


def nueva_red(consenso: str, n: int = 10, semilla: int = 7, saldo: int = 100, recompensa: int | None = None) -> Red:
    if recompensa is None:
        recompensa = 50
    return Red(consenso, n, semilla, saldo, recompensa, reproducible=True, contrasena=CONTRASENA_PRUEBA)


def minar(red: Red, bloques: int = 1, dificultad: int = 2, k: int = 200, max_rondas: int = 5000) -> None:
    """Mina de forma síncrona (sin hilo), ronda por ronda."""
    red.motor.iniciar(dificultad, k, max_rondas, bloques=bloques, pausa_ms=0, auto_transacciones=True, en_hilo=False)
    while red.motor.minando:
        red.motor.tick()


def todos_sincronizados(red: Red) -> bool:
    return len({n.ultimo_hash for n in red.nodos}) == 1


@pytest.fixture
def red_pow():
    return nueva_red("pow")


@pytest.fixture
def cliente():
    app = create_app(reproducible=True, contrasena=CONTRASENA_PRUEBA)
    app.config["TESTING"] = True
    yield app.test_client()
    for red in app.config["SIMULADOR"].redes.values():
        red.motor.detener()
