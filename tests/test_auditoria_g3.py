"""Pruebas de regresión de la auditoría con IA (grupo G3: núcleo y verificador). Una por hallazgo."""
import copy
import json

import pytest

import verificar_certificado as vc
from models.bloque import ErrorValidacion
from models.certificado import generar_certificado
from models.validacion import validar_cadena
from tests.cadena_v2 import (DOC_A, T0, Claves, crear_genesis, crear_sello, hash_bloque, minar_bloque, sha,
                             transferencia)


def genesis_con(claves, **parametros):
    """Génesis de prueba (formato de tests.cadena_v2) con parámetros adicionales, vuelto a firmar con su hash."""
    g = crear_genesis(claves)
    g["parametros"].update(parametros)
    g["hash"] = hash_bloque(g)
    return g


def tx(claves, i=1):
    return [transferencia("LAB-A", "LAB-B", 1, T0 + i, claves)]


@pytest.fixture(scope="module")
def claves():
    return {n: Claves() for n in ("LAB-A", "LAB-B", "LAB-C")}


# ---------------------------------------------------------------- AUD-004
def test_aud_004_dificultad_fija_por_el_genesis(claves):
    g = genesis_con(claves, dificultad=3)
    barato = minar_bloque(g, tx(claves), claves, "LAB-A", dificultad=1)
    with pytest.raises(ErrorValidacion, match="dificultad"):
        validar_cadena([g, barato], g["hash"])
    bueno = minar_bloque(g, tx(claves), claves, "LAB-A", dificultad=3)
    validar_cadena([g, bueno], g["hash"])


def test_aud_004_sin_parametro_se_mantiene_la_regla_antigua(claves):
    g = genesis_con(claves)
    validar_cadena([g, minar_bloque(g, tx(claves), claves, "LAB-A", dificultad=1)], g["hash"])


def test_aud_004_genesis_con_dificultad_invalida(claves):
    g = genesis_con(claves, dificultad=9)
    with pytest.raises(ErrorValidacion, match="dificultad"):
        validar_cadena([g], g["hash"])


def test_aud_004_verificador_independiente_exige_la_dificultad_del_genesis(claves):
    g = genesis_con(claves, dificultad=2)
    b1 = minar_bloque(g, [crear_sello(sha(DOC_A), claves, ["LAB-A", "LAB-B"])], claves, "LAB-A", dificultad=1)
    cert = generar_certificado([g, b1], sha(DOC_A), emitido=T0 + 100)
    r = vc.verificar(cert, DOC_A, g["hash"])
    assert not r["valido"] and "dificultad" in r["motivo"], r
    b1 = minar_bloque(g, [crear_sello(sha(DOC_A), claves, ["LAB-A", "LAB-B"])], claves, "LAB-A", dificultad=2)
    cert = generar_certificado([g, b1], sha(DOC_A), emitido=T0 + 100)
    assert vc.verificar(cert, DOC_A, g["hash"])["valido"]
