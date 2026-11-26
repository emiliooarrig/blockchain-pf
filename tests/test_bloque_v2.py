"""R2 · Bloque v2: raíz de Merkle en el encabezado, firma del minero en PoW y claves reproducibles con contraseña."""
import json

import pytest

from models import merkle
from models.bloque import EXCLUIDOS_HASH, ErrorValidacion, copiar, hash_bloque, preparar_hasher
from models.cripto import sha256_hex
from models.validacion import validar_cadena
from tests.conftest import CONTRASENA_PRUEBA, minar, nueva_red


@pytest.fixture
def cadena_pow():
    red = nueva_red("pow")
    minar(red, 2)
    return red, copiar(red.referencia().cadena)


def _validar(cadena):
    return validar_cadena(cadena, cadena[0]["hash"])


def _remina(bloque, claves):
    """Recalcula la raíz, busca otro nonce válido y vuelve a firmar (un atacante que reescribe el bloque)."""
    bloque["raiz_merkle"] = merkle.raiz_transacciones(bloque["transacciones"])
    calcular = preparar_hasher(bloque)
    nonce = 0
    while not calcular(nonce).startswith("0" * bloque["dificultad"]):
        nonce += 1
    bloque["nonce"] = nonce
    bloque["hash"] = hash_bloque(bloque)
    bloque["firma_minero"] = claves.firmar(bytes.fromhex(bloque["hash"]))


def test_el_hash_excluye_transacciones_firma_y_hash(cadena_pow):
    _, cadena = cadena_pow
    b = cadena[1]
    assert EXCLUIDOS_HASH == ("hash", "transacciones", "firma_minero")
    encabezado = {k: v for k, v in b.items() if k != "transacciones"}
    assert hash_bloque(encabezado) == b["hash"] == hash_bloque(b)
    esperado = sha256_hex(json.dumps({k: v for k, v in b.items() if k not in EXCLUIDOS_HASH}, sort_keys=True))
    assert esperado == b["hash"]


def test_preparar_hasher_coincide_con_hash_bloque(cadena_pow):
    _, cadena = cadena_pow
    b = cadena[1]
    assert preparar_hasher(b)(b["nonce"]) == b["hash"]
    assert preparar_hasher(cadena[0])(cadena[0]["nonce"]) == cadena[0]["hash"]


def test_todos_los_bloques_llevan_raiz_de_merkle(cadena_pow):
    _, cadena = cadena_pow
    assert cadena[0]["raiz_merkle"] == merkle.RAIZ_VACIA
    for b in cadena[1:]:
        assert b["raiz_merkle"] == merkle.raiz_transacciones(b["transacciones"])
        assert b["firma_minero"] and len(b["firma_minero"]) == 128
    _validar(cadena)


def test_alterar_una_transaccion_rompe_la_raiz_de_merkle(cadena_pow):
    _, cadena = cadena_pow
    cadena[1]["transacciones"][0]["monto"] += 1
    with pytest.raises(ErrorValidacion, match="raíz de Merkle no coincide"):
        _validar(cadena)


def test_quitar_o_agregar_transacciones_rompe_la_raiz(cadena_pow):
    _, cadena = cadena_pow
    extra = copiar(cadena[1]["transacciones"][0])
    cadena[1]["transacciones"].append(extra)
    with pytest.raises(ErrorValidacion, match="raíz de Merkle"):
        _validar(cadena)


def test_raiz_alterada_con_hash_recalculado_rompe_la_firma(cadena_pow):
    red, cadena = cadena_pow
    b = cadena[1]
    b["raiz_merkle"] = sha256_hex("otra raíz")
    b["hash"] = hash_bloque(b)
    with pytest.raises(ErrorValidacion, match="raíz de Merkle no coincide"):
        _validar(cadena)


def test_raiz_con_formato_invalido(cadena_pow):
    _, cadena = cadena_pow
    cadena[1]["raiz_merkle"] = "xyz"
    with pytest.raises(ErrorValidacion, match="raiz_merkle"):
        _validar(cadena)


def test_el_genesis_tambien_compromete_la_raiz(cadena_pow):
    _, cadena = cadena_pow
    cadena[0]["raiz_merkle"] = sha256_hex("falsa")
    with pytest.raises(ErrorValidacion):
        validar_cadena(cadena, cadena[0]["hash"])


def test_firma_minero_alterada(cadena_pow):
    _, cadena = cadena_pow
    f = cadena[1]["firma_minero"]
    cadena[1]["firma_minero"] = f[:-1] + ("0" if f[-1] != "0" else "1")
    with pytest.raises(ErrorValidacion, match="firma_minero inválida"):
        _validar(cadena)


def test_firma_minero_de_otro_nodo(cadena_pow):
    red, cadena = cadena_pow
    b = cadena[1]
    otro = next(n for n in red.nodos if n.id != b["proponente"])
    b["firma_minero"] = otro.claves.firmar(bytes.fromhex(b["hash"]))
    with pytest.raises(ErrorValidacion, match="firma_minero inválida"):
        _validar(cadena)


def test_firma_minero_sobre_otro_hash(cadena_pow):
    red, cadena = cadena_pow
    cadena[2]["firma_minero"] = cadena[1]["firma_minero"]
    with pytest.raises(ErrorValidacion, match="firma_minero inválida"):
        _validar(cadena)


def test_pow_sin_firma_minero(cadena_pow):
    _, cadena = cadena_pow
    del cadena[1]["firma_minero"]
    with pytest.raises(ErrorValidacion, match="faltan campos obligatorios: firma_minero"):
        _validar(cadena)


@pytest.mark.parametrize("valor", ["", "00", None, 5])
def test_firma_minero_con_formato_invalido(cadena_pow, valor):
    _, cadena = cadena_pow
    cadena[1]["firma_minero"] = valor
    with pytest.raises(ErrorValidacion, match="firma_minero inválida"):
        _validar(cadena)


def test_robar_el_bloque_cambiando_el_proponente_exige_su_clave(cadena_pow):
    red, cadena = cadena_pow
    b = cadena[1]
    original = red.nodo(b["proponente"])
    ladron = next(n for n in red.nodos if n is not original)
    b["proponente"] = ladron.id
    _remina(b, original.claves)
    with pytest.raises(ErrorValidacion, match="firma_minero inválida"):    # la firma es del minero original
        _validar(cadena[:2])
    _remina(b, ladron.claves)
    _validar(cadena[:2])                                       # el ladrón sí puede firmar su propio bloque...
    with pytest.raises(ErrorValidacion, match="hash_anterior no coincide"):
        _validar(cadena)                                       # ...pero el bloque siguiente ya no enlaza


def test_pos_lleva_raiz_de_merkle_y_se_valida():
    red = nueva_red("pos")
    for _ in range(2):
        if not red.pendientes:
            red.transaccion_aleatoria()
        red.motor.ronda_automatica()
    cadena = copiar(red.referencia().cadena)
    assert all(b["raiz_merkle"] == merkle.raiz_transacciones(b["transacciones"]) for b in cadena)
    assert all("firma_minero" not in b for b in cadena)
    _validar(cadena)
    cadena[1]["transacciones"][0]["monto"] += 1
    with pytest.raises(ErrorValidacion, match="raíz de Merkle no coincide"):
        _validar(cadena)


# ---------------------------------------------------------------- simulador con contraseña
def _publicas(red):
    return [n.claves.publica for n in red.nodos]


def test_misma_contrasena_y_semilla_dan_las_mismas_claves_y_el_mismo_genesis():
    from models.red import Red
    a = Red("pow", 10, 5, 100, 50, reproducible=True, contrasena=CONTRASENA_PRUEBA)
    b = Red("pow", 10, 5, 100, 50, reproducible=True, contrasena=CONTRASENA_PRUEBA)
    assert _publicas(a) == _publicas(b) and a.nodos[0].cadena[0]["hash"] == b.nodos[0].cadena[0]["hash"]
    assert len(set(_publicas(a))) == 10


def test_otra_contrasena_o_semilla_cambia_las_claves():
    from models.red import Red
    a = Red("pow", 10, 5, 100, 50, reproducible=True, contrasena=CONTRASENA_PRUEBA)
    assert _publicas(a) != _publicas(Red("pow", 10, 5, 100, 50, reproducible=True, contrasena="otra-contrasena-123"))
    assert _publicas(a) != _publicas(Red("pow", 10, 6, 100, 50, reproducible=True, contrasena=CONTRASENA_PRUEBA))
    assert _publicas(a) != _publicas(Red("pos", 10, 5, 100, 10, reproducible=True, contrasena=CONTRASENA_PRUEBA))


def test_sin_contrasena_las_claves_son_aleatorias():
    from models.red import Red
    a, b = Red("pow", 10, 5, 100, 50, reproducible=True), Red("pow", 10, 5, 100, 50, reproducible=True)
    assert _publicas(a) != _publicas(b)


def test_la_simulacion_con_contrasena_es_identica_bloque_a_bloque():
    a, b = nueva_red("pow", semilla=11), nueva_red("pow", semilla=11)
    minar(a, 2)
    minar(b, 2)
    assert a.referencia().cadena == b.referencia().cadena


def test_la_contrasena_no_se_filtra(cliente):
    secreta = "una-contrasena-muy-secreta"
    resp = cliente.post("/api/pow/simulacion", json={"n": 10, "semilla": 3, "contrasena": secreta})
    assert resp.status_code == 200
    estado = cliente.get("/api/pow/estado")
    assert secreta not in estado.get_data(as_text=True) and secreta not in resp.get_data(as_text=True)
    assert "contrasena" not in estado.get_json()["parametros"]
    app_sim = cliente.application.config["SIMULADOR"]
    red = app_sim.red("pow")
    assert secreta not in json.dumps(list(red.bitacora)) and secreta not in repr(red.parametros)


def test_reproducibilidad_por_la_api_con_contrasena(cliente):
    def claves():
        return [n["clave_publica"] for n in cliente.get("/api/pow/estado").get_json()["nodos"]]

    cuerpo = {"n": 10, "semilla": 9, "contrasena": "contrasena-reproducible"}
    assert cliente.post("/api/pow/simulacion", json=cuerpo).status_code == 200
    primera = claves()
    assert cliente.post("/api/pow/simulacion", json=cuerpo).status_code == 200
    assert claves() == primera
    assert cliente.post("/api/pow/simulacion", json={"n": 10, "semilla": 9}).status_code == 200
    assert claves() != primera


@pytest.mark.parametrize("valor,fragmento", [("corta", "al menos 10"), (12345678901, "texto"), ("x" * 300, "no puede pasar"),
                                             (["a"], "texto")])
def test_contrasena_invalida_por_la_api(cliente, valor, fragmento):
    antes = cliente.get("/api/pow/estado").get_json()["nodos"][0]["clave_publica"]
    resp = cliente.post("/api/pow/simulacion", json={"n": 10, "contrasena": valor})
    assert resp.status_code == 400 and fragmento in resp.get_json()["error"]
    assert str(valor) not in resp.get_json()["error"] or isinstance(valor, int)
    assert cliente.get("/api/pow/estado").get_json()["nodos"][0]["clave_publica"] == antes


def test_contrasena_vacia_equivale_a_no_enviarla(cliente):
    assert cliente.post("/api/pos/simulacion", json={"n": 10, "contrasena": ""}).status_code == 200
