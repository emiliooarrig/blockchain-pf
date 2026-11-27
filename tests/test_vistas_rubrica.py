"""Vistas de la rúbrica: secciones nuevas en la página, JS sin innerHTML con datos y sintaxis válida."""
import json
import os
import re
import shutil
import subprocess

import pytest

from app import create_app_nodo
from tests.laboratorios import crear_laboratorios

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTATICOS = os.path.join(RAIZ, "views", "static")
JS_TODOS = [os.path.join(ESTATICOS, n) for n in ("comun.js", "sellalo.js", "rubrica.js", "auditoria.js")]
EN_NODO = ["consenso", "verificacion"]          # secciones nuevas de la vista Nodo
MOVIDAS = ["rubrica", "recorrido", "auditoria", "entrega"]


@pytest.fixture(scope="module")
def paginas(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("labs_rubrica")
    genesis, rutas, _ = crear_laboratorios(carpeta)
    ruta = carpeta / "genesis.json"
    ruta.write_text(json.dumps(genesis), encoding="utf-8")
    app = create_app_nodo(str(carpeta / "datos"), str(ruta), "LAB-A", puerto_p2p=0, ruta_clave=rutas["LAB-A"], host_p2p="127.0.0.1")
    c = app.test_client()
    return {r: c.get(r).get_data(as_text=True) for r in ("/", "/rubrica", "/auditoria")}


def test_nodo_trae_secciones_nuevas_y_ya_no_las_movidas(paginas):
    html = paginas["/"]
    for s in EN_NODO:
        assert f'id="seccion-{s}"' in html
    for ancla in ("clave-panel", "consistencia", "persistencia", "form-simular", "btn-auditar"):
        assert f'id="{ancla}"' in html
    for s in MOVIDAS:
        assert f'id="seccion-{s}"' not in html
    assert "entrega-contenido" not in html and "aud-cuerpo" not in html


def test_rubrica_y_auditoria_estan_en_su_vista(paginas):
    r = paginas["/rubrica"]
    for ancla in ("seccion-rubrica", "rubrica-grid", "seccion-recorrido", "recorrido-lista"):
        assert f'id="{ancla}"' in r
    a = paginas["/auditoria"]
    for ancla in ("seccion-auditoria", "aud-cuerpo", "aud-filtros", "aud-resumen"):
        assert f'id="{ancla}"' in a


def test_js_sin_innerhtml_ni_dialogos():
    lineas = [l for js in JS_TODOS for l in open(js, encoding="utf-8").read().splitlines()]
    codigo = " ".join(l for l in lineas if not l.lstrip().startswith("//"))
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", codigo)
    assert not re.search(r"\b(alert|confirm|prompt)\(", codigo)


def test_js_consume_las_rutas_del_contrato():
    codigo = {os.path.basename(js): open(js, encoding="utf-8").read() for js in JS_TODOS}
    for ruta, js in (("/rubrica", "rubrica.js"), ("/clave", "sellalo.js"), ("/verificacion", "sellalo.js"),
                     ("/verificacion/simular", "sellalo.js"), ("/auditoria", "auditoria.js"), ("/estado", "comun.js")):
        assert f'"{ruta}"' in codigo[js], (ruta, js)
    assert '"/entrega"' not in "".join(codigo.values())


@pytest.mark.skipif(shutil.which("node") is None, reason="node no esta instalado")
def test_js_sintaxis_valida():
    for js in JS_TODOS:
        r = subprocess.run(["node", "--check", js], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
