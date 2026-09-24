"""Punto de entrada: sellado de tiempo de cuadernos de laboratorio (Flask + MVC)."""
import os
import secrets

from flask import Flask

from controllers import bp
from models import Blockchain, MiningRace

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def create_app() -> Flask:
    app = Flask(__name__,
                template_folder=os.path.join(BASE_DIR, "views", "templates"),
                static_folder=os.path.join(BASE_DIR, "views", "static"))
    app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

    blockchain = Blockchain(os.path.join(BASE_DIR, "data", "chain.json"))
    app.config["BLOCKCHAIN"] = blockchain
    app.config["MINING_RACE"] = MiningRace(blockchain)

    app.register_blueprint(bp)
    return app


app = create_app()

if __name__ == "__main__":
    # Sin reloader: los hilos de minado viven en un solo proceso.
    app.run(debug=True, use_reloader=False, threaded=True)
