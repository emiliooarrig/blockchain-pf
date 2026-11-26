"""Pruebas del nodo completo: persistencia, transacciones, minado real, recepción de bloques y cadenas."""
import json
import os
import time

import pytest

from models.bloque import hash_bloque, id_transaccion
from models.cripto import verificar
from models.errores import ErrorEntrada, ErrorEstado
from models.keystore import ErrorClave, crear_almacen
from models.multifirma import id_sello
from models.nodo_completo import MAX_PENDIENTES, NodoCompleto, trabajo
from tests import cadena_v2
from tests.laboratorios import (CONTRASENA, bloque_externo, crear_laboratorios, nuevo_nodo, rama,
                                transferencia)
from tests.laboratorios import sello as crear_sello_prueba


@pytest.fixture(scope="module")
def labs(tmp_path_factory):
    return crear_laboratorios(tmp_path_factory.mktemp("labs"))


def esperar(cond, limite=10.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def ahora():
    return time.time() - 100


@pytest.fixture
def nodo(tmp_path, labs):
    n = nuevo_nodo(tmp_path / "datos", labs)
    yield n
    n.detener_minado()


# ---------------------------------------------------------------- arranque, claves y persistencia
def test_nodo_id_inexistente(tmp_path, labs):
    with pytest.raises(ErrorEntrada, match="no existe"):
        NodoCompleto(str(tmp_path), labs[0], "LAB-Z")


def test_genesis_invalido(tmp_path, labs):
    g = json.loads(json.dumps(labs[0]))
    g["cuentas"]["LAB-A"]["saldo"] = 10**6
    with pytest.raises(ErrorEntrada, match="génesis"):
        NodoCompleto(str(tmp_path), g, "LAB-A")
    with pytest.raises(ErrorEntrada):
        NodoCompleto(str(tmp_path), {"hola": 1}, "LAB-A")


def test_clave_que_no_coincide_con_el_genesis(tmp_path, labs):
    ruta = str(tmp_path / "otra" / "clave.json")
    crear_almacen(ruta, "LAB-A", CONTRASENA)
    with pytest.raises(ErrorEntrada, match="no coincide"):
        NodoCompleto(str(tmp_path / "d"), labs[0], "LAB-A", ruta)
    with pytest.raises(ErrorEntrada, match="LAB-B"):
        NodoCompleto(str(tmp_path / "d2"), labs[0], "LAB-A", labs[1]["LAB-B"])


def test_desbloqueo_y_bloqueo(tmp_path, labs):
    n = nuevo_nodo(tmp_path, labs, desbloquear=False)
    assert not n.desbloqueado
    with pytest.raises(ErrorEstado):
        n.firmar(b"hola")
    with pytest.raises(ErrorClave):
        n.desbloquear("contrasena-equivocada")
    assert not n.desbloqueado
    n.desbloquear(CONTRASENA)
    assert verificar(n.clave_publica_de("LAB-A"), b"hola", n.firmar(b"hola"))
    n.bloquear()
    assert not n.desbloqueado
    with pytest.raises(ErrorEstado):
        n.firmar(b"hola")
    assert n.clave_publica_de("LAB-X") is None


def test_minar_bloqueado_o_sin_pendientes_o_dificultad_mala(tmp_path, labs):
    n = nuevo_nodo(tmp_path, labs, desbloquear=False)
    with pytest.raises(ErrorEstado, match="bloqueado"):
        n.iniciar_minado(1)
    n.desbloquear(CONTRASENA)
    with pytest.raises(ErrorEstado, match="pendientes"):
        n.iniciar_minado(1)
    for d in (0, 7, "2", True, None):
        with pytest.raises(ErrorEntrada):
            n.iniciar_minado(d)
    assert not n.minando


def test_persistencia_y_recarga(tmp_path, labs):
    datos = tmp_path / "d"
    n = nuevo_nodo(datos, labs)
    b1 = bloque_externo(labs, labs[0], [transferencia(labs, "LAB-C", "LAB-B", 3, ahora())])
    assert n.recibir_bloque(b1)[0] == "aceptado"
    tx = transferencia(labs, "LAB-A", "LAB-B", 5, ahora() + 1)
    n.agregar_transaccion(tx)
    assert os.path.exists(datos / "cadena.json") and os.path.exists(datos / "pendientes.json")
    otro = NodoCompleto(str(datos), labs[0], "LAB-A", labs[1]["LAB-A"])
    assert otro.altura == 1 and otro.punta == b1["hash"]
    assert otro.pendientes == [tx]
    assert otro.estado.saldos == n.estado.saldos


def test_cadena_alterada_en_disco_se_aparta(tmp_path, labs):
    datos = tmp_path / "d"
    n = nuevo_nodo(datos, labs)
    n.recibir_bloque(bloque_externo(labs, labs[0], [transferencia(labs, "LAB-C", "LAB-B", 3, ahora())]))
    ruta = datos / "cadena.json"
    cadena = json.loads(ruta.read_text(encoding="utf-8"))
    cadena[1]["transacciones"][0]["monto"] = 99
    ruta.write_text(json.dumps(cadena), encoding="utf-8")
    otro = NodoCompleto(str(datos), labs[0], "LAB-A", labs[1]["LAB-A"])
    assert otro.altura == 0
    assert any(f.startswith("cadena.json.corrupto-") for f in os.listdir(datos))
    assert any(e["tipo"] == "corrupto" for e in otro.bitacora)
    # ilegible
    ruta.write_text("{no es json", encoding="utf-8")
    assert NodoCompleto(str(datos), labs[0], "LAB-A").altura == 0


def test_pendientes_invalidos_se_descartan_al_cargar(tmp_path, labs):
    datos = tmp_path / "d"
    os.makedirs(datos)
    buena = transferencia(labs, "LAB-A", "LAB-B", 5, ahora())
    mala = {**transferencia(labs, "LAB-A", "LAB-B", 6, ahora()), "monto": 7}
    (datos / "pendientes.json").write_text(json.dumps([mala, buena, "basura", buena]), encoding="utf-8")
    n = NodoCompleto(str(datos), labs[0], "LAB-A")
    assert n.pendientes == [buena]


# ---------------------------------------------------------------- transacciones
def test_transferencia_valida_saldo_y_duplicada(nodo, labs):
    tx = transferencia(labs, "LAB-A", "LAB-B", 60, ahora())
    assert nodo.agregar_transaccion(tx) == id_transaccion(tx)
    assert "id" not in nodo.pendientes[0]
    with pytest.raises(ErrorEntrada, match="duplicada"):
        nodo.agregar_transaccion(tx)
    with pytest.raises(ErrorEntrada, match="Saldo insuficiente"):
        nodo.agregar_transaccion(transferencia(labs, "LAB-A", "LAB-C", 50, ahora() + 1))
    nodo.agregar_transaccion(transferencia(labs, "LAB-A", "LAB-C", 40, ahora() + 2))
    with pytest.raises(ErrorEntrada):
        nodo.agregar_transaccion({**tx, "firma": "00" * 64})
    with pytest.raises(ErrorEntrada):
        nodo.agregar_transaccion("no es una tx")
    with pytest.raises(ErrorEntrada):
        nodo.agregar_transaccion({"emisor": 3})
    assert len(nodo.pendientes) == 2


def test_sello_completo_e_incompleto(nodo, labs):
    h = cadena_v2.sha(b"doc")
    completo = crear_sello_prueba(labs, h)
    assert nodo.agregar_transaccion(completo) == id_sello(completo)
    with pytest.raises(ErrorEntrada, match="firmas suficientes"):
        nodo.agregar_transaccion(crear_sello_prueba(labs, h, firmantes=("LAB-A",), ts=ahora()))
    with pytest.raises(ErrorEntrada, match="duplicada"):
        nodo.agregar_transaccion(completo)
    assert len(nodo.pendientes) == 1


def test_maximo_de_pendientes(nodo, labs):
    for i in range(MAX_PENDIENTES):
        nodo.agregar_transaccion(crear_sello_prueba(labs, cadena_v2.sha(str(i).encode()), ts=ahora() + i))
    with pytest.raises(ErrorEstado, match="llena"):
        nodo.agregar_transaccion(crear_sello_prueba(labs, cadena_v2.sha(b"extra")))


def test_callbacks_y_origen(nodo, labs):
    vistos = []
    nodo.al_cambiar.append(lambda tipo, dato: vistos.append(tipo))
    nodo.agregar_transaccion(transferencia(labs, "LAB-A", "LAB-B", 1, ahora()))
    nodo.agregar_transaccion(transferencia(labs, "LAB-A", "LAB-B", 2, ahora() + 1), origen="LAB-B")
    assert vistos == ["tx", "tx_recibida"]
    nodo.al_cambiar.append(lambda t, d: 1 / 0)      # un callback roto no afecta al nodo
    nodo.agregar_transaccion(transferencia(labs, "LAB-A", "LAB-B", 3, ahora() + 2))


# ---------------------------------------------------------------- minado real
def test_minado_de_un_bloque_y_recompensa(nodo, labs):
    vistos = []
    nodo.al_cambiar.append(lambda tipo, dato: vistos.append((tipo, dato)))
    tx = transferencia(labs, "LAB-A", "LAB-B", 5, ahora())
    nodo.agregar_transaccion(tx)
    nodo.iniciar_minado(2)
    assert esperar(lambda: nodo.altura == 1 and not nodo.minando)
    b = nodo.cadena[1]
    assert b["proponente"] == "LAB-A" and b["transacciones"] == [tx] and b["hash"].startswith("00")
    assert b["hash"] == hash_bloque(b)
    assert verificar(nodo.clave_publica_de("LAB-A"), bytes.fromhex(b["hash"]), b["firma_minero"])
    assert ("bloque", b) in vistos
    assert nodo.pendientes == []
    est = nodo.publico()["estadisticas"]
    assert est["intentos"] >= 1 and est["bloques_minados"] == 1
    cuenta = {c["id"]: c for c in nodo.publico()["cuentas"]}
    assert cuenta["LAB-A"]["pendiente_recompensa"] == 10 and cuenta["LAB-A"]["saldo"] == 95
    # 6 confirmaciones: con 6 bloques más encima la recompensa se acredita
    prev = b
    for i in range(6):
        prev = bloque_externo(labs, prev, [transferencia(labs, "LAB-C", "LAB-B", 1, ahora() + 10 + i)])
        assert nodo.recibir_bloque(prev)[0] == "aceptado"
        cuenta = {c["id"]: c for c in nodo.publico()["cuentas"]}
        if i < 5:
            assert cuenta["LAB-A"]["pendiente_recompensa"] == 10
    assert cuenta["LAB-A"]["pendiente_recompensa"] == 0 and cuenta["LAB-A"]["saldo"] == 105


def test_minado_continuo_espera_y_se_detiene(nodo, labs):
    nodo.iniciar_minado(1, continuo=True)
    with pytest.raises(ErrorEstado, match="en curso"):
        nodo.iniciar_minado(1)
    time.sleep(0.2)
    assert nodo.minando and nodo.altura == 0
    nodo.agregar_transaccion(crear_sello_prueba(labs, cadena_v2.sha(b"x")))
    assert esperar(lambda: nodo.altura == 1)
    nodo.agregar_transaccion(crear_sello_prueba(labs, cadena_v2.sha(b"y"), ts=ahora() + 1))
    assert esperar(lambda: nodo.altura == 2)
    nodo.detener_minado()
    assert not nodo.minando


def test_bloquear_detiene_el_minado(nodo):
    nodo.iniciar_minado(1, continuo=True)
    nodo.bloquear()
    assert not nodo.minando and not nodo.desbloqueado


def test_bloque_de_otro_reinicia_la_plantilla(nodo, labs):
    nodo.agregar_transaccion(transferencia(labs, "LAB-A", "LAB-B", 1, ahora()))
    nodo.iniciar_minado(6)     # tan difícil que no lo encuentra: sólo reinicia si cambia la punta
    time.sleep(0.2)
    assert nodo.minando
    b1 = bloque_externo(labs, labs[0], [transferencia(labs, "LAB-C", "LAB-B", 3, ahora())])
    assert nodo.recibir_bloque(b1)[0] == "aceptado"
    assert esperar(lambda: nodo.publico()["estadisticas"]["bloque"] == 2)
    nodo.detener_minado()
    assert not nodo.minando


# ---------------------------------------------------------------- recibir_bloque
def test_recibir_bloque_aceptado_duplicado_sincronizar(nodo, labs):
    cadena = rama(labs, [[transferencia(labs, "LAB-C", "LAB-B", i + 1, ahora() + i)] for i in range(3)])
    vistos = []
    nodo.al_cambiar.append(lambda t, d: vistos.append(t))
    assert nodo.recibir_bloque(cadena[3], de="LAB-B")[0] == "sincronizar"
    assert nodo.altura == 0
    assert nodo.recibir_bloque(cadena[1])[0] == "aceptado"
    assert nodo.recibir_bloque(cadena[1])[0] == "duplicado"
    assert nodo.recibir_bloque(cadena[2])[0] == "aceptado"
    assert nodo.recibir_bloque(cadena[1])[0] == "duplicado"
    assert nodo.altura == 2 and vistos == ["bloque_recibido"] * 2
    # una rama alterna de la misma altura no es una falta
    alterna = bloque_externo(labs, cadena[1], [transferencia(labs, "LAB-C", "LAB-A", 9, ahora() + 9)], "LAB-C")
    assert nodo.recibir_bloque(alterna)[0] in ("duplicado", "sincronizar")


def test_recibir_bloque_quita_pendientes_incluidas(nodo, labs):
    tx = transferencia(labs, "LAB-C", "LAB-B", 4, ahora())
    nodo.agregar_transaccion(tx)
    otra = transferencia(labs, "LAB-A", "LAB-B", 4, ahora() + 1)
    nodo.agregar_transaccion(otra)
    assert nodo.recibir_bloque(bloque_externo(labs, labs[0], [tx]))[0] == "aceptado"
    assert nodo.pendientes == [otra]


def test_recibir_bloque_rechazos(nodo, labs):
    g = labs[0]
    tx = transferencia(labs, "LAB-C", "LAB-B", 4, ahora())
    bueno = bloque_externo(labs, g, [tx])

    alterado = {**bueno, "nonce": bueno["nonce"] + 1}                          # el hash ya no coincide
    assert nodo.recibir_bloque(alterado)[0] == "rechazado"

    merkle = {**bueno, "transacciones": [transferencia(labs, "LAB-C", "LAB-B", 5, ahora())]}
    assert nodo.recibir_bloque(merkle)[0] == "rechazado"

    ajeno = {**bueno, "firma_minero": labs[2]["LAB-C"].firmar(bytes.fromhex(bueno["hash"]))}
    estado, motivo = nodo.recibir_bloque(ajeno)
    assert estado == "rechazado" and "firma_minero" in motivo

    futuro = bloque_externo(labs, {**g, "timestamp": time.time() + 1000}, [tx])
    estado, motivo = nodo.recibir_bloque(futuro)
    assert estado == "rechazado" and "futuro" in motivo

    for basura in (None, 5, {}, {"hash": 3}, {"hash": "a" * 64, "numero": "x"}):
        assert nodo.recibir_bloque(basura)[0] == "rechazado"
    assert nodo.altura == 0
    assert nodo.recibir_bloque(bueno)[0] == "aceptado"


def test_bloque_lejano_alterado_no_pide_sincronizar(nodo, labs):
    cadena = rama(labs, [[transferencia(labs, "LAB-C", "LAB-B", i + 1, ahora() + i)] for i in range(2)])
    alterado = {**cadena[2], "nonce": cadena[2]["nonce"] + 1}
    assert nodo.recibir_bloque(alterado)[0] == "rechazado"


# ---------------------------------------------------------------- recibir_cadena
def _tx(labs, monto, k=0, emisor="LAB-C"):
    return transferencia(labs, emisor, "LAB-B", monto, ahora() + k)


def test_cadena_con_mas_trabajo_se_adopta_y_con_menos_no(tmp_path, labs):
    n = nuevo_nodo(tmp_path, labs)
    larga = rama(labs, [[_tx(labs, 1)], [_tx(labs, 2, 1)]])             # trabajo 32
    fuerte = rama(labs, [[_tx(labs, 3, 2)]], dificultad=2)              # trabajo 256, más corta
    assert trabajo(larga) == 32 and trabajo(fuerte) == 256
    assert n.recibir_cadena(larga) == (True, "adoptada")
    assert n.altura == 2 and n.resumen()["trabajo"] == 32
    assert not n.recibir_cadena(larga)[0]
    assert n.recibir_cadena(fuerte)[0] and n.altura == 1 and n.resumen()["trabajo"] == 256
    ok, motivo = n.recibir_cadena(larga)
    assert not ok and "menos trabajo" in motivo
    assert n.punta == fuerte[-1]["hash"]


def test_cadenas_invalidas_no_lanzan(nodo, labs):
    buena = rama(labs, [[_tx(labs, 1)]])
    rota = json.loads(json.dumps(buena))
    rota[1]["transacciones"][0]["monto"] = 50
    for mala in (None, [], "x", [1, 2], rota, buena[1:], [labs[0], {"a": 1}]):
        ok, motivo = nodo.recibir_cadena(mala)
        assert not ok and motivo
    ajena = json.loads(json.dumps(buena))
    ajena[0]["nombre"] = "x"
    assert not nodo.recibir_cadena(ajena)[0]
    assert nodo.altura == 0


def test_empate_gana_la_punta_con_hash_menor(tmp_path, labs):
    x = rama(labs, [[_tx(labs, 1)]], proponente="LAB-A")
    y = rama(labs, [[_tx(labs, 2)]], proponente="LAB-B")
    menor, mayor = sorted((x, y), key=lambda c: c[-1]["hash"])
    n1 = nuevo_nodo(tmp_path / "1", labs)
    assert n1.recibir_cadena(mayor)[0] and n1.recibir_cadena(menor)[0] and n1.punta == menor[-1]["hash"]
    n2 = nuevo_nodo(tmp_path / "2", labs)
    assert n2.recibir_cadena(menor)[0]
    ok, motivo = n2.recibir_cadena(mayor)
    assert not ok and "hash mayor" in motivo and n2.punta == menor[-1]["hash"]
    # el bloque rival de la misma altura con hash menor provoca sincronización; con hash mayor, no
    assert n1.recibir_bloque(mayor[1])[0] == "duplicado"
    assert n2.recibir_bloque(mayor[1])[0] == "duplicado"
    n3 = nuevo_nodo(tmp_path / "3", labs)
    n3.recibir_cadena(mayor)
    assert n3.recibir_bloque(menor[1])[0] == "sincronizar"


def test_reorganizacion_devuelve_pendientes(tmp_path, labs):
    n = nuevo_nodo(tmp_path, labs)
    perdida_tx = _tx(labs, 7)
    assert n.recibir_cadena(rama(labs, [[perdida_tx]]))[0] and n.pendientes == []
    comun = _tx(labs, 2, 5)
    ganadora = rama(labs, [[comun], [_tx(labs, 3, 6)]], proponente="LAB-A")
    n.agregar_transaccion(comun)             # estaba pendiente y la nueva cadena la incluye
    assert n.recibir_cadena(ganadora)[0]
    assert n.altura == 2
    assert n.pendientes == [perdida_tx]      # la de la rama perdida volvió; la ya incluida se quitó
    assert n.estado.saldos["LAB-C"] == 100 - 2 - 3


def test_reorganizacion_descarta_pendientes_ya_invalidas(tmp_path, labs):
    n = nuevo_nodo(tmp_path, labs)
    assert n.recibir_cadena(rama(labs, [[_tx(labs, 90)]]))[0]      # LAB-C gasta 90 en la rama que se perderá
    ganadora = rama(labs, [[_tx(labs, 80, 1)], [_tx(labs, 1, 2, "LAB-A")]], proponente="LAB-A")
    assert n.recibir_cadena(ganadora)[0]
    assert n.pendientes == []                               # a LAB-C ya sólo le quedan 20


# ---------------------------------------------------------------- consultas
def test_prioridad_devuelve_primero_el_sello_mas_antiguo(tmp_path):
    cadena, _ = cadena_v2.construir_cadena()
    n = NodoCompleto(str(tmp_path), cadena[0], "LAB-A")
    assert n.recibir_cadena(cadena)[0]
    p = n.prioridad(cadena_v2.sha(cadena_v2.DOC_A))
    assert [s["numero"] for s in p] == [2, 3] and p[0]["prioritario"] and not p[1]["prioritario"]
    assert p[0]["titulo"] == "Primer sello" and p[0]["confirmaciones"] == 2 and p[0]["confirmado"] is False
    assert p[0]["fecha_bloque"] == cadena[2]["timestamp"]
    assert n.prioridad(cadena_v2.sha(cadena_v2.DOC_NO_SELLADO)) == []
    assert n.prioridad(5) == []


def test_publico_no_filtra_secretos(nodo, labs):
    nodo.agregar_transaccion(transferencia(labs, "LAB-A", "LAB-B", 1, ahora()))
    nodo.agregar_transaccion(crear_sello_prueba(labs, cadena_v2.sha(b"d")))
    nodo.evento("prueba", "hola")
    pub = nodo.publico()
    texto = json.dumps(pub)
    assert CONTRASENA not in texto and labs[2]["LAB-A"].bytes_privados().hex() not in texto
    assert pub["id"] == "LAB-A" and pub["desbloqueado"] is True and len(pub["pendientes"]) == 2
    assert {c["id"] for c in pub["cuentas"]} == {"LAB-A", "LAB-B", "LAB-C"}
    assert pub["bitacora"][-1]["texto"] == "hola" and pub["ultimos_bloques"][0]["numero"] == 0
    assert nodo.bloques_desde(1) == [] and nodo.bloques_desde(0, 5) == []
