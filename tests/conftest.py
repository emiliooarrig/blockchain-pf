import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models.red import Red  # noqa: E402


def nueva_red(consenso: str, n: int = 10, semilla: int = 7, saldo: int = 100, recompensa: int | None = None) -> Red:
    if recompensa is None:
        recompensa = 50 if consenso == "pow" else 10
    return Red(consenso, n, semilla, saldo, recompensa, reproducible=True)


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
def red_pos():
    return nueva_red("pos")


@pytest.fixture
def cliente():
    app = create_app(reproducible=True)
    app.config["TESTING"] = True
    yield app.test_client()
    for red in app.config["SIMULADOR"].redes.values():
        red.motor.detener()
