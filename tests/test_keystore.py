"""R3 · Almacén de claves: scrypt + AES-256-GCM, sin la clave privada en claro en ningún lado."""
import json
import os
import subprocess
import sys

import pytest

from models.cripto import ParClaves, verificar
from models.errores import ErrorEntrada
from models.keystore import (CONTRASENA_MIN, ErrorClave, abrir_almacen, cambiar_contrasena, crear_almacen,
                             derivar_claves, leer_publica)

CONTRASENA = "una-contrasena-larga"
OTRA = "otra-contrasena-larga"


@pytest.fixture
def ruta(tmp_path):
    return str(tmp_path / "LAB-A" / "clave.json")


@pytest.fixture
def almacen(ruta):
    publica = crear_almacen(ruta, "LAB-A", CONTRASENA)
    return ruta, publica


def _alterar(ruta, cambio):
    with open(ruta, encoding="utf-8") as f:
        doc = json.load(f)
    cambio(doc)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(doc, f)


def _voltear_hex(texto):
    return texto[:-1] + ("0" if texto[-1] != "0" else "1")


def test_crear_y_abrir_firma_con_la_misma_clave(almacen):
    ruta, publica = almacen
    par = abrir_almacen(ruta, CONTRASENA)
    assert par.publica == publica
    assert verificar(publica, b"hola", par.firmar(b"hola"))
    assert leer_publica(ruta) == ("LAB-A", publica)


def test_formato_del_archivo(almacen):
    ruta, publica = almacen
    with open(ruta, encoding="utf-8") as f:
        doc = json.load(f)
    assert doc["formato"] == "sellalo-clave" and doc["version"] == 1 and doc["id"] == "LAB-A"
    assert doc["clave_publica"] == publica
    assert doc["kdf"]["alg"] == "scrypt" and (doc["kdf"]["n"], doc["kdf"]["r"], doc["kdf"]["p"]) == (32768, 8, 1)
    assert doc["kdf"]["largo"] == 32 and len(doc["kdf"]["sal"]) == 32 and len(doc["cifrado"]["nonce"]) == 24
    assert doc["cifrado"]["alg"] == "AES-256-GCM"


def test_las_claves_son_aleatorias(tmp_path):
    a = crear_almacen(str(tmp_path / "a.json"), "LAB-A", CONTRASENA)
    b = crear_almacen(str(tmp_path / "b.json"), "LAB-A", CONTRASENA)
    assert a != b


def test_contrasena_incorrecta(almacen):
    with pytest.raises(ErrorClave, match="contraseña es incorrecta o el archivo fue alterado"):
        abrir_almacen(almacen[0], OTRA)


def _alteraciones():
    return {
        "sal": lambda d: d["kdf"].__setitem__("sal", _voltear_hex(d["kdf"]["sal"])),
        "nonce": lambda d: d["cifrado"].__setitem__("nonce", _voltear_hex(d["cifrado"]["nonce"])),
        "texto_cifrado": lambda d: d["cifrado"].__setitem__("texto_cifrado", _voltear_hex(d["cifrado"]["texto_cifrado"])),
        "id": lambda d: d.__setitem__("id", "LAB-B"),
        "clave_publica": lambda d: d.__setitem__("clave_publica", _voltear_hex(d["clave_publica"])),
        "n": lambda d: d["kdf"].__setitem__("n", 16384),
    }


@pytest.mark.parametrize("campo", list(_alteraciones()))
def test_archivo_alterado_da_el_mismo_error_que_la_contrasena_incorrecta(almacen, campo):
    ruta, _ = almacen
    with pytest.raises(ErrorClave) as incorrecta:
        abrir_almacen(ruta, OTRA)
    _alterar(ruta, _alteraciones()[campo])
    with pytest.raises(ErrorClave) as alterado:
        abrir_almacen(ruta, CONTRASENA)
    assert str(alterado.value) == str(incorrecta.value)


def test_version_desconocida(almacen):
    _alterar(almacen[0], lambda d: d.__setitem__("version", 2))
    with pytest.raises(ErrorClave, match="Versión de almacén de claves desconocida"):
        abrir_almacen(almacen[0], CONTRASENA)


@pytest.mark.parametrize("contenido", ["", "no es json", "[]", '{"formato": "otra-cosa"}'])
def test_archivo_que_no_es_un_almacen(ruta, contenido):
    os.makedirs(os.path.dirname(ruta))
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)
    with pytest.raises(ErrorClave):
        abrir_almacen(ruta, CONTRASENA)
    with pytest.raises(ErrorClave):
        leer_publica(ruta)


def test_archivo_inexistente(ruta):
    with pytest.raises(ErrorClave, match="No existe"):
        abrir_almacen(ruta, CONTRASENA)


def test_n_absurdo_se_rechaza_sin_gastar_memoria(almacen):
    _alterar(almacen[0], lambda d: d["kdf"].__setitem__("n", 2**40))
    with pytest.raises(ErrorClave):
        abrir_almacen(almacen[0], CONTRASENA)


@pytest.mark.parametrize("contrasena", ["", "corta", "a" * (CONTRASENA_MIN - 1), None, 12345])
def test_contrasena_corta_o_invalida(ruta, contrasena):
    with pytest.raises(ErrorClave):
        crear_almacen(ruta, "LAB-A", contrasena)
    assert not os.path.exists(ruta)


@pytest.mark.parametrize("nodo_id", ["", "a", "lab-a", "LAB A", "X" * 17, "LAB/../A", None])
def test_id_invalido(ruta, nodo_id):
    with pytest.raises(ErrorClave):
        crear_almacen(ruta, nodo_id, CONTRASENA)


def test_no_sobrescribe_un_almacen_existente(almacen):
    ruta, publica = almacen
    with pytest.raises(ErrorClave, match="no se sobrescribe"):
        crear_almacen(ruta, "LAB-A", OTRA)
    assert abrir_almacen(ruta, CONTRASENA).publica == publica


def test_cambiar_contrasena(almacen):
    ruta, publica = almacen
    cambiar_contrasena(ruta, CONTRASENA, "nueva-contrasena-larga")
    assert abrir_almacen(ruta, "nueva-contrasena-larga").publica == publica
    with pytest.raises(ErrorClave):
        abrir_almacen(ruta, CONTRASENA)
    assert [f for f in os.listdir(os.path.dirname(ruta)) if f.endswith(".tmp")] == []


def test_cambiar_contrasena_con_la_actual_incorrecta_o_nueva_corta(almacen):
    ruta, _ = almacen
    with open(ruta, encoding="utf-8") as f:
        antes = f.read()
    with pytest.raises(ErrorClave):
        cambiar_contrasena(ruta, "equivocada-larga", "nueva-contrasena-larga")
    with pytest.raises(ErrorClave, match="al menos"):
        cambiar_contrasena(ruta, CONTRASENA, "corta")
    with open(ruta, encoding="utf-8") as f:
        assert f.read() == antes


def test_error_clave_es_error_de_entrada():
    assert issubclass(ErrorClave, ErrorEntrada) and ErrorClave.status == 400


def test_la_privada_no_aparece_en_repr_ni_en_el_archivo(almacen):
    ruta, publica = almacen
    par = abrir_almacen(ruta, CONTRASENA)
    privada = par.bytes_privados().hex()
    assert privada not in repr(par) and privada not in str(par) and publica[:16] in repr(par)
    with open(ruta, encoding="utf-8") as f:
        contenido = f.read()
    assert privada not in contenido and CONTRASENA not in contenido


def test_par_claves_generar_y_constructor():
    a, b = ParClaves.generar(), ParClaves.generar()
    assert a.publica != b.publica
    with pytest.raises(TypeError):
        ParClaves("una semilla en texto")


def test_derivar_claves_es_reproducible_y_depende_de_contrasena_y_sal():
    a = derivar_claves(CONTRASENA, "sal-1")
    assert a.publica == derivar_claves(CONTRASENA, "sal-1").publica
    assert a.publica != derivar_claves(CONTRASENA, "sal-2").publica
    assert a.publica != derivar_claves(OTRA, "sal-1").publica
    with pytest.raises(ErrorClave):
        derivar_claves("corta", "sal-1")


def test_script_crear_identidad(tmp_path):
    salida = tmp_path / "LAB-A" / "clave.json"
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    entorno = {**os.environ, "CLAVE_PRUEBA": CONTRASENA, "PYTHONIOENCODING": "utf-8"}
    base = [sys.executable, os.path.join(raiz, "scripts", "crear_identidad.py")]
    extra = ["--salida", str(salida), "--contrasena-env", "CLAVE_PRUEBA"]

    def correr(nodo_id):
        return subprocess.run(base + [nodo_id] + extra, capture_output=True, text=True, env=entorno,
                              encoding="utf-8")

    r = correr("LAB-A")
    assert r.returncode == 0, r.stderr
    publica = abrir_almacen(str(salida), CONTRASENA).publica
    assert "LAB-A" in r.stdout and publica in r.stdout and CONTRASENA not in r.stdout
    repetido = correr("LAB-A")
    assert repetido.returncode == 1 and "no se sobrescribe" in repetido.stderr
    malo = correr("lab a")
    assert malo.returncode == 1 and "id" in malo.stderr
