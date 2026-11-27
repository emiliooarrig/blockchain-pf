# HALLAZGOS de la auditoría con IA · Sellalo

Consolidación (AU5) de las cinco pasadas de la IA sobre la etiqueta `auditoria-inicio` (rama `proyecto-final`). Las respuestas íntegras están en [`respuestas/`](respuestas/). Este documento sólo une, deduplica y numera; **no decide qué se corrige ni verifica los hallazgos** (eso corresponde a AU6, al triaje y a los correctores). Las ubicaciones `archivo:línea` son las que citan las pasadas y no se han re-verificado una a una.

Reglas: un hallazgo único por defecto real; severidad = la más alta dada por alguna pasada salvo exageración (se anota en la ficha cuando difiere); orden por severidad y, dentro de ella, por grupo de corrección. Los hallazgos de `G4-limpieza` que tocan archivos de G1-G3 deben ejecutarse **después** de esos grupos para no chocar.

## 1. Resumen

### Hallazgos brutos por pasada

| Pasada | Brutos |
|---|---|
| P1 | 28 |
| P2 | 13 |
| P3a | 17 |
| P3b | 14 |
| P4 | 14 |
| **Total** | **86** |

**Hallazgos únicos tras deduplicar: 62** (de 86 brutos).

### Por severidad

| Severidad | Únicos |
|---|---|
| Crítica | 0 |
| Alta | 7 |
| Media | 17 |
| Baja | 38 |

Ninguna pasada asignó severidad Crítica: todas las Altas exigen una condición previa (ser laboratorio del génesis, nodo desbloqueado o navegador con el nodo abierto).

### Por categoría

| Categoría | Únicos |
|---|---|
| Seguridad | 19 |
| Procedimiento incompleto | 1 |
| Error de lógica | 18 |
| Manejo de excepciones | 6 |
| Código muerto o duplicado | 14 |
| Otro | 4 |

### Por grupo de corrección

| Grupo | Únicos | Alta | Media | Baja |
|---|---|---|---|---|
| G1-red | 18 | 2 | 9 | 7 |
| G2-api | 8 | 1 | 1 | 6 |
| G3-nucleo | 18 | 4 | 5 | 9 |
| G4-limpieza | 18 | 0 | 2 | 16 |

## 2. Correspondencia hallazgo original → AUD-ID (86)

| Original | AUD-ID | Original | AUD-ID | Original | AUD-ID |
|---|---|---|---|---|---|
| P1-1 | AUD-004 | P1-2 | AUD-003 | P1-3 | AUD-001 |
| P1-4 | AUD-005 | P1-5 | AUD-006 | P1-6 | AUD-002 |
| P1-7 | AUD-008 | P1-8 | AUD-009 | P1-9 | AUD-010 |
| P1-10 | AUD-011 | P1-11 | AUD-012 | P1-12 | AUD-020 |
| P1-13 | AUD-014 | P1-14 | AUD-017 | P1-15 | AUD-018 |
| P1-16 | AUD-015 | P1-17 | AUD-043 | P1-18 | AUD-034 |
| P1-19 | AUD-032 | P1-20 | AUD-031 | P1-21 | AUD-038, AUD-039 |
| P1-22 | AUD-026 | P1-23 | AUD-027 | P1-24 | AUD-033 |
| P1-25 | AUD-045 | P1-26 | AUD-046 | P1-27 | AUD-047, AUD-048, AUD-049, AUD-050, AUD-051, AUD-054, AUD-055, AUD-058 |
| P1-28 | AUD-059 | P2-1 | AUD-003 | P2-2 | AUD-008 |
| P2-3 | AUD-001 | P2-4 | AUD-012 | P2-5 | AUD-013 |
| P2-6 | AUD-005, AUD-019 | P2-7 | AUD-015 | P2-8 | AUD-004 |
| P2-9 | AUD-009 | P2-10 | AUD-014 | P2-11 | AUD-025 |
| P2-12 | AUD-034 | P2-13 | AUD-030, AUD-039 | P3a-1 | AUD-001 |
| P3a-2 | AUD-011 | P3a-3 | AUD-016 | P3a-4 | AUD-009 |
| P3a-5 | AUD-010 | P3a-6 | AUD-014 | P3a-7 | AUD-032 |
| P3a-8 | AUD-012 | P3a-9 | AUD-044 | P3a-10 | AUD-060 |
| P3a-11 | AUD-061 | P3a-12 | AUD-062 | P3a-13 | AUD-031 |
| P3a-14 | AUD-028 | P3a-15 | AUD-029 | P3a-16 | AUD-035 |
| P3a-17 | AUD-020 | P3b-1 | AUD-006 | P3b-2 | AUD-007 |
| P3b-3 | AUD-021 | P3b-4 | AUD-022 | P3b-5 | AUD-019 |
| P3b-6 | AUD-005 | P3b-7 | AUD-042 | P3b-8 | AUD-038 |
| P3b-9 | AUD-040 | P3b-10 | AUD-039 | P3b-11 | AUD-041 |
| P3b-12 | AUD-036 | P3b-13 | AUD-037 | P3b-14 | AUD-043 |
| P4-1 | AUD-047 | P4-2 | AUD-048 | P4-3 | AUD-049 |
| P4-4 | AUD-050 | P4-5 | AUD-051 | P4-6 | AUD-052 |
| P4-7 | AUD-023 | P4-8 | AUD-024 | P4-9 | AUD-053 |
| P4-10 | AUD-054 | P4-11 | AUD-055 | P4-12 | AUD-056 |
| P4-13 | AUD-057 | P4-14 | AUD-058 |  |  |

Un original puede aparecer en varios AUD cuando mezclaba causas o correcciones distintas (P1-15 y los listados mixtos de P1-21, P1-27, P2-6, P2-13).

## 3. Tabla maestra

| ID | Categoría | Severidad | Grupo | Archivo:línea | Descripción | Fuentes | Decisión | Commit | Prueba de regresión | Verificado en P5 |
|---|---|---|---|---|---|---|---|---|---|---|
| AUD-001 | Seguridad | Alta | G1-red | `models/red_p2p.py:403,413-420,172-185,328` | Faltas y vetos imputados a una identidad o IP sin autenticar. En el saludo `par.id` se asigna con el id declarado antes de probar la clave; las faltas del saludo se cargan a ese id y 5 faltas vetan al laboratorio real. | P1-3, P2-3, P3a-1 | Pendiente | — | — | Pendiente |
| AUD-002 | Error de lógica | Alta | G1-red | `models/nodo_completo.py:381-382,369-397` | Selección de cadena inconsistente: la rama con más trabajo y menos altura se ignora. `_recibir_bloque` descarta por altura bloques de una rama con más trabajo acumulado; sólo se sincroniza por trabajo en el saludo. | P1-6 | Pendiente | — | — | Pendiente |
| AUD-003 | Seguridad | Alta | G2-api | `app.py:25-66` | API HTTP del nodo sin autenticación, sin protección CSRF y sin validación de Host/Origin. Ninguna ruta de `/api/sellalo/*` exige token, Origin ni Host; `datos()` acepta formularios (petición simple sin preflight); DNS rebinding posible. | P1-2, P2-1 | Pendiente | — | — | Pendiente |
| AUD-004 | Error de lógica | Alta | G3-nucleo | `models/pow.py:17,33-42` | La dificultad PoW la declara el minero y el mínimo es 1: reescritura de historia e inflación. `verificar_pow` sólo exige que la dificultad declarada esté en 1..6; no hay dificultad de red, reajuste ni límite de reorganización. | P1-1, P2-8 | Pendiente | — | — | Pendiente |
| AUD-005 | Seguridad | Alta | G3-nucleo | `verificar_certificado.py:76-107,186-191,219-231 (P3b: 333-335,447-462)` | El verificador de certificados valida contra el génesis que trae el propio certificado. Sin `--genesis` el verificador declara "CERTIFICADO VÁLIDO" para una red inventada; el endpoint web devuelve `valido=True` aunque `misma_red` sea falso. | P1-4, P2-6, P3b-6 | Pendiente | — | — | Pendiente |
| AUD-006 | Error de lógica | Alta | G3-nucleo | `models/pos.py:79-131,134-157` | PoS: el comité de validadores y sus apuestas los declara el propio proponente. `verificar_pos` toma `validadores` del bloque; nada obliga a que el comité sea el conjunto de nodos con saldo ni exige quórum: un solo nodo forja bloques válidos. | P1-5, P3b-1 | Pendiente | — | — | Pendiente |
| AUD-007 | Error de lógica | Alta | G3-nucleo | `models/pos.py:61-76,98-125` | PoS: castigos y rondas rechazadas sin prueba; el proponente castiga a otros y se re-sortea. Los `castigos` y `excluidos` de rondas anteriores son datos libres: se descuentan saldos de nodos honestos sin prueba de que la ronda fracasó. | P3b-2 | Pendiente | — | — | Pendiente |
| AUD-008 | Seguridad | Media | G1-red | `models/red_p2p.py:305-306,392-427,466-471` | Autenticación P2P sin ligadura al canal: el reto sólo vincula al firmante (relé y suplantación). Cada extremo firma `reto|id_propio` sin incluir el id del otro, ambos retos ni el génesis: un tercero puede reenviar la firma y quedar registrado como otro laboratorio. | P1-7, P2-2 | Pendiente | — | — | Pendiente |
| AUD-009 | Seguridad | Media | G1-red | `models/red_p2p.py:187-208,620-648` | Deduplicación de BLOQUE/TX por el hash declarado y antes de validar. `_visto` marca la clave `B:<hash declarado>` antes de validar y no la retira al rechazar: un par puede "quemar" un bloque legítimo. | P1-8, P2-9, P3a-4 | Pendiente | — | — | Pendiente |
| AUD-010 | Error de lógica | Media | G1-red | `models/coordinador_sellos.py:221-230,279-288,320-329,150-160` | Un sello multifirma completo se borra de "en firma" antes de entrar a pendientes y puede perderse. Al alcanzar el umbral el sello se elimina de `_en_firma` y se guarda antes de `_a_pendientes`; si éste falla el sello desaparece y la UI dice "en_firma". | P1-9, P3a-5 | Pendiente | — | — | Pendiente |
| AUD-011 | Error de lógica | Media | G1-red | `models/red_p2p.py:172-185,620-648` | Rechazos que dependen del estado local y faltas sin decaimiento vetan a pares honestos. `_recibir_tx`/`_recibir_bloque` convierten en falta errores benignos (pendientes llena, saldo, duplicada, ya en cadena, reloj adelantado) y el contador nunca expira. | P1-10, P3a-2 | Pendiente | — | — | Pendiente |
| AUD-012 | Seguridad | Media | G1-red | `models/red_p2p.py:285-296,113-134,514-552,607-618,131,174-180` | Sin límite de conexiones entrantes, hilos ni tasa de mensajes; contadores sin purga. `_aceptar` crea un hilo por conexión sin tope global ni por IP, no hay límite de mensajes por par y `_faltas`/`_vetos` nunca se purgan. | P1-11, P2-4, P3a-8 | Pendiente | — | — | Pendiente |
| AUD-013 | Seguridad | Media | G1-red | `models/red_p2p.py:566-568,501-503,585-590,660-686` | Sincronización: un par puede hacer crecer la memoria sin límite y forzar validaciones largas. `_sincronizar` acumula hasta 200 000 bloques sin validar página a página, confía en `altura/trabajo` anunciados y `cola_bloques` no tiene tope. | P2-5 | Pendiente | — | — | Pendiente |
| AUD-014 | Seguridad | Media | G1-red | `models/coordinador_sellos.py:21-24,195-196,258-278,303-311` | Cupos de sellos en firma y de firmas huérfanas agotables por un laboratorio; huérfanas sin verificar ni expirar. `MAX_EN_FIRMA`/`MAX_HUERFANAS` (200) son globales sin cuota por par; `_huerfanas` no caduca, no verifica la firma y sobrescribe la firma real del mismo autor. | P1-13, P2-10, P3a-6 | Pendiente | — | — | Pendiente |
| AUD-015 | Seguridad | Media | G1-red | `models/coordinador_sellos.py:186-200,286` | El doc_hash se difunde antes de minarse: cualquier laboratorio puede adelantarse y quedarse con la prioridad. El sello viaja en claro (SELLO_PROPUESTO/TX) antes de entrar a un bloque y la prioridad es el orden en cadena: limitación de diseño sin compromiso-revelación. | P1-16, P2-7 | Pendiente | — | — | Pendiente |
| AUD-016 | Procedimiento incompleto | Media | G1-red | `controllers/sellalo.py:63-80` | No existe reconexión automática: caída de enlace, veto o BYE degradan la malla de forma permanente. `conectar` sólo se invoca una vez al desbloquear y desde `POST /pares`; ningún mecanismo reintenta tras PING sin PONG, falta, error de envío o BYE. | P3a-3 | Pendiente | — | — | Pendiente |
| AUD-017 | Seguridad | Media | G2-api | `controllers/sellalo.py:426-437` | Endpoint de ataques de demostración activo en el nodo real con la clave del laboratorio. `POST /api/sellalo/ataques` con `destino=red` firma y difunde bloques/transacciones inválidos con la clave real y no hay interruptor para desactivarlo. | P1-14 | Pendiente | — | — | Pendiente |
| AUD-018 | Error de lógica | Media | G3-nucleo | `models/validacion.py:33` | Timestamp de bloque sólo acotado por el bloque anterior: la fecha del certificado es manipulable hacia atrás. El único control es `timestamp >= anterior` (y `<= ahora+120 s` sólo para bloques sueltos): un minero puede reutilizar el timestamp previo tras horas de inactividad. | P1-15 | Pendiente | — | — | Pendiente |
| AUD-019 | Seguridad | Media | G3-nucleo | `verificar_certificado.py:109-133,178 (P3b: 339-363)` | El verificador de certificados no comprueba orden temporal: la fecha de prioridad es falsificable. El bucle de encabezados no exige timestamps no decrecientes ni `>=` génesis, ni números finitos; con dificultad 1 basta para inventar una fecha. | P3b-5, P2-6 | Pendiente | — | — | Pendiente |
| AUD-020 | Error de lógica | Media | G3-nucleo | `models/certificado.py:28-49` | Certificados emitidos y aceptados sin confirmaciones; la "prioridad" no es demostrable offline. `generar_certificado` incluye sellos en la punta (0 confirmaciones) y el verificador sólo exige `numero_bloque <= punta`; el certificado no excluye sellos anteriores del mismo documento. | P1-12, P3a-17 | Pendiente | — | — | Pendiente |
| AUD-021 | Error de lógica | Media | G3-nucleo | `models/pos.py:115,119,123,29-36,71-72` | PoS: `intento` y `monto` sin tipo estricto: varios sorteos distintos para el mismo bloque. `False`, `0.0` y `-0.0` pasan como `intento == 0` y siembran sorteos distintos (`"False"`, `"0.0"`); `monto=10.0`/`True` pasan donde se espera `10`/`1`. | P3b-3 | Pendiente | — | — | Pendiente |
| AUD-022 | Manejo de excepciones | Media | G3-nucleo | `models/bloque.py:39-40` | `es_numero` lanza OverflowError con enteros enormes y la excepción escapa de la validación. `math.isfinite(10**400)` lanza `OverflowError`, que `validar_cadena` no convierte en `ErrorValidacion`. | P3b-4 | Pendiente | — | — | Pendiente |
| AUD-023 | Código muerto o duplicado | Media | G4-limpieza | `models/red.py:196-285` | Lógica de admisión y depuración de pendientes duplicada entre simulador y red real. `Red.agregar_pendiente`/`tras_bloque` y `NodoCompleto.agregar_transaccion`/`_depurar` repiten tope, validación, duplicados, saldo comprometido y depuración, con diferencias probablemente accidentales. | P4-7 | Pendiente | — | — | Pendiente |
| AUD-024 | Código muerto o duplicado | Media | G4-limpieza | `models/red.py:63,69-98` | Dos pipelines paralelos de recepción y adopción de cadena (`_copia_json` frente a `_json_puro`). `_copia_json` y `_json_puro` son la misma función; el tramo copia/validación/mapeo de error está copiado entre `Nodo.recibir_cadena` y `NodoCompleto._recibir_cadena`. | P4-8 | Pendiente | — | — | Pendiente |
| AUD-025 | Seguridad | Baja | G1-red | `models/red_p2p.py:47-89,211-219,392-427` | Sin integridad ni cifrado del canal P2P tras el saludo. Los mensajes posteriores al AUTH no llevan MAC ni van sobre TLS. | P2-11 | Pendiente | — | — | Pendiente |
| AUD-026 | Manejo de excepciones | Baja | G1-red | `models/nodo_completo.py:196-206,328-343` | Persistencia: errores de escritura tragados y reescritura completa de la cadena bajo candado. `_guardar_cadena/_guardar_pendientes` sólo registran `OSError` en bitácora y el nodo continúa; cada bloque serializa y hace `fsync` de toda la cadena dentro de `self.lock`. | P1-22 | Pendiente | — | — | Pendiente |
| AUD-027 | Otro | Baja | G1-red | `models/red_p2p.py:211-219,697-706,535` | Difusión secuencial y bloqueante: un par lento retrasa a todos. `difundir` envía uno a uno con `sendall` bajo `lock_envio` y timeout de 10 s, desde el hilo de minado y los de recepción. | P1-23 | Pendiente | — | — | Pendiente |
| AUD-028 | Seguridad | Baja | G1-red | `models/nodo_completo.py:391-408` | Un bloque no enlazado con PoW mínimo provoca sincronizaciones completas repetidas. `_chequeo_ligero` sólo comprueba formato, hash y PoW y devuelve "sincronizar"; `_iniciar_sync` descarga y valida la cadena entera del par. | P3a-14 | Pendiente | — | — | Pendiente |
| AUD-029 | Error de lógica | Baja | G1-red | `models/red_p2p.py:335-345,429-484` | Conexiones simultáneas entre dos nodos pueden descartarse mutuamente. `conectar` registra la saliente antes del AUTH y rechaza la entrante del otro lado con "par ya conectado". | P3a-15 | Pendiente | — | — | Pendiente |
| AUD-030 | Seguridad | Baja | G1-red | `models/nodo_completo.py:226-233` | La clave privada sólo se "olvida" nominalmente al bloquear el nodo. `bloquear` pone `_claves = None` y registra que la clave se olvidó de la memoria, pero Python no borra de forma determinista los bytes. | P2-13 | Pendiente | — | — | Pendiente |
| AUD-031 | Seguridad | Baja | G1-red | `models/nodo_completo.py:213-224` | El desbloqueo ejecuta scrypt con el candado del nodo y sin límite de intentos. `desbloquear` llama a `abrir_almacen` (scrypt N=2^15, ~100 ms, 32 MB) con `self.lock`, que también toman `publico()`, `recibir_bloque` y `resumen()`; no hay contador de intentos y N está por debajo de lo recomendado (>=2^17). | P1-20, P3a-13 | Pendiente | — | — | Pendiente |
| AUD-032 | Error de lógica | Baja | G2-api | `controllers/sellalo.py:258-275` | Validación inconsistente de host en `/pares` y `--pares`; la ruta permite sondear destinos arbitrarios. El controlador y `parsear_pares` aceptan nombres de host (`RE_HOST`) pero `ServidorP2P.conectar` sólo admite IP; además `/pares` refleja el motivo detallado del fallo de conexión. | P1-19, P3a-7 | Pendiente | — | — | Pendiente |
| AUD-033 | Seguridad | Baja | G2-api | `views/templates/index.html:7-9` | Sin cabeceras de seguridad y fuentes externas sin SRI. No se envían CSP, `X-Content-Type-Options` ni `X-Frame-Options` y se cargan estilos de Google Fonts sin `integrity`. | P1-24 | Pendiente | — | — | Pendiente |
| AUD-034 | Seguridad | Baja | G2-api | `controllers/sellalo.py:390-422` | La verificación de certificados no acota el trabajo (encabezados y tamaño): DoS de CPU y memoria. El endpoint admite 25 MiB y `verificar` recorre sin tope cada encabezado recalculando hash y firma Ed25519. | P1-18, P2-12 | Pendiente | — | — | Pendiente |
| AUD-035 | Otro | Baja | G2-api | `controllers/sellalo.py:197-209,222` | `/estado` resuelve el nombre del equipo (`gethostbyname_ex`) en cada petición. `_direcciones_locales()` hace una resolución de nombre y abre un socket UDP en cada consulta de `/estado`, que la interfaz sondea periódicamente. | P3a-16 | Pendiente | — | — | Pendiente |
| AUD-036 | Manejo de excepciones | Baja | G2-api | `controllers/api.py:95-108` | `POST /transacciones/aleatoria` devuelve error tras haber creado parte de las transacciones. El bucle no captura `ErrorEstado` (pendientes llena); la respuesta 409 no indica que ya se crearon algunas. | P3b-12 | Pendiente | — | — | Pendiente |
| AUD-037 | Error de lógica | Baja | G2-api | `controllers/entradas.py:266-274` | POST JSON con cuerpo vacío rechazado en rutas sin parámetros. `datos()` trata `get_json(silent=True) == None` como error aunque `/pos/ronda`, `/pos/sortear`, `/pos/cerrar` sólo la llaman para descartar el cuerpo. | P3b-13 | Pendiente | — | — | Pendiente |
| AUD-038 | Manejo de excepciones | Baja | G3-nucleo | `models/keystore.py:96-122` | `RecursionError` sin capturar al leer JSON profundamente anidado (almacén de claves y verificador). `_leer` captura `(OSError, ValueError)` y `main` del verificador igual; `RecursionError` no es `ValueError` y escapa con traceback. | P1-21, P3b-8 | Pendiente | — | — | Pendiente |
| AUD-039 | Seguridad | Baja | G3-nucleo | `models/keystore.py:27,116-119` | Los parámetros scrypt del almacén de claves permiten pedir ~2 GiB de memoria por llamada. `N_MAX_ACEPTADO = 2**20` con `r<=16`, `p<=4` permite `128·N·r` = 2 GiB y el comentario afirma lo contrario. | P1-21, P2-13, P3b-10 | Pendiente | — | — | Pendiente |
| AUD-040 | Manejo de excepciones | Baja | G3-nucleo | `models/keystore.py:38-45,55,170-173` | Contraseña con sustituto Unicode suelto provoca `UnicodeEncodeError` sin controlar (500). `_validar_contrasena` y `entradas.contrasena` sólo comprueban tipo y longitud; `_kdf` hace `encode("utf-8")` y `"\ud800"` lanza. | P3b-9 | Pendiente | — | — | Pendiente |
| AUD-041 | Error de lógica | Baja | G3-nucleo | `models/keystore.py:129-133,87` | `crear_almacen`: comprobación de existencia y reemplazo no son atómicos. `os.path.exists` seguido de `_escribir` con `os.replace`, que sobrescribe. | P3b-11 | Pendiente | — | — | Pendiente |
| AUD-042 | Error de lógica | Baja | G3-nucleo | `models/red.py:96-100` | Simulador PoW: gana la cadena más larga sin considerar trabajo y la dificultad es libre por bloque. `Nodo.recibir_cadena` adopta por `len(copia) > len(self.cadena)` mientras la red real usa trabajo acumulado. | P3b-7 | Pendiente | — | — | Pendiente |
| AUD-043 | Seguridad | Baja | G3-nucleo | `models/ataques.py:46-51,55-70,176-200` | Los ataques del simulador minan hasta 3 M de hashes con `red.lock` tomado. `atacar_cadena` ejecuta la fábrica y `_minar` (hasta `LIMITE_MINADO_ATAQUE = 3_000_000`) dentro de `red.lock`, con dificultad de la configuración (hasta 6). | P1-17, P3b-14 | Pendiente | — | — | Pendiente |
| AUD-044 | Error de lógica | Baja | G3-nucleo | `models/ataques_sellalo.py:179-181` | `cadena_intacta` del ataque da falso negativo si la punta avanza legítimamente durante el ataque. `intacta = nodo.punta == punta or not rechazado` compara con la punta actual en lugar de comprobar que la anterior sigue en la cadena. | P3a-9 | Pendiente | — | — | Pendiente |
| AUD-045 | Error de lógica | Baja | G3-nucleo | `models/multifirma.py:31-57,93-124` | Coautores listados sin consentimiento cuando `umbral < n`. Un sello k-de-n es válido con k firmas y `autores` puede incluir laboratorios que no firmaron. | P1-25 | Pendiente | — | — | Pendiente |
| AUD-046 | Otro | Baja | G3-nucleo | `models/certificado.py:28-49` | Certificado y sincronización crecen sin límite (el certificado supera los 25 MiB que acepta el verificador). El certificado incluye todos los encabezados (~0,7 KiB c/u); a ~35 000 bloques supera el tope de 25 MiB y `MAX_BLOQUES_SYNC = 200 000` lo excede. | P1-26 | Pendiente | — | — | Pendiente |
| AUD-047 | Código muerto o duplicado | Baja | G4-limpieza | `models/merkle.py:52` | `merkle.verificar_camino` sin uso en producción (duplicada por `_camino_ok` del verificador). Sólo la usan las pruebas; el verificador independiente tiene su copia casi literal (64 pasos máx.). | P4-1, P1-27 | Pendiente | — | — | Pendiente |
| AUD-048 | Código muerto o duplicado | Baja | G4-limpieza | `models/keystore.py:164` | `keystore.cambiar_contrasena` sin consumidor en producción. Sólo existe en pruebas; ninguna ruta, script ni botón cambia la contraseña de un almacén. | P4-2, P1-27 | Pendiente | — | — | Pendiente |
| AUD-049 | Código muerto o duplicado | Baja | G4-limpieza | `models/red_p2p.py:158` | `ServidorP2P.faltas_de` sólo se usa en pruebas. Accesor sin llamadas en producción (7 en pruebas). | P4-3, P1-27 | Pendiente | — | — | Pendiente |
| AUD-050 | Código muerto o duplicado | Baja | G4-limpieza | `models/coordinador_sellos.py:18` | Imports sin uso: `firmar_sello` en `coordinador_sellos`, `time` en `pow` (y dos en pruebas). Importaciones que no se usan en su archivo. | P4-4, P1-27 | Pendiente | — | — | Pendiente |
| AUD-051 | Código muerto o duplicado | Baja | G4-limpieza | `models/multifirma.py:27` | `multifirma.firmar_sello` sólo la usan las pruebas; el cálculo está inline en tres sitios (y la clase `_Firmador`). `claves.firmar(mensaje_sello(tx))` se repite a mano porque el nodo sólo expone `firmar(bytes)`; `_Firmador` es el adaptador anónimo. | P4-5, P1-27 | Pendiente | — | — | Pendiente |
| AUD-052 | Código muerto o duplicado | Baja | G4-limpieza | `views/static/styles.css:182,194-196,444,448,449` | CSS sin uso: `.inline`, `.flash*`, `.bloqueado-nota`, `.ev-multifirma`, `.ev-ataque`. Reglas sin ningún elemento que las use (los dos `ev-*` sólo si ningún módulo emite esos tipos). | P4-6 | Pendiente | — | — | Pendiente |
| AUD-053 | Código muerto o duplicado | Baja | G4-limpieza | `models/pow.py:60` | Búsqueda de nonce copiada en cuatro lugares (dos `_minar` idénticas). `ataques.py` y `ataques_sellalo.py` tienen la misma `_minar` con 3 000 000 intentos; la segunda es más lenta (sin hasher precalculado). | P4-9 | Pendiente | — | — | Pendiente |
| AUD-054 | Código muerto o duplicado | Baja | G4-limpieza | `models/pow.py:271` | `_rango` duplicada en `pow.py` y `red.py`; validación de enteros repetida en `entradas.entero`. Dos funciones idénticas línea por línea y una tercera lógica de rango con otro mensaje. | P4-10, P1-27 | Pendiente | — | — | Pendiente |
| AUD-055 | Código muerto o duplicado | Baja | G4-limpieza | `models/red.py:26-27` | Constantes de configuración repetidas: `MAX_PENDIENTES`, confirmaciones, `MARGEN_FUTURO`, límites de autores/título, `ID_VALIDO`. Mismos valores literales en varios módulos sin referencia entre ellos (`MAX_PENDIENTES` 200 x2, `CONFIRMACIONES` 6 x3, `MARGEN_FUTURO` 120 frente a 600, `TITULO_MAX/INVESTIGADOR_MAX`, límite de 5 autores en tres sitios incluido el JS, `ID_VALIDO` x2). | P4-11, P1-27 | Pendiente | — | — | Pendiente |
| AUD-056 | Código muerto o duplicado | Baja | G4-limpieza | `scripts/demo_e2e.py:136-228` | `demo_e2e.RedLocal` repite la preparación y el lanzamiento de `lanzar_red_local.py`. Ambos crean almacenes, génesis, arman la línea de `app.py` y lanzan `subprocess.Popen`. | P4-12 | Pendiente | — | — | Pendiente |
| AUD-057 | Código muerto o duplicado | Baja | G4-limpieza | `tests/test_adversarial.py:35` | Helper `esperar` copiado en seis módulos de prueba (y una variante en `demo_e2e`). Mismo bucle `monotonic` con `sleep(0.02)`; sólo cambia el límite por defecto. | P4-13 | Pendiente | — | — | Pendiente |
| AUD-058 | Código muerto o duplicado | Baja | G4-limpieza | `controllers/api.py:28` | `_ok` duplicada en los dos blueprints. Ambas arman `jsonify(ok=True, mensaje=..., **extra)`. | P4-14, P1-27 | Pendiente | — | — | Pendiente |
| AUD-059 | Otro | Baja | G4-limpieza | `requirements.txt` | Dependencias sin fijar y herramientas de prueba mezcladas con las de ejecución. `flask>=3.0`, `cryptography>=42.0`, `pytest>=8.0` sin límite superior ni archivo de bloqueo; `pytest` se instala en producción; sin CI ni auditoría de dependencias. | P1-28 | Pendiente | — | — | Pendiente |
| AUD-060 | Error de lógica | Baja | G4-limpieza | `scripts/lanzar_red_local.py:46-65,98-103` | `lanzar_red_local.py` reutiliza un génesis de otra configuración y no pide la contraseña al ampliar la red. El génesis sólo se crea si no existe y la contraseña sólo se pide si falta `LAB-A/clave.json`. | P3a-10 | Pendiente | — | — | Pendiente |
| AUD-061 | Manejo de excepciones | Baja | G4-limpieza | `scripts/demo_e2e.py:549-558,147-155,173-185` | `demo_e2e.py`: procesos huérfanos y trazas si falla el arranque; sólo se captura `AssertionError`. `RedLocal(...)` y `lanzar_todos()` están antes del `try/finally` que llama a `red.cerrar()`; `main` sólo captura `AssertionError`. | P3a-11 | Pendiente | — | — | Pendiente |
| AUD-062 | Error de lógica | Baja | G4-limpieza | `scripts/demo_e2e.py:431-434` | `demo_e2e.py` paso 8: espera fija de 0,8 s y comprobación satisfacible con rechazos previos. `time.sleep(0.8)` y búsqueda de rechazos en toda la bitácora sin comparar con lo previo al ataque. | P3a-12 | Pendiente | — | — | Pendiente |

## 4. Fichas

### AUD-001 · Faltas y vetos imputados a una identidad o IP sin autenticar

- **Categoría:** Seguridad · **Severidad:** Alta · **Grupo:** G1-red
- **Ubicación:** `models/red_p2p.py:403,413-420,172-185,328`
- **Descripción:** En `_saludo_entrante` se hace `par.id = msg["nodo"]` antes de leer el AUTH. Un AUTH inválido, ausente o vencido ejecuta `_sumar_falta(par.id ...)`; a las 5 faltas `_vetos[id]` queda activo y `_validar_datos_hello` rechaza al laboratorio verdadero ("par vetado temporalmente"). Los saludos vencidos también suman faltas a la IP, y en la red local todos los nodos comparten 127.0.0.1.
- **Escenario de falla:** Un host con acceso TCP al puerto P2P abre 5 conexiones, manda un HELLO válido con `nodo="LAB-B"` y un AUTH basura (o nada): la víctima veta a LAB-B 60 s; repetido cada minuto lo aísla. En la malla local, 5 sondas calladas vetan 127.0.0.1 y el nodo descarta todas las conexiones entrantes.
- **Corrección propuesta:** Contar faltas sólo por IP (`par.ip`) hasta que `par.autenticado` sea True; asignar `par.id` y aplicar vetos por id sólo tras verificar la firma del reto; no vetar loopback ni IPs de pares conocidos; limitar HELLO sin autenticar por IP.
- **Fuentes:** [P1-3](respuestas/P1_integral.md), [P2-3](respuestas/P2_seguridad_diff.md), [P3a-1](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-002 · Selección de cadena inconsistente: la rama con más trabajo y menos altura se ignora

- **Categoría:** Error de lógica · **Severidad:** Alta · **Grupo:** G1-red
- **Ubicación:** `models/nodo_completo.py:381-382,369-397; models/red_p2p.py:501-503,563-568`
- **Descripción:** `_recibir_bloque` trata como duplicado cualquier bloque con `numero < altura` (o igual altura y hash mayor) aunque su rama tenga más trabajo. `_recibir_cadena` sí compara trabajo, pero sólo se invoca si el bloque supera la altura. `_actualizar_resumen` (PING/PONG) actualiza `par.trabajo` sin disparar sincronización.
- **Escenario de falla:** A mina a d=4 (5 bloques, trabajo 327 680) y B a d=2 (100 bloques, trabajo 25 600): los bloques nuevos de A tienen número menor que la altura de B y se ignoran; B nunca converge hasta reconectar y las dos redes quedan divididas.
- **Corrección propuesta:** Si el bloque (o el resumen de un par) anuncia más trabajo, pedir sincronización en lugar de descartar por altura; disparar `_iniciar_sync` cuando `par.trabajo > resumen()["trabajo"]` tras cualquier actualización de resumen.
- **Fuentes:** [P1-6](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-003 · API HTTP del nodo sin autenticación, sin protección CSRF y sin validación de Host/Origin

- **Categoría:** Seguridad · **Severidad:** Alta · **Grupo:** G2-api · **También toca:** G3 (ninguno de código obligatorio); cabeceras relacionadas en AUD-033
- **Ubicación:** `app.py:25-66; controllers/entradas.py:17-33; controllers/sellalo.py:99-102,231-437`
- **Descripción:** Con el nodo desbloqueado, cualquier página web puede enviar formularios `x-www-form-urlencoded` o multipart a `/transferencias`, `/sellos`, `/minar`, `/bloquear`, `/pares`, `/ataques`, `/desbloquear`. No hay `before_request` de seguridad (sólo `_solo_nodo`), ni validación de `Host` (DNS rebinding permite además leer respuestas), ni cabeceras anti-clickjacking.
- **Escenario de falla:** El investigador abre una página maliciosa mientras su nodo está desbloqueado en 127.0.0.1:5001; un `<form method=post action=.../transferencias>` con `receptor=LAB-X&monto=100` firma y difunde la transferencia; igual se pueden sellar hashes ajenos en su nombre, sondear puertos internos con `/pares` o hacer que sus pares lo veten con `/ataques`.
- **Corrección propuesta:** `before_request` global en modo nodo: 403 si `Host` no es 127.0.0.1/localhost:puerto (o el `--host` configurado) y, en métodos no seguros, exigir `Origin`/`Sec-Fetch-Site: same-origin`; exigir `Content-Type: application/json` salvo en subidas; token por proceso (`X-Sellalo-Token`) entregado en `/` para rutas multipart; añadir `X-Frame-Options: DENY` y CSP `frame-ancestors 'none'`.
- **Fuentes:** [P1-2](respuestas/P1_integral.md), [P2-1](respuestas/P2_seguridad_diff.md)
- **Verificación:** pendiente

### AUD-004 · La dificultad PoW la declara el minero y el mínimo es 1: reescritura de historia e inflación

- **Categoría:** Error de lógica · **Severidad:** Alta · **Grupo:** G3-nucleo · **También toca:** G1 (`nodo_completo.py`: `_chequeo_ligero`, persistencia)
- **Ubicación:** `models/pow.py:17,33-42; models/nodo_completo.py:40-47,438-445`
- **Nota de consolidación:** P2-8 la calificó Media; se toma Alta (P1-1) por ser la misma causa y permitir reescribir la historia.
- **Descripción:** `DIF_MIN, DIF_MAX = 1, 6` y `trabajo()` suma `16**dificultad` de lo que cada bloque declara. El génesis no fija dificultad mínima, no hay reajuste ni profundidad máxima de reorganización, y cada bloque barato acuña `recompensa` (10 créditos) y reescribe `cadena.json` completo en todos los nodos.
- **Escenario de falla:** Un laboratorio (basta una clave del génesis) mina una cadena paralela con bloques de dificultad 1-3 desde el génesis; si suma más trabajo que la honrada (p. ej. 1 000 bloques a d=2, unos 256 000 hashes) todos la adoptan: se pierden sellos ajenos, puede re-sellar los mismos `doc_hash` quedando primero y acuña créditos casi gratis.
- **Corrección propuesta:** Fijar `dificultad_minima` (y objetivo) en `parametros` del génesis y exigirla en `verificar_pow`/`validar_bloque` y en `_chequeo_ligero`; reajuste de dificultad o mínimo alto; limitar profundidad de reorganización con puntos de control; opcionalmente límite de bloques por proponente por ventana de tiempo.
- **Fuentes:** [P1-1](respuestas/P1_integral.md), [P2-8](respuestas/P2_seguridad_diff.md)
- **Verificación:** pendiente

### AUD-005 · El verificador de certificados valida contra el génesis que trae el propio certificado

- **Categoría:** Seguridad · **Severidad:** Alta · **Grupo:** G3-nucleo · **También toca:** G2 (`controllers/sellalo.py:412`)
- **Ubicación:** `verificar_certificado.py:76-107,186-191,219-231 (P3b: 333-335,447-462); controllers/sellalo.py:403-422`
- **Nota de consolidación:** P3b-6 la calificó Media; se toma Alta (P1-4, P2-6). La parte de fechas/timestamps de P2-6 va a AUD-019.
- **Descripción:** `genesis_esperado` es opcional. Sin él se acepta el génesis incluido en el JSON, se comprueba su coherencia, el enlace de bloques con PoW de dificultad 1 y las firmas contra las claves de ese mismo génesis. La CLI imprime "CERTIFICADO VÁLIDO" (exit 0) sin advertencia y `controllers/sellalo.py:412` llama a `verificar(cert, documento)` sin génesis esperado.
- **Escenario de falla:** Un tercero crea claves, génesis propio y un bloque de dificultad 1 con un sello arbitrario; `python verificar_certificado.py cert.json` responde "CERTIFICADO VÁLIDO". Quien no pase `--genesis` no se entera.
- **Corrección propuesta:** Hacer `--genesis` obligatorio o imprimir "COHERENTE (red no confirmada)" con código de salida distinto (p. ej. 3); en el endpoint pasar `genesis_esperado=_ctx().nodo.hash_genesis` o devolver `valido=false`/`no_comprobado` cuando `misma_red` sea falso; publicar el hash del génesis en el README.
- **Fuentes:** [P1-4](respuestas/P1_integral.md), [P2-6](respuestas/P2_seguridad_diff.md), [P3b-6](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-006 · PoS: el comité de validadores y sus apuestas los declara el propio proponente

- **Categoría:** Error de lógica · **Severidad:** Alta · **Grupo:** G3-nucleo
- **Ubicación:** `models/pos.py:79-131,134-157; models/validacion.py:45-54`
- **Descripción:** `verificar_pos` sólo exige que los ids existan, estén ordenados, `apuesta > 0` y `<= saldo`; el sorteo y el 2/3 de votos se calculan sobre esa lista autodeclarada. Reproducido por dos pasadas.
- **Escenario de falla:** N00 arma un bloque con `validadores=[{"id":"N00","apuesta":1}]`, firma la propuesta y vota él mismo; `N03.recibir_cadena` devuelve `(True, 'aceptada')`. Un nodo produce toda la cadena PoS y cobra recompensas.
- **Corrección propuesta:** Derivar el comité del estado de la cadena (nodos con saldo >= umbral o muestra con semilla pública `hash_anterior`), verificar que `validadores` coincide y exigir quórum de peso medido contra el saldo total de la red, no contra la lista autodeclarada.
- **Fuentes:** [P1-5](respuestas/P1_integral.md), [P3b-1](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-007 · PoS: castigos y rondas rechazadas sin prueba; el proponente castiga a otros y se re-sortea

- **Categoría:** Error de lógica · **Severidad:** Alta · **Grupo:** G3-nucleo
- **Ubicación:** `models/pos.py:61-76,98-125`
- **Descripción:** `_revisar_castigo` sólo valida formato, fórmula de `monto` y `saldo >= apuesta`; `hash_propuesta`, `valor_transacciones`, `regla`, `alfa_pct` son libres. `excluidos` sólo debe coincidir con el sorteo determinista, que cualquiera calcula. Reproducido.
- **Escenario de falla:** N00 declara excluidos falsos y fija `intento=k` poniéndose como proponente; o incluye un castigo `{"validador":"N05","apuesta":100,"monto":100,"regla":"A"}` que deja a N05 en saldo 0; los validadores honestos votan a favor porque usan la misma validación y los excluidos pierden su voto en el 2/3.
- **Corrección propuesta:** Exigir con cada castigo la propuesta rechazada (hash, firma del proponente y votos en contra que sumen >1/3), o eliminar los castigos del bloque y que las rondas fallidas sólo afecten al `intento`; fijar `regla`/`alfa_pct` en `parametros` del génesis y recalcular `valor_transacciones`.
- **Fuentes:** [P3b-2](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-008 · Autenticación P2P sin ligadura al canal: el reto sólo vincula al firmante (relé y suplantación)

- **Categoría:** Seguridad · **Severidad:** Media · **Grupo:** G1-red
- **Ubicación:** `models/red_p2p.py:305-306,392-427,466-471`
- **Descripción:** `_firma_reto` firma el reto ajeno y el id del propio firmante; el HELLO_ACK firma incluso antes de autenticar a quien llama. No hay separación de dominio ni ligadura a la sesión.
- **Escenario de falla:** M abre una conexión a B diciendo ser LAB-A y recibe `reto_B`; abre otra a A con ese reto y obtiene `firma_A(reto_B|LAB-A)`, que reenvía a B como AUTH: M queda registrado como LAB-A en B, eclipsa al real ("par ya conectado") y sus faltas se cargan a LAB-A. No forja bloques ni transacciones (impacto de disponibilidad y atribución).
- **Corrección propuesta:** Firmar con etiqueta de dominio `sellalo-p2p-v2|hash_genesis|reto_iniciador|reto_respondedor|id_iniciador|id_respondedor|rol`; el respondedor sólo firma tras probar el iniciador su identidad; opcionalmente cifrar/autenticar el canal (ver AUD-025).
- **Fuentes:** [P1-7](respuestas/P1_integral.md), [P2-2](respuestas/P2_seguridad_diff.md)
- **Verificación:** pendiente

### AUD-009 · Deduplicación de BLOQUE/TX por el hash declarado y antes de validar

- **Categoría:** Seguridad · **Severidad:** Media · **Grupo:** G1-red
- **Ubicación:** `models/red_p2p.py:187-208,620-648`
- **Nota de consolidación:** P1-8 y P3a-4 la calificaron Media; P2-9 Baja.
- **Descripción:** `_clave_dedup` usa `obj["hash"]` sin recalcular y `_recibir_bloque`/`_recibir_tx` llaman a `_visto` antes del nodo. Una TX rechazada por saldo (llegó antes que su financiación) o un bloque rechazado por timestamp futuro quedan marcados y se ignoran al reenviarse.
- **Escenario de falla:** M envía a B un bloque basura con el `hash` de un bloque legítimo X antes de que llegue X: B lo rechaza (una falta) pero cuando A le manda el X verdadero lo descarta como visto y no lo reenvía; B queda atrás hasta que otro bloque dispare sincronización.
- **Corrección propuesta:** Marcar como visto sólo tras `recibir_bloque` con resultado aceptado/duplicado; calcular la clave con `hash_bloque(bloque)` (y `_id_tx` para TX) en lugar del hash declarado.
- **Fuentes:** [P1-8](respuestas/P1_integral.md), [P2-9](respuestas/P2_seguridad_diff.md), [P3a-4](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-010 · Un sello multifirma completo se borra de "en firma" antes de entrar a pendientes y puede perderse

- **Categoría:** Error de lógica · **Severidad:** Media · **Grupo:** G1-red
- **Ubicación:** `models/coordinador_sellos.py:221-230,279-288,320-329,150-160; controllers/sellalo.py:311-318`
- **Descripción:** En `firmar`, `_procesar_propuesto` y `_procesar_firma` se hace `del self._en_firma[...]` + `_guardar()` antes de `_a_pendientes`, que captura `ErrorEntrada/ErrorValidacion` y devuelve False sin reinsertar. `firmar` responde `estado: "en_firma"`/"Firma agregada (2/2)" aunque el sello ya no existe.
- **Escenario de falla:** Con 200 pendientes (o un sello rechazado por `revisar_sello` en ese instante) la última firma completa el sello, éste desaparece de `sellos_en_firma.json` y no hay forma de reintentar ("no está esperando firmas"); hay que repetir todo el proceso.
- **Corrección propuesta:** No borrar de `_en_firma` hasta que `_a_pendientes` tenga éxito (o dejar que `_limpiar` lo retire cuando `_ya_resuelto`); devolver un estado distinto ("completo, pendiente de espacio") cuando falle y reintentar.
- **Fuentes:** [P1-9](respuestas/P1_integral.md), [P3a-5](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-011 · Rechazos que dependen del estado local y faltas sin decaimiento vetan a pares honestos

- **Categoría:** Error de lógica · **Severidad:** Media · **Grupo:** G1-red · **También toca:** G3 (`validacion.py`/`bloque.py` si se crean excepciones distintas)
- **Ubicación:** `models/red_p2p.py:172-185,620-648; models/nodo_completo.py:280-321`
- **Descripción:** `_faltas[clave]` sólo se reinicia al llegar a 5. `agregar_transaccion` lanza `ErrorEntrada/ErrorEstado` por causas que no son culpa del par y `_recibir_bloque` penaliza "timestamp más de 120 s en el futuro". La quinta demostración de `/ataques` destino red expulsa al propio nodo de sus pares.
- **Escenario de falla:** Con 200 pendientes, cada TX válida que retransmite un par honesto suma una falta y a la quinta se veta 60 s; 5 rechazos espaciados durante horas (reloj 3 min adelantado, TX ya minada por otro camino) producen el mismo veto.
- **Corrección propuesta:** Distinguir errores estructurales (firma, formato, hash) de "no aplicable ahora" (duplicada, ya en cadena, pendientes llena, saldo, futuro), que sólo se registran en bitácora; guardar faltas como marcas de tiempo y contar sólo una ventana de N minutos.
- **Fuentes:** [P1-10](respuestas/P1_integral.md), [P3a-2](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-012 · Sin límite de conexiones entrantes, hilos ni tasa de mensajes; contadores sin purga

- **Categoría:** Seguridad · **Severidad:** Media · **Grupo:** G1-red
- **Ubicación:** `models/red_p2p.py:285-296,113-134,514-552,607-618,131,174-180`
- **Nota de consolidación:** P3a-8 la calificó Baja; se toma Media (P1-11, P2-4).
- **Descripción:** Cada conexión retiene un hilo hasta `tiempo_saludo` (5 s); el veto por IP exige 5 faltas a posteriori. Tras el saludo, cada `GET_BLOQUES` serializa hasta ~1 MiB en el hilo lector y cada BLOQUE/TX válido en forma dispara verificación de firmas/PoW.
- **Escenario de falla:** Un host abre miles de sockets callados o, ya autenticado, envía `GET_BLOQUES` en bucle: el nodo agota hilos/CPU/memoria y deja de minar y de atender la interfaz.
- **Corrección propuesta:** Tope global (p. ej. 32-64) y por IP (3-4) de conexiones sin autenticar, cierre inmediato al excederlo; token bucket por par con falta/cierre; una petición `GET_BLOQUES` pendiente por par; expirar entradas antiguas de `_faltas`/`_vetos`.
- **Fuentes:** [P1-11](respuestas/P1_integral.md), [P2-4](respuestas/P2_seguridad_diff.md), [P3a-8](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-013 · Sincronización: un par puede hacer crecer la memoria sin límite y forzar validaciones largas

- **Categoría:** Seguridad · **Severidad:** Media · **Grupo:** G1-red
- **Ubicación:** `models/red_p2p.py:566-568,501-503,585-590,660-686; models/nodo_completo.py:418-424`
- **Descripción:** `_tras_saludo` inicia la sincronización con sólo que el HELLO diga `trabajo` mayor; `par.altura` también la fija el par. Sólo al final se llama a `recibir_cadena`/`validar_cadena`.
- **Escenario de falla:** Un laboratorio malicioso anuncia `altura=10**9` y envía páginas de relleno cercanas a 1 MiB: la víctima acumula varios GB; o envía 199 999 bloques válidos de dificultad 1 y el último inválido, gastando minutos de CPU por una sola falta.
- **Corrección propuesta:** Validar cada página al llegar (enlace, PoW, firma) y vetar al primer bloque inválido; tope de bytes/bloques por sincronización relativo a la altura propia; `queue.Queue(maxsize=4)`; descartar `BLOQUES` no solicitados; no confiar en `altura/trabajo` hasta recibir un bloque que lo respalde.
- **Fuentes:** [P2-5](respuestas/P2_seguridad_diff.md)
- **Verificación:** pendiente

### AUD-014 · Cupos de sellos en firma y de firmas huérfanas agotables por un laboratorio; huérfanas sin verificar ni expirar

- **Categoría:** Seguridad · **Severidad:** Media · **Grupo:** G1-red
- **Ubicación:** `models/coordinador_sellos.py:21-24,195-196,258-278,303-311`
- **Nota de consolidación:** P2-10 la calificó Baja.
- **Descripción:** Un laboratorio puede llenar los pendientes (200) y los sellos en firma (24 h) con sellos/propuestas válidos propios y las huérfanas con `SELLO_FIRMA` de `id_sello` aleatorios (basta `autor` en el génesis); una huérfana basura reemplaza a la firma legítima adelantada y el gossip no la reemite.
- **Escenario de falla:** Tras 200 firmas basura las firmas legítimas anticipadas se descartan hasta reiniciar y el sello 2-de-2 no completa; con 200 propuestas propias los demás reciben "demasiados sellos esperando firmas" durante 24 h, y cada propuesta reescribe `sellos_en_firma.json`.
- **Corrección propuesta:** Cuota por par/laboratorio en `_en_firma` y pendientes (p. ej. 10 y 20 por origen); TTL (p. ej. 10 min) y varias firmas por autor sin sobrescribir en `_huerfanas`; verificar la firma al guardarla o ligarla a `(autor, sid)` con tope.
- **Fuentes:** [P1-13](respuestas/P1_integral.md), [P2-10](respuestas/P2_seguridad_diff.md), [P3a-6](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-015 · El doc_hash se difunde antes de minarse: cualquier laboratorio puede adelantarse y quedarse con la prioridad

- **Categoría:** Seguridad · **Severidad:** Media · **Grupo:** G1-red · **También toca:** G2 (UI/certificado)
- **Ubicación:** `models/coordinador_sellos.py:186-200,286; models/nodo_completo.py:607-621; models/multifirma.py:128-132`
- **Nota de consolidación:** Es una limitación de diseño; puede resolverse documentándola (decisión en triaje).
- **Descripción:** El `doc_hash`, título e investigador se difunden desde que se propone (hasta 24 h en firma) y no hay prueba de que quien sella conozca el documento; combinado con AUD-004 un bloque propio de dificultad 1 queda antes.
- **Escenario de falla:** LAB-M ve un `SELLO_PROPUESTO` o TX con `doc_hash=H` de LAB-A, crea su propio sello `umbral=1` sobre H y lo mina primero: queda `prioritario` con certificado válido y LAB-A es segundo.
- **Corrección propuesta:** Esquema commit-reveal (sellar `H(doc_hash||sal)` y revelar tras k bloques) o no difundir hasta que el sello esté completo; como mínimo documentar la limitación y mostrar en la interfaz/certificado todos los sellos del mismo documento.
- **Fuentes:** [P1-16](respuestas/P1_integral.md), [P2-7](respuestas/P2_seguridad_diff.md)
- **Verificación:** pendiente

### AUD-016 · No existe reconexión automática: caída de enlace, veto o BYE degradan la malla de forma permanente

- **Categoría:** Procedimiento incompleto · **Severidad:** Media · **Grupo:** G1-red · **También toca:** G2 (`ContextoNodo` está en `controllers/sellalo.py`)
- **Ubicación:** `controllers/sellalo.py:63-80; models/red_p2p.py:514-552,221-241`
- **Descripción:** La búsqueda de `.conectar(` sólo encuentra `ContextoNodo._conectar_inicial` (un intento por par) y la ruta manual. El fallo queda en bitácora.
- **Escenario de falla:** Un corte de red de más de 12 s cierra el enlace y al volver los nodos siguen aislados minando cada uno su rama hasta que un humano reconecte; igual con un par que no escuchaba cuando el otro se desbloqueó.
- **Corrección propuesta:** Hilo de mantenimiento (en `ContextoNodo` o `ServidorP2P`) que cada pocos segundos intente `conectar` a los pares configurados ausentes de `_pares` y no vetados, con retroceso exponencial.
- **Fuentes:** [P3a-3](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-017 · Endpoint de ataques de demostración activo en el nodo real con la clave del laboratorio

- **Categoría:** Seguridad · **Severidad:** Media · **Grupo:** G2-api · **También toca:** G3 (`models/ataques_sellalo.py`)
- **Ubicación:** `controllers/sellalo.py:426-437; models/ataques_sellalo.py:143-186`
- **Descripción:** Con el nodo desbloqueado, la ruta fabrica mensajes inválidos firmados con la clave del laboratorio y los envía a todos los pares.
- **Escenario de falla:** Por CSRF (AUD-003) o un usuario curioso, cada par recibe 5 mensajes inválidos y veta al nodo 60 s, degradando su reputación y conectividad.
- **Corrección propuesta:** Registrar la ruta sólo con una opción explícita (`--habilitar-ataques`/`--demo`) y limitar `destino="red"` a redes de demostración.
- **Fuentes:** [P1-14](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-018 · Timestamp de bloque sólo acotado por el bloque anterior: la fecha del certificado es manipulable hacia atrás

- **Categoría:** Error de lógica · **Severidad:** Media · **Grupo:** G3-nucleo · **También toca:** G1 (`nodo_completo.py:345-346`)
- **Ubicación:** `models/validacion.py:33; models/nodo_completo.py:345-346`
- **Descripción:** Sin mediana de los últimos N bloques ni cota respecto al reloj local para cadenas completas. El verificador de certificados tampoco comprueba monotonía (ver AUD-019).
- **Escenario de falla:** Tras un periodo sin actividad, un laboratorio mina su bloque con la fecha del anterior (horas antes) y el certificado muestra esa "Fecha del bloque".
- **Corrección propuesta:** Exigir `timestamp > mediana(últimos N)` y `<= ahora + margen`; replicar la comprobación en el verificador.
- **Fuentes:** [P1-15](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-019 · El verificador de certificados no comprueba orden temporal: la fecha de prioridad es falsificable

- **Categoría:** Seguridad · **Severidad:** Media · **Grupo:** G3-nucleo
- **Ubicación:** `verificar_certificado.py:109-133,178 (P3b: 339-363)`
- **Nota de consolidación:** P2-6 (Alta) cubre además la red inventada, tratada en AUD-005; aquí queda la parte de fechas/trabajo (Media según P3b-5).
- **Descripción:** Verifica hash, enlace, numeración, dificultad 1..6 y firma del minero, pero no `timestamp >= previo` (el nodo sí, `validacion.py:33`) ni `<= emitido + margen`. Reproducido con timestamps `0, -5, 3, 1` (fecha 1970 y `valido=True`, incluso con `--genesis` correcto).
- **Escenario de falla:** Un laboratorio con clave del génesis arma una rama privada de dificultad 1 con fechas anteriores y un sello `umbral=1` sobre el documento de otro; el certificado pasa y reivindica prioridad.
- **Corrección propuesta:** Exigir `es_numero(ts)`, `ts >= ts_previo` (empezando por el génesis) y `ts <= emitido + margen`; parametrizar dificultad o trabajo acumulado mínimo (`--dif-min`) y, idealmente, anclar la punta con `--punta HASH`.
- **Fuentes:** [P3b-5](respuestas/P3b_logica_nucleo.md), [P2-6](respuestas/P2_seguridad_diff.md)
- **Verificación:** pendiente

### AUD-020 · Certificados emitidos y aceptados sin confirmaciones; la "prioridad" no es demostrable offline

- **Categoría:** Error de lógica · **Severidad:** Media · **Grupo:** G3-nucleo · **También toca:** G2 (`controllers/sellalo.py:379-388`)
- **Ubicación:** `models/certificado.py:28-49; verificar_certificado.py:134-137,179-183; controllers/sellalo.py:379-388`
- **Nota de consolidación:** P3a-17 la calificó Baja; se toma Media (P1-12).
- **Descripción:** No se usa `parametros.confirmaciones` (6) en la emisión ni en la verificación, y `resumen_certificado` lo presenta como certificado de prioridad cuando sólo prueba existencia en una cadena.
- **Escenario de falla:** Se emite un certificado de un sello recién minado; una reorganización (AUD-002/AUD-004, o la partición del paso 9 de la demo) lo elimina y el titular conserva un certificado "válido".
- **Corrección propuesta:** Negar la generación (409) o marcar "provisional"/`confirmado: false` con menos de `confirmaciones`; que el verificador exija `confirmaciones >= parametros.confirmaciones` para "válido definitivo"; incluir sellos previos conocidos o declarar la limitación en el texto.
- **Fuentes:** [P1-12](respuestas/P1_integral.md), [P3a-17](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-021 · PoS: `intento` y `monto` sin tipo estricto: varios sorteos distintos para el mismo bloque

- **Categoría:** Error de lógica · **Severidad:** Media · **Grupo:** G3-nucleo
- **Ubicación:** `models/pos.py:115,119,123,29-36,71-72; models/bloque.py:121-128`
- **Descripción:** `revisar_campos` no valida el tipo de `intento`; `verificar_pos` compara con `!=`; `sortear` siembra con `f"{hash_anterior}|{numero}|{intento}"`. Reproducido.
- **Escenario de falla:** Con un bloque sin excluidos, `sortear(...,0)` elige N05, `sortear(...,False)` elige N02 y `sortear(...,0.0)` elige N00; N02 construye con `intento=False` y se acepta: un proponente tiene hasta 4 tiradas. Con `monto=10.0` los saldos pasan a `float`.
- **Corrección propuesta:** Exigir `es_entero` en `intento`, `c["monto"]` y `voto["peso"]` en `verificar_pos`, y sembrar el sorteo con `int(intento)`.
- **Fuentes:** [P3b-3](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-022 · `es_numero` lanza OverflowError con enteros enormes y la excepción escapa de la validación

- **Categoría:** Manejo de excepciones · **Severidad:** Media · **Grupo:** G3-nucleo · **También toca:** G1 (`nodo_completo._cargar`)
- **Ubicación:** `models/bloque.py:39-40; models/validacion.py:91; models/red.py:88-115; models/multifirma.py:52; models/nodo_completo.py:166`
- **Descripción:** Reproducido en `validar_cadena` y `Nodo.recibir_cadena`; `nuevo_sello` y `revisar_transaccion` tienen el mismo defecto y `nodo_completo._cargar` no incluye `OverflowError`/`RecursionError` en su lista de excepciones.
- **Escenario de falla:** Un bloque con `timestamp` de 400 dígitos (JSON válido) hace que `Nodo.recibir_cadena` termine en 500 en lugar de "cadena rechazada"; un `cadena.json` alterado con ese valor tumba el arranque del nodo en lugar de moverse a `.corrupto-…`. Falta comprobar `coordinador_sellos._normalizar`.
- **Corrección propuesta:** `es_numero`: `try: return type(v) in (int, float) and math.isfinite(v) except OverflowError: return False`; añadir `OverflowError` y `RecursionError` a la conversión de `validar_cadena` y a la lista de `_cargar`.
- **Fuentes:** [P3b-4](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-023 · Lógica de admisión y depuración de pendientes duplicada entre simulador y red real

- **Categoría:** Código muerto o duplicado · **Severidad:** Media · **Grupo:** G4-limpieza · **También toca:** G1 (`nodo_completo.py`) y G3 (`red.py`): ejecutar tras G1-G3
- **Ubicación:** `models/red.py:196-285; models/nodo_completo.py:267-330`
- **Nota de consolidación:** Refactor: ejecutar después de las correcciones de G1/G3 para evitar conflictos.
- **Descripción:** Ambas siguen la misma secuencia con `MAX_PENDIENTES = 200` definido dos veces. Ya difieren en excepciones atrapadas (`KeyError/TypeError`), uso de `_id_tx`, admisión de sellos y mensajes.
- **Escenario de falla:** Un arreglo de borde (p. ej. el saldo comprometido) hecho en un lado deja el defecto en el otro.
- **Corrección propuesta:** Extraer a `models/pendientes.py` (o `bloque.py`) una función pura `admitir(estado, pendientes, tx, disponible_fn, max_pendientes)` y `depurar(estado, candidatas)`; `Red` y `NodoCompleto` conservan sólo eventos y persistencia.
- **Fuentes:** [P4-7](respuestas/P4_codigo_muerto.md)
- **Verificación:** pendiente

### AUD-024 · Dos pipelines paralelos de recepción y adopción de cadena (`_copia_json` frente a `_json_puro`)

- **Categoría:** Código muerto o duplicado · **Severidad:** Media · **Grupo:** G4-limpieza · **También toca:** G1 y G3: ejecutar tras G1-G3
- **Ubicación:** `models/red.py:63,69-98; models/nodo_completo.py:54,402-455`
- **Nota de consolidación:** Refactor: ver AUD-023.
- **Descripción:** Difieren en el criterio de elección (legítimo) pero también en las excepciones atrapadas (el nodo real añade `except Exception`).
- **Escenario de falla:** Si `validar_cadena` cambia el conjunto de excepciones que propaga, simulador y red real reaccionan distinto ante la misma cadena malformada.
- **Corrección propuesta:** Mover una única `copia_json_pura` a `models/bloque.py` y, opcionalmente, `validar_recibida(cadena, hash_genesis) -> (copia, estado)`; cada nodo aplica después su regla de selección.
- **Fuentes:** [P4-8](respuestas/P4_codigo_muerto.md)
- **Verificación:** pendiente

### AUD-025 · Sin integridad ni cifrado del canal P2P tras el saludo

- **Categoría:** Seguridad · **Severidad:** Baja · **Grupo:** G1-red
- **Ubicación:** `models/red_p2p.py:47-89,211-219,392-427`
- **Nota de consolidación:** Candidato a "no aplicar" con mitigación documentada.
- **Descripción:** Sólo el saludo prueba la identidad; BLOQUE/TX son autoverificables pero BYE/JSON inválido pueden inyectarse en un flujo establecido.
- **Escenario de falla:** Un nodo en la ruta (ARP/DNS spoofing) inyecta `{"tipo":"BYE"}` o JSON inválido en un flujo A-B: B cierra la conexión o veta a A (disponibilidad, no integridad).
- **Corrección propuesta:** Derivar clave de sesión en el saludo (X25519 firmada con las claves de identidad) y autenticar cada línea con HMAC, o TLS con pinning de claves del génesis; alternativa: documentar el modelo de amenaza (red de laboratorio cerrada).
- **Fuentes:** [P2-11](respuestas/P2_seguridad_diff.md)
- **Verificación:** pendiente

### AUD-026 · Persistencia: errores de escritura tragados y reescritura completa de la cadena bajo candado

- **Categoría:** Manejo de excepciones · **Severidad:** Baja · **Grupo:** G1-red
- **Ubicación:** `models/nodo_completo.py:196-206,328-343; models/coordinador_sellos.py:60-78`
- **Descripción:** Disco lleno: el nodo sigue minando y difundiendo con la cadena en memoria adelantada respecto al disco; el I/O es O(n²) y bloquea P2P.
- **Escenario de falla:** Al reiniciar se pierden bloques y sellos propios sin aviso visible fuera de la bitácora.
- **Corrección propuesta:** Propagar el error a `publico()` (estado "no persistente") o parar el minado; guardado incremental (añadir bloque) y fuera del candado.
- **Fuentes:** [P1-22](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-027 · Difusión secuencial y bloqueante: un par lento retrasa a todos

- **Categoría:** Otro · **Severidad:** Baja · **Grupo:** G1-red
- **Ubicación:** `models/red_p2p.py:211-219,697-706,535`
- **Descripción:** Un par que no lee ocupa hasta 10 s por mensaje.
- **Escenario de falla:** Un par lento retrasa la difusión de bloques al resto y el hilo de minado.
- **Corrección propuesta:** Cola de salida por par con hilo propio y límite de tamaño.
- **Fuentes:** [P1-23](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-028 · Un bloque no enlazado con PoW mínimo provoca sincronizaciones completas repetidas

- **Categoría:** Seguridad · **Severidad:** Baja · **Grupo:** G1-red
- **Ubicación:** `models/nodo_completo.py:391-408; models/red_p2p.py:633-686`
- **Descripción:** El par sólo suma falta si anunciaba más trabajo; `par.sincronizando` vuelve a False al terminar.
- **Escenario de falla:** Un par autenticado mina a dificultad 1 un bloque con `numero` mayor cada pocos segundos y la víctima descarga y valida la cadena completa cada vez.
- **Corrección propuesta:** Limitar a una sincronización por par cada N segundos y sumar falta cuando una cadena descargada no mejora la propia tras haberla provocado un bloque suelto.
- **Fuentes:** [P3a-14](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-029 · Conexiones simultáneas entre dos nodos pueden descartarse mutuamente

- **Categoría:** Error de lógica · **Severidad:** Baja · **Grupo:** G1-red
- **Ubicación:** `models/red_p2p.py:335-345,429-484; controllers/sellalo.py:74-80`
- **Descripción:** Si ambos nodos con `--pares` mutuos se desbloquean casi a la vez, cada uno rechaza la entrante del otro.
- **Escenario de falla:** Ambas conexiones mueren y, sin AUD-016, nadie reintenta.
- **Corrección propuesta:** Desempate determinista en `_registrar` (conservar la conexión iniciada por el id menor) además de la reconexión.
- **Fuentes:** [P3a-15](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-030 · La clave privada sólo se "olvida" nominalmente al bloquear el nodo

- **Categoría:** Seguridad · **Severidad:** Baja · **Grupo:** G1-red · **También toca:** G3 (`keystore.py`) si se cambia la representación
- **Ubicación:** `models/nodo_completo.py:226-233`
- **Nota de consolidación:** Segunda mitad de P2-13; la primera va a AUD-039.
- **Descripción:** Un volcado de memoria tras "bloquear" aún puede contener la clave.
- **Escenario de falla:** Impacto bajo: requiere acceso al proceso.
- **Corrección propuesta:** Reformular el mensaje ("se descartó la referencia") o guardar la clave en un `bytearray` que se sobrescribe al bloquear.
- **Fuentes:** [P2-13](respuestas/P2_seguridad_diff.md)
- **Verificación:** pendiente

### AUD-031 · El desbloqueo ejecuta scrypt con el candado del nodo y sin límite de intentos

- **Categoría:** Seguridad · **Severidad:** Baja · **Grupo:** G1-red · **También toca:** G2 (`controllers/sellalo.py`) y G3 (`keystore.py`)
- **Ubicación:** `models/nodo_completo.py:213-224; controllers/sellalo.py:231-241; models/keystore.py:25`
- **Descripción:** Cada intento (también los fallidos) paraliza P2P, PING y `/estado`.
- **Escenario de falla:** Un cliente local o CSRF repite contraseñas erróneas en paralelo manteniendo el nodo detenido y sin freno de fuerza bruta.
- **Corrección propuesta:** Derivar la clave fuera del candado y comprobar dentro sólo estado y clave pública; límite de intentos con retardo exponencial; subir N a 2^17 (el archivo guarda sus parámetros).
- **Fuentes:** [P1-20](respuestas/P1_integral.md), [P3a-13](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-032 · Validación inconsistente de host en `/pares` y `--pares`; la ruta permite sondear destinos arbitrarios

- **Categoría:** Error de lógica · **Severidad:** Baja · **Grupo:** G2-api · **También toca:** G1 (`red_p2p.conectar`)
- **Ubicación:** `controllers/sellalo.py:258-275; app.py:69-80; models/red_p2p.py:429-452`
- **Descripción:** `localhost:6002` pasa la validación y siempre falla con "IP inválida" (en `--pares` sólo queda en la bitácora). Combinado con AUD-003 la ruta permite escanear la red interna por las diferencias entre "Connection refused" y "no respondió al saludo".
- **Escenario de falla:** `POST /pares {"ip":"localhost","puerto":6002}` falla siempre; un atacante vía CSRF distingue puertos abiertos.
- **Corrección propuesta:** Resolver con `socket.getaddrinfo` en `conectar` o exigir IP literal en las tres entradas; no reflejar el motivo detallado; autenticar la ruta (AUD-003).
- **Fuentes:** [P1-19](respuestas/P1_integral.md), [P3a-7](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-033 · Sin cabeceras de seguridad y fuentes externas sin SRI

- **Categoría:** Seguridad · **Severidad:** Baja · **Grupo:** G2-api
- **Ubicación:** `views/templates/index.html:7-9; views/templates/sellalo.html:7-9; app.py`
- **Nota de consolidación:** Se solapa con la parte (e) de la corrección de AUD-003; pueden implementarse juntas.
- **Descripción:** No se halló XSS (el JS usa `textContent`); el riesgo es clickjacking y dependencia de un tercero.
- **Escenario de falla:** La interfaz puede enmarcarse y hacer clickjacking sobre "Firmar"/"Desbloquear".
- **Corrección propuesta:** `after_request` con CSP restrictiva (`default-src 'self'; frame-ancestors 'none'`) y `nosniff`; alojar las fuentes localmente.
- **Fuentes:** [P1-24](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-034 · La verificación de certificados no acota el trabajo (encabezados y tamaño): DoS de CPU y memoria

- **Categoría:** Seguridad · **Severidad:** Baja · **Grupo:** G2-api · **También toca:** G3 (`verificar_certificado.py`)
- **Ubicación:** `controllers/sellalo.py:390-422; app.py:30,38; verificar_certificado.py:109-137`
- **Descripción:** Un certificado con decenas de miles de encabezados ocupa un hilo de Flask varios segundos y cientos de MB.
- **Escenario de falla:** El usuario abre un "certificado" recibido por correo, o un sitio externo lo envía por CSRF: el nodo no responde unos segundos por petición.
- **Corrección propuesta:** Límite de `len(encabezados)` (p. ej. 100 000) al inicio de `verificar`; reducir `MAX_CONTENT_LENGTH` de las rutas que no suben documentos (p. ej. 5 MiB).
- **Fuentes:** [P1-18](respuestas/P1_integral.md), [P2-12](respuestas/P2_seguridad_diff.md)
- **Verificación:** pendiente

### AUD-035 · `/estado` resuelve el nombre del equipo (`gethostbyname_ex`) en cada petición

- **Categoría:** Otro · **Severidad:** Baja · **Grupo:** G2-api
- **Ubicación:** `controllers/sellalo.py:197-209,222`
- **Descripción:** Con DNS lento o roto cada sondeo espera la resolución (segundos en Windows).
- **Escenario de falla:** El panel se vuelve lento aunque el nodo esté sano.
- **Corrección propuesta:** Calcular las direcciones al arrancar o cachearlas (p. ej. 60 s).
- **Fuentes:** [P3a-16](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-036 · `POST /transacciones/aleatoria` devuelve error tras haber creado parte de las transacciones

- **Categoría:** Manejo de excepciones · **Severidad:** Baja · **Grupo:** G2-api · **También toca:** G3 (`models/red.py`)
- **Ubicación:** `controllers/api.py:95-108; models/red.py:197-198`
- **Descripción:** Con 195 pendientes y `cantidad=20` se crean 5 y la sexta lanza el error.
- **Escenario de falla:** El usuario ve 409 "La lista de pendientes está llena" sin saber que 5 se agregaron.
- **Corrección propuesta:** Capturar `ErrorEstado` dentro del bucle, cortar y responder 200 con el conteo y aviso si `creadas > 0`.
- **Fuentes:** [P3b-12](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-037 · POST JSON con cuerpo vacío rechazado en rutas sin parámetros

- **Categoría:** Error de lógica · **Severidad:** Baja · **Grupo:** G2-api
- **Ubicación:** `controllers/entradas.py:266-274; controllers/api.py:171-230`
- **Descripción:** Reproducido: con `Content-Type: application/json` y cuerpo vacío devuelve 400; la interfaz envía `{}` y no lo nota.
- **Escenario de falla:** `curl -X POST -H "Content-Type: application/json" /api/pos/pos/ronda` devuelve 400.
- **Corrección propuesta:** No llamar `datos()` en esas rutas o hacer que devuelva `{}` con cuerpo vacío.
- **Fuentes:** [P3b-13](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-038 · `RecursionError` sin capturar al leer JSON profundamente anidado (almacén de claves y verificador)

- **Categoría:** Manejo de excepciones · **Severidad:** Baja · **Grupo:** G3-nucleo · **También toca:** G1 (`nodo_completo.py` arranque), relacionada con AUD-022
- **Ubicación:** `models/keystore.py:96-122; verificar_certificado.py:433-438`
- **Descripción:** Reproducido en el verificador: 100 000 `[` produce traceback y exit 1 en lugar de 2 (contrato de la CLI).
- **Escenario de falla:** Un `clave.json` con miles de `[` rompe el arranque del nodo (`NodoCompleto.__init__` -> `leer_publica`).
- **Corrección propuesta:** Añadir `RecursionError` a los `except` de `_leer` y de `main` del verificador.
- **Fuentes:** [P1-21](respuestas/P1_integral.md), [P3b-8](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-039 · Los parámetros scrypt del almacén de claves permiten pedir ~2 GiB de memoria por llamada

- **Categoría:** Seguridad · **Severidad:** Baja · **Grupo:** G3-nucleo
- **Ubicación:** `models/keystore.py:27,116-119`
- **Nota de consolidación:** Combina la segunda mitad de P1-21 y la primera de P2-13.
- **Descripción:** Un archivo alterado fuerza gasto de varios GiB y decenas de segundos antes de fallar el descifrado.
- **Escenario de falla:** Quien pueda escribir `clave.json` pone `n=2**20, r=16, p=4` y el siguiente `/desbloquear` (o `cambiar_contrasena`) agota memoria (falta medir el uso real).
- **Corrección propuesta:** Acotar a lo que la aplicación escribe (`n<=2**16`, `r<=8`, `p=1`) o limitar `128·n·r·p` a ~64 MiB; rechazar el resto de inmediato.
- **Fuentes:** [P1-21](respuestas/P1_integral.md), [P2-13](respuestas/P2_seguridad_diff.md), [P3b-10](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-040 · Contraseña con sustituto Unicode suelto provoca `UnicodeEncodeError` sin controlar (500)

- **Categoría:** Manejo de excepciones · **Severidad:** Baja · **Grupo:** G3-nucleo · **También toca:** G2 (`controllers/entradas.py`)
- **Ubicación:** `models/keystore.py:38-45,55,170-173; controllers/entradas.py:337-348`
- **Descripción:** Reproducido: en `_abrir` se captura como `ValueError`, no en `_documento` ni `derivar_claves`.
- **Escenario de falla:** `POST /api/pow/simulacion {"n":10,"contrasena":"\ud800aaaaaaaaaaaa"}` devuelve 500 "Error interno inesperado (UnicodeEncodeError)".
- **Corrección propuesta:** Hacer `valor.encode("utf-8")` dentro de un `try` en `_validar_contrasena` y `entradas.contrasena` y lanzar `ErrorClave/ErrorEntrada` (400); validar también `sal` en `derivar_claves`.
- **Fuentes:** [P3b-9](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-041 · `crear_almacen`: comprobación de existencia y reemplazo no son atómicos

- **Categoría:** Error de lógica · **Severidad:** Baja · **Grupo:** G3-nucleo
- **Ubicación:** `models/keystore.py:129-133,87`
- **Descripción:** Dos procesos con la misma ruta pueden pasar la comprobación a la vez.
- **Escenario de falla:** Dos `crear_identidad` simultáneos: el segundo reemplaza al primero, que ya mostró su clave pública, y se pierde su clave privada sin aviso.
- **Corrección propuesta:** Publicar con `os.link(temporal, ruta)` (falla si existe) y borrar el temporal, o abrir el destino con `O_EXCL`.
- **Fuentes:** [P3b-11](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-042 · Simulador PoW: gana la cadena más larga sin considerar trabajo y la dificultad es libre por bloque

- **Categoría:** Error de lógica · **Severidad:** Baja · **Grupo:** G3-nucleo
- **Ubicación:** `models/red.py:96-100; models/pow.py:33-42`
- **Descripción:** No alcanzable desde la API actual (sólo si se añade un ataque que inyecte una cadena).
- **Escenario de falla:** Un nodo presenta 12 bloques de dificultad 1 frente a 10 honestos de dificultad 4 y los demás la adoptan con una fracción del trabajo.
- **Corrección propuesta:** Reutilizar `trabajo()` en `Nodo.recibir_cadena` o fijar la dificultad en `parametros` (comparte corrección con AUD-004).
- **Fuentes:** [P3b-7](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-043 · Los ataques del simulador minan hasta 3 M de hashes con `red.lock` tomado

- **Categoría:** Seguridad · **Severidad:** Baja · **Grupo:** G3-nucleo · **También toca:** G2 (`controllers/api.py`)
- **Ubicación:** `models/ataques.py:46-51,55-70,176-200; controllers/api.py:122-135`
- **Nota de consolidación:** P1-17 la clasificó Seguridad/Baja y P3b-14 Otro/Baja.
- **Descripción:** Con dificultad 5-6 la prueba agota el límite tras varios segundos y toda la simulación queda bloqueada; al final lanza `ErrorEstado` sin posibilidad de cancelar; el endpoint no exige autenticación.
- **Escenario de falla:** Un cliente repite `POST /api/pow/ataques {"tipo":"recompensa_falsa"}` con dificultad 6 y mantiene la red bloqueada.
- **Corrección propuesta:** Minar fuera del candado con una copia de lo necesario o limitar la dificultad del ataque (`min(dificultad, 3)`).
- **Fuentes:** [P1-17](respuestas/P1_integral.md), [P3b-14](respuestas/P3b_logica_nucleo.md)
- **Verificación:** pendiente

### AUD-044 · `cadena_intacta` del ataque da falso negativo si la punta avanza legítimamente durante el ataque

- **Categoría:** Error de lógica · **Severidad:** Baja · **Grupo:** G3-nucleo
- **Ubicación:** `models/ataques_sellalo.py:179-181`
- **Descripción:** Con minado continuo o un bloque honesto recibido entre la captura y la comparación, `rechazado=True` pero `intacta=False`.
- **Escenario de falla:** `demo_e2e.paso8_ataque` (que exige `cadena_intacta`) informa que la cadena fue alterada.
- **Corrección propuesta:** `intacta = punta in nodo._hashes` bajo `nodo.lock` (o método `contiene(hash)`).
- **Fuentes:** [P3a-9](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-045 · Coautores listados sin consentimiento cuando `umbral < n`

- **Categoría:** Error de lógica · **Severidad:** Baja · **Grupo:** G3-nucleo · **También toca:** G2 (UI)
- **Ubicación:** `models/multifirma.py:31-57,93-124; controllers/sellalo.py:287-309`
- **Nota de consolidación:** Posible comportamiento intencional; decidir en triaje.
- **Descripción:** `umbral=1` con 5 autores se publica sin intervención de los demás; el certificado atribuye autoría a quienes no firmaron.
- **Escenario de falla:** LAB-A sella con `autores=[A,B,C]`, `umbral=1`; el certificado atribuye autoría a B y C.
- **Corrección propuesta:** Distinguir "autores" de "firmantes" efectivos en UI y certificado y documentar la semántica.
- **Fuentes:** [P1-25](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-046 · Certificado y sincronización crecen sin límite (el certificado supera los 25 MiB que acepta el verificador)

- **Categoría:** Otro · **Severidad:** Baja · **Grupo:** G3-nucleo · **También toca:** G1 (`red_p2p.py:27`)
- **Ubicación:** `models/certificado.py:28-49; controllers/sellalo.py:380-388; models/red_p2p.py:27`
- **Descripción:** Cada `GET /certificado/<hash>` recorre la cadena completa.
- **Escenario de falla:** En cadenas largas el certificado emitido no puede verificarse con el propio endpoint.
- **Corrección propuesta:** Incluir encabezados sólo desde el bloque del sello hasta la punta más una cadena de enlace compacta, o checkpoints.
- **Fuentes:** [P1-26](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-047 · `merkle.verificar_camino` sin uso en producción (duplicada por `_camino_ok` del verificador)

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza
- **Ubicación:** `models/merkle.py:52; verificar_certificado.py:54`
- **Descripción:** La duplicación es intencional (el verificador no importa `models/`), pero las pruebas validan la copia que no se ejecuta.
- **Escenario de falla:** Un cambio de regla (p. ej. el límite de 64 pasos) se aplica en una copia y se olvida en la otra.
- **Corrección propuesta:** Conservarla como oráculo de pruebas y añadir una prueba cruzada con `_camino_ok`; o borrarla junto con sus pruebas y menciones en `CONTRATOS.md`/`PLAN_PROYECTO_FINAL.md`.
- **Fuentes:** [P4-1](respuestas/P4_codigo_muerto.md), [P1-27](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-048 · `keystore.cambiar_contrasena` sin consumidor en producción

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza
- **Ubicación:** `models/keystore.py:164`
- **Descripción:** La documentación puede sugerir una capacidad inalcanzable.
- **Escenario de falla:** Ningún usuario puede ejecutarla sin escribir código.
- **Corrección propuesta:** Exponerla (`--cambiar` en `crear_identidad.py` o ruta de API), documentarla como API de biblioteca o eliminarla con sus pruebas.
- **Fuentes:** [P4-2](respuestas/P4_codigo_muerto.md), [P1-27](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-049 · `ServidorP2P.faltas_de` sólo se usa en pruebas

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza
- **Ubicación:** `models/red_p2p.py:158`
- **Descripción:** Ocupa API pública sin consumidor.
- **Escenario de falla:** Ninguno funcional.
- **Corrección propuesta:** Documentarlo como observabilidad, mostrarlo en `pares_publico()` o renombrarlo `_faltas_de`.
- **Fuentes:** [P4-3](respuestas/P4_codigo_muerto.md), [P1-27](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-050 · Imports sin uso: `firmar_sello` en `coordinador_sellos`, `time` en `pow` (y dos en pruebas)

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza · **También toca:** G1 (`coordinador_sellos.py`) y G3 (`pow.py`): ejecutar tras G1-G3
- **Ubicación:** `models/coordinador_sellos.py:18; models/pow.py:10; tests/test_certificado.py:1; tests/test_pos.py:13`
- **Descripción:** Equivalente a pyflakes (no instalado) por AST.
- **Escenario de falla:** Ninguno; ruido.
- **Corrección propuesta:** Quitar los cuatro imports.
- **Fuentes:** [P4-4](respuestas/P4_codigo_muerto.md), [P1-27](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-051 · `multifirma.firmar_sello` sólo la usan las pruebas; el cálculo está inline en tres sitios (y la clase `_Firmador`)

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza · **También toca:** G1, G2 y G3: ejecutar tras G1-G3
- **Ubicación:** `models/multifirma.py:27; models/coordinador_sellos.py:188,219; models/ataques_sellalo.py:73; controllers/sellalo.py:349-352`
- **Descripción:** Si cambia la forma del mensaje firmado hay que tocar cuatro lugares.
- **Escenario de falla:** Firmas de prueba válidas y de producción inválidas tras un cambio parcial.
- **Corrección propuesta:** Hacer que `firmar_sello` acepte cualquier objeto con `.firmar(bytes)` y usarla en coordinador y ataques; eliminar `_Firmador`.
- **Fuentes:** [P4-5](respuestas/P4_codigo_muerto.md), [P1-27](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-052 · CSS sin uso: `.inline`, `.flash*`, `.bloqueado-nota`, `.ev-multifirma`, `.ev-ataque`

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza · **También toca:** G2 (`views/`)
- **Ubicación:** `views/static/styles.css:182,194-196,444,448,449`
- **Descripción:** Los avisos usan `.toast`; los tipos de evento reales no incluyen `multifirma` ni `ataque`.
- **Escenario de falla:** Sólo peso muerto.
- **Corrección propuesta:** Borrar las reglas; antes de los dos `ev-*` confirmar que ningún módulo nuevo emita esos tipos.
- **Fuentes:** [P4-6](respuestas/P4_codigo_muerto.md)
- **Verificación:** pendiente

### AUD-053 · Búsqueda de nonce copiada en cuatro lugares (dos `_minar` idénticas)

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza · **También toca:** G1 y G3: ejecutar tras G1-G3
- **Ubicación:** `models/pow.py:60; models/nodo_completo.py:562-575; models/ataques.py:176-190; models/ataques_sellalo.py:17,43-56`
- **Descripción:** Un ajuste de rendimiento o límite se aplica en un lugar y no en el otro.
- **Escenario de falla:** `sello_alterado` en la red real tarda más que su equivalente del simulador sin motivo.
- **Corrección propuesta:** `minar_bloque(bloque, dificultad, limite)` en `models/pow.py` basada en `preparar_hasher`, usada por ambos ataques; el motor real mantiene su bucle (cancelación y estadísticas).
- **Fuentes:** [P4-9](respuestas/P4_codigo_muerto.md)
- **Verificación:** pendiente

### AUD-054 · `_rango` duplicada en `pow.py` y `red.py`; validación de enteros repetida en `entradas.entero`

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza · **También toca:** G2 y G3: ejecutar tras G2-G3
- **Ubicación:** `models/pow.py:271; models/red.py:332; controllers/entradas.py:40`
- **Descripción:** Los tests de mensajes del simulador dependen del texto.
- **Escenario de falla:** Las copias divergen al cambiar un mensaje.
- **Corrección propuesta:** Una sola `validar_rango` en `models/errores.py` (o `bloque.py`) importada por ambas.
- **Fuentes:** [P4-10](respuestas/P4_codigo_muerto.md), [P1-27](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-055 · Constantes de configuración repetidas: `MAX_PENDIENTES`, confirmaciones, `MARGEN_FUTURO`, límites de autores/título, `ID_VALIDO`

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza · **También toca:** G1, G2 y G3: ejecutar tras G1-G3
- **Ubicación:** `models/red.py:26-27; models/nodo_completo.py:33-34; scripts/inicializar_red.py:22; models/multifirma.py:12; controllers/sellalo.py:34,190; models/keystore.py:24; scripts/crear_identidad.py:21`
- **Descripción:** Los valores de `MARGEN_FUTURO` ya difieren (puede ser intencional).
- **Escenario de falla:** Cambiar uno y no los otros muestra umbrales distintos para la misma regla.
- **Corrección propuesta:** Definir cada constante una vez (p. ej. en `models/bloque.py` junto a `MAX_TX_POR_BLOQUE`) e importarla; documentar si `MARGEN_FUTURO` difiere a propósito.
- **Fuentes:** [P4-11](respuestas/P4_codigo_muerto.md), [P1-27](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-056 · `demo_e2e.RedLocal` repite la preparación y el lanzamiento de `lanzar_red_local.py`

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza
- **Ubicación:** `scripts/demo_e2e.py:136-228; scripts/lanzar_red_local.py:41-103`
- **Descripción:** Ya difieren en `-u` y en el nombre del génesis.
- **Escenario de falla:** Si `app.py` cambia un argumento hay que corregir dos scripts.
- **Corrección propuesta:** `RedLocal` usa `lanzar_red_local.preparar()` y `comando()` y añade sólo `puerto_libre`, logs y guardián de tiempo.
- **Fuentes:** [P4-12](respuestas/P4_codigo_muerto.md)
- **Verificación:** pendiente

### AUD-057 · Helper `esperar` copiado en seis módulos de prueba (y una variante en `demo_e2e`)

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza
- **Ubicación:** `tests/test_adversarial.py:35; tests/test_coordinador_sellos.py:20; tests/test_nodo_completo.py:25; tests/test_red_integracion.py:14; tests/test_red_p2p.py:17; tests/test_sellalo_api.py:17; scripts/demo_e2e.py:48`
- **Descripción:** `tests/conftest.py` concentra helpers pero no `esperar`.
- **Escenario de falla:** Un ajuste de robustez se hace en un módulo y el resto sigue con el viejo.
- **Corrección propuesta:** Mover `esperar(cond, limite=10.0)` a `tests/conftest.py` (o `tests/laboratorios.py`).
- **Fuentes:** [P4-13](respuestas/P4_codigo_muerto.md)
- **Verificación:** pendiente

### AUD-058 · `_ok` duplicada en los dos blueprints

- **Categoría:** Código muerto o duplicado · **Severidad:** Baja · **Grupo:** G4-limpieza · **También toca:** G2: ejecutar tras G2
- **Ubicación:** `controllers/api.py:28; controllers/sellalo.py:105`
- **Descripción:** Los manejadores de error ya están centralizados en `app.py`.
- **Escenario de falla:** Casi ninguno; cambiar el formato exige replicar.
- **Corrección propuesta:** Una sola `respuesta_ok(mensaje=None, **extra)` en `controllers/entradas.py`.
- **Fuentes:** [P4-14](respuestas/P4_codigo_muerto.md), [P1-27](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-059 · Dependencias sin fijar y herramientas de prueba mezcladas con las de ejecución

- **Categoría:** Otro · **Severidad:** Baja · **Grupo:** G4-limpieza
- **Ubicación:** `requirements.txt`
- **Descripción:** No hay pip-audit/gitleaks/vulture instalados en el entorno de la auditoría.
- **Escenario de falla:** Una instalación futura trae versiones incompatibles o vulnerables sin aviso.
- **Corrección propuesta:** `requirements.txt` con versiones exactas (o `pip-compile`), `requirements-dev.txt` para `pytest` y `pip-audit` en CI.
- **Fuentes:** [P1-28](respuestas/P1_integral.md)
- **Verificación:** pendiente

### AUD-060 · `lanzar_red_local.py` reutiliza un génesis de otra configuración y no pide la contraseña al ampliar la red

- **Categoría:** Error de lógica · **Severidad:** Baja · **Grupo:** G4-limpieza
- **Ubicación:** `scripts/lanzar_red_local.py:46-65,98-103`
- **Descripción:** Tras `--labs 3`, ejecutar `--labs 4` conserva el génesis de 3 laboratorios.
- **Escenario de falla:** `preparar` aborta con "Falta la contraseña..." aunque haya terminal; con `--contrasena-env` crea LAB-D pero su nodo falla con "no existe en el génesis".
- **Corrección propuesta:** Comparar `genesis["cuentas"]` con los ids de `nodos` y abortar indicando otra `--carpeta`; pedir contraseña cuando falte cualquier identidad.
- **Fuentes:** [P3a-10](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-061 · `demo_e2e.py`: procesos huérfanos y trazas si falla el arranque; sólo se captura `AssertionError`

- **Categoría:** Manejo de excepciones · **Severidad:** Baja · **Grupo:** G4-limpieza
- **Ubicación:** `scripts/demo_e2e.py:549-558,147-155,173-185`
- **Descripción:** `crear_almacen` lanza `ErrorClave` si la carpeta ya tiene `clave.json`; `URLError/KeyError/ValueError` salen con traza.
- **Escenario de falla:** Si el segundo nodo no arranca, el primero queda huérfano ocupando puertos; con `--carpeta` usada termina sin explicación.
- **Corrección propuesta:** Mover construcción, lanzamiento y guion dentro del mismo `try/finally`; capturar `(AssertionError, OSError, ValueError, KeyError, ErrorEntrada)` e imprimir "FALLÓ EL GUION: ...".
- **Fuentes:** [P3a-11](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente

### AUD-062 · `demo_e2e.py` paso 8: espera fija de 0,8 s y comprobación satisfacible con rechazos previos

- **Categoría:** Error de lógica · **Severidad:** Baja · **Grupo:** G4-limpieza
- **Ubicación:** `scripts/demo_e2e.py:431-434`
- **Descripción:** Máquina lenta: falla sin motivo; rechazo previo: pasa sin que el ataque llegara.
- **Escenario de falla:** Resultado de la demo no fiable.
- **Corrección propuesta:** Guardar el último `n` de la bitácora antes del ataque y usar `esperar` para exigir un rechazo con número mayor.
- **Fuentes:** [P3a-12](respuestas/P3a_logica_red.md)
- **Verificación:** pendiente
