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


# ---------------------------------------------------------------- AUD-005
def _cert_basico(claves):
    g = genesis_con(claves, dificultad=1)
    b1 = minar_bloque(g, [crear_sello(sha(DOC_A), claves, ["LAB-A", "LAB-B"])], claves, "LAB-A", dificultad=1)
    return generar_certificado([g, b1], sha(DOC_A), emitido=T0 + 100), g


def test_aud_005_sin_genesis_esperado_no_es_valido(claves):
    cert, g = _cert_basico(claves)
    r = vc.verificar(cert, DOC_A)
    assert r["valido"] is False and r["genesis_confirmado"] is False
    assert r["concluyente"] is False and "no concluyente" in r["motivo"].lower()


def test_aud_005_con_genesis_esperado_es_valido_y_confirmado(claves):
    cert, g = _cert_basico(claves)
    r = vc.verificar(cert, DOC_A, g["hash"])
    assert r["valido"] is True and r["genesis_confirmado"] is True
    r = vc.verificar(cert, DOC_A, "ab" * 32)
    assert r["valido"] is False and r["genesis_confirmado"] is False and r["concluyente"] is True


def test_aud_005_cli_sin_genesis_sale_con_codigo_3(claves, tmp_path, capsys):
    cert, g = _cert_basico(claves)
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps(cert), encoding="utf-8")
    assert vc.main([str(ruta)]) == 3
    assert "NO CONCLUYENTE" in capsys.readouterr().out
    assert vc.main([str(ruta), "--genesis", g["hash"]]) == 0
    assert vc.main([str(ruta), "--genesis", "ab" * 32]) == 1


# ---------------------------------------------------------------- PoS: ayudas
def _forjar_bloque_pos(red, proponente, validadores, excluidos=(), castigos=(), intento=0, votantes=None):
    """Arma a mano un bloque PoS (lo que haría un proponente malicioso) con las firmas reales de sus nodos."""
    from models import merkle
    from models.bloque import hash_bloque as hb
    from models.pos import mensaje_propuesta, mensaje_voto
    from models.cripto import sha256_hex
    ref = red.referencia()
    txs = [dict(red.pendientes[0])]
    b = {"numero": ref.altura + 1, "timestamp": red.reloj(), "transacciones": txs, "hash_anterior": ref.ultimo_hash,
         "raiz_merkle": merkle.raiz_transacciones(txs), "nonce": 0, "proponente": proponente,
         "recompensa": ref.estado.params["recompensa"], "validadores": list(validadores), "intento": intento,
         "excluidos": list(excluidos), "castigos": list(castigos), "firma_proponente": "", "votos": [], "hash": ""}
    b["firma_proponente"] = red.nodo(proponente).claves.firmar(mensaje_propuesta(b))
    hp = sha256_hex(mensaje_propuesta(b))
    for v in validadores:
        if votantes is not None and v["id"] not in votantes:
            continue
        b["votos"].append({"validador": v["id"], "peso": v["apuesta"], "a_favor": True,
                           "firma": red.nodo(v["id"]).claves.firmar(mensaje_voto(hp, v["id"], True))})
    b["hash"] = hb(b)
    return b


# ---------------------------------------------------------------- AUD-006
def test_aud_006_un_solo_nodo_no_puede_ser_el_comite():
    from tests.conftest import nueva_red
    red = nueva_red("pos")
    red.crear_transaccion("N00", "N01", 5)
    b = _forjar_bloque_pos(red, "N00", [{"id": "N00", "apuesta": 1}])
    cadena = red.referencia().cadena + [b]
    with pytest.raises(ErrorValidacion, match="comité"):
        validar_cadena(cadena, cadena[0]["hash"])
    ok, motivo = red.nodo("N03").recibir_cadena(cadena)
    assert not ok


def test_aud_006_el_comite_derivado_si_se_acepta():
    from tests.conftest import nueva_red
    red = nueva_red("pos")
    red.crear_transaccion("N00", "N01", 5)
    red.motor.configurar(4, "A", 50, "firma")      # subconjunto reproducible de 4 nodos
    red.motor.ronda_automatica()
    b = red.referencia().cadena[1]
    assert len(b["validadores"]) == 4
    red.crear_transaccion("N00", "N01", 5)
    red.motor.configurar(0, "A", 50, "firma")      # todos los nodos con saldo
    red.motor.ronda_automatica()
    assert len(red.referencia().cadena[2]["validadores"]) == 10
    assert red.referencia().altura == 2


# ---------------------------------------------------------------- AUD-007
def _escenario_castigo(red):
    """Comité completo con 10 apuestas iguales: devuelve (validadores, excluido del intento 0, proponente del intento 1)."""
    from models.pos import sortear
    ref = red.referencia()
    vals = [{"id": n.id, "apuesta": 10} for n in sorted(red.nodos, key=lambda n: n.id)]
    ex = sortear(vals, ref.ultimo_hash, ref.altura + 1, 0)[0]["id"]
    restantes = [v for v in vals if v["id"] != ex]
    prop = sortear(restantes, ref.ultimo_hash, ref.altura + 1, 1)[0]["id"]
    return vals, ex, prop


def _castigo(ex, hp="ab" * 32, valor=5, **extra):
    c = {"validador": ex, "apuesta": 10, "valor_transacciones": valor, "regla": "A", "alfa_pct": 50, "monto": 10,
         "motivo": "votos insuficientes", "hash_propuesta": hp}
    c.update(extra)
    return c


def _candidato_firmado(red, vals, proponente, fraudulento: bool):
    """Candidato (sin hash ni votos) del intento 0 firmado por `proponente`; inválido si fraudulento (firma de tx rota)."""
    from models import merkle
    from models.pos import mensaje_propuesta
    ref = red.referencia()
    tx = dict(red.pendientes[0])
    if fraudulento:
        tx["firma"] = tx["firma"][:-1] + ("0" if tx["firma"][-1] != "0" else "1")
    b = {"numero": ref.altura + 1, "timestamp": red.reloj(), "transacciones": [tx], "hash_anterior": ref.ultimo_hash,
         "raiz_merkle": merkle.raiz_transacciones([tx]), "nonce": 0, "proponente": proponente,
         "recompensa": ref.estado.params["recompensa"], "validadores": vals, "intento": 0, "excluidos": [],
         "castigos": [], "firma_proponente": "", "votos": [], "hash": ""}
    b["firma_proponente"] = red.nodo(proponente).claves.firmar(mensaje_propuesta(b))
    return b


def _bloque_con_castigo(red, castigo_fn):
    vals, ex, prop = _escenario_castigo(red)
    cand = None
    from models.pos import mensaje_propuesta
    from models.cripto import sha256_hex
    candidato = _candidato_firmado(red, vals, ex, fraudulento=True)
    cand = castigo_fn(vals, ex, candidato, sha256_hex(mensaje_propuesta(candidato)))
    restantes = [v for v in vals if v["id"] != ex]
    b = _forjar_bloque_pos(red, prop, vals, excluidos=[ex], castigos=[cand], intento=1,
                           votantes={v["id"] for v in restantes})
    return b


def test_aud_007_castigo_sin_prueba_se_rechaza():
    from tests.conftest import nueva_red
    red = nueva_red("pos")
    red.crear_transaccion("N00", "N01", 5)
    b = _bloque_con_castigo(red, lambda vals, ex, cand, hp: _castigo(ex, hp))
    cadena = red.referencia().cadena + [b]
    with pytest.raises(ErrorValidacion, match="prueba"):
        validar_cadena(cadena, cadena[0]["hash"])


def test_aud_007_castigo_con_prueba_real_se_acepta():
    from tests.conftest import nueva_red
    red = nueva_red("pos")
    red.crear_transaccion("N00", "N01", 5)
    b = _bloque_con_castigo(red, lambda vals, ex, cand, hp: _castigo(ex, hp, propuesta=cand,
                                                                       valor=cand["transacciones"][0]["monto"]))
    cadena = red.referencia().cadena + [b]
    validar_cadena(cadena, cadena[0]["hash"])


def test_aud_007_la_prueba_debe_ser_invalida_y_estar_firmada_por_el_castigado():
    from tests.conftest import nueva_red
    from models.cripto import sha256_hex
    from models.pos import mensaje_propuesta
    red = nueva_red("pos")
    red.crear_transaccion("N00", "N01", 5)
    vals, ex, prop = _escenario_castigo(red)

    def con(candidato_fn):
        def f(vals, ex, _cand, _hp):
            cand = candidato_fn(vals, ex)
            return _castigo(ex, sha256_hex(mensaje_propuesta(cand)), propuesta=cand,
                            valor=cand["transacciones"][0]["monto"])
        return f
    # candidato VÁLIDO del castigado: no hay fraude que probar
    b = _bloque_con_castigo(red, con(lambda v, e: _candidato_firmado(red, v, e, fraudulento=False)))
    cadena = red.referencia().cadena + [b]
    with pytest.raises(ErrorValidacion, match="válida|fundamento"):
        validar_cadena(cadena, cadena[0]["hash"])

    # candidato inválido firmado por OTRO nodo (el acusador no puede fabricar el de la víctima)
    def firmado_por_otro(v, e):
        c = _candidato_firmado(red, v, e, fraudulento=True)
        c["firma_proponente"] = red.nodo(prop).claves.firmar(mensaje_propuesta(c))
        return c
    b = _bloque_con_castigo(red, con(firmado_por_otro))
    cadena = red.referencia().cadena + [b]
    with pytest.raises(ErrorValidacion, match="firma"):
        validar_cadena(cadena, cadena[0]["hash"])


def test_aud_007_motor_registra_la_prueba_al_rechazar():
    from tests.conftest import nueva_red
    red = nueva_red("pos")
    red.motor.configurar(0, "A", 50, "firma")
    red.crear_transaccion("N00", "N01", 20)
    red.motor.iniciar_ronda()
    red.motor.apuestas_automaticas()
    red.motor.sortear_proponente()
    malo = red.motor.ronda["proponente"]
    red.nodo(malo).deshonesto = True
    red.motor.construir_candidato()
    red.motor.votacion_automatica()
    red.motor.cerrar_votacion()
    c = red.motor.ronda["castigos"][0]
    assert c["validador"] == malo and c["propuesta"]["firma_proponente"]
    assert c["propuesta"]["hash"] == "" and c["propuesta"]["votos"] == []
    red.motor.ronda_automatica()
    bloque = red.referencia().cadena[1]
    assert bloque["castigos"][0]["propuesta"]["proponente"] == malo
    validar_cadena(red.referencia().cadena, red.referencia().cadena[0]["hash"])
