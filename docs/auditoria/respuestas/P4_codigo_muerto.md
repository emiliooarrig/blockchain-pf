# P4 · Código muerto y duplicado

Repositorio `blockchain-pf`, rama `proyecto-final`. Sólo lectura; únicamente se escribió este archivo.

## Cómo se comprobó

Todas las herramientas fueron scripts temporales fuera del repositorio, ejecutados con el `.venv`, más `grep`.

1. **Definiciones Python sin uso.** Con `ast` se listaron todas las funciones, clases, métodos y constantes de módulo de los archivos `*.py` versionados. Para cada nombre se contaron las apariciones como palabra completa (`\bnombre\b`) en todo el código de producción y por separado en `tests/`.
   - Se revisaron a mano los nombres con 1 aparición (sólo la definición) y con 2 apariciones (unos 130 nombres).
   - Los que resultaron ser manejadores de ruta Flask se descartaron como código muerto, porque el decorador `@api.post`, `@sellalo.get` y similares los registra.
2. **Métodos de clase.** Se repitió la cuenta sólo para métodos, buscando uso fuera de su definición. Salió un único caso: `faltas_de`.
3. **Atributos `self.x = ...` que nunca se leen.** Se buscó `.x` en producción y la clave `"x"` en diccionarios serializados. No salió ninguno.
4. **Imports sin uso.** Con `ast` se compararon los nombres importados contra sus apariciones en el archivo (equivalente a pyflakes, que no está instalado).
5. **Rutas HTTP sin consumidor.** Se contrastó cada `@api.*`, `@sellalo.*` y `@paginas*.*` (`controllers/`) con las URL usadas en `views/static/app.js`, `views/static/sellalo.js`, las pruebas y el README.
6. **JS.** Se contó cada `function` y cada `const/let` en `app.js` y `sellalo.js` frente a ambos JS y ambas plantillas. No hay funciones JS huérfanas.
7. **CSS.** Se extrajeron todas las clases de `styles.css` y se buscaron en JS y HTML. Antes de dar una clase por muerta se descartó que se construya dinámicamente (`toast-${tipo}`, `status-${estado}`, `ev-${tipo}`, `chip-${papel}`, `papel-${papel}`). Para los `ev-*` se listaron los tipos reales pasados a `evento(...)` en `models/`.
8. **IDs HTML.** Los `id=` sin referencia en JS o CSS son anclas ARIA (`t-*`, `seccion-*`) o contenedores. Salvo `#minado-stats` y `#app` no se consideraron hallazgos.
9. **Duplicados sim/red real.** Lectura comparada de `models/red.py`, `pow.py` y `pos.py` (simulador) frente a `nodo_completo.py`, `red_p2p.py`, `coordinador_sellos.py` (red real), de `ataques.py` frente a `ataques_sellalo.py`, de `verificar_certificado.py` frente a `merkle.py`, y de `scripts/demo_e2e.py` frente a `scripts/lanzar_red_local.py`. También se buscaron funciones homónimas (`def _rango`, `def esperar`, `def _ok`, `copia_json`).

**Conclusión general:** el código de producción está muy limpio. Todas las constantes (`HASH_CERO`, `TIPOS_BASE`, `MAX_BLOQUES_SYNC`, `CAMPOS_VOTO`, etc.), las clases y las funciones públicas tienen al menos un uso real. Lo muerto es poco y de bajo riesgo. Lo más relevante es la duplicación entre el simulador y la red real.

---

## Hallazgos

### P4-1. `models/merkle.verificar_camino` nunca se usa en producción
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `models/merkle.py:52`; contraparte en `verificar_certificado.py:54` (`_camino_ok`)
- Confianza: Seguro
- Evidencia: `grep -rnw verificar_camino` sólo devuelve la definición, `tests/test_merkle.py` (líneas 5, 32, 39, 41, 47) y menciones en `docs/diseno/CONTRATOS.md:52` y `docs/PLAN_PROYECTO_FINAL.md:86`. Ningún módulo de `models/`, `controllers/` ni `scripts/` la llama. `models/certificado.py` sólo genera la prueba (`merkle.camino`) y la verificación real la hace `verificar_certificado._camino_ok`, una copia casi literal (mismas cotas: 64 pasos, mismos chequeos `lado` y `hash`).
- Escenario de falla: no hay falla funcional. La prueba de Merkle tiene dos implementaciones, y una sola está en producción; las pruebas de `test_merkle.py` validan la copia que no se ejecuta. Un cambio futuro de la regla (por ejemplo el límite de 64 pasos) puede aplicarse en una y olvidarse en la otra.
- Corrección propuesta: conservar `verificar_camino` deliberadamente como oráculo de pruebas y añadir una prueba que verifique que `_camino_ok` del verificador independiente da el mismo resultado que `merkle.verificar_camino` sobre los mismos casos. Así la duplicación, que es intencional (el verificador no debe importar `models/`), queda protegida contra divergencias. Si no se quiere conservar, borrarla junto con las líneas de `test_merkle.py` y de `CONTRATOS.md` que la citan.

### P4-2. `models/keystore.cambiar_contrasena` sin consumidor en producción
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `models/keystore.py:164`
- Confianza: Seguro
- Evidencia: sólo aparece en su definición y en `tests/test_keystore.py:11,143,155,157`. No hay ruta en `controllers/sellalo.py`, ni script en `scripts/`, ni botón en `sellalo.html` o `sellalo.js` que cambie la contraseña de un almacén.
- Escenario de falla: la función está probada pero no es alcanzable por ningún usuario. El README o el reporte pueden dar a entender que existe la capacidad de cambiar la contraseña, y no hay forma de ejecutarla sin escribir código.
- Corrección propuesta: exponerla (opción `--cambiar` en `scripts/crear_identidad.py` o ruta `POST /api/sellalo/contrasena`), o declararla en la documentación como API de biblioteca no cableada, o eliminarla con sus pruebas.

### P4-3. `ServidorP2P.faltas_de` sólo se usa en pruebas
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `models/red_p2p.py:158`
- Confianza: Seguro
- Evidencia: no hay llamadas en `models/`, `controllers/` ni `scripts/`; las 7 llamadas están en `tests/test_red_p2p.py:226,254,265`, `tests/test_red_integracion.py:100` y `tests/test_coordinador_sellos.py:159`. El método `vetado` sí tiene consumidores. La UI de pares no muestra las faltas acumuladas.
- Escenario de falla: ninguno funcional. Es un accesor de prueba que ocupa la API pública del servidor.
- Corrección propuesta: dejarlo y documentarlo como accesor de observabilidad, o mostrar las faltas en `pares_publico()`, o renombrarlo `_faltas_de` para dejar claro que es de pruebas.

### P4-4. Imports sin uso: `firmar_sello` en `coordinador_sellos` y `time` en `pow`
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `models/coordinador_sellos.py:18`, `models/pow.py:10`
- Confianza: Seguro
- Evidencia: en `coordinador_sellos.py`, `firmar_sello` se importa y no vuelve a aparecer en el archivo; el coordinador firma con `nodo.firmar(mensaje_sello(sello))` (líneas 188 y 219). En `pow.py`, `import time` es la única aparición de `time` (el motor usa `red.reloj()` y `cancelar.wait`). Las importaciones de prueba sin uso (`tests/test_certificado.py:1 import copy`, `tests/test_pos.py:13 nueva_red`) son del mismo tipo.
- Escenario de falla: ninguno; ruido y posible confusión sobre qué firma se usa.
- Corrección propuesta: quitar los cuatro imports.

### P4-5. `firmar_sello` de `multifirma` sólo la usan las pruebas; el mismo cálculo está inline en tres sitios
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `models/multifirma.py:27`; inline en `models/coordinador_sellos.py:188,219` y `models/ataques_sellalo.py:73`
- Confianza: Seguro
- Evidencia: `firmar_sello(tx, claves)` es `claves.firmar(mensaje_sello(tx))`. En producción nadie la llama (sólo `tests/test_multifirma.py` líneas 38, 78, 265, 272, 274, 321). El coordinador y los ataques repiten `nodo.firmar(mensaje_sello(sello))` a mano. El nodo no expone `ParClaves`, sólo `firmar(bytes)`, por eso no pudieron usar el helper.
- Escenario de falla: si la forma del mensaje firmado de un sello cambia (por ejemplo, añadir un dominio de separación), hay que tocar cuatro lugares. Un olvido hace que las firmas de pruebas sean válidas y las de producción no.
- Corrección propuesta: hacer que `firmar_sello` acepte cualquier objeto con `.firmar(bytes)` (el nodo ya lo cumple) y usarla en `coordinador_sellos.py` y `ataques_sellalo.py`. Con eso la función deja de estar muerta y el cálculo queda en un solo sitio.

### P4-6. CSS sin ningún elemento que lo use
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `views/static/styles.css:182` (`.inline`), `:194-196` (`.flash`, `.flash-ok`, `.flash-error`), `:444` (`.bloqueado-nota`), `:448` (`.ev-multifirma`), `:449` (`.ev-ataque`)
- Confianza: Seguro para `.inline`, `.flash*` y `.bloqueado-nota`; Posible para `.ev-multifirma` y `.ev-ataque`
- Evidencia:
  - `.inline`, `.flash*` y `.bloqueado-nota` no aparecen en ninguna plantilla ni JS (sólo existe `inline-label`, otra clase). Los avisos usan `.toast` (`toast()` en ambos JS), no `.flash`.
  - `.ev-multifirma` y `.ev-ataque` son clases dinámicas (`ev-${ev.tipo}`), pero `grep` de los tipos pasados a `evento(...)` en `models/` y `controllers/` no encuentra "multifirma" ni "ataque". Los tipos reales son bloque, castigo, clave, corrupto, difusion, error, nodo, p2p, pendientes, pos, pow, rechazo, recompensa, red, sello, tx y voto.
- Escenario de falla: sólo peso muerto. Los `flash` probablemente quedaron de una versión anterior que mostraba avisos en línea.
- Corrección propuesta: borrar esas reglas. Para los dos `ev-*`, antes de borrarlos, confirmar que ningún módulo nuevo emita esos tipos.

### P4-7. Duplicación de la lógica de pendientes entre `Red` (simulador) y `NodoCompleto` (red real)
- Categoría: Código muerto o duplicado
- Severidad: Media
- Ubicación: `models/red.py:196-230` (`agregar_pendiente`, `compromisos`, `saldo_disponible`) frente a `models/nodo_completo.py:285-330` (`agregar_transaccion`, `_disponible`); también `models/red.py:264-285` (`tras_bloque`) frente a `models/nodo_completo.py:_depurar` (~línea 267)
- Confianza: Seguro
- Evidencia: ambas siguen la misma secuencia:
  1. tope de pendientes (`MAX_PENDIENTES = 200`, definida **dos veces**: `red.py:27` y `nodo_completo.py:33`);
  2. `revisar_transaccion(estado, tx)` y traducción de `ErrorValidacion` a `ErrorEntrada("Transacción rechazada: ...")` más `evento("rechazo", ...)`;
  3. detección de duplicado `any(id == tid ...)`;
  4. comprobación de saldo disponible menos lo comprometido en pendientes;
  5. `append` y evento de aceptación.

  `tras_bloque` y `_depurar` repiten la depuración: revisar cada pendiente contra el estado nuevo y descartar las inválidas o sin saldo.
- Escenario de falla: la regla de admisión de transacciones no es única. Las diferencias ya existentes pueden ser accidentales: el simulador no atrapa `KeyError/TypeError` (el nodo sí, "formato inválido"); el simulador no compara ids con `_id_tx` ni admite sellos; los mensajes de error difieren ("doble gasto" frente a "duplicada"). Si se corrige un caso de borde (por ejemplo el saldo comprometido) en un lado, el otro queda con el defecto.
- Corrección propuesta: extraer a `models/bloque.py` o a un módulo `models/pendientes.py` una función pura `admitir(estado, pendientes, tx, disponible_fn, max_pendientes) -> tid` (más `depurar(estado, candidatas)`), con `MAX_PENDIENTES` única. `Red` y `NodoCompleto` conservarían sólo sus eventos y su persistencia.

### P4-8. Dos pipelines paralelos de recepción y adopción de cadena
- Categoría: Código muerto o duplicado
- Severidad: Media
- Ubicación: `models/red.py:63,69-98` (`_copia_json`, `Nodo.recibir_cadena`, `_rechazar`) frente a `models/nodo_completo.py:54,402-455` (`_json_puro`, `_recibir_cadena`)
- Confianza: Seguro
- Evidencia: `_copia_json` y `_json_puro` son la misma función de una línea (`json.loads(json.dumps(obj))`) con otro nombre y otra docstring. Ambos `recibir_cadena` hacen: copia pura, `validar_cadena(copia, hash_génesis)`, comparar contra la cadena propia, reemplazar `cadena` y `estado`. Difieren en el criterio de elección (simulador: más larga; red real: más trabajo, desempate por hash menor, timestamps futuros), que es la regla del contrato C5 y está bien que esté sólo en la red real. El tramo común de "serializar, validar, mapear error a mensaje" está copiado.
- Escenario de falla: `Nodo.recibir_cadena` del simulador atrapa `TypeError/ValueError` al serializar, mientras `NodoCompleto.recibir_cadena` agrega además un `except Exception` global. Si `validar_cadena` cambia el conjunto de excepciones que puede propagar, el simulador y la red real reaccionarán distinto ante la misma cadena malformada.
- Corrección propuesta: mover una única `copia_json_pura` a `models/bloque.py` (ya contiene `copiar`) y reutilizarla en ambos. Opcionalmente, extraer `validar_recibida(cadena, hash_genesis) -> (copia, estado)` que haga serialización más validación y devuelva el mensaje de error; cada nodo aplicaría después su propia regla de selección.

### P4-9. Búsqueda de nonce por fuerza bruta copiada en cuatro lugares (motor PoW, nodo real y dos ataques)
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `models/pow.py:60` (`ronda_pow`), `models/nodo_completo.py:562-575` (`_buscar_nonce`), `models/ataques.py:176-190` (`_minar`, `LIMITE_MINADO_ATAQUE`), `models/ataques_sellalo.py:17,43-56` (`_minar`, `LIMITE_MINADO`)
- Confianza: Seguro
- Evidencia: las cuatro llaman a `preparar_hasher` / `hash_bloque` en un bucle y comprueban `cumple_objetivo`/`startswith("0"*d)`. `ataques.py` y `ataques_sellalo.py` tienen la **misma función `_minar`** con la misma constante de 3 000 000 intentos y el mismo `ErrorEstado` de límite alcanzado. La de `ataques.py` además firma; la de `ataques_sellalo.py` usa `hash_bloque` sin hasher precalculado, por lo que es más lenta (recalcula el JSON por intento).
- Escenario de falla: un ajuste del rendimiento o del límite se aplica en un ataque y no en el otro. Con `DIF_REMINADO_MAX = 4`, `sello_alterado` en la red real puede tardar mucho más que su equivalente del simulador sin motivo.
- Corrección propuesta: crear en `models/pow.py` una función `minar_bloque(bloque, dificultad, limite)` basada en `preparar_hasher` que devuelva `(nonce, hash)` o lance `ErrorEstado`, y usarla en ambos módulos de ataques. El motor real mantiene su bucle propio porque necesita cancelar y reportar estadísticas.

### P4-10. `_rango` duplicada en `pow.py` y `red.py`, y validación de enteros repetida en `entradas.entero`
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `models/pow.py:271`, `models/red.py:332`, `controllers/entradas.py:40`
- Confianza: Seguro
- Evidencia: las dos funciones `_rango` son idénticas, línea por línea, incluido el mensaje. `entradas.entero` repite la lógica de rango con otro mensaje. Ambas `_rango` están en el mismo árbol de importación (`red.py` importa de `pow.py`).
- Escenario de falla: dos copias que divergirán al cambiar el texto del mensaje (los tests de mensajes del simulador dependen de él).
- Corrección propuesta: dejar una sola `validar_rango` en `models/errores.py` (o en `models/bloque.py`) e importarla en `pow.py` y `red.py`.

### P4-11. Constantes de configuración repetidas: `MAX_PENDIENTES`, `CONFIRMACIONES`
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `models/red.py:26-27` (`CONFIRMACIONES_POW = 6`, `MAX_PENDIENTES = 200`), `models/nodo_completo.py:33` (`MAX_PENDIENTES = 200`), `scripts/inicializar_red.py:22` (`CONFIRMACIONES = 6`)
- Confianza: Seguro
- Evidencia: el mismo valor literal en tres módulos sin referencia entre ellos. La profundidad de confirmación de la red real y la del simulador PoW deberían ser la misma regla del consenso.
- Escenario de falla: subir uno de los valores y no los otros hace que la UI de la red real y la del simulador muestren umbrales distintos para lo que el documento de diseño presenta como la misma regla.
- Corrección propuesta: definirlas una vez en `models/bloque.py` (junto a `MAX_TX_POR_BLOQUE`) e importarlas.

### P4-12. `scripts/demo_e2e.RedLocal` repite la preparación y el lanzamiento de `scripts/lanzar_red_local.py`
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `scripts/demo_e2e.py:136-228` (`RedLocal.__init__`, `comando`, `lanzar`, `cerrar`) frente a `scripts/lanzar_red_local.py:41-103` (`preparar`, `comando`, `lanzar`)
- Confianza: Seguro
- Evidencia: ambos crean `crear_almacen` por laboratorio, llaman a `construir_genesis`, escriben `genesis.json`, arman la lista `[sys.executable, "app.py", "--modo", "nodo", "--nodo", ..., "--pares", ...]` y lanzan `subprocess.Popen` terminando con `terminate`/`kill`. Cambian los puertos (uno con `puerto_libre`) y el registro a archivo.
- Escenario de falla: si `app.py` cambia un argumento (por ejemplo `--clave`), hay que corregir `comando()` en dos scripts; ya difieren en `-u` y en el nombre del génesis.
- Corrección propuesta: que `demo_e2e.RedLocal` use `lanzar_red_local.preparar()` y `comando()`, y sólo añada `puerto_libre`, los logs y el guardián de tiempo.

### P4-13. Helper `esperar` copiado en seis módulos de prueba
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `tests/test_adversarial.py:35`, `tests/test_coordinador_sellos.py:20`, `tests/test_nodo_completo.py:25`, `tests/test_red_integracion.py:14`, `tests/test_red_p2p.py:17`, `tests/test_sellalo_api.py:17` (y una séptima variante en `scripts/demo_e2e.py:48`)
- Confianza: Seguro
- Evidencia: el cuerpo es el mismo bucle `monotonic` con `sleep(0.02)`; sólo cambia el límite por defecto (5 o 10 s). `tests/conftest.py` ya concentra helpers (`nueva_red`, `todos_sincronizados`) pero no `esperar`.
- Escenario de falla: un ajuste de robustez (por ejemplo contra pruebas inestables en CI lento) se hace en un módulo y el resto sigue con el viejo.
- Corrección propuesta: mover `esperar(cond, limite=10.0)` a `tests/conftest.py` (o a `tests/laboratorios.py`) y pasar el límite explícito donde difiere.

### P4-14. `_ok` duplicada en los dos blueprints y `ErrorEstado/ErrorEntrada` mapeados dos veces
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `controllers/api.py:28`, `controllers/sellalo.py:105`
- Confianza: Seguro
- Evidencia: ambas arman `jsonify(ok=True, mensaje=..., **extra)`; la de `sellalo.py` hace opcional el mensaje. No hay otra pieza duplicada en los manejadores de error, que están centralizados en `app.py` (`error_entrada`, `error_http`, `error_inesperado`).
- Escenario de falla: casi ninguno; un cambio del formato de respuesta tendría que replicarse.
- Corrección propuesta: mover una sola `respuesta_ok(mensaje=None, **extra)` a `controllers/entradas.py` y usarla en ambos.

---

## Revisado y descartado (no son código muerto)

- Los manejadores `error_entrada`, `error_http` y `error_inesperado` (`app.py:49,53,60`), `_solo_nodo` (`controllers/sellalo.py:100`) y las 18 rutas `@api.*`/`@sellalo.*`/`@paginas*` que el barrido marcó con 1 sola referencia están registrados por decorador.
- La ruta `GET /api/<v>/nodos/<id>/recompensas` (`controllers/api.py:56`) no tiene consumidor en `app.js`, pero está documentada en el README (línea 130) y la prueban `tests/test_pow.py:134` y `tests/test_entradas.py:58`. Es API pública, no muerta.
- `verificar_certificado.py` repite a propósito `hash_bloque`, `_es_hex`, `_camino_ok` y `_canonico`. Es el requisito de verificador independiente que no importa `models/`. Sólo conviene la prueba cruzada propuesta en P4-1.
- Clases CSS dinámicas (`toast-*`, `status-*`, `papel-*`, `chip-*`, `par-sinc/dif/div`, `ev-*` salvo los dos señalados) se construyen con plantillas en JS.
- `RelojReal`, `RelojSimulado`, `HASH_CERO`, `TIPOS_BASE`, `CAMPOS_CASTIGO`, `CAMPOS_VOTO`, `MAX_LATENCIA_MS`, `LARGO_CIFRADO`, `N_MAX_ACEPTADO` y similares tienen un uso real único pero legítimo.
- La lógica de consenso PoS (`pos.py`) no tiene contraparte en la red real; no hay duplicación a compartir.
- La validación de bloques y cadenas (`validacion.py`, `bloque.py`, `merkle.py`, `multifirma.py`, `pow.verificar_pow`) **ya está compartida** entre el simulador y la red real. Es lo correcto y no requiere cambios.

## Tabla resumen

| id | título | categoría | severidad | ubicación |
|---|---|---|---|---|
| P4-1 | `merkle.verificar_camino` sin uso en producción | Código muerto o duplicado | Baja | `models/merkle.py:52` |
| P4-2 | `keystore.cambiar_contrasena` sin consumidor | Código muerto o duplicado | Baja | `models/keystore.py:164` |
| P4-3 | `ServidorP2P.faltas_de` sólo en pruebas | Código muerto o duplicado | Baja | `models/red_p2p.py:158` |
| P4-4 | Imports sin uso (`firmar_sello`, `time`) | Código muerto o duplicado | Baja | `models/coordinador_sellos.py:18`, `models/pow.py:10` |
| P4-5 | `firmar_sello` sólo en pruebas; cálculo inline en 3 sitios | Código muerto o duplicado | Baja | `models/multifirma.py:27`, `coordinador_sellos.py:188,219`, `ataques_sellalo.py:73` |
| P4-6 | CSS sin uso (`.inline`, `.flash*`, `.bloqueado-nota`, `.ev-multifirma`, `.ev-ataque`) | Código muerto o duplicado | Baja | `views/static/styles.css:182,194-196,444,448,449` |
| P4-7 | Lógica de pendientes duplicada simulador y red real | Código muerto o duplicado | Media | `models/red.py:196-285`, `models/nodo_completo.py:267-330` |
| P4-8 | Pipelines de recepción de cadena y copia JSON duplicados | Código muerto o duplicado | Media | `models/red.py:63-98`, `models/nodo_completo.py:54,402-455` |
| P4-9 | Búsqueda de nonce copiada en 4 sitios (dos `_minar` idénticas) | Código muerto o duplicado | Baja | `models/ataques.py:176`, `models/ataques_sellalo.py:43`, `models/nodo_completo.py:562`, `models/pow.py:60` |
| P4-10 | `_rango` duplicada y validación de enteros repetida | Código muerto o duplicado | Baja | `models/pow.py:271`, `models/red.py:332`, `controllers/entradas.py:40` |
| P4-11 | Constantes repetidas (`MAX_PENDIENTES`, confirmaciones) | Código muerto o duplicado | Baja | `models/red.py:26-27`, `models/nodo_completo.py:33`, `scripts/inicializar_red.py:22` |
| P4-12 | Lanzamiento de red local duplicado en scripts | Código muerto o duplicado | Baja | `scripts/demo_e2e.py:136-228`, `scripts/lanzar_red_local.py:41-103` |
| P4-13 | Helper `esperar` copiado en 6 módulos de prueba | Código muerto o duplicado | Baja | `tests/test_adversarial.py:35` y otros 5 |
| P4-14 | `_ok` duplicada en ambos blueprints | Código muerto o duplicado | Baja | `controllers/api.py:28`, `controllers/sellalo.py:105` |

Resumen por severidad: Crítica 0, Alta 0, Media 2, Baja 12.
