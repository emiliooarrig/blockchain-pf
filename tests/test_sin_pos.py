"""Proof of Stake se eliminó del sistema (2026-11-27): el único consenso es Proof of Work.
Estas pruebas fijan que nada de PoS sigue aceptándose ni respondiendo."""
import pytest

from models.bloque import ErrorValidacion, copiar
from models.errores import ErrorEntrada
from models.simulador import Simulador
from models.validacion import validar_bloque, validar_cadena
from tests.cadena_v2 import Claves, crear_genesis, hash_bloque
from tests.conftest import minar, nueva_red


# ---------------------------------------------------------------- API: nunca 500, mensaje claro
def test_estado_pos_responde_400_con_mensaje_claro(cliente):
    r = cliente.get("/api/pos/estado")
    assert r.status_code == 400
    assert "sólo usa Proof of Work" in r.get_json()["error"] and r.get_json()["ok"] is False


def test_simulacion_pos_responde_400_con_mensaje_claro(cliente):
    r = cliente.post("/api/pos/simulacion", json={"n": 10})
    assert r.status_code == 400
    assert "Versión desconocida «pos»" in r.get_json()["error"]


@pytest.mark.parametrize("ruta", ["/api/pos/pos/ronda", "/api/pos/pos/votar", "/api/pos/pos/config",
                                  "/api/pos/nodos/N00/deshonesto", "/api/pos/transacciones"])
def test_rutas_pos_nunca_dan_500(cliente, ruta):
    assert cliente.post(ruta, json={}).status_code in (400, 404)


@pytest.mark.parametrize("ruta", ["/api/pow/pos/ronda", "/api/pow/pos/apostar", "/api/pow/pos/votar",
                                  "/api/pow/nodos/N00/deshonesto"])
def test_rutas_pos_bajo_pow_ya_no_existen(cliente, ruta):
    assert cliente.post(ruta, json={}).status_code == 404


def test_catalogo_de_ataques_sin_casos_pos(cliente):
    cadena = {c["id"] for c in cliente.get("/api/pow/estado").get_json()["ataques"]["cadena"]}
    assert "voto_doble" not in cadena and "voto_no_validador" not in cadena


def test_el_simulador_solo_conoce_pow():
    sim = Simulador(reproducible=True)
    assert sim.red("pow").consenso == "pow"
    with pytest.raises(ErrorEntrada, match="sólo usa Proof of Work"):
        sim.red("pos")
    sim.red("pow").motor.detener()


def test_no_se_puede_crear_una_red_pos():
    from models.red import Red
    with pytest.raises(ErrorEntrada, match="pow"):
        Red("pos", 10, 1, 100, 10)


# ---------------------------------------------------------------- núcleo: génesis y bloques
def test_genesis_con_consenso_pos_se_rechaza():
    claves = {n: Claves() for n in ("LAB-A", "LAB-B")}
    g = crear_genesis(claves)
    g["parametros"]["consenso"] = "pos"
    g["hash"] = hash_bloque(g)
    with pytest.raises(ErrorValidacion, match="parámetros inválidos"):
        validar_cadena([g], g["hash"])


def test_bloque_con_campos_pos_se_rechaza_por_campos_desconocidos():
    red = nueva_red("pow")
    minar(red, 1)
    ref = red.referencia()
    bloque = copiar(ref.cadena[1])
    bloque.update({"validadores": [], "intento": 0, "excluidos": [], "castigos": [], "firma_proponente": "", "votos": []})
    bloque["hash"] = hash_bloque(bloque)
    with pytest.raises(ErrorValidacion, match="campos desconocidos: .*validadores"):
        validar_bloque(_estado_previo(ref), bloque)


def test_cadena_con_un_bloque_pos_se_rechaza():
    red = nueva_red("pow")
    minar(red, 2)
    cadena = copiar(red.referencia().cadena)
    cadena[2]["votos"] = []
    with pytest.raises(ErrorValidacion, match="campos desconocidos: votos"):
        validar_cadena(cadena, cadena[0]["hash"])


def test_bloque_pow_sin_firma_minero_ni_dificultad_no_se_acepta_como_pos():
    red = nueva_red("pow")
    minar(red, 1)
    bloque = copiar(red.referencia().cadena[1])
    for campo in ("dificultad", "firma_minero"):
        del bloque[campo]
    with pytest.raises(ErrorValidacion, match="faltan campos obligatorios"):
        validar_bloque(_estado_previo(red.referencia()), bloque)


def _estado_previo(nodo):
    """Estado de cuentas justo antes del último bloque de la cadena del nodo."""
    from models.bloque import Estado
    estado = Estado(nodo.cadena[0])
    for b in nodo.cadena[1:-1]:
        validar_bloque(estado, b)
    return estado
