"""Sección 5 · Cadena: bloque con hash o hash_anterior alterado; cadena recibida más corta o inválida;
manipular un bloque intermedio y verificar que la cadena completa se rechaza."""
import pytest

from models import ataques
from models.bloque import ErrorValidacion, copiar, hash_bloque
from models.validacion import validar_cadena
from tests.conftest import minar, nueva_red


@pytest.fixture(params=["pow", "pos"])
def red_con_bloques(request):
    red = nueva_red(request.param)
    if red.consenso == "pow":
        minar(red, 4)
    else:
        for _ in range(4):
            if not red.pendientes:
                red.transaccion_aleatoria()
            red.motor.ronda_automatica()
    assert red.referencia().altura == 4
    return red


def _tips(red):
    return [n.ultimo_hash for n in red.nodos]


def test_cadena_completa_valida_en_todos_los_nodos(red_con_bloques):
    for n in red_con_bloques.nodos:
        estado = validar_cadena(n.cadena, n.cadena[0]["hash"])
        assert estado.altura == 4


@pytest.mark.parametrize("tipo,motivo", [
    ("hash_alterado", "el hash no coincide"),
    ("hash_anterior_alterado", "hash_anterior no coincide"),
    ("cadena_corta", "no es más larga"),
    ("cadena_mal_formada", "faltan campos"),
    ("bloque_intermedio", "bloque #"),
])
def test_cadenas_manipuladas_se_rechazan_y_nadie_cambia(red_con_bloques, tipo, motivo):
    red = red_con_bloques
    antes = _tips(red)
    r = ataques.atacar_cadena(red, tipo, "N09")
    assert r["rechazado"], r["mensaje"]
    assert motivo in r["mensaje"]
    assert _tips(red) == antes


def test_hash_alterado_en_validar_cadena(red_con_bloques):
    cadena = copiar(red_con_bloques.referencia().cadena)
    cadena[2]["hash"] = "f" * 64
    with pytest.raises(ErrorValidacion, match="bloque #2: el hash no coincide"):
        validar_cadena(cadena, cadena[0]["hash"])


def test_bloque_intermedio_rompe_toda_la_cadena(red_con_bloques):
    """Se modifica el bloque 2 y se recalcula su hash: el bloque 3 deja de enlazar (o falla la firma/PoW)."""
    cadena = copiar(red_con_bloques.referencia().cadena)
    cadena[2]["transacciones"][0]["monto"] += 1
    cadena[2]["hash"] = hash_bloque(cadena[2])
    with pytest.raises(ErrorValidacion, match="bloque #2"):
        validar_cadena(cadena, cadena[0]["hash"])
    cadena[3]["hash_anterior"] = cadena[2]["hash"]          # ni reenlazando el siguiente se salva
    cadena[3]["hash"] = hash_bloque(cadena[3])
    with pytest.raises(ErrorValidacion):
        validar_cadena(cadena, cadena[0]["hash"])


def test_bloque_intermedio_reminado_en_pow_rompe_el_enlace():
    red = nueva_red("pow")
    minar(red, 4)
    r = ataques.atacar_cadena(red, "bloque_intermedio", "N05")
    assert r["rechazado"] and "bloque #3: hash_anterior no coincide" in r["mensaje"]


def test_cadena_mas_corta_pero_valida(red_con_bloques):
    nodo = red_con_bloques.nodos[0]
    ok, motivo = nodo.recibir_cadena(nodo.cadena[:-1])
    assert not ok and "no es más larga" in motivo
    assert nodo.altura == 4


@pytest.mark.parametrize("basura", [None, [], "cadena", 42, [{"numero": 0}], [[1, 2]], [{}]])
def test_cadena_invalida_o_mal_formada(red_pow, basura):
    nodo = red_pow.nodos[0]
    ok, motivo = nodo.recibir_cadena(basura)
    assert not ok and motivo
    assert nodo.altura == 0


def test_cadena_de_otra_red_se_rechaza(red_pow):
    otra = nueva_red("pow", semilla=999)
    minar(otra, 2)
    ok, motivo = red_pow.nodos[0].recibir_cadena(otra.nodos[0].cadena)
    assert not ok and "génesis" in motivo


def test_genesis_alterado(red_pow):
    cadena = copiar(red_pow.nodos[0].cadena)
    cadena[0]["cuentas"]["N00"]["saldo"] = 10**6
    cadena[0]["hash"] = hash_bloque(cadena[0])
    with pytest.raises(ErrorValidacion, match="génesis"):
        validar_cadena(cadena, red_pow.nodos[0].cadena[0]["hash"])


def test_bloque_con_campo_extra_o_faltante(red_con_bloques):
    cadena = copiar(red_con_bloques.referencia().cadena)
    cadena[1]["extra"] = 1
    with pytest.raises(ErrorValidacion, match="campos desconocidos"):
        validar_cadena(cadena, cadena[0]["hash"])
    cadena = copiar(red_con_bloques.referencia().cadena)
    del cadena[1]["proponente"]
    with pytest.raises(ErrorValidacion, match="faltan campos"):
        validar_cadena(cadena, cadena[0]["hash"])


def test_bloque_sin_transacciones_se_rechaza(red_pow):
    from models.pow import cumple_objetivo
    from models.bloque import preparar_hasher
    tope = red_pow.referencia().cadena[-1]
    b = {"numero": 1, "timestamp": red_pow.reloj(), "transacciones": [], "hash_anterior": tope["hash"], "nonce": 0,
         "proponente": "N01", "recompensa": 50, "dificultad": 1}
    calc = preparar_hasher(b)
    b["nonce"] = next(i for i in range(10_000) if cumple_objetivo(calc(i), 1))
    b["hash"] = hash_bloque(b)
    ok, motivo = red_pow.nodos[0].recibir_cadena(red_pow.nodos[0].cadena + [b])
    assert not ok and "no contiene transacciones" in motivo
