"""Punto de entrada: sellado de tiempo de cuadernos de laboratorio (Flask + MVC)."""
import argparse
import os
import secrets

from flask import Flask

from controllers import bp, network_bp
from models import Blockchain, MiningRace, PeerNode
from models.network import DEFAULT_PEER_PORT

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def create_app(data_path: str, peer_port: int = DEFAULT_PEER_PORT, identity: str | None = None) -> Flask:
    app = Flask(__name__,
                template_folder=os.path.join(BASE_DIR, "views", "templates"),
                static_folder=os.path.join(BASE_DIR, "views", "static"))
    app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

    blockchain = Blockchain(data_path)
    race = MiningRace(blockchain)
    node = PeerNode(blockchain, race, port=peer_port, identity=identity)
    node.start()

    app.config["BLOCKCHAIN"] = blockchain
    app.config["MINING_RACE"] = race
    app.config["PEER_NODE"] = node

    app.register_blueprint(bp)
    app.register_blueprint(network_bp)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="LabChain: sellado de tiempo con minado distribuido Alice vs Bob.")
    parser.add_argument("--host", default="127.0.0.1", help="Interfaz de la página web (por defecto 127.0.0.1).")
    parser.add_argument("--port", type=int, default=5000, help="Puerto de la página web (por defecto 5000).")
    parser.add_argument("--peer-port", type=int, default=DEFAULT_PEER_PORT,
                        help=f"Puerto TCP para conectar con la otra PC (por defecto {DEFAULT_PEER_PORT}).")
    parser.add_argument("--data", default=os.path.join(BASE_DIR, "data", "chain.json"),
                        help="Archivo donde se guarda la cadena.")
    parser.add_argument("--miner", choices=("Alice", "Bob"), help="Identidad inicial de esta PC.")
    args = parser.parse_args()

    app = create_app(os.path.abspath(args.data), args.peer_port, args.miner)
    # Sin reloader: los hilos de minado y de red viven en un solo proceso.
    app.run(host=args.host, port=args.port, debug=True, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
