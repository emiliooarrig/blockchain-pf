# Simulador de blockchain: Proof of Work

Aplicación web en **Python + Flask** que simula una blockchain de **10 a 20 nodos** con **Proof of Work**, el único consenso del sistema: los nodos son mineros que compiten por rondas buscando un nonce válido, con nonces disjuntos.

> 2026-11-27: se eliminó Proof of Stake. El único consenso es PoW (en el simulador y en la red Sellalo).

Las transacciones van firmadas (Ed25519) y **cada nodo conserva su propia copia de la cadena y valida la cadena completa antes de aceptarla**.

## Requisitos

- Python **3.10 o superior**
- `pip`

## Instalación y ejecución (máquina limpia)

```bash
git clone https://github.com/emiliooarrig/blockchain-pf.git
cd blockchain-pf
git checkout medi-termino

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

flask run
```

Abre **http://127.0.0.1:5000**. También funciona `python app.py`. La página principal es el **Simulador Proof of Work**.

## Pruebas

```bash
pytest
```

Hay 710 pruebas en `tests/` (incluidas las de la red Sellalo), cubriendo cada caso de la sección 5 de la guía (ver [tabla de casos](#casos-contemplados)).

## Cómo usarla

1. **Red de nodos:** elige N (10–20), la semilla, el saldo inicial y la recompensa, y pulsa *Crear / reiniciar simulación*. Con *Modo reproducible* el reloj es simulado y, con la misma semilla, la simulación se repite igual.
2. **Transacción firmada:** elige emisor, receptor y monto. El servidor firma con la clave privada del emisor y la red verifica la firma con su clave pública antes de aceptarla en *Pendientes*.
3. **Minado:** elige la dificultad (1–6 ceros; se sugiere 3–5), los nonces por minero y ronda, el límite de rondas y cuántos bloques seguidos minar. Las tarjetas muestran en vivo el nonce, los intentos y el último hash de cada minero. *Minar 10 bloques seguidos* permite ver madurar las primeras recompensas.
4. **Estado de cada nodo:** altura, hash del último bloque, si está sincronizado, saldo disponible y recompensas pendientes.
5. **Laboratorio de casos:** un nodo atacante envía cadenas o transacciones manipuladas y la red las rechaza con su motivo, sin que cambie la cadena de ningún nodo.
6. **Bitácora:** bloques minados, difusiones, rechazos y recompensas acreditadas.

## Diseño

```
blockchain-pf/
├── app.py                     # create_app(): Flask, manejadores de error (JSON, nunca traceback)
├── controllers/
│   ├── api.py                 # rutas: sólo leen la petición, validan entradas y llaman al núcleo
│   └── entradas.py            # validación de entradas (enteros, textos, booleanos)
├── models/                    # núcleo: se ejecuta y se prueba sin Flask
│   ├── cripto.py              # SHA-256, JSON canónico, claves y firmas Ed25519
│   ├── bloque.py              # transacciones, hash_bloque, Estado de cuentas, doble gasto
│   ├── validacion.py          # validar_bloque y validar_cadena (reglas a–c)
│   ├── pow.py                 # ronda_pow, nonces disjuntos, desempate, MotorPoW
│   ├── red.py                 # Nodo, Red, difundir(), pendientes y bitácora
│   ├── ataques.py             # laboratorio de casos
│   └── simulador.py           # la red PoW del simulador
├── views/templates/index.html
├── views/static/{app.js, styles.css}   # interfaz: consulta /estado con fetch cada 250–1000 ms
├── tests/                     # pytest
└── docs/REPORTE.md            # reporte breve
```

### Bloque

| Campo | Descripción |
|---|---|
| `numero` | Altura; el génesis es 0 |
| `timestamp` | Momento de creación |
| `transacciones` | Al menos una transacción firmada (`emisor, receptor, monto, timestamp, firma`) |
| `raiz_merkle` | Raíz de Merkle de las transacciones |
| `hash_anterior` | Hash del bloque previo |
| `nonce` | Número que hace válido el hash |
| `hash` | `SHA-256` del encabezado (todos los campos salvo `hash`, `transacciones` y `firma_minero`) en JSON canónico |
| `proponente` | Minero ganador |
| `recompensa` | Debe ser la establecida en el génesis |
| `dificultad` | Ceros hexadecimales requeridos |
| `firma_minero` | Firma del proponente sobre el hash (no entra al hash) |

Un bloque con cualquier otro campo se rechaza por «campos desconocidos».

El génesis guarda además las cuentas (clave pública y saldo inicial) y los parámetros de la red.

### Validación (cada nodo, cadena completa)

Un nodo adopta una cadena recibida sólo si: **(a)** cada `hash` coincide con el recalculado y cada `hash_anterior` con el bloque previo; **(b)** todas las firmas son válidas y nadie gasta más de lo que tiene, incluido el doble gasto en el mismo bloque o entre bloques; **(c)** se cumple el consenso (Proof of Work: hash bajo el objetivo y firma del minero); **(d)** es más larga que la propia. Si algo falla, la rechaza, conserva la suya y el motivo queda en la bitácora.

### Proof of Work

- Rondas (ticks) en un hilo de fondo. En cada ronda el minero `i` prueba `k` nonces de la secuencia `i, i+N, i+2N…`.
- **Desempate:** una ronda representa un intervalo en el que todos trabajan en paralelo; si varios encuentran un nonce válido en la misma ronda, **gana el hash menor**. Todos se detienen, el ganador agrega el bloque a su cadena y la difunde.
- **Recompensa con 6 confirmaciones:** la recompensa del bloque `h` se acredita cuando la cadena llega a `h+6`. La interfaz separa el saldo disponible de las recompensas pendientes.
- Pedir minar mientras ya se mina se rechaza. Hay un límite de rondas configurable y botón de cancelar.

## Casos contemplados

| Ámbito | Caso | Prueba |
|---|---|---|
| Entradas | N fuera de 10–20; montos negativos, cero, no numéricos o vacíos; emisor = receptor; nodos inexistentes; dificultad fuera de rango | `tests/test_entradas.py` |
| Transacciones | Firma alterada; firmada por otra clave; saldo insuficiente; doble gasto en el mismo bloque y entre bloques; pendientes vacías al minar | `tests/test_transacciones.py` |
| Cadena | Hash o `hash_anterior` alterado; cadena más corta o inválida; bloque intermedio manipulado; génesis ajeno | `tests/test_cadena.py` |
| PoW | Nonces disjuntos; dos ganadores en la misma ronda; minar mientras se mina; límite de rondas y cancelación; recompensa antes de 6 confirmaciones; recompensa falsa; 10 bloques seguidos | `tests/test_pow.py` |
| Sin PoS | Génesis con consenso `pos`, bloques con campos PoS y rutas `/api/pos/...` se rechazan con mensaje claro | `tests/test_sin_pos.py` |
| Aplicación | Reiniciar; recargar a mitad del minado; dos pestañas a la vez; peticiones con datos mal formados (ninguna devuelve 500) | `tests/test_aplicacion.py` |

## API

Todas las rutas responden JSON `{ok, mensaje}` o `{ok: false, error}` (400 entrada inválida, 409 acción no permitida en el estado actual). `<v>` es siempre `pow`; cualquier otra versión (por ejemplo `pos`) responde 400 «el sistema sólo usa Proof of Work».

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/<v>/estado` | Nodos, pendientes, motor de consenso, recompensas y bitácora |
| GET | `/api/<v>/cadena?nodo=N03` | Últimos bloques de la copia de un nodo |
| GET | `/api/<v>/nodos/<id>/recompensas` | Recompensas del nodo y sus confirmaciones |
| POST | `/api/<v>/simulacion` | `{n, semilla, saldo_inicial, recompensa, reproducible}` |
| POST | `/api/<v>/transacciones` | `{emisor, receptor, monto}` |
| POST | `/api/<v>/transacciones/aleatoria` | `{cantidad}` |
| POST | `/api/<v>/ataques` | `{tipo, nodo}` (laboratorio de casos) |
| POST | `/api/pow/minar` · `/api/pow/minar/cancelar` | `{dificultad, nonces_por_ronda, max_rondas, bloques, pausa_ms, auto_transacciones}` |

## Notas

- La red se simula en memoria; reiniciar el servidor reinicia la simulación.
- La interfaz no calcula hashes ni firmas: todo ocurre en el servidor, que valida cada petición aunque el formulario ya lo haga.
- Proyecto académico; usa el servidor de desarrollo de Flask.
