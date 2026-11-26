# Contratos congelados · Proyecto final Sellalo

> Fase 0 del [plan](../PLAN_PROYECTO_FINAL.md). Todos los subagentes implementan **contra este documento**.
> Cambiar un contrato requiere avisar al orquestador; no se cambia en silencio.

Convenciones: código, identificadores y mensajes en **español**; mensajes de error claros (se muestran en la UI);
errores de entrada → `ErrorEntrada` (HTTP 400), acción fuera de estado → `ErrorEstado` (HTTP 409),
datos de red/cadena inválidos → `ErrorValidacion`. Nunca un traceback ni un 500 por datos del usuario o de un par.

---

## C1 · Bloque v2 (simulador y red Sellalo)

### Hash del bloque

```python
EXCLUIDOS_HASH = ("hash", "transacciones", "firma_minero")

def hash_bloque(b):
    datos = {k: v for k, v in b.items() if k not in EXCLUIDOS_HASH}
    return hashlib.sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()
```

- `json.dumps` con los parámetros por defecto (`ensure_ascii=True`, separadores por defecto) + `sort_keys=True`.
  El verificador independiente usa exactamente la misma serialización.
- Las transacciones quedan comprometidas por el campo **`raiz_merkle`** (ver C2), que sí entra al hash.
- **Encabezado** = el bloque sin `transacciones`. `hash_bloque(encabezado) == bloque["hash"]`.
- `preparar_hasher` se ajusta para excluir los mismos campos.

### Campos

| Conjunto | Campos |
|---|---|
| `CAMPOS_COMUNES` | `numero, timestamp, transacciones, hash_anterior, raiz_merkle, nonce, proponente, recompensa, hash` |
| `CAMPOS_POW` | comunes + `dificultad, firma_minero` |
| `CAMPOS_POS` | comunes + `validadores, intento, excluidos, castigos, firma_proponente, votos` (sin cambios de semántica) |
| `CAMPOS_GENESIS` | comunes + `cuentas, parametros` (raíz de Merkle de la lista vacía) |

- `raiz_merkle == merkle.raiz_transacciones(bloque["transacciones"])`; si no, `ErrorValidacion("la raíz de Merkle no coincide con las transacciones")`.
- **`firma_minero`** (sólo PoW) = `claves_del_proponente.firmar(bytes.fromhex(bloque["hash"]))` (hex de 128).
  Se verifica con `estado.claves[proponente]`. Se firma **después** de encontrar el nonce (por eso no entra al hash).
  `verificar_pow(estado, bloque)` recibe ahora el estado.
- PoS: `mensaje_propuesta` sigue excluyendo `hash, votos, firma_proponente`; ahora también excluye `transacciones`
  sólo si así se decide en A1 — **por defecto se deja igual** (las transacciones siguen firmadas por el proponente).
- `parametros` del génesis acepta además `"red": "simulador" | "sellalo"` y `"nombre": str` (opcionales en el simulador).

## C2 · Merkle (`models/merkle.py`, YA implementado en fase 0)

- `hoja_tx(tx) = sha256_hex(canonico(tx))` — transacción completa con firmas.
- Padre = `sha256_hex(hijo_izq_hex + hijo_der_hex)`; nivel impar duplica el último; vacío = `sha256_hex(b"")`.
- `camino(hojas, i) -> [{"lado": "izq"|"der", "hash": h}, ...]`; `lado` = posición del **hermano**.
- `verificar_camino(hoja, pasos, raiz) -> bool`.

## C3 · Transacciones

### Transferencia (sin cambios)

`{emisor, receptor, monto, timestamp, firma}` — sin campo `tipo`. Se valida con `revisar_transaccion` como hoy.

### Sello multifirma (nuevo)

```json
{
  "tipo": "sello",
  "doc_hash": "<sha256 hex del documento, 64>",
  "titulo": "<1..120 caracteres>",
  "investigador": "<1..80 caracteres>",
  "laboratorio": "<id del nodo que registra; debe estar en autores>",
  "autores": ["<ids de nodo, ordenados, sin repetir>"],
  "umbral": 2,
  "timestamp": 1767225600.123456,
  "firmas": {"<id autor>": "<firma hex 128>"}
}
```

- `mensaje_sello(tx) = canonico({k: tx[k] for k in ("tipo","doc_hash","titulo","investigador","laboratorio","autores","umbral","timestamp")})`
  (`canonico` = `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False).encode("utf-8")`).
- `id_sello(tx) = sha256_hex(mensaje_sello(tx))` — es el id que entra a `estado.tx_ids` (evita repetir el mismo sello).
- Reglas **dentro de un bloque** (estrictas): `1 ≤ umbral ≤ len(autores) ≤ 5`; autores existentes en `estado.claves`,
  ordenados y sin repetir; `laboratorio ∈ autores`; **toda** firma presente es de un autor y válida para este mensaje;
  `len(firmas) ≥ umbral`; campos exactos (ni más ni menos); textos sin caracteres de control.
- Reglas **mientras se recolectan firmas** (fuera de la cadena): una firma inválida o de un no autor se descarta con mensaje;
  el sello entra a pendientes sólo al llegar a `umbral` firmas válidas.
- Un sello no mueve saldos. Se puede sellar el mismo `doc_hash` más de una vez (sellos distintos); la **prioridad** es del
  sello más antiguo en la cadena (menor `numero` de bloque, y dentro del bloque, menor índice).
- `Estado` agrega `sellos: dict[doc_hash, list[{"id", "numero", "indice", "timestamp", "laboratorio", "autores", "titulo", "investigador"}]]`
  en orden de cadena.

API (`models/multifirma.py`, A1):

```python
CAMPOS_SELLO: tuple
UMBRAL_MAX_AUTORES = 5
def nuevo_sello(doc_hash, titulo, investigador, laboratorio, autores, umbral, timestamp) -> dict  # sin firmas, valida formato (ErrorEntrada)
def mensaje_sello(tx) -> bytes
def id_sello(tx) -> str
def firmar_sello(tx, claves) -> str                       # firma hex del autor
def agregar_firma(tx, autor, firma, claves_publicas) -> dict   # valida y devuelve copia con la firma; ErrorEntrada si no sirve
def firmas_validas(tx, claves_publicas) -> list[str]       # autores con firma válida
def revisar_sello(estado, tx, vistos=None) -> str          # reglas estrictas; ErrorValidacion; devuelve id_sello
```

## C4 · Almacén de claves (`models/keystore.py`, A1)

Archivo JSON (`data/<nodo>/clave.json`):

```json
{
  "formato": "sellalo-clave", "version": 1, "id": "LAB-A",
  "clave_publica": "<hex 64>",
  "kdf": {"alg": "scrypt", "sal": "<hex 32>", "n": 32768, "r": 8, "p": 1, "largo": 32},
  "cifrado": {"alg": "AES-256-GCM", "nonce": "<hex 24>", "texto_cifrado": "<hex>"}
}
```

- Clave privada Ed25519 **aleatoria** (`Ed25519PrivateKey.generate()`); se cifran sus 32 bytes crudos.
- Datos asociados (AAD) de GCM = `f"sellalo-clave|{id}|{clave_publica}".encode()` → alterar id o clave pública rompe el descifrado.
- Contraseña mínima 10 caracteres. Contraseña incorrecta / archivo alterado → `ErrorClave` (subclase de `ErrorEntrada`)
  con mensaje claro, sin distinguir cuál de los dos ocurrió.
- Tras descifrar se comprueba que la clave pública derivada coincide con la del archivo.

```python
class ErrorClave(ErrorEntrada)
CONTRASENA_MIN = 10
def crear_almacen(ruta, nodo_id, contrasena) -> str                 # devuelve la clave pública; no sobrescribe uno existente
def abrir_almacen(ruta, contrasena) -> ParClaves
def leer_publica(ruta) -> tuple[str, str]                            # (id, clave_publica) sin contraseña
def cambiar_contrasena(ruta, actual, nueva) -> None                  # escritura atómica
def derivar_claves(contrasena, sal: str) -> ParClaves                # scrypt(contraseña, sal) → semilla Ed25519 (simulador)
```

`ParClaves` (en `models/cripto.py`): `ParClaves(privada: Ed25519PrivateKey)`, `ParClaves.generar()`, `.publica`, `.firmar(datos)`.
Se elimina la derivación desde la semilla pública. `__repr__` nunca muestra la clave privada.

**Simulador:** `Red(..., contrasena: str | None = None)`. Con contraseña, claves = `derivar_claves(contrasena, f"sellalo-sim|{semilla}|{consenso}|nodo|{i}")`
(reproducible); sin contraseña, `ParClaves.generar()`. La contraseña nunca se guarda en `parametros`, bitácora ni `/estado`.
Para que crear 20 nodos no tarde, `derivar_claves` usa scrypt con `n=2**14`.

## C5 · Nodo completo y red P2P (A2)

`models/nodo_completo.py`:

```python
class NodoCompleto:
    def __init__(self, dir_datos: str, genesis: dict, nodo_id: str, ruta_clave: str | None = None)
    id, genesis, cadena, estado, pendientes, revision, bitacora (deque de eventos {n, t, tipo, texto})
    lock: threading.RLock
    desbloqueado -> bool ; desbloquear(contrasena) ; bloquear()
    agregar_transaccion(tx, origen="") -> str            # valida (transferencia o sello completo) y la pone en pendientes
    recibir_bloque(bloque, de="") -> tuple[str, str]     # ("aceptado"|"duplicado"|"sincronizar"|"rechazado", motivo)
                                                         #  "sincronizar" = no enlaza con mi punta pero es más alto: pedir la cadena
    recibir_cadena(cadena, de="") -> tuple[bool, str]    # valida completa; adopta si tiene MÁS TRABAJO
    # --- interfaz que usa ServidorP2P (A2 la implementa con un nodo falso en sus pruebas) ---
    hash_genesis -> str
    clave_publica_de(nodo_id) -> str | None              # desde las cuentas del génesis
    firmar(datos: bytes) -> str                          # ErrorEstado si el nodo está bloqueado
    resumen() -> {"altura", "trabajo", "punta"}
    bloques_desde(numero: int, maximo: int = 100) -> list[dict]
    evento(tipo, texto)                                  # escribe en la bitácora
    iniciar_minado(dificultad: int) / detener_minado() / minando -> bool
    al_cambiar: list[callable]                            # callbacks (p. ej. difundir bloque nuevo)
    publico() -> dict                                     # para la UI; nunca incluye la clave privada
def trabajo(cadena) -> int                               # sum(16 ** b["dificultad"]) de bloques PoW
```

- Selección: válida → mayor trabajo → hash de punta menor. Reorganización: transacciones de los bloques descartados que no
  estén en la nueva cadena vuelven a pendientes si siguen siendo válidas.
- Persistencia en `dir_datos`: `cadena.json`, `pendientes.json` (escritura atómica con `os.replace`). Al arrancar revalida la
  cadena completa; si es inválida la renombra a `cadena.json.corrupto-<ts>` y empieza desde el génesis.
- Minado real en un hilo cancelable (`threading.Event`); requiere nodo desbloqueado (firma `firma_minero`).
- Un nodo **bloqueado** puede cargar, revalidar y mostrar su copia, pero **no puede unirse a la red** (el saludo va firmado),
  ni minar, ni firmar sellos. `ServidorP2P.iniciar()` / `conectar()` lanzan `ErrorEstado` si el nodo está bloqueado.
- Sincronización: al saludar, si el par anuncia más trabajo se piden `GET_BLOQUES desde=1` por páginas, se arma
  `[genesis] + bloques` y se llama `recibir_cadena`. Si `recibir_bloque` responde `"sincronizar"`, se hace lo mismo.
- La recompensa y las 6 confirmaciones usan `Estado` como en el simulador.

`models/red_p2p.py` — JSON por línea sobre TCP, máximo 1 MiB por línea, tiempo límite de lectura:

| Mensaje | Campos |
|---|---|
| `HELLO` | `version:2, nodo, genesis (hash), altura, trabajo, punta, reto (hex 32), puerto` |
| `HELLO_ACK` | igual que HELLO + `firma_reto` = firma de `f"{reto_recibido}|{nodo_propio}"` |
| `AUTH` | `firma_reto` del iniciador sobre `f"{reto_del_ack}|{nodo_propio}"` |
| `HELLO_REJECT` | `motivo` |
| `PING` / `PONG` | `t` |
| `GET_BLOQUES` / `BLOQUES` | `desde` / `bloques` (máx. 100 por mensaje) |
| `BLOQUE` | `bloque` |
| `TX` | `tx` (transferencia o sello completo) |
| `SELLO_PROPUESTO` | `sello` (sin firmas suficientes) |
| `SELLO_FIRMA` | `id_sello, autor, firma` |
| `BYE` | — |

- La clave pública de un par se toma del **génesis** (`cuentas[nodo].clave_publica`); génesis distinto o firma de reto
  inválida → `HELLO_REJECT` y cierre.
- Difusión por *gossip* con deduplicación por hash; un par que envía datos inválidos acumula faltas y se veta temporalmente.

```python
class ServidorP2P:
    def __init__(self, nodo: NodoCompleto, host="0.0.0.0", puerto=6000)
    iniciar() ; detener()
    conectar(ip, puerto) -> str ; desconectar(nodo_id)
    difundir(tipo, datos, excepto=None)
    registrar_manejador(tipo, fn(par_id, mensaje))       # A4 lo usa para SELLO_PROPUESTO / SELLO_FIRMA
    pares_publico() -> list[dict]                        # id, dirección, altura, punta, trabajo, latencia, estado
```

## C6 · Certificado (`models/certificado.py` + `verificar_certificado.py`, A3)

```json
{
  "formato": "sellalo-certificado", "version": 1,
  "emitido": 1767225600.0,
  "doc_hash": "<hex 64>",
  "sello": { "...transacción sello completa..." },
  "prueba_merkle": {"hoja": "<hex>", "indice": 0, "camino": [{"lado": "der", "hash": "<hex>"}]},
  "numero_bloque": 3,
  "genesis": { "...bloque génesis completo..." },
  "encabezados": [ "...encabezados 1..punta (bloques sin 'transacciones')..." ]
}
```

- `generar_certificado(cadena, doc_hash) -> dict` toma el sello **más antiguo** del documento; `ErrorEntrada` si no está sellado.
- El verificador independiente (sólo `hashlib`, `json` y `cryptography`, **sin importar el proyecto**) comprueba:
  hash del génesis (y, si se pasa `--genesis <hash>`, que coincida), cada encabezado (hash recalculado, enlace, dificultad,
  `firma_minero` con la clave del génesis), la multifirma del sello con las claves del génesis, `hoja_tx(sello)` → camino →
  `raiz_merkle` del bloque indicado, y opcionalmente `SHA-256(archivo) == doc_hash`.
  Imprime fecha del bloque, autores, laboratorio, bloque y confirmaciones; o el motivo exacto del rechazo. Código de salida 0/1.

## C7 · Rutas HTTP de la red Sellalo (A4)

Prefijo `/api/sellalo`. Todas responden `{ok, ...}` o `{ok: false, error}`; nunca 500 por datos mal formados.
El simulador conserva `/api/pow/...` y `/api/pos/...` sin cambios.

`app.py`: `--modo simulador|nodo` (por defecto `simulador`, para no romper `flask run`), y en modo nodo:
`--nodo LAB-A --datos data/LAB-A --genesis red/genesis.json --puerto-p2p 6000 --pares ip:puerto,...`.
