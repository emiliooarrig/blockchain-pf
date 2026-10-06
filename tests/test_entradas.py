"""Sección 5 · Entradas: N fuera de 10–20; montos negativos, cero, no numéricos o vacíos; emisor igual a
receptor; nodos inexistentes; dificultad fuera de rango."""
import pytest

from models.errores import ErrorEntrada
from models.red import Red


def _error(resp, status=400):
    assert resp.status_code == status, resp.get_json()
    datos = resp.get_json()
    assert datos["ok"] is False and datos["error"]
    return datos["error"]


@pytest.mark.parametrize("n", [9, 21, 0, -3, "abc", "", None, 10.5, True, "1e3"])
def test_n_fuera_de_rango_se_rechaza(cliente, n):
    error = _error(cliente.post("/api/pow/simulacion", json={"n": n}))
    assert "nodos" in error.lower()


@pytest.mark.parametrize("n", [9, 21])
def test_n_fuera_de_rango_en_el_nucleo(n):
    with pytest.raises(ErrorEntrada, match="entre 10 y 20"):
        Red("pow", n, 1, 100, 50)


@pytest.mark.parametrize("n", [10, 20])
def test_n_en_los_limites_se_acepta(cliente, n):
    resp = cliente.post("/api/pos/simulacion", json={"n": n})
    assert resp.status_code == 200
    assert len(cliente.get("/api/pos/estado").get_json()["nodos"]) == n


@pytest.mark.parametrize("monto,fragmento", [
    (-5, "mayor que cero"), (0, "mayor que cero"), ("abc", "numérico"), ("", "obligatorio"),
    (None, "obligatorio"), (2.5, "entero"), ("3.7", "entero"), (True, "entero"), ({"x": 1}, "entero"),
    ("nan", "entero"), (10**12, "entre"),
])
def test_montos_invalidos(cliente, monto, fragmento):
    error = _error(cliente.post("/api/pow/transacciones", json={"emisor": "N00", "receptor": "N01", "monto": monto}))
    assert fragmento in error
    assert cliente.get("/api/pow/estado").get_json()["pendientes"] == []


def test_emisor_igual_a_receptor(cliente):
    error = _error(cliente.post("/api/pow/transacciones", json={"emisor": "N03", "receptor": "N03", "monto": 5}))
    assert "mismo nodo" in error


@pytest.mark.parametrize("emisor,receptor", [("N99", "N01"), ("N00", "zzz"), ("", "N01"), (5, "N01")])
def test_nodos_inexistentes(cliente, emisor, receptor):
    error = _error(cliente.post("/api/pow/transacciones", json={"emisor": emisor, "receptor": receptor, "monto": 5}))
    assert "no existe" in error or "obligatorio" in error or "texto" in error


def test_nodo_inexistente_en_otras_rutas(cliente):
    assert "no existe" in _error(cliente.get("/api/pow/nodos/N77/recompensas"))
    assert "no existe" in _error(cliente.post("/api/pos/nodos/N77/deshonesto", json={"deshonesto": True}))


@pytest.mark.parametrize("dificultad", [0, 7, -1, "x", "", 3.5])
def test_dificultad_fuera_de_rango(cliente, dificultad):
    cliente.post("/api/pow/transacciones", json={"emisor": "N00", "receptor": "N01", "monto": 5})
    error = _error(cliente.post("/api/pow/minar", json={"dificultad": dificultad}))
    assert "dificultad" in error.lower()
    assert cliente.get("/api/pow/estado").get_json()["motor"]["minando"] is False


def test_dificultad_fuera_de_rango_en_el_nucleo(red_pow):
    red_pow.crear_transaccion("N00", "N01", 5)
    with pytest.raises(ErrorEntrada, match="dificultad"):
        red_pow.motor.iniciar(9, 10, 10, en_hilo=False)
