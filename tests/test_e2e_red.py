"""Extremo a extremo: red de 3 PROCESOS reales (`app.py --modo nodo`) recorriendo el guion §3.7 completo.

El guion vive en scripts/demo_e2e.py (es también la demo automática del plan B); aquí se ejecuta en silencio, se
afirman las evidencias principales y se revisan los archivos y logs que dejaron los procesos.
Límite total: 90 s (un guardián mata los procesos si algo se cuelga).
"""
import json
import os
import time

import pytest

from models.keystore import CONTRASENA_MIN
from models.validacion import validar_cadena
from scripts.demo_e2e import Guion, RedLocal

CONTRASENA = "contrasena-e2e-no-secreta-987"
LIMITE_TOTAL = 90.0

pytestmark = pytest.mark.e2e


def test_guion_completo_con_tres_procesos(tmp_path):
    assert len(CONTRASENA) >= CONTRASENA_MIN
    t0 = time.monotonic()
    red = RedLocal(str(tmp_path / "red"), CONTRASENA, limite_total=LIMITE_TOTAL - 5, dificultad=2)
    lineas: list[str] = []
    try:
        red.lanzar_todos()
        guion = Guion(red, CONTRASENA, str(tmp_path / "evidencia"), salida=lineas.append)
        ev = guion.ejecutar()

        # --- evidencias del guion
        assert "CERTIFICADO VÁLIDO" in ev["verificador_valido"]
        assert "el documento no coincide con el hash sellado" in ev["verificador_invalido"]
        assert set(ev["ataques"]) == {"merkle_falsa", "sello_alterado"}
        assert ev["rechazos_bitacora"] is True
        assert any("Paso 9" in l for l in lineas) and any("intactas" in l for l in lineas)

        # --- los 3 nodos terminan con la misma cadena, válida, también en disco
        resumenes = {n.id: n.resumen() for n in guion.todos}
        assert len(set(resumenes.values())) == 1
        assert resumenes["LAB-A"][0] == ev["altura_final"]
        # --- ningún secreto en la API, la bitácora ni los logs de los procesos
        for n in guion.todos:
            assert CONTRASENA not in json.dumps(n.estado())
            assert n.estado()["nodo"]["desbloqueado"] is True
        assert CONTRASENA not in red.logs()
        assert CONTRASENA not in "\n".join(lineas)
    finally:
        red.cerrar()

    # procesos cerrados y cadenas en disco revalidables de forma independiente
    assert all(n.proceso.poll() is not None for n in red.nodos.values())
    with open(red.ruta_genesis, encoding="utf-8") as f:
        genesis = json.load(f)
    puntas = set()
    for nid, n in red.nodos.items():
        with open(os.path.join(n.datos, "cadena.json"), encoding="utf-8") as f:
            cadena = json.load(f)
        validar_cadena(cadena, genesis["hash"])
        puntas.add(cadena[-1]["hash"])
        assert not [x for x in os.listdir(n.datos) if x.startswith("cadena.json.corrupto")]
    assert len(puntas) == 1
    assert time.monotonic() - t0 < LIMITE_TOTAL, "el e2e tardó más de 90 s"
