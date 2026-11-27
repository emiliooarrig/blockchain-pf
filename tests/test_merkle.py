"""Raíz de Merkle y pruebas de inclusión (contrato C2)."""
import pytest

from models.cripto import sha256_hex
from models.merkle import RAIZ_VACIA, camino, hoja_tx, raiz, raiz_transacciones, verificar_camino


def _hojas(n):
    return [sha256_hex(f"tx{i}") for i in range(n)]


def test_raiz_vacia():
    assert raiz([]) == RAIZ_VACIA == sha256_hex(b"")


def test_raiz_una_hoja_es_la_hoja():
    h = _hojas(1)
    assert raiz(h) == h[0]


def test_raiz_impar_duplica_el_ultimo():
    a, b, c = _hojas(3)
    esperado = sha256_hex(sha256_hex(a + b) + sha256_hex(c + c))
    assert raiz([a, b, c]) == esperado


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 8, 10])
def test_camino_valido_para_cada_hoja(n):
    hojas = _hojas(n)
    r = raiz(hojas)
    for i, h in enumerate(hojas):
        assert verificar_camino(h, camino(hojas, i), r)


def test_camino_alterado_o_hoja_ajena_se_rechaza():
    hojas = _hojas(5)
    r = raiz(hojas)
    pasos = camino(hojas, 2)
    assert not verificar_camino(sha256_hex("otra"), pasos, r)
    pasos[0] = {**pasos[0], "lado": "izq" if pasos[0]["lado"] == "der" else "der"}
    assert not verificar_camino(hojas[2], pasos, r)


@pytest.mark.parametrize("pasos", [None, "x", [{"lado": "arriba", "hash": "0" * 64}], [{"lado": "der"}], [1]])
def test_camino_mal_formado(pasos):
    hojas = _hojas(2)
    assert not verificar_camino(hojas[0], pasos, raiz(hojas))


def test_hoja_compromete_la_firma():
    tx = {"emisor": "N00", "receptor": "N01", "monto": 1, "timestamp": 1.0, "firma": "a" * 128}
    assert hoja_tx(tx) != hoja_tx({**tx, "firma": "b" * 128})
    assert raiz_transacciones([tx]) == hoja_tx(tx)


def test_indice_fuera_de_rango():
    with pytest.raises(IndexError):
        camino(_hojas(2), 2)
