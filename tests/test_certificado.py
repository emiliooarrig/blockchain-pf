import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

import verificar_certificado as vc
from models.certificado import generar_certificado, resumen_certificado
from models.errores import ErrorEntrada
from tests.cadena_v2 import DOC_A, DOC_B, DOC_NO_SELLADO, construir_cadena, crear_sello, mensaje_sello, sha

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def mundo():
    cadena, claves = construir_cadena(dificultad=2)
    return cadena, claves


@pytest.fixture
def cert(mundo):
    return generar_certificado(mundo[0], sha(DOC_A), emitido=1767300000.0)


def rechaza(cert, fragmento, **kw):
    r = vc.verificar(cert, **kw)
    assert not r["valido"]
    assert fragmento in r["motivo"], r["motivo"]


def test_valido(cert):
    r = vc.verificar(cert, DOC_A)
    assert r["valido"], r["motivo"]
    assert r["detalle"]["bloque"] == 2 and r["detalle"]["titulo"] == "Primer sello"
    assert r["detalle"]["documento_comprobado"]


def test_sin_documento_valido(cert):
    assert vc.verificar(cert)["valido"]


def test_documento_distinto(cert):
    rechaza(cert, "documento no coincide", documento=DOC_A[:-1] + b"X")


def test_firma_autor_alterada(cert):
    cert["sello"]["firmas"]["LAB-A"] = "00" * 64
    rechaza(cert, "firma de LAB-A")


def test_solo_una_firma(cert):
    del cert["sello"]["firmas"]["LAB-B"]
    rechaza(cert, "umbral exige 2")


def test_firma_de_no_autor(mundo):
    cadena, claves = mundo
    # sello con autores A,B; C firma sin ser autor
    tx = crear_sello(sha(b"otro"), claves, ["LAB-A", "LAB-B"], autores=("LAB-A", "LAB-B"))
    tx["firmas"]["LAB-C"] = claves["LAB-C"].firmar(mensaje_sello(tx))
    cert = _cert_con_sello(mundo, tx)
    rechaza(cert, "LAB-C, que no es autor")


def _cert_con_sello(mundo, tx):
    """Cadena nueva cuyo bloque 1 contiene `tx`."""
    from tests.cadena_v2 import crear_genesis, minar_bloque
    _, claves = mundo
    g = crear_genesis(claves)
    b1 = minar_bloque(g, [tx], claves, "LAB-A", 1)
    return generar_certificado([g, b1], tx["doc_hash"], emitido=1.0)


def test_camino_merkle_alterado(cert):
    cert["prueba_merkle"]["camino"][0]["hash"] = "ab" * 32
    rechaza(cert, "prueba de Merkle")


def test_sello_alterado(cert):
    cert["sello"]["titulo"] = "Otro titulo"
    rechaza(cert, "firma de")


def test_encabezado_nonce_alterado(cert):
    cert["encabezados"][1]["nonce"] += 1
    rechaza(cert, "bloque 2 no coincide")


def test_encabezado_hash_anterior_alterado(cert):
    cert["encabezados"][2]["hash_anterior"] = "11" * 32
    rechaza(cert, "bloque 3")


def test_firma_minero_alterada(cert):
    cert["encabezados"][0]["firma_minero"] = "00" * 64
    rechaza(cert, "firma del minero del bloque 1")


def test_genesis_alterado(cert):
    cert["genesis"]["parametros"]["nombre"] = "falso"
    rechaza(cert, "génesis")


def test_genesis_esperado(cert):
    g = cert["genesis"]["hash"]
    assert vc.verificar(cert, genesis_esperado=g)["valido"]
    rechaza(cert, "no es el esperado", genesis_esperado="ab" * 32)


def test_version_desconocida(cert):
    cert["version"] = 99
    rechaza(cert, "versión")


def test_formato_desconocido(cert):
    cert["formato"] = "otro"
    rechaza(cert, "formato")


def test_basura_no_lanza():
    for x in (None, [], {"formato": "sellalo-certificado", "version": 1}, "texto"):
        assert not vc.verificar(x)["valido"]


def test_elige_sello_mas_antiguo(mundo, cert):
    assert cert["numero_bloque"] == 2 and cert["sello"]["titulo"] == "Primer sello"
    assert cert["prueba_merkle"]["indice"] == 1


def test_no_sellado(mundo):
    with pytest.raises(ErrorEntrada, match="no está sellado"):
        generar_certificado(mundo[0], sha(DOC_NO_SELLADO))


def test_hash_invalido(mundo):
    with pytest.raises(ErrorEntrada):
        generar_certificado(mundo[0], "xyz")


def test_confirmaciones_y_resumen(mundo):
    cadena, _ = mundo
    c = generar_certificado(cadena, sha(DOC_B))
    assert c["numero_bloque"] == 3
    assert vc.verificar(c)["detalle"]["confirmaciones"] == 1
    r = resumen_certificado(c)
    assert r["confirmaciones"] == 1 and r["bloque"] == 3 and r["umbral"] == 2
    assert r["laboratorio"] == "LAB-B" and r["fecha"].endswith("Z")
    assert len(c["encabezados"]) == 4 and all("transacciones" not in h for h in c["encabezados"])


def test_certificado_serializable(cert):
    assert vc.verificar(json.loads(json.dumps(cert)), DOC_A)["valido"]


def _cli(tmp_path, cert, *args, doc=None, texto=None):
    ruta = tmp_path / "cert.json"
    ruta.write_text(texto if texto is not None else json.dumps(cert), encoding="utf-8")
    cmd = [sys.executable, str(RAIZ / "verificar_certificado.py"), str(ruta), *args]
    if doc is not None:
        d = tmp_path / "doc.bin"
        d.write_bytes(doc)
        cmd += ["--documento", str(d)]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=tmp_path)


def test_cli_valido(tmp_path, cert):
    p = _cli(tmp_path, cert, "--genesis", cert["genesis"]["hash"], doc=DOC_A)
    assert p.returncode == 0, p.stdout + p.stderr
    for t in ("Primer sello", "Dra. Ñandú", "LAB-A", "Confirmaciones: 2", "UTC", cert["genesis"]["hash"]):
        assert t in p.stdout


def test_cli_documento_distinto(tmp_path, cert):
    p = _cli(tmp_path, cert, doc=b"otra cosa")
    assert p.returncode == 1 and "NO VÁLIDO" in p.stdout and "Traceback" not in p.stderr


def test_cli_genesis_otro(tmp_path, cert):
    assert _cli(tmp_path, cert, "--genesis", "ab" * 32).returncode == 1


def test_cli_json_invalido(tmp_path):
    p = _cli(tmp_path, None, texto="{no es json")
    assert p.returncode == 2 and "Traceback" not in p.stderr


def test_cli_archivo_inexistente(tmp_path):
    p = subprocess.run([sys.executable, str(RAIZ / "verificar_certificado.py"), str(tmp_path / "nada.json")],
                       capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 2


def test_verificador_no_importa_proyecto():
    fuente = (RAIZ / "verificar_certificado.py").read_text(encoding="utf-8")
    assert "import models" not in fuente and "from models" not in fuente
