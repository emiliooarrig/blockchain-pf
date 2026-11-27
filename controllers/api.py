"""Rutas JSON. Sólo reciben la petición, validan las entradas y llaman al núcleo (models/)."""
from flask import Blueprint, current_app, jsonify, render_template, request

from controllers.entradas import booleano, contrasena, datos, entero, texto
from models import ataques
from models.bloque import MONTO_MAX
from models.errores import ErrorEntrada, ErrorEstado
from models.pow import (DIF_MAX, DIF_MIN, K_MAX, K_MIN, PAUSA_MAX, PAUSA_MIN, RONDAS_MAX, RONDAS_MIN, SERIE_MAX,
                        SERIE_MIN)
from models.red import N_MAX, N_MIN, RECOMPENSA_MAX, RECOMPENSA_MIN, SALDO_MAX, SALDO_MIN, SEMILLA_MAX

paginas = Blueprint("paginas", __name__)
api = Blueprint("api", __name__, url_prefix="/api/<version>")


def _sim():
    return current_app.config["SIMULADOR"]


def _red(version: str):
    return _sim().red(version)


def _ok(mensaje: str, **extra):
    return jsonify(ok=True, mensaje=mensaje, **extra)


# ---------------------------------------------------------------- páginas
@paginas.get("/")
def inicio():
    return render_template("index.html")


# ---------------------------------------------------------------- estado
@api.get("/estado")
def estado(version):
    red = _red(version)
    with red.lock:
        datos_red = red.publico()
    datos_red["ataques"] = ataques.catalogo()
    return jsonify(ok=True, **datos_red)


@api.get("/cadena")
def cadena(version):
    red = _red(version)
    nodo = request.args.get("nodo") or None
    with red.lock:
        return jsonify(ok=True, **red.cadena_publica(nodo))


@api.get("/nodos/<nodo_id>/recompensas")
def recompensas(version, nodo_id):
    red = _red(version)
    with red.lock:
        nodo = red.nodo(nodo_id)
        filas = red.recompensas(nodo.id)
        ref = red.referencia()
        pendiente = ref.estado.pendiente_de(nodo.id)
        mensaje = (f"{nodo.id}: saldo {ref.estado.saldos[nodo.id]}, recompensas pendientes {pendiente} "
                   f"(se acreditan al llegar a {ref.estado.params['confirmaciones']} confirmaciones).")
        return _ok(mensaje, nodo=nodo.id, saldo=ref.estado.saldos[nodo.id], pendiente=pendiente, recompensas=filas)


# ---------------------------------------------------------------- simulación y transacciones
@api.post("/simulacion")
def reiniciar(version):
    d = datos()
    _red(version)
    parametros = {
        "n": entero(d, "n", "El número de nodos N", N_MIN, N_MAX),
        "semilla": entero(d, "semilla", "La semilla", 0, SEMILLA_MAX, defecto=2026),
        "saldo_inicial": entero(d, "saldo_inicial", "El saldo inicial", SALDO_MIN, SALDO_MAX, defecto=100),
        "recompensa": entero(d, "recompensa", "La recompensa por bloque", RECOMPENSA_MIN, RECOMPENSA_MAX,
                             defecto=50),
        "reproducible": booleano(d, "reproducible", "Modo reproducible", defecto=False),
    }
    red = _sim().reiniciar(version, contrasena=contrasena(d, "contrasena", "La contraseña"), **parametros)
    return _ok(f"Simulación reiniciada con {parametros['n']} nodos.", revision=red.revision)


@api.post("/transacciones")
def transaccion(version):
    d = datos()
    red = _red(version)
    tx = red.crear_transaccion(texto(d, "emisor", "El emisor"), texto(d, "receptor", "El receptor"),
                               entero(d, "monto", "El monto", 1, MONTO_MAX))
    return _ok(f"Transacción {tx['emisor']} → {tx['receptor']} por {tx['monto']} firmada y agregada a pendientes.")


@api.post("/transacciones/aleatoria")
def transaccion_aleatoria(version):
    d = datos()
    red = _red(version)
    cantidad = entero(d, "cantidad", "La cantidad", 1, 20, defecto=1)
    creadas, aviso = 0, ""
    with red.lock:
        for _ in range(cantidad):
            try:
                if red.transaccion_aleatoria() is None:
                    break
            except ErrorEstado as exc:      # AUD-036: p. ej. lista de pendientes llena a mitad del lote
                if not creadas:
                    raise
                aviso = f" Se detuvo el lote: {exc}"
                break
            creadas += 1
    if not creadas:
        raise ErrorEntrada("Ningún nodo tiene saldo disponible para generar transacciones.")
    return _ok(f"{creadas} transacción(es) aleatoria(s) firmada(s) y agregada(s) a pendientes.{aviso}", creadas=creadas)


@api.post("/ataques")
def atacar(version):
    d = datos()
    red = _red(version)
    tipo = texto(d, "tipo", "El tipo de caso")
    nodo = texto(d, "nodo", "El nodo", obligatorio=False)
    if tipo in ataques.ATAQUES_TX:
        resultado = ataques.atacar_transaccion(red, tipo, nodo)
    else:
        resultado = ataques.atacar_cadena(red, tipo, nodo)
    return _ok(resultado["mensaje"], rechazado=resultado["rechazado"])


# ---------------------------------------------------------------- PoW
@api.post("/minar")
def minar(version):
    d = datos()
    red = _red(version)
    mensaje = red.motor.iniciar(
        dificultad=entero(d, "dificultad", "La dificultad", DIF_MIN, DIF_MAX),
        nonces_por_ronda=entero(d, "nonces_por_ronda", "Los nonces por ronda", K_MIN, K_MAX, defecto=100),
        max_rondas=entero(d, "max_rondas", "El límite de rondas", RONDAS_MIN, RONDAS_MAX, defecto=2000),
        bloques=entero(d, "bloques", "El número de bloques", SERIE_MIN, SERIE_MAX, defecto=1),
        pausa_ms=entero(d, "pausa_ms", "La pausa entre rondas", PAUSA_MIN, PAUSA_MAX, defecto=120),
        auto_transacciones=booleano(d, "auto_transacciones", "Generar transacciones", defecto=False),
    )
    return _ok(mensaje)


@api.post("/minar/cancelar")
def cancelar_minado(version):
    return _ok(_red(version).motor.cancelar())
