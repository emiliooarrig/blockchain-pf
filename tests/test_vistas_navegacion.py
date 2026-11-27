"""Navegación entre vistas: Nodo, Rúbrica, Auditoría y Simulador, con encabezado común y barra de 5 grupos."""
import json
import os
import re
import shutil
import subprocess

import pytest

from app import create_app, create_app_nodo
from tests.laboratorios import crear_laboratorios

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTATICOS = os.path.join(RAIZ, "views", "static")
JS = [os.path.join(ESTATICOS, n) for n in ("comun.js", "sellalo.js", "rubrica.js", "ataques.js", "auditoria.js", "app.js")]
VISTAS = {"/": "nodo", "/rubrica": "rubrica", "/ataques": "ataques", "/auditoria": "auditoria", "/simulador": "simulador"}


@pytest.fixture(scope="module")
def nodo(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("labs_nav")
    genesis, rutas, _ = crear_laboratorios(carpeta)
    ruta = carpeta / "genesis.json"
    ruta.write_text(json.dumps(genesis), encoding="utf-8")
    app = create_app_nodo(str(carpeta / "datos"), str(ruta), "LAB-A", puerto_p2p=0, ruta_clave=rutas["LAB-A"], host_p2p="127.0.0.1")
    return app.test_client()


@pytest.fixture(scope="module")
def simulador():
    return create_app().test_client()


def pestanas(html):
    return re.findall(r'<(?:a|span) class="vista-tab[^"]*"([^>]*)>([^<]+)<', html)


@pytest.mark.parametrize("ruta", list(VISTAS))
def test_vistas_responden_200_en_modo_nodo(nodo, ruta):
    assert nodo.get(ruta).status_code == 200


@pytest.mark.parametrize("ruta", ["/rubrica", "/ataques", "/auditoria"])
def test_rubrica_ataques_y_auditoria_en_modo_simulador_avisan(simulador, ruta):
    r = simulador.get(ruta)
    assert r.status_code == 200
    assert "requiere el modo nodo" in r.get_data(as_text=True)
    assert simulador.get("/api/sellalo/rubrica").status_code == 409
    assert simulador.get("/api/sellalo/auditoria").status_code == 409


def test_nodo_ya_no_trae_rubrica_recorrido_auditoria_ni_entrega(nodo):
    html = nodo.get("/").get_data(as_text=True)
    for s in ("rubrica", "recorrido", "auditoria", "entrega"):
        assert f"seccion-{s}" not in html


def test_rubrica_tiene_tablero_y_recorrido(nodo):
    html = nodo.get("/rubrica").get_data(as_text=True)
    assert 'id="rubrica-grid"' in html and 'id="recorrido-lista"' in html
    assert "rubrica.js" in html and "comun.js" in html


def test_auditoria_tiene_la_tabla_y_rutas_en_texto(nodo):
    html = nodo.get("/auditoria").get_data(as_text=True)
    assert 'id="aud-cuerpo"' in html and "auditoria.js" in html
    assert "docs/auditoria/" in html


@pytest.mark.parametrize("ruta,activa", list(VISTAS.items()))
def test_selector_de_vistas_con_cinco_pestanas_y_la_activa_marcada(nodo, ruta, activa):
    html = nodo.get(ruta).get_data(as_text=True)
    tabs = pestanas(html)
    assert [t for _, t in tabs] == ["Nodo", "Rúbrica", "Ataques", "Auditoría", "Simulador"]
    marcadas = [attrs for attrs, _ in tabs if 'aria-current="page"' in attrs]
    assert len(marcadas) == 1 and f'data-vista="{activa}"' in marcadas[0]
    assert 'aria-label="Vistas de la aplicación"' in html


def test_simulador_en_modo_simulador_deshabilita_vistas_del_nodo(simulador):
    tabs = pestanas(simulador.get("/").get_data(as_text=True))
    assert [t for _, t in tabs] == ["Nodo", "Rúbrica", "Ataques", "Auditoría", "Simulador"]
    deshabilitadas = [t for attrs, t in tabs if 'aria-disabled="true"' in attrs]
    assert deshabilitadas == ["Nodo", "Rúbrica", "Ataques", "Auditoría"]
    assert all("title=" in attrs for attrs, t in tabs if t in deshabilitadas)


def test_nodo_tiene_exactamente_cinco_grupos_en_la_barra_secundaria(nodo):
    html = nodo.get("/").get_data(as_text=True)
    assert len(re.findall(r"data-grupo=", html)) == 5
    assert 'class="indice"' not in html
    cubiertas = set()
    for href, secciones in re.findall(r'href="#(seccion-\w+)" data-grupo="\w+" data-secciones="([^"]+)"', html):
        assert f'id="{href}"' in html
        cubiertas.update(secciones.split())
    assert set(re.findall(r'<section class="card" id="seccion-(\w+)"', html)) == cubiertas
    assert 'id="ir-a"' in html and 'aria-label="Ir a…"' in html


def test_las_otras_vistas_no_tienen_barra_de_grupos(nodo):
    for ruta in ("/rubrica", "/ataques", "/auditoria"):
        assert "data-grupo=" not in nodo.get(ruta).get_data(as_text=True)


def test_js_sin_innerhtml_con_datos_ni_dialogos():
    for js in JS:
        codigo = " ".join(l for l in open(js, encoding="utf-8").read().splitlines() if not l.lstrip().startswith("//"))
        assert not re.search(r"innerHTML\s*[+]?=|outerHTML|insertAdjacentHTML|document\.write", codigo), js
        assert not re.search(r"\b(alert|confirm|prompt)\(", codigo), js


@pytest.mark.skipif(shutil.which("node") is None, reason="node no esta instalado")
@pytest.mark.parametrize("js", JS)
def test_js_sintaxis_valida(js):
    r = subprocess.run(["node", "--check", js], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_ataques_tiene_formulario_historial_y_panel_de_cadena(nodo):
    html = nodo.get("/ataques").get_data(as_text=True)
    for ident in ("form-ataque", "in-ataque-destino", "atq-catalogo", "atq-historial", "atq-a-punta", "atq-d-punta", "atq-desactivado"):
        assert f'id="{ident}"' in html
    assert "ataques.js" in html and "--laboratorio-ataques" in html
    assert nodo.get("/static/ataques.js").status_code == 200


def test_nodo_ya_no_contiene_la_seccion_de_ataques(nodo):
    html = nodo.get("/").get_data(as_text=True)
    assert "seccion-ataques" not in html and "form-ataque" not in html and "Laboratorio de ataques" not in html
    with open(os.path.join(ESTATICOS, "sellalo.js"), encoding="utf-8") as f:
        assert "ataque" not in f.read().lower()


def test_barra_del_nodo_tiene_grupo_verificacion_y_no_seguridad(nodo):
    html = nodo.get("/").get_data(as_text=True)
    textos = re.findall(r'data-grupo="\w+" data-secciones="[^"]*">([^<]+)<', html)
    assert len(textos) == 5 and "Verificación" in textos and "Seguridad" not in textos
    assert '<option value="seccion-verificacion">Verificación</option>' in html


def test_ataques_js_sin_innerhtml_ni_localstorage():
    codigo = " ".join(l for l in open(os.path.join(ESTATICOS, "ataques.js"), encoding="utf-8").read().splitlines() if not l.lstrip().startswith("//"))
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|localStorage|sessionStorage", codigo)
