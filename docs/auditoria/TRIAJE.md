# Triaje de hallazgos de la auditoría con IA

> Decisión del orquestador (Claude Opus 5.5) antes de corregir, con los criterios de
> [PLAN_AUDITORIA_IA.md §5](../PLAN_AUDITORIA_IA.md): se corrige todo defecto real; "No aplicar" sólo para falsos
> positivos demostrados, limitaciones fuera del alcance de un proyecto académico (con mitigación documentada) o
> decisiones de diseño explícitas. Cada corrector **reproduce primero** el defecto con una prueba que falla en
> `auditoria-inicio` y luego lo corrige; si no se puede reproducir, lo marca como falso positivo con evidencia.
> Detalle de cada hallazgo en [HALLAZGOS.md](HALLAZGOS.md).

Leyenda: **C** corregir · **CP** corregir parcialmente (se indica qué queda) · **RE** resuelto por eliminación (el código afectado ya no existe) · **NA** no aplicar (justificación) · **D** documentar como limitación.

## G1 · red (`red_p2p.py`, `nodo_completo.py`, `coordinador_sellos.py`)

| ID | Decisión | Qué se hace |
|---|---|---|
| AUD-001 | C | Antes del AUTH las faltas se cuentan sólo por IP (con tope propio y sin vetar loopback de forma global); a una identidad sólo se le imputan faltas después de autenticarla. |
| AUD-002 | C | Un bloque válido en formato/PoW que no está en mi cadena y no la extiende → `"sincronizar"` aunque su altura sea ≤ la mía; la sincronización decide por trabajo. Con límite de tasa (AUD-028). |
| AUD-008 | C | La firma del saludo liga el canal: `sellalo-p2p|génesis|reto_A|reto_B|firmante|destinatario`. |
| AUD-009 | C | Deduplicación por hash **recalculado** y sólo tras aceptar; un rechazo no "quema" el hash. |
| AUD-010 | C | El sello completo sólo sale de "en firma" después de entrar a pendientes; si falla, se conserva y la API lo informa. |
| AUD-011 | C | Rechazos benignos (duplicada, pendientes llena, saldo, ya en cadena, desfase de reloj) no suman falta; las faltas decaen con el tiempo. |
| AUD-012 | C | Tope de conexiones entrantes (global y por IP), purga periódica de `_faltas`/`_vetos`. |
| AUD-013 | C | La sincronización se acota a la altura anunciada y a un máximo de bloques/bytes; cola de bloques acotada. |
| AUD-014 | C | Cuota de sellos en firma y de firmas huérfanas por laboratorio; las huérfanas se verifican al llegar y caducan. |
| AUD-015 | D | Adelantarse con un `doc_hash` visible antes del minado es inherente a difundir el sello en claro. Mitigación documentada: las firmas de autores prueban la autoría (un tercero no puede firmar por ellos); trabajo futuro: esquema *commit–reveal*. |
| AUD-016 | C | Reconexión automática a los pares configurados (`--pares` y conectados manualmente) con espera exponencial. |
| AUD-025 | NA | TLS/MAC del canal fuera del alcance académico. Cada bloque, transacción, sello y firma viaja firmado y se valida por contenido; el saludo está autenticado (y ligado al canal tras AUD-008). Se documenta. |
| AUD-026 | C | Un error de escritura queda visible en `/estado` (`error_persistencia`) además de la bitácora. |
| AUD-027 | C | Envío con tiempo límite corto por par para que uno lento no bloquee la difusión. |
| AUD-028 | C | Límite de sincronizaciones por par (una cada N s). |
| AUD-029 | C | Desempate determinista de conexiones simultáneas (se conserva la iniciada por el id menor). |
| AUD-030 | NA | Python no permite borrar de forma determinista la clave interna de `cryptography`; se eliminan todas las referencias y se documenta la limitación. |
| AUD-031 | C | scrypt fuera del candado del nodo y retardo creciente tras intentos fallidos de desbloqueo. |

## G2 · API e interfaz (`controllers/`, `app.py`, `views/`)

| ID | Decisión | Qué se hace |
|---|---|---|
| AUD-003 | C | Toda escritura a `/api/*` cuyo `Origin` no sea el del propio nodo, o con `Sec-Fetch-Site: cross-site`/`same-site`, se rechaza con 403 (los navegadores siempre envían `Origin` en un POST entre sitios); `Host` restringido a `127.0.0.1`/`localhost`/`[::1]`/`--host` (DNS rebinding). Los clientes sin navegador (curl, pruebas, demo) no envían `Origin` y siguen funcionando. |
| AUD-017 | C | El laboratorio de ataques sólo se activa con `--laboratorio-ataques` (la demo y el lanzador lo pasan); sin la opción responde 409. |
| AUD-032 | C | `/pares` y `--pares` resuelven nombres de host a IP antes de conectar, con el mismo validador. |
| AUD-033 | CP | Cabeceras `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`. SRI para Google Fonts: NA (la hoja CSS de Google es dinámica); se acota con CSP. |
| AUD-034 | C | Límites de tamaño y de encabezados para `/certificado/verificar` (junto con AUD-046). |
| AUD-035 | C | Direcciones locales en caché (60 s). |
| AUD-036 | C | Respuesta indica cuántas transacciones se crearon antes del error. |
| AUD-037 | C | Cuerpo vacío aceptado en rutas sin parámetros. |

## G3 · núcleo y verificador

| ID | Decisión | Qué se hace |
|---|---|---|
| AUD-004 | C | El génesis de la red Sellalo fija `parametros.dificultad`; todo bloque debe usar exactamente esa dificultad (el minero ya no la elige). `inicializar_red.py --dificultad` (por defecto 4). El simulador conserva la dificultad configurable que pide la guía. El límite residual (51 % del trabajo) se documenta. |
| AUD-005 | C | Sin `--genesis` el verificador no concluye "VÁLIDO" (resultado "no concluyente", código 3); el endpoint web sólo marca válido si el génesis es el de la red del nodo. |
| AUD-006 | RE | **Resuelto por eliminación:** se eliminó PoS del sistema el 2026-11-27; el código afectado ya no existe. (Decisión original: el comité PoS debía ser derivable de `hash_anterior|numero` y `tam_comite`.) |
| AUD-007 | RE | **Resuelto por eliminación:** se eliminó PoS del sistema el 2026-11-27; el código afectado ya no existe. (Decisión original: cada castigo/excluido debía traer la prueba de fraude firmada.) |
| AUD-018 | C | Regla de *mediana de tiempo pasado* (11 bloques): el timestamp debe ser ≥ la mediana de los anteriores; en la red Sellalo además ≤ ahora + 120 s al recibir. |
| AUD-019 | C | El verificador exige números finitos, timestamps no decrecientes respecto a la mediana y ≥ génesis. |
| AUD-020 | CP | El verificador muestra las confirmaciones y acepta `--min-confirmaciones` (advertencia si < 6). Emitir con 0 confirmaciones se permite pero queda indicado. |
| AUD-021 | CP | **Corregido parcialmente / resto resuelto por eliminación:** `intento` y las apuestas eran exclusivas de PoS, que se eliminó el 2026-11-27 (el código afectado ya no existe). Queda `monto` en las transferencias PoW, que ya se valida con tipo estricto (`es_entero`: `type(x) is int`, rechaza `bool` y `float`) en `revisar_transaccion` y lo cubre `test_transferencias_con_monto_invalido`. |
| AUD-022 | C | `es_numero` sin `OverflowError`; `validar_cadena` convierte cualquier error de tipo/valor en `ErrorValidacion`. |
| AUD-038 | C | `RecursionError` capturado en almacén de claves y verificador. |
| AUD-039 | C | Tope de memoria de scrypt aceptado (`128·N·r ≤ 64 MiB`, `p ≤ 2`) y comentario corregido. |
| AUD-040 | C | Contraseñas con sustitutos Unicode sueltos rechazadas con mensaje claro. |
| AUD-041 | C | Creación exclusiva (`O_EXCL`) del almacén. |
| AUD-042 | NA | El simulador aplica la regla (d) de la guía de medio término ("cadena válida más larga") explícitamente; la red real usa trabajo acumulado. Decisión de diseño documentada. |
| AUD-043 | C | Minado de ataques fuera de `red.lock` y con dificultad acotada. |
| AUD-044 | C | `cadena_intacta` comprueba que la punta previa sigue en la cadena. |
| AUD-045 | CP | La semántica k-de-n se mantiene (es la técnica elegida), pero el verificador, la API de prioridad y el certificado distinguen **firmantes** de **autores declarados**; se documenta. |
| AUD-046 | D | El certificado incluye todos los encabezados por diseño (verificable desde el génesis). A escala académica (< 10 000 bloques ≈ 7 MB) es suficiente; trabajo futuro: puntos de control firmados. Tope coherente con AUD-034. |

## G4 · limpieza (después de G1–G3)

| ID | Decisión | Qué se hace |
|---|---|---|
| AUD-023 | NA | Las reglas de pendientes difieren a propósito (en el simulador el saldo comprometido incluía apuestas PoS, ya eliminadas; en la red, sellos sin saldo). Se comparten las constantes (AUD-055). |
| AUD-024 | C | Una sola función de copia JSON pura en `models/cripto.py`. |
| AUD-047 | NA | Duplicación intencional: el verificador es independiente por contrato (C6); `merkle.verificar_camino` es la implementación de referencia que la prueba de compatibilidad contrasta con él. |
| AUD-048 | C | Se le da consumidor: `scripts/cambiar_contrasena.py`. |
| AUD-049 | C | Las faltas de cada par se exponen en `pares_publico()` (útil en la interfaz). |
| AUD-050 | C | Quitar imports sin uso. |
| AUD-051 | C | Usar `firmar_sello` en los sitios con el cálculo en línea. |
| AUD-052 | C | Quitar CSS sin uso (comprobando las clases dinámicas `ev-*`). |
| AUD-053 | C | Una sola búsqueda de nonce para ataques en `models/pow.py`. |
| AUD-054 | C | Una sola `_rango`. |
| AUD-055 | C | Constantes compartidas en un módulo de parámetros. |
| AUD-056 | C | `demo_e2e` reutiliza `lanzar_red_local.preparar`. |
| AUD-057 | C | `esperar` en un helper común de pruebas. |
| AUD-058 | C | `_ok` compartida. |
| AUD-059 | C | Rangos de versión acotados y `requirements-dev.txt` con `pytest`. |
| AUD-060 | C | El lanzador detecta génesis de otra configuración y pide contraseña al ampliar. |
| AUD-061 | C | `demo_e2e` cierra procesos en cualquier error. |
| AUD-062 | C | Paso 8 de la demo compara la bitácora antes/después y espera por sondeo. |

**Resumen:** 62 hallazgos → C 49 · CP 4 · RE 2 · NA 5 · D 2 (los "D" y "NA" quedan justificados arriba y en el reporte final).

**Desviación del plan:** el verificador adversarial (AU6) se integró en cada corrector (reproducir con una prueba que falla
antes de corregir), para ahorrar una pasada completa; la verificación independiente de cierre (P5) se mantiene.
