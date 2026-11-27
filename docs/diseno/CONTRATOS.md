# Contratos congelados · Proyecto final Sellalo

> Fase 0 del [plan](../PLAN_PROYECTO_FINAL.md). Todos los subagentes implementan **contra este documento**.
> Cambiar un contrato requiere avisar al orquestador; no se cambia en silencio.
>
> **2026-11-27: se eliminó Proof of Stake; el único consenso es PoW.** Desaparecieron `CAMPOS_POS`, `models/pos.py`
> y todo lo relativo a comité, votos, apuestas y castigos; el génesis sólo acepta `consenso == "pow"`.

Convenciones: código, identificadores y mensajes en **español**; mensajes de error claros (se muestran en la UI);
errores de entrada → `ErrorEntrada` (HTTP 400), acción fuera de estado → `ErrorEstado` (HTTP 409),
datos de red/cadena inválidos → `ErrorValidacion`. Nunca un traceback ni un 500 por datos del usuario o de un par.

---

## C1 · Bloque v2 (simulador y red Sellalo, sólo PoW)

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
| `CAMPOS_GENESIS` | comunes + `cuentas, parametros` (raíz de Merkle de la lista vacía) |

- `raiz_merkle == merkle.raiz_transacciones(bloque["transacciones"])`; si no, `ErrorValidacion("la raíz de Merkle no coincide con las transacciones")`.
- **`firma_minero`** = `claves_del_proponente.firmar(bytes.fromhex(bloque["hash"]))` (hex de 128).
  Se verifica con `estado.claves[proponente]`. Se firma **después** de encontrar el nonce (por eso no entra al hash).
  `verificar_pow(estado, bloque)` recibe ahora el estado.
- `parametros` del génesis acepta además `"red": "simulador" | "sellalo"` y `"nombre": str` (opcionales en el simulador).
- **Dificultad (AUD-004 y C9).** La dificultad ya no la elige el minero: si `parametros.dificultad` existe, el bloque `h`
  debe declarar exactamente la **dificultad vigente** (`Estado.dificultad_vigente`): la del génesis, o la que fijó el
  último ajuste co-firmado aplicado en un bloque anterior (ver C9). Sin `parametros.dificultad` (simulador) cada bloque
  declara la suya entre `DIF_MIN` y `DIF_MAX`. El trabajo acumulado sigue siendo `Σ 16^dificultad`.

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

### C5.1 · Lo que `ServidorP2P` (ya implementado) exige del nodo

- `resumen()` → `altura` y `trabajo` enteros ≥ 0, `punta` str.
- `bloques_desde(n, max)`: `n ≥ 1` es número de bloque; el génesis nunca se envía.
- `recibir_bloque` es thread-safe y rápido; **`"rechazado"` suma una falta al par**, así que bloques viejos o ya
  conocidos devuelven `"duplicado"`, nunca `"rechazado"`.
- `agregar_transaccion` lanza `ErrorEntrada`/`ErrorEstado` ante una tx inválida (cuenta como falta).
- Deduplicación: bloques por `hash`; transacciones por `tx["id"]` si existe o por el hash del JSON canónico.
- `clave_publica_de` devuelve `None` si el id no existe; `firmar` lanza `ErrorEstado` con el nodo bloqueado.
- El nodo (o su envoltura) llama `servidor.difundir("BLOQUE", {"bloque": b})` / `("TX", {"tx": tx})` para lo creado localmente.
- Al bloquear el nodo se debe llamar `servidor.detener()`; para reiniciar se crea otro `ServidorP2P`.
- Constructor real: `ServidorP2P(nodo, host, puerto, *, intervalo_ping=3, tiempo_sin_respuesta=12, tiempo_saludo=5,
  tiempo_sync=10, segundos_veto=60, max_vistos=10000)`; con `puerto=0` el puerto asignado queda en `.puerto`.
  `pares_publico()` agrega `saliente`; `estado` es `"conectado"` o `"sincronizando"`.

## C6 · Certificado (`models/certificado.py` + `verificar_certificado.py`, A3)

```json
{
  "formato": "sellalo-certificado", "version": 1,
  "emitido": 1767225600.0,
  "doc_hash": "<hex 64>",
  "sello": { "...transacción sello completa..." },
  "prueba_merkle": {"hoja": "<hex>", "indice": 0, "camino": [{"lado": "der", "hash": "<hex>"}]},
  "numero_bloque": 3,
  "ajustes": [ {"bloque": 2, "tx": { "...ajuste_dificultad completo..." }, "prueba_merkle": {"hoja": "<hex>", "indice": 1, "camino": []}} ],
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
- `ajustes` (opcional; ausente = `[]`) lista cada ajuste de dificultad de la cadena con su número de bloque y su prueba de
  Merkle. El verificador recalcula la dificultad vigente por altura (la del génesis, y desde el bloque siguiente a cada
  ajuste probado: firmas válidas de laboratorios del génesis, más de la mitad, inclusión en la raíz del bloque) y exige que
  cada encabezado la use: un encabezado que cambia de dificultad sin un ajuste probado hace el certificado **no válido**.

## C7 · Aplicación en modo nodo y rutas HTTP de la red Sellalo (A4 implementa, A6 consume)

### Arranque

- `python app.py` / `flask run` → **modo simulador** (como hoy; `/` es el simulador PoW).
- `python app.py --modo nodo --nodo LAB-A --datos data/demo/LAB-A --genesis data/demo/genesis.json --puerto 5001 --puerto-p2p 6001 --pares 127.0.0.1:6002,127.0.0.1:6003 [--host 127.0.0.1] [--clave data/demo/LAB-A/clave.json]`
  → **modo nodo**: `/` es la página Sellalo (`views/templates/sellalo.html`), `/simulador` el simulador.
  La clave por defecto es `<datos>/clave.json`. El nodo arranca **bloqueado**; al desbloquearse inicia el `ServidorP2P`
  (`0.0.0.0:<puerto-p2p>`) y se conecta a `--pares` (los fallos de conexión van a la bitácora, no detienen nada).
- En modo simulador, `/api/sellalo/*` responde 409 `"Este proceso no es un nodo Sellalo; arráncalo con --modo nodo."`.
- `MAX_CONTENT_LENGTH` = 25 MiB (documentos). El contenido del documento **nunca** se guarda ni se transmite: sólo su SHA-256.

### Rutas (`controllers/sellalo.py`, prefijo `/api/sellalo`)

Respuesta: `{ok: true, mensaje?, ...}` o `{ok: false, error}` con 400/409; nunca 500 por datos del usuario.
`archivo` = campo multipart; si en su lugar llega `doc_hash` (hex 64) se usa tal cual.

| Método | Ruta | Entrada | Salida |
|---|---|---|---|
| GET | `/estado` | — | `nodo` (= `NodoCompleto.publico()`), `pares` (= `pares_publico()` o `[]`), `red` `{nombre, hash_genesis, puerto_p2p, direcciones}` (IPs locales), `laboratorios` `[{id, clave_publica}]`, `sellos_en_firma` (ver abajo), `solicitudes` (sellos en firma donde soy autor y aún no firmé) |
| POST | `/desbloquear` | `{contrasena}` | inicia P2P y conecta a los pares configurados |
| POST | `/bloquear` | — | detiene minado y P2P |
| POST | `/pares` | `{ip, puerto}` | `{par}` |
| POST | `/pares/<id>/desconectar` | — | |
| POST | `/sellos` | multipart `archivo` o `doc_hash`, `titulo`, `investigador`, `autores` (lista o CSV; debe incluir al propio nodo), `umbral` | `{sello: {id, doc_hash, estado: "en_firma"\|"pendiente", firmas, umbral}}` — el nodo firma de inmediato; si `umbral == 1` pasa directo a pendientes y se difunde como `TX`; si no, se difunde `SELLO_PROPUESTO` |
| POST | `/sellos/<id>/firmar` | — | agrega mi firma, difunde `SELLO_FIRMA`; al llegar al umbral el nodo que lo completa lo agrega a pendientes y lo difunde como `TX` |
| GET | `/dificultad` | — | ver C9 |
| POST | `/dificultad/proponer` | `{dificultad}` | `{ajuste: {id, dificultad, estado: "en_firma"\|"pendiente", firmas, umbral}}` |
| POST | `/dificultad/<id>/firmar` | — | agrega mi firma; al llegar a la mayoría pasa a pendientes |
| POST | `/minar` | `{dificultad, continuo}` | |
| POST | `/minar/detener` | — | |
| POST | `/transferencias` | `{receptor, monto}` | `{id}` |
| POST | `/prioridad` | multipart `archivo` o `doc_hash` | `{doc_hash, sellos: NodoCompleto.prioridad(...)}` (`sellos: []` si no está sellado) |
| GET | `/certificado/<doc_hash>` | — | descarga `certificado-<8 hex>.json` (`Content-Disposition: attachment`); 400 si no está sellado |
| POST | `/certificado/verificar` | multipart `certificado` (JSON) y opcional `documento` | `{valido, motivo, detalle, resumen}` usando `verificar_certificado.verificar` |
| POST | `/ataques` | `{tipo, destino: "local"\|"red"}`; `tipo` ∈ `sello_alterado`, `firma_falsa`, `merkle_falsa`, `cadena_corta`, `multifirma_incompleta`, `firma_minero_ajena` | `{rechazado: bool, motivos: [...]}` — construye una copia manipulada de la cadena/bloque y la entrega al propio nodo (`local`) o la envía a los pares (`red`); en ningún caso cambia la cadena honesta |

`sellos_en_firma[]`: `{id, doc_hash, titulo, investigador, laboratorio, autores, umbral, firmas: [ids], faltan: n, creado}`.
Persistencia en `<datos>/sellos_en_firma.json` (escritura atómica). Coordinación en `models/coordinador_sellos.py`
(`CoordinadorSellos(nodo, servidor)`), que registra los manejadores `SELLO_PROPUESTO` y `SELLO_FIRMA` del transporte.


## C8 · La rúbrica en la interfaz (rutas de verificación, clave, consenso, auditoría y rúbrica)

Contrato completo y auditoría en [`docs/RUBRICA_EN_INTERFAZ.md`](../RUBRICA_EN_INTERFAZ.md) (§3). Implementado en
`controllers/sellalo.py`, `models/rubrica.py` y `models/verificacion_detallada.py`. Resumen:

| Método | Ruta | Contenido |
|---|---|---|
| GET | `/estado` | además: `nodo.dificultad_red`, `nodo.trabajo`, `nodo.consenso`, `nodo.persistencia`, `consistencia`, `sesion`, `recorrido` (10 pasos) |
| GET | `/verificacion` | auditoría de la copia local, comprobación por comprobación (sin detenerse en el primer error) |
| POST | `/verificacion/simular` | `{tipo, bloque}` sobre una **copia**; `cadena_real_intacta`; es la única escritura nueva |
| GET | `/clave` | metadatos públicos del almacén (sin sal, nonce ni texto cifrado), `intentos_fallidos`, `espera_s` |
| POST | `/certificado/verificar` | además: `pasos` y `merkle` |
| GET | `/auditoria` · `/entrega` · `/rubrica` | estado de la auditoría con IA, entregables y tablero R1-R8 + EX |

Precisiones de la implementación (sin cambiar los campos del contrato):

- `NodoCompleto.iniciar_minado(dificultad=None, continuo=False)`: si el génesis fija `parametros.dificultad` se usa la
  vigente (la del génesis o la del último ajuste aplicado, C9); otra distinta es `ErrorEntrada`. `POST /minar` sin `dificultad` funciona con ese génesis.
- `desbloquear`: contador de contraseñas incorrectas seguidas y espera 0, 1, 2, 4... s (máx. 30) antes del siguiente
  intento, fuera del candado del nodo y del contexto. `/clave` la expone.
- `pasos[].ok` es `true`/`false` si el paso se evaluó y `null` (con `evaluado: false`) si no se llegó a él (falló uno
  anterior) o no había datos (documento no entregado). `merkle` es `null` si no se llegó al paso de Merkle.
- `/verificacion` agrega `genesis` `{hash, ok}`, `dificultad_red` y `otras_reglas` `{ok, error}` (el validador del nodo
  se ejecuta además, por si una regla no itemizada falla). Tipos de alteración: `transaccion`, `firma_tx`, `hash`,
  `enlace`, `merkle`, `firma_minero`, `multifirma`, `nonce`; `COMPROBACIONES_ESPERADAS` dice cuáles deben fallar.
- `reorganizaciones` registra **toda** cadena adoptada vía `recibir_cadena`; hay reorganización real cuando
  `bloques_descartados > 0`.
- Ids de sección de `/rubrica`: R1 `seccion-firmas`, R2 `seccion-verificacion`, R3 `seccion-identidad`, R4
  `seccion-consenso`, R5 `seccion-red`, R6 `seccion-prioridad`, R7 `seccion-recorrido`, R8 `seccion-entrega`,
  EX `seccion-auditoria`.
- Estados de un criterio: `demostrado` = todas sus evidencias en ok; `parcial` = alguna; `pendiente` = ninguna
  (condiciones de cada una en la docstring de `models.rubrica.criterios`).
- `docs/auditoria/estado.json` lo genera `scripts/estado_auditoria.py` (HALLAZGOS.md + TRIAJE.md + `git log`).

---

## C9 · Ajuste de dificultad co-firmado

La dificultad de la red nació fija en el génesis (AUD-004): ya no la elige el minero. Para poder volver más lento (o más
rápido) el minado **sin reiniciar la red ni perder la cadena**, la dificultad vigente puede cambiar únicamente por
**acuerdo de la mayoría de los laboratorios registrado en la cadena**. Sólo existe en redes cuyo génesis fija
`parametros.dificultad`; en el simulador no hay ajustes.

### Transacción `ajuste_dificultad` (no mueve saldos)

```json
{"tipo": "ajuste_dificultad", "dificultad": 5, "proponente": "LAB-A", "timestamp": 1767225600.0,
 "firmas": {"LAB-A": "<hex 128>", "LAB-B": "<hex 128>"}}
```

- Mensaje firmado = `models.cripto.canonico` de todos los campos salvo `firmas`; id = SHA-256 de ese mensaje (como en C3).
- Reglas estrictas dentro de un bloque (`models/ajuste_dificultad.py::revisar_ajuste`): campos exactos;
  `DIF_MIN ≤ dificultad ≤ DIF_MAX` (enteros, no booleanos); distinta de la vigente; `proponente` está en el génesis y
  firmó; toda firma presente es válida y de un laboratorio del génesis; firmas válidas **> n/2** (n = laboratorios del
  génesis; con 3 laboratorios bastan 2); a lo sumo un ajuste por bloque; su id no está en `estado.tx_ids`.
- **Vigencia.** `Estado.dificultad_vigente` (inicial = parámetro del génesis o `None`) y `Estado.ajustes`
  (`{numero, dificultad_anterior, dificultad, proponente, firmantes, id}`). El bloque `h` que contiene el ajuste se valida
  con la dificultad anterior; la nueva rige **desde el bloque `h+1`**. Si una reorganización descarta el bloque del ajuste,
  la vigente vuelve a la anterior (el estado se recalcula desde el génesis) y el ajuste regresa a pendientes si sigue
  siendo válido. Un ajuste pendiente que queda obsoleto (ya aplicado o igual a la vigente) se descarta.
- Nodo: `iniciar_minado` y la plantilla del minado usan la vigente (el minado continuo la relee en cada bloque);
  `publico()` agrega `dificultad_red` (= vigente), `dificultad_genesis` y `ajustes`.

### Co-firma por P2P (`models/coordinador_ajustes.py`)

Mismo patrón que los sellos: `AJUSTE_PROPUESTO {ajuste}` (lo difunde el proponente, ya firmado) y
`AJUSTE_FIRMA {id_ajuste, lab, firma}`. Quien completa la mayoría lo agrega a sus pendientes (se difunde como `TX`).
Persistencia atómica en `<datos>/ajustes_en_firma.json`; caducan a las 24 h; una propuesta nueva reemplaza a la
pendiente del mismo proponente; datos inválidos quedan en la bitácora (tipo `dificultad`) y nunca lanzan al transporte.

### API (`/api/sellalo`; las escrituras pasan por la defensa CSRF/Host de siempre)

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/dificultad` | `{vigente, genesis, minimo, maximo, umbral, laboratorios, ajustes, en_firma, solicitudes}`; `en_firma[]` = `{id, dificultad, proponente, firmas: [ids], umbral, faltan, creado, firmado_por_mi}`; `solicitudes` = las que aún no firmé. También viaja en `GET /estado` como `dificultad` |
| POST | `/dificultad/proponer` `{dificultad}` | 400 si no es un entero entre `minimo` y `maximo`; 409 si el nodo está bloqueado, la red no fija la dificultad o ya es la vigente |
| POST | `/dificultad/<id>/firmar` | 400 si el id no es un hash; 409 si el nodo está bloqueado, ya firmó o la propuesta no existe, caducó o quedó obsoleta |

### Verificación

`verificacion_detallada` evalúa cada ajuste (firmas, mayoría, rango y distinta de la vigente) y exige a cada bloque la
dificultad vigente calculada en la propia recorrida (`dificultad_final`, `ajustes`). La rúbrica R4 muestra la evidencia
informativa «ajustes de dificultad co-firmados aplicados: n» (no se exige haber ajustado). El certificado y el
verificador independiente: ver C6.
