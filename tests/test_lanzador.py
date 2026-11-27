"""scripts/lanzar_red_local.py: puertos configurables para que dos redes locales no choquen."""
import pytest

from models.errores import ErrorEntrada
from scripts.lanzar_red_local import preparar

CONTRASENA = "contrasena-de-prueba-larga"


def test_puertos_base_configurables(tmp_path):
    _, nodos = preparar(2, str(tmp_path), CONTRASENA, http_base=5301, p2p_base=6301)
    assert [(x["http"], x["p2p"]) for x in nodos] == [(5301, 6301), (5302, 6302)]
    assert nodos[0]["pares"] == "127.0.0.1:6302"


@pytest.mark.parametrize("http_base,p2p_base", [(80, 6301), (5301, 70000), (5301, 5302)])
def test_puertos_base_invalidos(tmp_path, http_base, p2p_base):
    with pytest.raises(ErrorEntrada):
        preparar(2, str(tmp_path), CONTRASENA, http_base=http_base, p2p_base=p2p_base)
