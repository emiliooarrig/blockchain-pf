"""Simulador de blockchain con Proof of Work y Proof of Stake (Flask + MVC).

Ejecutar:  flask run      (o bien: python app.py)
"""
import argparse
import logging
import os

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from controllers import api, paginas
from models import Simulador
from models.errores import ErrorEntrada

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MENSAJES_HTTP = {
    400: "Petición mal formada.",
    404: "La ruta solicitada no existe.",
    405: "Método HTTP no permitido para esta ruta.",
    413: "La petición es demasiado grande.",
    415: "Tipo de contenido no soportado.",
}


def create_app(reproducible: bool = False) -> Flask:
    app = Flask(__name__,
                template_folder=os.path.join(BASE_DIR, "views", "templates"),
                static_folder=os.path.join(BASE_DIR, "views", "static"))
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    app.config["JSON_SORT_KEYS"] = False
    app.json.sort_keys = False
    app.json.ensure_ascii = False
    app.config["SIMULADOR"] = Simulador(reproducible=reproducible)
    app.register_blueprint(paginas)
    app.register_blueprint(api)

    @app.errorhandler(ErrorEntrada)
    def error_entrada(exc: ErrorEntrada):
        return jsonify(ok=False, error=str(exc)), exc.status

    @app.errorhandler(HTTPException)
    def error_http(exc: HTTPException):
        mensaje = MENSAJES_HTTP.get(exc.code, exc.description or exc.name)
        if not request.path.startswith("/api/") and exc.code == 404:
            return f"<h1>404</h1><p>{mensaje}</p><p><a href='/'>Volver al simulador</a></p>", 404
        return jsonify(ok=False, error=mensaje), exc.code

    @app.errorhandler(Exception)
    def error_inesperado(exc: Exception):
        # Red de seguridad: nunca se muestra un traceback al usuario; el detalle queda en el log del servidor.
        app.logger.exception("Error no controlado en %s %s", request.method, request.path)
        return jsonify(ok=False, error=f"Error interno inesperado ({type(exc).__name__}); el estado de la "
                                       f"simulación no se modificó."), 500

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador de blockchain: Proof of Work y Proof of Stake.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
