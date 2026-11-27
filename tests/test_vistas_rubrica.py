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
JS = os.path.join(RAIZ, "views", "static", "sellalo.js")
NUEVAS = ["rubrica", "recorrido", "consenso", "verificacion", "auditoria", "entrega"]


@pytest.fixture(scope="module")
def html(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("labs_rubrica")
    genesis, rutas, _ = crear_laboratorios(carpeta)
    ruta = carpeta / "genesis.json"
    ruta.write_text(json.dumps(genesis), encoding="utf-8")
    app = create_app_nodo(str(carpeta / "datos"), str(ruta), "LAB-A", puerto_p2p=0, ruta_clave=rutas["LAB-A"], host_p2p="127.0.0.1")
    return app.test_client().get("/").get_data(as_text=True)


def test_pagina_trae_secciones_nuevas_e_indice(html):
    for s in NUEVAS:
        assert f'id="seccion-{s}"' in html
        assert f'href="#seccion-{s}"' in html
    for ancla in ("clave-panel", "consistencia", "persistencia", "form-simular", "btn-auditar", "aud-cuerpo"):
        assert f'id="{ancla}"' in html


def test_js_sin_innerhtml_ni_dialogos():
    lineas = open(JS, encoding="utf-8").read().splitlines()
    codigo = " ".join(l for l in lineas if not l.lstrip().startswith("//"))
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", codigo)
    assert not re.search(r"\b(alert|confirm|prompt)\(", codigo)


def test_js_consume_las_rutas_del_contrato():
    codigo = open(JS, encoding="utf-8").read()
    for ruta in ("/rubrica", "/clave", "/verificacion", "/verificacion/simular", "/auditoria", "/entrega"):
        assert f'"{ruta}"' in codigo


@pytest.mark.skipif(shutil.which("node") is None, reason="node no esta instalado")
def test_js_sintaxis_valida():
    r = subprocess.run(["node", "--check", JS], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
