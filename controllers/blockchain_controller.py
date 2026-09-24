"""Controlador: rutas HTTP que conectan las vistas con los modelos."""
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from models.crypto import format_timestamp
from models.mining import MIN_DIFFICULTY, MAX_DIFFICULTY

bp = Blueprint("blockchain", __name__)

DEFAULT_DIFFICULTY = 5


def _chain():
    return current_app.config["BLOCKCHAIN"]


def _race():
    return current_app.config["MINING_RACE"]


def _node():
    return current_app.config["PEER_NODE"]


def _block_view(block, validation) -> dict:
    """Prepara un bloque para la vista (toda la lógica se resuelve aquí, en Python)."""
    zeros = block.difficulty
    return {
        **block.to_dict(),
        "timestamp_fmt": format_timestamp(block.timestamp),
        "hash_prefix": block.hash[:zeros],
        "hash_rest": block.hash[zeros:],
        "valid": validation["valid"],
        "errors": validation["errors"],
        "entries": [{**e, "submitted_fmt": format_timestamp(e["submitted_at"])} for e in block.entries],
    }


def _render_index(verify_result=None, verify_text=""):
    chain = _chain()
    validation = chain.validate()
    blocks = [_block_view(b, v) for b, v in zip(chain.chain, validation)]
    pending = [{**e, "submitted_fmt": format_timestamp(e["submitted_at"])} for e in chain.pending_snapshot()]
    return render_template(
        "index.html",
        blocks=blocks,
        chain_valid=all(v["valid"] for v in validation),
        pending=pending,
        race=_race().status(),
        network=_node().status(),
        revision=chain.revision,
        difficulty_range=range(MIN_DIFFICULTY, MAX_DIFFICULTY + 1),
        default_difficulty=DEFAULT_DIFFICULTY,
        verify_result=verify_result,
        verify_text=verify_text,
    )


@bp.get("/")
def index():
    return _render_index()


@bp.post("/entries")
def add_entry():
    researcher = request.form.get("researcher", "").strip()
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    if not (researcher and title and content):
        flash("Completa investigador, título y contenido.", "error")
    else:
        entry = _chain().add_entry(researcher, title, content)
        _node().broadcast_entry(entry)
        flash(f"Entrada registrada. SHA-256: {entry['content_hash']}", "ok")
    return redirect(url_for("blockchain.index") + "#pendientes")


@bp.post("/mine")
def mine():
    try:
        difficulty = int(request.form.get("difficulty", DEFAULT_DIFFICULTY))
    except ValueError:
        difficulty = DEFAULT_DIFFICULTY
    difficulty = max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, difficulty))
    try:
        _race().start(difficulty)
    except (RuntimeError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("blockchain.index") + "#minado")


@bp.post("/mine/stop")
def stop_mining():
    _race().stop()
    return redirect(url_for("blockchain.index") + "#minado")


@bp.get("/api/status")
def status():
    """Estado del minado, de la conexión y revisión de la cadena (la vista lo consulta periódicamente)."""
    return jsonify(race=_race().status(), network=_node().status(), revision=_chain().revision)


@bp.post("/verify")
def verify():
    text = request.form.get("content", "").strip()
    if not text:
        flash("Pega el contenido a verificar.", "error")
        return redirect(url_for("blockchain.index") + "#verificar")
    result = _chain().find_content(text)
    if result["status"] == "sellado":
        result["timestamp_fmt"] = format_timestamp(result["block"].timestamp)
        result["submitted_fmt"] = format_timestamp(result["entry"]["submitted_at"])
    return _render_index(verify_result=result, verify_text=text)


@bp.post("/blocks/<int:index>/tamper")
def tamper(index):
    if _race().running:
        flash("Espera a que termine el minado.", "error")
    elif _chain().tamper(index):
        flash(f"Se alteró el contenido del bloque #{index}. Observa cómo la cadena deja de ser válida.", "error")
    return redirect(url_for("blockchain.index") + "#cadena")


@bp.post("/chain/reset")
def reset():
    if _race().running:
        flash("Detén el minado antes de reiniciar.", "error")
    elif _node().connected:
        flash("Desconéctate de la otra PC antes de reiniciar la cadena.", "error")
    else:
        _chain().reset()
        _race().clear()
        flash("Cadena reiniciada con un nuevo bloque génesis.", "ok")
    return redirect(url_for("blockchain.index"))
