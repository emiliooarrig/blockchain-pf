# P3b · Errores de lógica y manejo de excepciones: núcleo

Módulos revisados: `models/bloque.py`, `validacion.py`, `pow.py`, `pos.py`, `red.py`, `simulador.py`, `ataques.py`,
`multifirma.py`, `keystore.py`, `cripto.py`, `merkle.py`, `certificado.py`, `verificar_certificado.py`,
`controllers/api.py` y `controllers/entradas.py`.

Los hallazgos P3b-1 a P3b-6, P3b-8 y P3b-9 se reprodujeron con scripts temporales fuera del repositorio. No se modificó ningún
archivo del repositorio.

`cripto.py`, `merkle.py`, `simulador.py` y `certificado.py` no dieron hallazgos propios. La verificación de firmas, la
construcción de la prueba de Merkle y el uso de `copia()` antes de validar son correctos. `Estado.copia()` basta para que
`validar_bloque` no deje estado a medias en `nodo_completo` ni en `red`.

---

### P3b-1. PoS: el comité de validadores lo declara el propio proponente; un solo nodo fabrica bloques válidos
- Categoría: Error de lógica
- Severidad: Alta
- Ubicación: `models/pos.py:81-131`, `models/pos.py:134-157`, `models/validacion.py:45-48`
- Confianza: Seguro (reproducido)
- Evidencia: `verificar_pos` toma `validadores` del propio bloque. Sólo exige que los ids existan, estén ordenados, que
  `apuesta > 0` y que `apuesta <= saldo`. `verificar_votos` calcula el 2/3 sobre `restantes`, que sale de ese mismo campo.
  Ninguna regla liga el comité a "todos los nodos con saldo", ni a un tamaño mínimo, ni a un quórum.
- Escenario de falla: el nodo N00 arma el bloque 1 con `validadores=[{"id":"N00","apuesta":1}]`, `intento=0`, se autosortea
  (es el único candidato), firma la propuesta y adjunta su propio voto. `validar_cadena([génesis, bloque])` devuelve el estado
  sin error (se ejecutó: "ACEPTADO comité de 1", altura 1). Esperado: rechazo, porque no está el resto de la red y no
  hay 2/3 de la apuesta real de la red. Un nodo puede producir toda la cadena PoS solo y, al ser la "más larga", imponerla.
- Corrección propuesta: derivar el comité del estado de la cadena en lugar de leerlo del bloque. Por ejemplo, el comité es
  el conjunto de nodos con saldo ≥ umbral (o un sorteo con semilla pública); el bloque sólo lleva las apuestas y se verifica
  que cada id del comité esté presente. Exigir además un quórum mínimo de peso, medido contra el saldo total de la red, no
  contra el comité autodeclarado.

### P3b-2. PoS: castigos y rondas rechazadas no tienen prueba; el proponente puede castigar a otros y re-sortearse
- Categoría: Error de lógica
- Severidad: Alta
- Ubicación: `models/pos.py:61-76` (`_revisar_castigo`), `models/pos.py:98-125`, `models/pos.py:110-113`
- Confianza: Seguro (reproducido)
- Evidencia: los castigos de "rondas anteriores" (`castigos[:corte]`) sólo se comprueban en formato, en que `monto` coincida
  con la fórmula y en que `saldo >= apuesta`, y luego se descuentan de `estado.saldos`. `hash_propuesta`, `valor_transacciones`,
  `regla` y `alfa_pct` son libres; no hay votos ni firma que demuestren que esa ronda fracasó. Con `excluidos` pasa lo
  mismo: basta que cada excluido coincida con el sorteo determinista del intento `k`, que cualquiera puede calcular.
- Escenario de falla:
  1. N00 no ganó el sorteo del intento 0. Calcula la secuencia de sorteos, declara `excluidos=[N06, N00-previos…]` con castigos
     inventados (regla A, `apuesta` completa), fija `intento=k` y se pone él como proponente. `validar_cadena` lo acepta
     (se ejecutó con N09: excluidos falsos N06 y N00, saldos castigados 90 y 89). Se descuentan fondos a nodos honestos
     que nunca fallaron, y los excluidos pierden su voto, así que ya no cuentan en el 2/3.
  2. Sin necesidad de sorteo: un `castigos` con `{"validador":"N05","apuesta":100,"monto":100,"regla":"A",…}` en un bloque
     válido deja a N05 en saldo 0 (aceptado en la prueba). Los validadores honestos votan a favor porque
     `evaluar_propuesta` usa la misma validación.
  Esperado: el castigo debe poder verificarse (propuesta rechazada con sus votos) o no existir.
- Corrección propuesta: no aceptar castigos "de rondas anteriores" como dato libre. Cada castigo debe ir acompañado de la
  propuesta rechazada (hash, firma del proponente y votos en contra que suman >1/3). Alternativa más simple: eliminar los
  castigos del bloque y que las rondas fallidas sólo afecten al `intento`, sin tocar saldos. Fijar `regla`/`alfa_pct` en
  `parametros` del génesis y comprobarlos, y recalcular `valor_transacciones` desde la propuesta.

### P3b-3. PoS: `intento` y `monto` sin tipo estricto; un proponente obtiene varios sorteos distintos para el mismo bloque
- Categoría: Error de lógica
- Severidad: Media
- Ubicación: `models/pos.py:115`, `models/pos.py:119`, `models/pos.py:123`, `models/pos.py:29-36`, `models/pos.py:71-72`, `models/bloque.py:121-128`
- Confianza: Seguro (reproducido)
- Evidencia: `revisar_campos` no verifica el tipo de `intento`. `verificar_pos` sólo compara `bloque["intento"] != len(excluidos)`,
  y `False == 0`, `0.0 == 0` y `-0.0 == 0`. `sortear` siembra con `f"{hash_anterior}|{numero}|{intento}"`, así que
  `"0"`, `"False"`, `"0.0"` y `"-0.0"` dan semillas distintas. De igual forma, `castigo["monto"]` se compara con `!=`, de modo
  que `10.0` o `True` pasan donde se espera `10` o `1`.
- Escenario de falla: con un bloque sin excluidos, `sortear(..., 0)` elige N05, pero `sortear(..., False)` elige N02 y
  `sortear(..., 0.0)` elige N00 (salida real de la prueba). N02 construye el bloque con `intento=False` y se acepta ("ACEPTADO
  intento=False"). Un proponente tiene así hasta 4 tiradas del sorteo en lugar de 1. Con `monto=10.0` los saldos se
  vuelven `float` en el estado.
- Corrección propuesta: en `verificar_pos` exigir `es_entero(bloque["intento"])` y `es_entero(c["monto"])` (y
  `es_entero(voto["peso"])`), y sembrar el sorteo con `int(intento)`.

### P3b-4. `es_numero` lanza `OverflowError` con enteros enormes y la excepción escapa de la validación
- Categoría: Manejo de excepciones
- Severidad: Media
- Ubicación: `models/bloque.py:39-40`, `models/validacion.py:91`, `models/red.py:88-101`, `models/red.py:107-115`, `models/multifirma.py:52`, `models/bloque.py:190`, `models/nodo_completo.py:166`
- Confianza: Seguro en `validar_cadena` y `Nodo.recibir_cadena` (reproducido); Posible en los demás sitios de llamada
- Evidencia: `es_numero` hace `math.isfinite(v)` sobre un `int`. Con `10**400` lanza `OverflowError: int too large to convert to float`.
  `validar_cadena` sólo convierte `TypeError, KeyError, ValueError, AttributeError` en `ErrorValidacion`.
- Escenario de falla: un bloque con `"timestamp": 1e400 escrito como entero de 400 dígitos` (JSON válido). En `Nodo.recibir_cadena`
  de `red.py` la excepción sale sin capturar (se ejecutó: `ESCAPA OverflowError`) y la petición termina en 500 en lugar de
  "cadena rechazada". `nuevo_sello(..., timestamp=10**400)` y `revisar_transaccion` tienen el mismo defecto.
  `nodo_completo._cargar` no incluye `OverflowError` en su lista de excepciones: un `cadena.json` alterado a mano con ese valor tumba el
  arranque del nodo en lugar de moverlo a `.corrupto-…`. En `nodo_completo.recibir_cadena` y `recibir_bloque` sí hay
  `except Exception`, por eso ahí no escapa. Habría que comprobar qué ocurre en `coordinador_sellos._normalizar` (P3a), que invoca
  `nuevo_sello` con el timestamp de un sello recibido por la red.
- Corrección propuesta: en `es_numero`, `try: return type(v) in (int, float) and math.isfinite(v) except OverflowError: return False`.
  Además, añadir `OverflowError` y `RecursionError` a la conversión de `validar_cadena` y a la lista de `_cargar`.

### P3b-5. El verificador de certificados no comprueba ninguna regla de tiempo ni trabajo mínimo: se puede falsificar la fecha de prioridad
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `verificar_certificado.py:339-363`, `verificar_certificado.py:408`, `verificar_certificado.py:247`
- Confianza: Seguro (reproducido)
- Evidencia: el bucle de encabezados verifica hash, enlace, numeración, `dificultad` entre 1 y 6 y firma del minero. No comprueba
  `timestamp >= timestamp del bloque previo`, ni `>= timestamp del génesis`, ni que el timestamp sea un número finito razonable. El
  nodo sí exige monotonía (`validacion.py:33`). La dificultad 1 basta, así que tanto el "trabajo" como el número de
  `confirmaciones` del certificado cuestan unos 16 hashes por bloque.
- Escenario de falla: quien tiene la clave de un nodo del génesis (un laboratorio de la red) arma una rama privada con
  `dificultad=1`, timestamps `0, -5, 3, 1` y un sello firmado por él mismo con umbral 1. `verificar(cert, None, hash_génesis)` devuelve
  `valido=True, "certificado válido", fecha 1970-01-01 00:00:00 UTC, confirmaciones 3`. Esperado: rechazo por
  timestamps no monótonos o anteriores al génesis. Así se puede reivindicar prioridad con una fecha inventada.
- Corrección propuesta: en el bucle exigir `es_numero(ts)`, `ts >= ts_previo` (empezando por el timestamp del génesis) y, opcionalmente,
  `ts <= emitido + margen`. Documentar y, mejor, parametrizar una dificultad mínima (`--dif-min`) o el trabajo acumulado
  mínimo para las confirmaciones.

### P3b-6. La CLI del verificador da "CERTIFICADO VÁLIDO" sin anclar la red cuando se omite `--genesis`
- Categoría: Procedimiento incompleto
- Severidad: Media
- Ubicación: `verificar_certificado.py:333-335`, `verificar_certificado.py:447-462`
- Confianza: Seguro
- Evidencia: `genesis_esperado` es opcional. Si falta, sólo se comprueba que el génesis del propio certificado sea coherente. La
  salida imprime `CERTIFICADO VÁLIDO` y, al final, `Génesis: <hash>` sin advertencia de que la red no se verificó.
- Escenario de falla: un tercero fabrica su propio génesis, claves, bloques de dificultad 1 y un sello. `python verificar_certificado.py falso.json`
  imprime `CERTIFICADO VÁLIDO` con título, investigador y laboratorio arbitrarios. Esperado: que el resultado deje claro
  "válido, pero la red no fue confirmada". (La ruta web `controllers/sellalo.py` devuelve `misma_red`, así que ahí el dato existe; la CLI no.)
- Corrección propuesta: sin `--genesis`, imprimir `CERTIFICADO COHERENTE (red no confirmada: use --genesis HASH)` y devolver un código de salida
  distinto (por ejemplo 3), o exigir `--genesis`/`--confiar-en-genesis-del-certificado` de forma explícita.

### P3b-7. Simulador PoW: la cadena "más larga" gana sin considerar trabajo y la dificultad la elige cada bloque
- Categoría: Error de lógica
- Severidad: Baja
- Ubicación: `models/red.py:96-100`, `models/pow.py:33-42`
- Confianza: Posible (no alcanzable desde la API actual; habría que añadir un caso de ataque que inyecte una cadena)
- Evidencia: `Nodo.recibir_cadena` adopta por `len(copia) > len(self.cadena)`. `verificar_pow` acepta cualquier
  `dificultad` de 1 a 6 declarada en el propio bloque; el génesis no fija una dificultad de red. `nodo_completo` sí usa trabajo acumulado
  (`16**dificultad`), pero la red simulada no.
- Escenario de falla: un nodo mina 12 bloques con `dificultad=1` y presenta una cadena más larga que la honesta de 10 bloques con
  dificultad 4. Los demás la adoptan: reorganización con una fracción del trabajo (esperado: rechazo, menos trabajo).
- Corrección propuesta: reutilizar `trabajo()` de `nodo_completo` para decidir en `Nodo.recibir_cadena` o fijar la dificultad en `parametros`
  del génesis y comprobarla en `verificar_pow`.

### P3b-8. `verificar_certificado.py main` termina con traceback en JSON profundamente anidado
- Categoría: Manejo de excepciones
- Severidad: Baja
- Ubicación: `verificar_certificado.py:433-438`
- Confianza: Seguro (reproducido)
- Evidencia: `json.load` sólo se protege con `except (OSError, ValueError)`; `RecursionError` no es `ValueError`.
- Escenario de falla: un archivo con 100 000 corchetes `[` produce `RecursionError: Stack overflow` con traceback. El contrato de
  la CLI dice "2 archivo ilegible o que no es JSON"; el código de salida real es 1 y se muestra un traceback.
- Corrección propuesta: `except (OSError, ValueError, RecursionError)`.

### P3b-9. Contraseña con sustituto Unicode suelto provoca `UnicodeEncodeError` sin controlar (500)
- Categoría: Manejo de excepciones
- Severidad: Baja
- Ubicación: `models/keystore.py:38-45`, `models/keystore.py:55`, `models/keystore.py:170-173`, `controllers/entradas.py:337-348`
- Confianza: Seguro (reproducido)
- Evidencia: `_validar_contrasena` y `entradas.contrasena` sólo comprueban tipo y longitud. `_kdf` hace `contrasena.encode("utf-8")` y un
  `"\ud800"` suelto (admitido por `json.loads`) lanza `UnicodeEncodeError`. En `_abrir` se captura como `ValueError`, pero en `_documento` y
  `derivar_claves` no.
- Escenario de falla: `POST /api/pow/simulacion {"n":10,"contrasena":"\ud800aaaaaaaaaaaa"}` devuelve 500
  "Error interno inesperado (UnicodeEncodeError)". Esperado: 400 "La contraseña contiene caracteres no válidos".
- Corrección propuesta: en `_validar_contrasena` y en `entradas.contrasena`, hacer `valor.encode("utf-8")` dentro de un `try` y lanzar
  `ErrorClave`/`ErrorEntrada`. En `derivar_claves`, validar también `sal`.

### P3b-10. El tope de scrypt aceptado al abrir un almacén permite pedir ~2 GiB de memoria por llamada
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `models/keystore.py:27`, `models/keystore.py:116-117`
- Confianza: Posible (hay que medir el uso real en la plataforma)
- Evidencia: `N_MAX_ACEPTADO = 2**20` y `r <= 16`, `p <= 4`. La memoria de scrypt es ≈ `128·N·r` = 2 GiB (y CPU ×p). El comentario afirma que
  un archivo alterado "no puede pedir una cantidad absurda de memoria".
- Escenario de falla: un `clave.json` con `n=1048576, r=16, p=4` y campos válidos obliga a `abrir_almacen`/`cambiar_contrasena` a gastar
  varios GiB y decenas de segundos antes de fallar el descifrado; el servicio se queda sin memoria. Esperado: rechazo inmediato.
- Corrección propuesta: acotar los parámetros a los que la propia aplicación escribe (`n <= 2**16`, `r == 8`, `p == 1`) o al menos limitar `128·n·r·p` a unos 64 MiB.

### P3b-11. `crear_almacen`: comprobación de existencia y reemplazo no son atómicos
- Categoría: Error de lógica
- Severidad: Baja
- Ubicación: `models/keystore.py:129-133`, `models/keystore.py:87`
- Confianza: Posible
- Evidencia: se hace `os.path.exists(ruta)` y después `_escribir`, que termina con `os.replace(temporal, ruta)` (sobrescribe).
- Escenario de falla: dos procesos lanzan `crear_identidad` con la misma ruta casi a la vez; ambos ven que no existe y el segundo
  reemplaza al primero. El primero ya mostró su clave pública y se pierde la clave privada correspondiente, sin aviso.
- Corrección propuesta: publicar con `os.link(temporal, ruta)` (falla si existe) y borrar el temporal, o abrir el destino con `O_EXCL`.

### P3b-12. `POST /transacciones/aleatoria` devuelve error tras haber creado parte de las transacciones
- Categoría: Manejo de excepciones
- Severidad: Baja
- Ubicación: `controllers/api.py:95-108`, `models/red.py:197-198`
- Confianza: Seguro (por lectura; requiere saldos altos para llegar a 200 pendientes)
- Evidencia: el bucle llama `red.transaccion_aleatoria()` hasta `cantidad` veces. `agregar_pendiente` lanza `ErrorEstado` cuando hay 200 pendientes y no se captura dentro del bucle.
- Escenario de falla: 195 pendientes y `cantidad=20`: se crean 5, la sexta lanza `ErrorEstado` y la respuesta es 409
  "La lista de pendientes está llena" sin decir que 5 ya se agregaron. Esperado: 200 con "5 creadas; la lista se llenó".
- Corrección propuesta: capturar `ErrorEstado` dentro del bucle, cortar y, si `creadas > 0`, responder con el conteo y el aviso.

### P3b-13. Endpoints sin parámetros rechazan un POST con `Content-Type: application/json` y cuerpo vacío
- Categoría: Error de lógica
- Severidad: Baja
- Ubicación: `controllers/entradas.py:266-274`, `controllers/api.py:171-230`
- Confianza: Seguro (reproducido)
- Evidencia: `datos()` trata un cuerpo JSON ausente (`get_json(silent=True)` devuelve `None`) como error. Las rutas `/pos/ronda`, `/pos/sortear`, `/pos/cerrar`,
  etc. llaman `datos()` sólo para descartar el cuerpo.
- Escenario de falla: `curl -X POST -H "Content-Type: application/json" /api/pos/pos/ronda` (sin cuerpo) devuelve 400 "El cuerpo de la petición no es JSON válido";
  sin la cabecera funciona. La interfaz sí envía `{}`, por eso no se nota allí.
- Corrección propuesta: en esas rutas no llamar `datos()`, o hacer que `datos()` devuelva `{}` cuando el cuerpo está vacío.

### P3b-14. El laboratorio de ataques mina hasta 3 000 000 de hashes con `red.lock` tomado
- Categoría: Otro
- Severidad: Baja
- Ubicación: `models/ataques.py:46-51`, `models/ataques.py:190-200`
- Confianza: Posible (depende de la velocidad de hash de la máquina)
- Evidencia: `atacar_cadena` ejecuta `_FABRICAS[tipo](...)` dentro de `with red.lock`, y `_minar` itera hasta `LIMITE_MINADO_ATAQUE` usando la dificultad de la configuración (hasta 6, ≈16 M de intentos esperados).
- Escenario de falla: con dificultad 5 o 6 la prueba suele agotar el límite tras varios segundos. Mientras tanto toda la simulación (estado, transacciones, minado) está bloqueada, y al final se lanza `ErrorEstado` sin
  que el usuario pueda cancelar.
- Corrección propuesta: minar el bloque falso fuera del lock con una copia de lo necesario, o fijar para el ataque una dificultad máxima baja (por ejemplo `min(dificultad, 3)`).

---

## Tabla resumen

| id | título | categoría | severidad | ubicación |
|---|---|---|---|---|
| P3b-1 | PoS: comité autodeclarado, un solo nodo fabrica bloques válidos | Error de lógica | Alta | `models/pos.py:81-157`, `models/validacion.py:45-48` |
| P3b-2 | PoS: castigos y rondas rechazadas sin prueba (castigo falso, re-sorteo) | Error de lógica | Alta | `models/pos.py:61-76`, `models/pos.py:98-125` |
| P3b-3 | PoS: `intento`/`monto` sin tipo estricto (varios sorteos por bloque) | Error de lógica | Media | `models/pos.py:115-123`, `models/pos.py:29-36`, `models/bloque.py:121-128` |
| P3b-4 | `es_numero` lanza `OverflowError` que escapa de la validación | Manejo de excepciones | Media | `models/bloque.py:39-40`, `models/validacion.py:91`, `models/red.py:88-115`, `models/nodo_completo.py:166` |
| P3b-5 | Verificador sin reglas de tiempo ni trabajo mínimo (fecha falsificable) | Seguridad | Media | `verificar_certificado.py:339-363` |
| P3b-6 | CLI da "VÁLIDO" sin anclar la red si falta `--genesis` | Procedimiento incompleto | Media | `verificar_certificado.py:333-335`, `verificar_certificado.py:447-462` |
| P3b-7 | Simulador PoW: gana la cadena más larga y la dificultad es libre por bloque | Error de lógica | Baja | `models/red.py:96-100`, `models/pow.py:33-42` |
| P3b-8 | `main` del verificador con traceback ante JSON muy anidado | Manejo de excepciones | Baja | `verificar_certificado.py:433-438` |
| P3b-9 | Contraseña con sustituto Unicode provoca `UnicodeEncodeError` (500) | Manejo de excepciones | Baja | `models/keystore.py:38-55`, `models/keystore.py:170-173` |
| P3b-10 | Tope de scrypt aceptado permite ~2 GiB por llamada | Seguridad | Baja | `models/keystore.py:27`, `models/keystore.py:116-117` |
| P3b-11 | `crear_almacen`: existencia y reemplazo no atómicos | Error de lógica | Baja | `models/keystore.py:129-133`, `models/keystore.py:87` |
| P3b-12 | `transacciones/aleatoria` falla tras crear parte | Manejo de excepciones | Baja | `controllers/api.py:95-108` |
| P3b-13 | POST JSON con cuerpo vacío rechazado en rutas sin parámetros | Error de lógica | Baja | `controllers/entradas.py:266-274` |
| P3b-14 | Ataques minan con `red.lock` tomado | Otro | Baja | `models/ataques.py:46-51`, `models/ataques.py:190-200` |
