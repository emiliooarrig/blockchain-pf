"""R1 · Sellos multifirma k-de-n: formato estricto, firmas por autor, no repetición y prioridad del sello más antiguo."""
import copy

import pytest

from models.bloque import Estado, ErrorValidacion, aplicar_transacciones, crear_genesis, hash_bloque
from models.cripto import ParClaves, sha256_hex
from models.errores import ErrorEntrada
from models.merkle import raiz_transacciones
from models.multifirma import (CAMPOS_SELLO, agregar_firma, firmar_sello, firmas_validas, id_sello, mensaje_sello,
                               nuevo_sello, revisar_sello)
from models.validacion import validar_bloque, validar_cadena

IDS = ["LAB-A", "LAB-B", "LAB-C", "LAB-D", "LAB-E", "LAB-F", "LAB-G"]
DOC = sha256_hex("documento de prueba")


@pytest.fixture(scope="module")
def claves():
    return {i: ParClaves.generar() for i in IDS}


@pytest.fixture
def genesis(claves):
    cuentas = {i: {"clave_publica": c.publica, "saldo": 100} for i, c in claves.items()}
    return crear_genesis(cuentas, {"consenso": "pow", "recompensa": 50, "confirmaciones": 6}, 1.0)


@pytest.fixture
def estado(genesis):
    return Estado(genesis)


def crear(claves, autores=("LAB-A", "LAB-B", "LAB-C"), umbral=2, firman=("LAB-A", "LAB-B"), doc=DOC, ts=100.0,
          laboratorio="LAB-A", titulo="Resultados del ensayo 7"):
    tx = nuevo_sello(doc, titulo, "Dra. Pérez", laboratorio, list(autores), umbral, ts)
    for a in firman:
        tx = agregar_firma(tx, a, firmar_sello(tx, claves[a]), {i: c.publica for i, c in claves.items()})
    return tx


def publicas(claves):
    return {i: c.publica for i, c in claves.items()}


def test_dos_de_tres_valido(estado, claves):
    tx = crear(claves)
    assert len(tx["firmas"]) == 2
    assert revisar_sello(estado, tx) == id_sello(tx)
    assert firmas_validas(tx, publicas(claves)) == ["LAB-A", "LAB-B"]


def test_el_sello_no_mueve_saldos_y_registra_su_id(estado, claves):
    tx = crear(claves)
    saldos = dict(estado.saldos)
    aplicar_transacciones(estado, [tx], 1)
    assert estado.saldos == saldos and id_sello(tx) in estado.tx_ids
    assert estado.sellos[DOC][0]["numero"] == 1 and estado.sellos[DOC][0]["indice"] == 0


def test_mensaje_canonico_y_campos(claves):
    tx = crear(claves)
    assert set(CAMPOS_SELLO) == {"tipo", "doc_hash", "titulo", "investigador", "laboratorio", "autores", "umbral",
                                 "timestamp"}
    assert mensaje_sello(tx).startswith(b'{"autores":["LAB-A","LAB-B","LAB-C"],"doc_hash":"')
    assert "firmas" not in mensaje_sello(tx).decode()
    assert id_sello(tx) == sha256_hex(mensaje_sello(tx))


def test_el_id_no_depende_de_las_firmas(claves):
    uno = crear(claves, firman=("LAB-A", "LAB-B"))
    otro = crear(claves, firman=("LAB-A", "LAB-C"))
    assert id_sello(uno) == id_sello(otro)


def test_firma_de_alguien_que_no_es_autor(estado, claves):
    tx = crear(claves)
    tx["firmas"]["LAB-D"] = firmar_sello(tx, claves["LAB-D"])
    with pytest.raises(ErrorValidacion, match="firmó pero no es autor"):
        revisar_sello(estado, tx)


def test_firma_alterada(estado, claves):
    tx = crear(claves)
    f = tx["firmas"]["LAB-B"]
    tx["firmas"]["LAB-B"] = f[:-1] + ("0" if f[-1] != "0" else "1")
    with pytest.raises(ErrorValidacion, match="firma de LAB-B no corresponde"):
        revisar_sello(estado, tx)


def test_firma_de_un_autor_puesta_a_nombre_de_otro(estado, claves):
    tx = crear(claves)
    tx["firmas"]["LAB-B"] = tx["firmas"]["LAB-A"]
    with pytest.raises(ErrorValidacion, match="no corresponde"):
        revisar_sello(estado, tx)


def test_firma_reutilizada_de_otro_sello(estado, claves):
    otro = crear(claves, doc=sha256_hex("otro documento"))
    tx = crear(claves, firman=("LAB-A",))
    tx["firmas"]["LAB-B"] = otro["firmas"]["LAB-B"]
    with pytest.raises(ErrorValidacion, match="firma de LAB-B no corresponde"):
        revisar_sello(estado, tx)


def test_cambiar_el_contenido_invalida_las_firmas(estado, claves):
    tx = crear(claves)
    tx["titulo"] = "Otro título"
    with pytest.raises(ErrorValidacion, match="no corresponde"):
        revisar_sello(estado, tx)


def test_firmas_insuficientes(estado, claves):
    tx = crear(claves, firman=("LAB-A",))
    with pytest.raises(ErrorValidacion, match="sin firmas suficientes"):
        revisar_sello(estado, tx)


@pytest.mark.parametrize("umbral", [0, -1, 4, 1.5, True, "2", None])
def test_umbral_fuera_de_rango(estado, claves, umbral):
    tx = crear(claves)
    tx["umbral"] = umbral
    with pytest.raises(ErrorValidacion, match="umbral"):
        revisar_sello(estado, tx)
    with pytest.raises(ErrorEntrada, match="umbral"):
        nuevo_sello(DOC, "t", "i", "LAB-A", ["LAB-A", "LAB-B", "LAB-C"], umbral, 1.0)


def test_mas_de_cinco_autores(estado, claves):
    seis = IDS[:6]
    tx = crear(claves)
    tx["autores"] = seis
    with pytest.raises(ErrorValidacion, match="como máximo 5"):
        revisar_sello(estado, tx)
    with pytest.raises(ErrorEntrada, match="como máximo 5"):
        nuevo_sello(DOC, "t", "i", "LAB-A", seis, 2, 1.0)


def test_cinco_autores_es_valido(estado, claves):
    tx = crear(claves, autores=IDS[:5], umbral=5, firman=IDS[:5])
    revisar_sello(estado, tx)


def test_autores_repetidos_desordenados_o_inexistentes(estado, claves):
    base = crear(claves)
    casos = {
        "repetidos": ["LAB-A", "LAB-A", "LAB-B"],
        "ordenado": ["LAB-B", "LAB-A", "LAB-C"],
        "no existe": ["LAB-A", "LAB-B", "LAB-Z"],
        "vacío": [],
    }
    for nombre, autores in casos.items():
        tx = {**base, "autores": autores}
        with pytest.raises(ErrorValidacion):
            revisar_sello(estado, tx)
    with pytest.raises(ErrorEntrada, match="repetidos"):
        nuevo_sello(DOC, "t", "i", "LAB-A", ["LAB-A", "LAB-A"], 1, 1.0)


def test_nuevo_sello_ordena_los_autores(claves):
    tx = nuevo_sello(DOC, "t", "i", "LAB-C", ["LAB-C", "LAB-A", "LAB-B"], 2, 1.0)
    assert tx["autores"] == ["LAB-A", "LAB-B", "LAB-C"] and tx["firmas"] == {}


def test_laboratorio_fuera_de_autores(estado, claves):
    tx = crear(claves)
    tx["laboratorio"] = "LAB-D"
    with pytest.raises(ErrorValidacion, match="laboratorio"):
        revisar_sello(estado, tx)
    with pytest.raises(ErrorEntrada, match="laboratorio"):
        nuevo_sello(DOC, "t", "i", "LAB-D", ["LAB-A", "LAB-B"], 1, 1.0)


def test_campos_de_mas_o_de_menos(estado, claves):
    tx = crear(claves)
    con_extra = {**tx, "nota": "x"}
    sin_titulo = {k: v for k, v in tx.items() if k != "titulo"}
    sin_firmas = {k: v for k, v in tx.items() if k != "firmas"}
    for malo in (con_extra, sin_titulo, sin_firmas, "no es un objeto", None):
        with pytest.raises(ErrorValidacion):
            revisar_sello(estado, malo)


@pytest.mark.parametrize("campo,valor", [
    ("doc_hash", "abc"), ("doc_hash", DOC.upper()), ("doc_hash", 5), ("titulo", ""), ("titulo", "   "),
    ("titulo", "x" * 121), ("titulo", "con\nsalto"), ("titulo", 5), ("investigador", ""), ("investigador", "y" * 81),
    ("investigador", "a\x00b"), ("timestamp", -1), ("timestamp", "hoy"), ("timestamp", float("nan")),
    ("tipo", "otro"),
])
def test_campos_con_formato_invalido(estado, claves, campo, valor):
    tx = crear(claves)
    tx[campo] = valor
    with pytest.raises(ErrorValidacion):
        revisar_sello(estado, tx)


def test_firmas_con_tipo_incorrecto(estado, claves):
    tx = crear(claves)
    for malas in ([], "x", None, {"LAB-A": 5}):
        with pytest.raises(ErrorValidacion):
            revisar_sello(estado, {**tx, "firmas": malas})


def test_limites_de_longitud_validos(estado, claves):
    tx = crear(claves, titulo="x" * 120)
    revisar_sello(estado, tx)


def test_sello_repetido_en_el_mismo_bloque_y_entre_bloques(estado, claves):
    tx = crear(claves)
    with pytest.raises(ErrorValidacion, match="dos veces en el bloque"):
        aplicar_transacciones(estado, [tx, copy.deepcopy(tx)], 1)
    estado = Estado(estado_genesis(claves))
    aplicar_transacciones(estado, [tx], 1)
    with pytest.raises(ErrorValidacion, match="ya está en la cadena"):
        aplicar_transacciones(estado, [copy.deepcopy(tx)], 2)


def estado_genesis(claves):
    cuentas = {i: {"clave_publica": c.publica, "saldo": 100} for i, c in claves.items()}
    return crear_genesis(cuentas, {"consenso": "pow", "recompensa": 50, "confirmaciones": 6}, 1.0)


def test_mismo_documento_en_dos_sellos_gana_el_mas_antiguo(estado, claves):
    primero = crear(claves, ts=100.0)
    segundo = crear(claves, ts=101.0, autores=("LAB-C", "LAB-D"), umbral=1, firman=("LAB-D",), laboratorio="LAB-D")
    aplicar_transacciones(estado, [primero], 1)
    aplicar_transacciones(estado, [segundo], 2)
    ids = [s["id"] for s in estado.sellos[DOC]]
    assert ids == [id_sello(primero), id_sello(segundo)]
    assert [(s["numero"], s["indice"]) for s in estado.sellos[DOC]] == [(1, 0), (2, 0)]
    # dentro de un mismo bloque manda el índice
    nuevo = Estado(estado_genesis(claves))
    aplicar_transacciones(nuevo, [segundo, primero], 1)
    assert [(s["id"], s["indice"]) for s in nuevo.sellos[DOC]] == [(id_sello(segundo), 0), (id_sello(primero), 1)]


def test_copia_del_estado_no_comparte_sellos(estado, claves):
    copia = estado.copia()
    aplicar_transacciones(copia, [crear(claves)], 1)
    assert estado.sellos == {} and len(copia.sellos[DOC]) == 1
    copia2 = copia.copia()
    copia2.sellos[DOC].append({})
    assert len(copia.sellos[DOC]) == 1


def test_transferencia_y_sello_conviven(estado, claves):
    from models.bloque import nueva_transaccion
    transferencia = nueva_transaccion("LAB-A", "LAB-B", 10, 5.0, claves["LAB-A"])
    aplicar_transacciones(estado, [transferencia, crear(claves)], 1)
    assert estado.saldos["LAB-A"] == 90 and estado.saldos["LAB-B"] == 110 and len(estado.tx_ids) == 2


def test_transferencia_con_campo_tipo_se_rechaza(estado, claves):
    from models.bloque import nueva_transaccion
    tx = nueva_transaccion("LAB-A", "LAB-B", 10, 5.0, claves["LAB-A"])
    tx["tipo"] = "transferencia"
    with pytest.raises(ErrorValidacion, match="exactamente"):
        aplicar_transacciones(estado, [tx], 1)


# ---------------------------------------------------------------- recolección de firmas (fuera de la cadena)
def test_agregar_firma_valida_devuelve_copia(claves):
    tx = nuevo_sello(DOC, "t", "i", "LAB-A", ["LAB-A", "LAB-B", "LAB-C"], 2, 1.0)
    nuevo = agregar_firma(tx, "LAB-B", firmar_sello(tx, claves["LAB-B"]), publicas(claves))
    assert tx["firmas"] == {} and list(nuevo["firmas"]) == ["LAB-B"]


def test_agregar_firma_descarta_las_invalidas(claves):
    tx = nuevo_sello(DOC, "t", "i", "LAB-A", ["LAB-A", "LAB-B", "LAB-C"], 2, 1.0)
    p = publicas(claves)
    buena = firmar_sello(tx, claves["LAB-B"])
    with pytest.raises(ErrorEntrada, match="no es autor"):
        agregar_firma(tx, "LAB-D", firmar_sello(tx, claves["LAB-D"]), p)
    with pytest.raises(ErrorEntrada, match="no es válida"):
        agregar_firma(tx, "LAB-C", buena, p)                      # firma de otro autor
    with pytest.raises(ErrorEntrada, match="no es válida"):
        agregar_firma(tx, "LAB-B", buena[:-1] + ("0" if buena[-1] != "0" else "1"), p)
    with pytest.raises(ErrorEntrada, match="no es válida"):
        agregar_firma(tx, "LAB-B", "no es hex", p)
    with pytest.raises(ErrorEntrada, match="no es válida"):
        agregar_firma(tx, "LAB-B", buena, {})                     # clave pública desconocida
    assert tx["firmas"] == {}


def test_firmas_validas_ignora_las_malas(claves):
    tx = crear(claves)
    tx["firmas"]["LAB-C"] = "00" * 64
    assert firmas_validas(tx, publicas(claves)) == ["LAB-A", "LAB-B"]
    assert firmas_validas({"autores": ["LAB-A"]}, publicas(claves)) == []


# ---------------------------------------------------------------- dentro de un bloque real
def _bloque_pow(estado, claves, transacciones, proponente="LAB-A", dificultad=1):
    from models.pow import cumple_objetivo
    b = {"numero": estado.altura + 1, "timestamp": estado.ultimo_ts + 1, "transacciones": transacciones,
         "hash_anterior": estado.ultimo_hash, "raiz_merkle": raiz_transacciones(transacciones), "nonce": 0,
         "proponente": proponente, "recompensa": 50, "dificultad": dificultad}
    while not cumple_objetivo(hash_bloque(b), dificultad):
        b["nonce"] += 1
    b["hash"] = hash_bloque(b)
    b["firma_minero"] = claves[proponente].firmar(bytes.fromhex(b["hash"]))
    return b


def test_cadena_con_sellos_se_valida_y_prioriza(genesis, claves):
    estado = Estado(genesis)
    primero, segundo = crear(claves, ts=100.0), crear(claves, ts=101.0, titulo="Copia posterior")
    b1 = _bloque_pow(estado, claves, [primero])
    validar_bloque(estado, b1)
    b2 = _bloque_pow(estado, claves, [segundo], proponente="LAB-B")
    validar_bloque(estado, b2)
    final = validar_cadena([genesis, b1, b2], genesis["hash"])
    assert [(s["numero"], s["titulo"]) for s in final.sellos[DOC]] == [(1, "Resultados del ensayo 7"),
                                                                       (2, "Copia posterior")]


def test_cadena_rechaza_un_sello_con_firma_de_mas(genesis, claves):
    estado = Estado(genesis)
    malo = crear(claves)
    malo["firmas"]["LAB-D"] = firmar_sello(malo, claves["LAB-D"])
    b1 = _bloque_pow(estado, claves, [malo])
    with pytest.raises(ErrorValidacion, match="transacción 1: sello inválido"):
        validar_cadena([genesis, b1], genesis["hash"])


def test_cadena_rechaza_el_mismo_sello_en_dos_bloques(genesis, claves):
    estado = Estado(genesis)
    tx = crear(claves)
    b1 = _bloque_pow(estado, claves, [tx])
    validar_bloque(estado, b1)
    b2 = _bloque_pow(estado, claves, [copy.deepcopy(tx)])
    with pytest.raises(ErrorValidacion, match="ya está en la cadena"):
        validar_cadena([genesis, b1, b2], genesis["hash"])
