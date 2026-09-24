"""Controlador de la conexión TCP/IP con la otra PC."""
from flask import Blueprint, current_app, flash, redirect, request, url_for

from models.network import DEFAULT_PEER_PORT

bp = Blueprint("network", __name__, url_prefix="/network")


def _node():
    return current_app.config["PEER_NODE"]


def _back():
    return redirect(url_for("blockchain.index") + "#conexion")


@bp.post("/identity")
def set_identity():
    try:
        _node().set_identity(request.form.get("identity", ""))
    except (ValueError, RuntimeError) as exc:
        flash(str(exc), "error")
    return _back()


@bp.post("/connect")
def connect():
    ip = request.form.get("ip", "")
    try:
        port = int(request.form.get("port") or DEFAULT_PEER_PORT)
    except ValueError:
        flash("El puerto debe ser un número.", "error")
        return _back()
    try:
        _node().connect(ip, port)
        node = _node()
        flash(f"Conexión exitosa: {node.identity} ⇄ {node.remote_identity} ({ip}:{port}). Ya puedes minar.", "ok")
    except (ValueError, RuntimeError, ConnectionError) as exc:
        flash(str(exc), "error")
    return _back()


@bp.post("/disconnect")
def disconnect():
    if current_app.config["MINING_RACE"].running:
        flash("Detén el minado antes de desconectarte.", "error")
    else:
        _node().disconnect()
        flash("Conexión cerrada.", "ok")
    return _back()
