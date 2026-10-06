"""Rutas JSON. Sólo reciben la petición, validan las entradas y llaman al núcleo (models/)."""
from flask import Blueprint, current_app, jsonify, render_template, request

from controllers.entradas import booleano, datos, entero, opcion, texto
from models import ataques
from models.bloque import MONTO_MAX
from models.errores import ErrorEntrada
from models.pos import FRAUDES, REGLAS_CASTIGO
from models.pow import (DIF_MAX, DIF_MIN, K_MAX, K_MIN, PAUSA_MAX, PAUSA_MIN, RONDAS_MAX, RONDAS_MIN, SERIE_MAX,
                        SERIE_MIN)
from models.red import N_MAX, N_MIN, RECOMPENSA_MAX, RECOMPENSA_MIN, SALDO_MAX, SALDO_MIN, SEMILLA_MAX

paginas = Blueprint("paginas", __name__)
api = Blueprint("api", __name__, url_prefix="/api/<version>")


def _sim():
    return current_app.config["SIMULADOR"]


def _red(version: str, consenso: str | None = None):
    red = _sim().red(version)
    if consenso and red.consenso != consenso:
        raise ErrorEntrada(f"Esta acción sólo existe en la versión {consenso.upper()}.")
    return red


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
    datos_red["ataques"] = ataques.catalogo(red.consenso)
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
                             defecto=50 if version == "pow" else 10),
        "reproducible": booleano(d, "reproducible", "Modo reproducible", defecto=False),
    }
    red = _sim().reiniciar(version, **parametros)
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
    creadas = 0
    with red.lock:
        for _ in range(cantidad):
            if red.transaccion_aleatoria() is None:
                break
            creadas += 1
    if not creadas:
        raise ErrorEntrada("Ningún nodo tiene saldo disponible para generar transacciones.")
    return _ok(f"{creadas} transacción(es) aleatoria(s) firmada(s) y agregada(s) a pendientes.")


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


@api.post("/nodos/<nodo_id>/deshonesto")
def marcar_deshonesto(version, nodo_id):
    d = datos()
    red = _red(version, "pos")
    valor = booleano(d, "deshonesto", "El campo deshonesto")
    with red.lock:
        nodo = red.nodo(nodo_id)
        nodo.deshonesto = valor
        red.evento("pos", f"{nodo.id} marcado como {'DESHONESTO' if valor else 'honesto'}.")
    return _ok(f"{nodo.id} ahora es {'deshonesto: si lo sortean propondrá un bloque inválido' if valor else 'honesto'}.")


# ---------------------------------------------------------------- PoW
@api.post("/minar")
def minar(version):
    d = datos()
    red = _red(version, "pow")
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
    return _ok(_red(version, "pow").motor.cancelar())


# ---------------------------------------------------------------- PoS
@api.post("/pos/config")
def configurar_pos(version):
    d = datos()
    red = _red(version, "pos")
    mensaje = red.motor.configurar(
        tam_comite=entero(d, "tam_comite", "El tamaño del comité", 0, N_MAX, defecto=0),
        regla=opcion(d, "regla", "La regla de castigo", REGLAS_CASTIGO, defecto="A"),
        alfa_pct=entero(d, "alfa_pct", "α (%)", 1, 100, defecto=50),
        fraude=opcion(d, "fraude", "El fraude", FRAUDES, defecto="firma"),
    )
    return _ok(mensaje)


@api.post("/pos/ronda")
def iniciar_ronda(version):
    datos()
    return _ok(_red(version, "pos").motor.iniciar_ronda())


@api.post("/pos/apostar")
def apostar(version):
    d = datos()
    red = _red(version, "pos")
    return _ok(red.motor.apostar(texto(d, "nodo", "El nodo"), entero(d, "monto", "La apuesta", 1, MONTO_MAX)))


@api.post("/pos/apuestas-automaticas")
def apuestas_automaticas(version):
    datos()
    return _ok(_red(version, "pos").motor.apuestas_automaticas())


@api.post("/pos/sortear")
def sortear(version):
    datos()
    return _ok(_red(version, "pos").motor.sortear_proponente())


@api.post("/pos/candidato")
def candidato(version):
    datos()
    return _ok(_red(version, "pos").motor.construir_candidato())


@api.post("/pos/votar")
def votar(version):
    d = datos()
    red = _red(version, "pos")
    return _ok(red.motor.votar(texto(d, "nodo", "El nodo"), booleano(d, "a_favor", "El sentido del voto")))


@api.post("/pos/votacion-automatica")
def votacion_automatica(version):
    datos()
    return _ok(_red(version, "pos").motor.votacion_automatica())


@api.post("/pos/cerrar")
def cerrar_votacion(version):
    datos()
    return _ok(_red(version, "pos").motor.cerrar_votacion())


@api.post("/pos/ronda-automatica")
def ronda_automatica(version):
    datos()
    return _ok(_red(version, "pos").motor.ronda_automatica())


@api.post("/pos/cancelar")
def cancelar_ronda(version):
    datos()
    return _ok(_red(version, "pos").motor.cancelar_ronda())
