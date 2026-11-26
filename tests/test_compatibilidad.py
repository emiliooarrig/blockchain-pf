"""El núcleo y el verificador independiente deben coincidir byte a byte (contratos C1–C3, C6)."""
import verificar_certificado as vc
from models.certificado import generar_certificado
from models.validacion import validar_cadena
from tests.cadena_v2 import DOC_A, construir_cadena, sha
from tests.conftest import minar, nueva_red


def test_el_nucleo_acepta_la_cadena_construida_segun_los_contratos():
    cadena, _ = construir_cadena(2)
    estado = validar_cadena(cadena, cadena[0]["hash"])
    assert estado.altura == 4
    prioridad = estado.sellos[sha(DOC_A)]
    assert [s["numero"] for s in prioridad] == [2, 3]


def test_el_verificador_acepta_los_encabezados_minados_por_el_nucleo():
    red = nueva_red("pow")
    minar(red, bloques=3, dificultad=2)
    cadena = red.referencia().cadena
    cert = {"formato": "sellalo-certificado", "version": 1, "emitido": 0.0, "doc_hash": "0" * 64, "sello": {},
            "prueba_merkle": {}, "numero_bloque": 1, "genesis": cadena[0],
            "encabezados": [{k: v for k, v in b.items() if k != "transacciones"} for b in cadena[1:]]}
    resultado = vc.verificar(cert)
    # génesis y encabezados pasan; sólo falla el sello vacío puesto a propósito
    assert not resultado["valido"] and "sello" in resultado["motivo"]


def test_certificado_de_una_cadena_validada_por_el_nucleo():
    cadena, _ = construir_cadena(1)
    validar_cadena(cadena, cadena[0]["hash"])
    assert vc.verificar(generar_certificado(cadena, sha(DOC_A)), documento=DOC_A)["valido"]
