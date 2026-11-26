"""Páginas: la interfaz del nodo trae sus 9 secciones, el simulador conserva la suya y el JS no inserta HTML sin escapar."""
import json
import os
import re

import pytest

from app import create_app, create_app_nodo
from tests.laboratorios import crear_laboratorios

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECCIONES = ["identidad", "red", "sellar", "firmas", "minado", "cadena", "prioridad", "ataques", "cuentas"]


@pytest.fixture(scope="module")
def cliente_nodo(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("labs_vistas")
    genesis, rutas, _ = crear_laboratorios(carpeta)
    ruta = carpeta / "genesis.json"
    ruta.write_text(json.dumps(genesis), encoding="utf-8")
    app = create_app_nodo(str(carpeta / "datos"), str(ruta), "LAB-A", puerto_p2p=0, ruta_clave=rutas["LAB-A"],
                          host_p2p="127.0.0.1")
    return app.test_client()


def test_nodo_pagina_principal_tiene_las_nueve_secciones(cliente_nodo):
    r = cliente_nodo.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for s in SECCIONES:
        assert f'id="seccion-{s}"' in html
    assert 'type="password"' in html and 'autocomplete="current-password"' in html
    assert "sellalo.js" in html and "styles.css" in html


def test_nodo_sirve_simulador_y_estaticos(cliente_nodo):
    assert cliente_nodo.get("/simulador").status_code == 200
    assert cliente_nodo.get("/static/sellalo.js").status_code == 200
    assert cliente_nodo.get("/static/styles.css").status_code == 200


def test_simulador_tiene_campo_de_contrasena():
    html = create_app().test_client().get("/").get_data(as_text=True)
    assert 'name="contrasena"' in html and 'autocomplete="new-password"' in html


def test_sellalo_js_no_inserta_html_sin_escapar():
    with open(os.path.join(RAIZ, "views", "static", "sellalo.js"), encoding="utf-8") as f:
        js = f.read()
    codigo = "\n".join(l for l in js.splitlines() if not l.lstrip().startswith("//"))
    for m in re.finditer(r"innerHTML\s*\+?=([^;\n]*)", codigo):
        asignacion = m.group(1)
        assert not re.search(r"[+`$]", asignacion) or "esc(" in asignacion, asignacion
    assert "alert(" not in codigo and "confirm(" not in codigo and "prompt(" not in codigo
    assert "localStorage" not in codigo
