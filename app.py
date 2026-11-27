"""Simulador de blockchain con Proof of Work (Flask + MVC).

Ejecutar:  flask run      (o bien: python app.py)
"""
import argparse
import json
import logging
import os
from urllib.parse import urlsplit

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from controllers import api, paginas
from controllers.sellalo import ContextoNodo, paginas_nodo, paginas_vistas, resolver_host, sellalo
from models import Simulador
from models.coordinador_ajustes import CoordinadorAjustes
from models.coordinador_sellos import CoordinadorSellos
from models.errores import ErrorEntrada
from models.nodo_completo import NodoCompleto

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MENSAJES_HTTP = {
    400: "Petición mal formada.",
    404: "La ruta solicitada no existe.",
    405: "Método HTTP no permitido para esta ruta.",
    413: "La petición es demasiado grande.",
    415: "Tipo de contenido no soportado.",
}


MAX_DOCUMENTO = 25 * 1024 * 1024     # modo nodo: documentos y certificados (el contenido nunca se guarda)


HOSTS_LOCALES = {"127.0.0.1", "localhost", "[::1]"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def _nombre_host(netloc: str) -> str:
    """«host:puerto» -> «host» en minúsculas (conserva los corchetes de IPv6)."""
    netloc = netloc.strip().lower()
    if netloc.startswith("["):
        return netloc[:netloc.find("]") + 1] if "]" in netloc else netloc
    return netloc.rsplit(":", 1)[0] if ":" in netloc else netloc


def create_app(reproducible: bool = False, contrasena: str | None = None, contexto_nodo: ContextoNodo | None = None,
               host_http: str | None = None, laboratorio_ataques: bool = False) -> Flask:
    """Modo simulador por defecto; con `contexto_nodo` (ver create_app_nodo) es un nodo de la red Sellalo.

    `host_http` es el --host configurado (además de los locales). `laboratorio_ataques` habilita en modo nodo el
    endpoint de ataques de demostración (AUD-017)."""
    app = Flask(__name__,
                template_folder=os.path.join(BASE_DIR, "views", "templates"),
                static_folder=os.path.join(BASE_DIR, "views", "static"))
    app.config["MAX_CONTENT_LENGTH"] = MAX_DOCUMENTO if contexto_nodo else 64 * 1024
    app.config["CONTEXTO_NODO"] = contexto_nodo
    app.config["LABORATORIO_ATAQUES"] = laboratorio_ataques
    hosts_permitidos = set(HOSTS_LOCALES)
    if host_http and host_http not in ("0.0.0.0", "::"):
        hosts_permitidos.add(host_http.lower() if host_http.count(":") < 2 else f"[{host_http.strip('[]').lower()}]")
    app.config["JSON_SORT_KEYS"] = False
    app.json.sort_keys = False
    app.json.ensure_ascii = False
    app.config["SIMULADOR"] = Simulador(reproducible=reproducible, contrasena=contrasena)
    app.register_blueprint(paginas_nodo if contexto_nodo else paginas)
    app.register_blueprint(paginas_vistas)
    app.register_blueprint(api)
    app.register_blueprint(sellalo)

    @app.context_processor
    def modo():
        return {"modo_nodo": contexto_nodo is not None}

    @app.before_request
    def proteger_escrituras():
        """Defensa CSRF y DNS rebinding para toda escritura bajo /api/ (AUD-003). Los clientes sin navegador (curl,
        pruebas, demo) no envían Origin ni Sec-Fetch-Site y se permiten."""
        if request.method in METODOS_SEGUROS or not request.path.startswith("/api/"):
            return None
        if _nombre_host(request.host) not in hosts_permitidos:
            return jsonify(ok=False, error="Host no permitido: usa la dirección local del nodo."), 403
        origen = request.headers.get("Origin")
        if origen is not None:
            partes = urlsplit(origen)
            if partes.scheme not in ("http", "https") or partes.netloc.lower() != request.host.lower():
                return jsonify(ok=False, error="Origen no permitido: la petición no viene de la interfaz del nodo."), 403
        if request.headers.get("Sec-Fetch-Site", "").lower() in ("cross-site", "same-site"):
            return jsonify(ok=False, error="Petición entre sitios rechazada."), 403
        return None

    @app.after_request
    def cabeceras_de_seguridad(resp):
        """AUD-033: anti-clickjacking, anti-sniffing y CSP; las fuentes de Google se acotan por CSP (sin SRI)."""
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    @app.errorhandler(ErrorEntrada)
    def error_entrada(exc: ErrorEntrada):
        return jsonify(ok=False, error=str(exc)), exc.status

    @app.errorhandler(HTTPException)
    def error_http(exc: HTTPException):
        mensaje = MENSAJES_HTTP.get(exc.code, exc.description or exc.name)
        if not request.path.startswith("/api/") and exc.code == 404:
            return f"<h1>404</h1><p>{mensaje}</p><p><a href='/'>Volver al inicio</a></p>", 404
        return jsonify(ok=False, error=mensaje), exc.code

    @app.errorhandler(Exception)
    def error_inesperado(exc: Exception):
        # Red de seguridad: nunca se muestra un traceback al usuario; el detalle queda en el log del servidor.
        app.logger.exception("Error no controlado en %s %s", request.method, request.path)
        return jsonify(ok=False, error=f"Error interno inesperado ({type(exc).__name__}); el estado de la "
                                       f"simulación no se modificó."), 500

    return app


def parsear_pares(texto: str | None) -> list[tuple[str, int]]:
    """«ip:puerto,ip:puerto» -> [(ip, puerto)]. ErrorEntrada si algún par está mal escrito."""
    pares = []
    for item in (texto or "").split(","):
        item = item.strip()
        if not item:
            continue
        host, _, puerto = item.rpartition(":")
        if not host or not puerto.isdigit() or not 1 <= int(puerto) <= 65535:
            raise ErrorEntrada(f"Par inválido «{item}»: usa ip:puerto (por ejemplo 127.0.0.1:6002).")
        pares.append((resolver_host(host), int(puerto)))
    return pares


def create_app_nodo(dir_datos: str, ruta_genesis: str, nodo_id: str, puerto_p2p: int = 6000,
                    pares: list[tuple[str, int]] | None = None, ruta_clave: str | None = None,
                    host_p2p: str = "0.0.0.0", opciones_p2p: dict | None = None, host_http: str | None = None,
                    laboratorio_ataques: bool = False) -> Flask:
    """Aplicación en modo nodo: construye el NodoCompleto (bloqueado) y el coordinador de sellos. El ServidorP2P se
    crea cuando el nodo se desbloquea (POST /api/sellalo/desbloquear)."""
    try:
        with open(ruta_genesis, encoding="utf-8") as f:
            genesis = json.load(f)
    except OSError as exc:
        raise ErrorEntrada(f"No se pudo leer el génesis «{ruta_genesis}»: {exc.strerror or exc}.") from None
    except ValueError:
        raise ErrorEntrada(f"El génesis «{ruta_genesis}» no es un JSON válido.") from None
    ruta_clave = ruta_clave or os.path.join(dir_datos, "clave.json")
    nodo = NodoCompleto(dir_datos, genesis, nodo_id, ruta_clave)
    coordinador = CoordinadorSellos(nodo, dir_datos)
    contexto = ContextoNodo(nodo, coordinador, host_p2p, puerto_p2p, pares, opciones_p2p,
                            ajustes=CoordinadorAjustes(nodo, dir_datos))
    return create_app(contexto_nodo=contexto, host_http=host_http, laboratorio_ataques=laboratorio_ataques)


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sellalo: simulador de blockchain y nodo de la red de sellado.")
    parser.add_argument("--modo", choices=("simulador", "nodo"), default="simulador")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", "--puerto", dest="port", type=int, default=5000, help="puerto HTTP")
    nodo = parser.add_argument_group("modo nodo")
    nodo.add_argument("--nodo", help="id del laboratorio (por ejemplo LAB-A)")
    nodo.add_argument("--datos", help="carpeta de datos del nodo")
    nodo.add_argument("--genesis", help="archivo genesis.json de la red")
    nodo.add_argument("--clave", help="almacén de claves (por defecto <datos>/clave.json)")
    nodo.add_argument("--puerto-p2p", type=int, default=6000)
    nodo.add_argument("--pares", default="", help="pares iniciales: ip:puerto,ip:puerto")
    nodo.add_argument("--laboratorio-ataques", action="store_true",
                      help="habilita el endpoint de ataques de demostración (usa la clave del laboratorio)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    instancia = app
    if args.modo == "nodo":
        faltan = [n for n in ("nodo", "datos", "genesis") if not getattr(args, n)]
        if faltan:
            parser.error("--modo nodo requiere " + ", ".join(f"--{n}" for n in faltan))
        if not 1 <= args.puerto_p2p <= 65535:
            parser.error("--puerto-p2p debe estar entre 1 y 65535")
        try:
            instancia = create_app_nodo(args.datos, args.genesis, args.nodo, args.puerto_p2p,
                                        parsear_pares(args.pares), args.clave, host_http=args.host,
                                        laboratorio_ataques=args.laboratorio_ataques)
        except ErrorEntrada as exc:
            parser.exit(1, f"Error: {exc}\n")
        print(f"Nodo {args.nodo} bloqueado. Desbloquéalo en http://{args.host}:{args.port}/ "
              f"(P2P: puerto {args.puerto_p2p}).", flush=True)
    instancia.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
