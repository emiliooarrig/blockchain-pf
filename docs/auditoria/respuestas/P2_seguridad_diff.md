# P2 · Revisión de seguridad del diff `main...auditoria-inicio`

Nota de método: la habilidad `security-review` figura en la lista de habilidades, pero está pensada para revisar los cambios pendientes de la rama actual; aquí el alcance es `git diff main...auditoria-inicio` y las instrucciones de `P2_seguridad_diff.md`, así que se siguió esta instrucción directamente (revisión manual del código nuevo, leído desde la etiqueta `auditoria-inicio`). No se ejecutó código ni se modificó nada salvo este archivo. Las afirmaciones "Seguro" salen de leer el código; no se montó un PoC.

Archivos revisados con detalle: `app.py`, `controllers/{sellalo,entradas}.py`, `models/{red_p2p,nodo_completo,coordinador_sellos,multifirma,bloque,validacion,pow,merkle,certificado,cripto,keystore,ataques_sellalo}.py`, `verificar_certificado.py`, `views/static/sellalo.js`, `views/templates/*.html`, scripts de lanzamiento. La interfaz construye el DOM con `textContent`/`createTextNode` (función `h()`); no se encontró XSS con títulos, investigadores ni ids de otros nodos.

---

### P2-1. CSRF y DNS rebinding contra `/api/sellalo/*` (sin Origin, sin Host, sin token)
- Categoría: Seguridad
- Severidad: Alta
- Ubicación: `controllers/entradas.py:17-33` (`datos()` acepta formularios), `controllers/sellalo.py:99-102` (`_solo_nodo` es el único `before_request`), `app.py:33-66` (sin validación de `Host`/`Origin`, sin cabeceras de seguridad)
- Confianza: Seguro
- Evidencia: `datos()` acepta `application/x-www-form-urlencoded` (`elif request.form: cuerpo = request.form.to_dict()`) y `_entrada()` acepta `multipart/form-data`. Ninguna ruta POST comprueba `Origin`, `Host` ni un token. `app.py` no registra ningún `after_request`/`before_request` de seguridad.
- Escenario de falla:
  1. El usuario tiene su nodo desbloqueado en `http://127.0.0.1:5001` y abre en otra pestaña una página maliciosa.
  2. La página envía un `<form method=POST action="http://127.0.0.1:5001/api/sellalo/transferencias">` con `receptor=LAB-B&monto=100` (petición "simple", sin preflight; las cookies no importan porque no hay sesión: basta con que el nodo esté desbloqueado). El nodo firma con la clave privada en memoria y deja la transferencia en pendientes (se difunde y se mina).
  3. Del mismo modo puede: `POST /sellos` con `doc_hash`, `titulo`, `investigador`, `autores`, `umbral=1` (sello firmado por el laboratorio de la víctima sobre un hash elegido por el atacante: irrevocable una vez minado); `POST /minar` (CPU); `POST /bloquear` (corta la red); `POST /pares` con `ip`/`puerto` arbitrarios (el nodo se conecta a cualquier IP:puerto de su red y envía una línea JSON: sondeo de puertos internos); y `POST /ataques` con `destino=red`, que difunde bloques/transacciones inválidos a los pares: cada uno suma una falta al laboratorio de la víctima y a las 5 faltas los demás nodos lo vetan 60 s (`FALTAS_PARA_VETO`).
  4. Sin comprobar `Host`, un DNS rebinding (dominio del atacante que pasa a resolver a 127.0.0.1) hace la página del atacante "mismo origen" con el nodo y le permite además **leer** las respuestas: `/estado` (bitácora, pendientes, IPs locales), certificados, y probar contraseñas en `POST /desbloquear` (sin límite de intentos; el nodo mantiene `nodo.lock` mientras corre scrypt, así que además bloquea el resto del nodo).
  - Esperado: las rutas que cambian estado sólo deben aceptar peticiones del propio origen del nodo.
- Corrección propuesta: (a) `before_request` global en modo nodo que rechace (403) cualquier petición con `Host` distinto de `127.0.0.1:<puerto>`/`localhost:<puerto>` (o del `--host` configurado), y que en métodos no seguros exija `Origin` (o `Sec-Fetch-Site: same-origin`) coincidente; (b) exigir `Content-Type: application/json` en las rutas JSON (un `fetch` cruzado con ese tipo dispara preflight, que no se responde) y no aceptar formularios en rutas que no suben archivos; (c) para `/sellos` y `/prioridad` (multipart) exigir un token por proceso (cabecera `X-Sellalo-Token` entregado en el HTML de `/`); (d) limitar intentos de `/desbloquear` (p. ej. 5 fallos y espera creciente) y no mantener `nodo.lock` durante scrypt; (e) cabeceras `X-Frame-Options: DENY` y `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'` (hoy se puede enmarcar la interfaz y hacer clickjacking sobre "Firmar", "Desbloquear").

---

### P2-2. El saludo P2P firma un reto ajeno antes de autenticar al otro lado: se puede suplantar a un laboratorio por reenvío
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `models/red_p2p.py:305-306` (`_firma_reto`), `:396-411` (`_saludo_entrante`: firma `firma_reto` en el HELLO_ACK antes de leer el AUTH), `:417` (verificación), `:467-471` (lado saliente)
- Confianza: Seguro
- Evidencia: el HELLO_ACK incluye `firma_reto = nodo.firmar(f"{reto}|{self.nodo.id}")` para cualquier `reto` hexadecimal de 32 caracteres que mande un desconocido que declare una identidad del génesis. El mensaje firmado sólo contiene el reto y el id **del firmante**; no incluye el id del destinatario, ni el reto propio, ni el hash del génesis, ni la dirección. El verificador comprueba `f"{reto_propio}|{par.id}"`.
- Escenario de falla (atacante M en la red local; A y B son laboratorios honestos y A es alcanzable):
  1. M se conecta a B y envía `HELLO` con `nodo="LAB-A"` y su reto. B responde con `HELLO_ACK` que trae `reto_B`.
  2. M se conecta a A y envía `HELLO` con `nodo="LAB-C"` (cualquier otra identidad del génesis; no se le autentica hasta el AUTH) y `reto = reto_B`. A responde `firma_reto = firma_A(reto_B|LAB-A)`.
  3. M reenvía esa firma a B como `AUTH`. B la verifica con la clave pública de LAB-A y registra a M como LAB-A.
  - Resultado: M queda registrado en B bajo la identidad de LAB-A (mientras LAB-A no esté ya conectado a B, o tras forzar su desconexión), por lo que B rechaza al LAB-A real con "par ya conectado" (eclipse), y las faltas que cometa M se cargan al id LAB-A (veto de LAB-A en B). No puede forjar bloques ni transacciones (siguen llevando firmas propias del laboratorio), así que el impacto es de disponibilidad y de atribución, no de integridad de la cadena. El mismo reenvío funciona en sentido contrario porque `conectar` también firma `msg["reto"]` sin que el otro extremo se haya probado.
  - Esperado: la prueba de identidad debe atar la firma a ambos extremos y a la sesión.
- Corrección propuesta: firmar un mensaje con separación de dominio que incluya ambos retos y ambas identidades, p. ej. `"sellalo-p2p-v2|" + hash_genesis + "|" + reto_iniciador + "|" + reto_respondedor + "|" + id_iniciador + "|" + id_respondedor + "|" + rol`. Así la firma de A hacia M (como "LAB-C") no sirve para el "LAB-A→B" que M intenta fabricar. Además, quien responde puede firmar sólo después de que el iniciador haya demostrado su identidad (o limitar el número de HELLO sin autenticar por IP).

---

### P2-3. Un desconocido puede vetar a un laboratorio legítimo (faltas imputadas a un id sin autenticar)
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `models/red_p2p.py:373` y `:387` (`_sumar_falta(par.id or par.ip, …)` durante el saludo), `:403` (`par.id = msg["nodo"]` antes del AUTH), `:417-419` (falta por firma inválida a `par.id`), `:328` (`_validar_datos_hello` rechaza si `vetado(pid)`), `:172-185`
- Confianza: Seguro
- Evidencia: tras recibir un HELLO válido en forma, `par.id` toma el valor declarado por quien llama, sin probar nada. Un AUTH con firma inválida (o ausente / tiempo agotado) ejecuta `self._sumar_falta(par.id, …)`, con `par.id` = id de otro laboratorio. A las 5 faltas, `_vetos[clave]` se activa 60 s y el HELLO legítimo de ese laboratorio recibe "par vetado temporalmente".
- Escenario de falla: un nodo cualquiera de la red hace 5 conexiones, en cada una envía `HELLO` con `nodo="LAB-A"` y después un `AUTH` basura. En menos de 1 s el nodo B veta a LAB-A durante 60 s; repitiéndolo cada minuto, LAB-A no puede unirse a B (ni B a LAB-A: `conectar` también consulta `_validar_datos_hello`). Esperado: sólo los pares autenticados acumulan faltas bajo su id; los no autenticados, bajo su IP.
- Corrección propuesta: en el saludo, usar siempre `par.ip` como clave de falta hasta completar el AUTH (y no asignar `par.id` hasta entonces); aplicar el veto por id sólo a conexiones autenticadas. Limitar además el número de HELLO sin autenticar por IP.

---

### P2-4. Sin límite de conexiones, hilos ni tasa de mensajes: agotamiento de hilos, CPU y ancho de banda por un par
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `models/red_p2p.py:285-296` (`_aceptar` crea un hilo por conexión, sin tope), `:113-134` (`listen(16)` pero ningún máximo de `_conexiones`), `:514-552` (`_bucle` sin tasa), `:607-618` (`_responder_bloques`)
- Confianza: Seguro (la falta de topes); el impacto práctico depende de los límites del sistema operativo
- Evidencia: cada conexión entrante (autenticada o no) lanza un hilo y puede quedarse hasta `tiempo_saludo` (5 s) por mensaje; el veto por IP sólo ocurre tras 5 faltas, y cuenta por IP después de cerrarse la conexión. Tras el saludo no hay límite de mensajes por segundo: cada `GET_BLOQUES` serializa hasta 100 bloques (hasta ~1 MiB, con reducciones repetidas de `json.dumps` en `:612-617`) en el hilo lector, y cada `BLOQUE`/`TX` válido en forma provoca verificación de firmas/PoW.
- Escenario de falla: un host abre cientos o miles de sockets al puerto P2P (cada uno retiene un hilo hasta 5-10 s y se repite sin llegar a vetarse porque sólo se cuenta una falta por IP al agotar el tiempo del saludo, y se tarda en llegar a 5) o, ya autenticado, envía `GET_BLOQUES` en bucle: el nodo se queda sin hilos/CPU y deja de minar y de atender la interfaz. Esperado: topes de conexiones por IP y totales, y límite de tasa por par.
- Corrección propuesta: máximo de conexiones simultáneas (p. ej. 64) y de no autenticadas por IP (p. ej. 3), cerrar de inmediato al superarlo; contador de mensajes por ventana (token bucket) por par con falta/cierre al excederlo, y una cola de respuestas para `GET_BLOQUES` (máximo 1 petición pendiente por par y 1 por segundo).

---

### P2-5. Sincronización: un par puede hacer crecer la memoria sin límite y forzar validaciones largas
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `models/red_p2p.py:566-568` y `:501-503` (`trabajo`/`altura` anunciados sin comprobar), `:585-590` (`par.cola_bloques.put` sin tope), `:660-686` (`_sincronizar`: acumula hasta `MAX_BLOQUES_SYNC = 200_000` bloques antes de validar nada), `models/nodo_completo.py:418-424` (`validar_cadena` de todo lo acumulado)
- Confianza: Seguro (acumulación y falta de tope en bytes); Posible el volumen exacto de memoria
- Evidencia: `_tras_saludo` inicia la sincronización con sólo que el HELLO diga `trabajo` mayor; `par.altura` también la fija el par (y hasta se actualiza con el `numero` de cualquier BLOQUE, sin cota en `:626-627`). `_sincronizar` repite `GET_BLOQUES` y va guardando listas de hasta 100 diccionarios por página mientras `len(acumulado) < par.altura` y `< 200_000`; cada página puede pesar casi 1 MiB (límite de línea). Sólo al final se llama a `recibir_cadena`. La cola `cola_bloques` no tiene tamaño máximo.
- Escenario de falla: un laboratorio malicioso (autenticado) anuncia `altura=10**9`, `trabajo` enorme y responde con páginas de bloques de relleno cerca del límite de línea: el nodo víctima acumula hasta ~2000 páginas × 1 MiB (varios GB al convertirlas en objetos Python) antes de rechazar la cadena. Otra variante: 199 999 bloques válidos (PoW de dificultad 1 y firma del propio laboratorio, baratos de fabricar) y el último inválido: la víctima gasta minutos de CPU en `validar_cadena`, y sólo recibe 1 falta por intento. Esperado: validar página a página y limitar bytes/bloques pendientes.
- Corrección propuesta: validar cada página al llegar (enlace de hash, PoW, firma) y descartar y vetar al par en el primer bloque inválido; tope de bytes acumulados y de bloques por sincronización relativo a `altura` anunciada razonable (p. ej. máximo `altura_propia + N`); `queue.Queue(maxsize=4)` para `cola_bloques` y descartar `BLOQUES` no solicitados; no confiar en `altura/trabajo` del saludo hasta recibir un bloque que lo respalde.

---

### P2-6. El verificador acepta como "VÁLIDO" certificados de una red inventada y con fechas elegidas por el emisor
- Categoría: Seguridad
- Severidad: Alta
- Ubicación: `verificar_certificado.py:17` y `:109-133` (encabezados), `:103-105` (génesis esperado opcional), `:178` (fecha), `:219-231` (CLI); `controllers/sellalo.py:412` (`verificar(cert, documento)` sin génesis esperado)
- Confianza: Seguro
- Evidencia: el verificador comprueba que los encabezados enlazan, que cada hash empieza por `dif` ceros con `dif` entre 1 y 6 (dificultad 1 = 16 intentos de media), que `firma_minero` corresponde a la clave del génesis **que viene dentro del propio certificado**, y que el sello y su prueba de Merkle cuadran. No comprueba: timestamps crecientes ni razonables (ni siquiera `>=` al del génesis), trabajo acumulado mínimo, número mínimo de confirmaciones, ni que la cadena sea la canónica. El génesis esperado (`--genesis`) es opcional; sin él se imprime "CERTIFICADO VÁLIDO" sin advertencia (la interfaz web sí muestra el chip "De otra red", pero el campo `valido` sigue en `true`).
- Escenario de falla (dos variantes):
  1. Falsificación total: un tercero genera sus propias claves, construye un génesis y una cadena de 1 bloque con dificultad 1, y un sello de "Dr. X, LAB-Z" con la fecha que quiera. `python verificar_certificado.py cert.json` termina con código 0 y "CERTIFICADO VÁLIDO". Quien no pase `--genesis` no se entera.
  2. Adelantar la fecha con la red real (el caso relevante para disputas de prioridad entre laboratorios): un laboratorio (con su clave, cualquier miembro del génesis) mina en su ordenador una cadena paralela desde el génesis real con bloques de dificultad 1 (milisegundos), con `timestamp` anteriores y un sello `umbral=1` sobre el documento de otro. El certificado pasa la verificación incluso con `--genesis` correcto, porque la fecha mostrada es la del encabezado, que decide el minero, y no se exige ningún respaldo de la cadena real.
  - Esperado: el verificador no debe presentar como válido algo cuyo único respaldo es un trabajo trivial y datos autodeclarados.
- Corrección propuesta: (a) hacer `--genesis` obligatorio en la CLI (o imprimir "RED NO CONFIRMADA" y salir con código distinto) y en la API pasar `genesis_esperado=_ctx().nodo.hash_genesis` (o devolver `valido=false` si no coincide); (b) exigir timestamps no decrecientes y `>= génesis`, y rechazar fechas posteriores a `emitido`; (c) exigir un trabajo acumulado mínimo y confirmaciones mínimas (`parametros.confirmaciones` del génesis) y reforzar el mínimo de dificultad por consenso (ver P2-8); (d) idealmente anclar la prueba comparando la punta con la de un nodo de confianza (`--punta HASH`) o añadir un parámetro de sello de tiempo externo.

---

### P2-7. Los sellos se difunden antes de minarse: cualquier laboratorio puede registrar primero el mismo `doc_hash` y quedarse con la prioridad
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `models/coordinador_sellos.py:200` (`_difundir("SELLO_PROPUESTO", …)`), `:286`, `models/nodo_completo.py:607-621` (`prioridad`: "el primero tiene la prioridad"), `models/multifirma.py:128-132`
- Confianza: Posible (depende de la ventana de carrera; el camino de ataque es concreto)
- Evidencia: el `doc_hash` y el título se envían en claro a todos los pares tan pronto como un laboratorio propone un sello, y el sello completo viaja como `TX` antes de minarse (a veces horas: hay hasta 24 h de caducidad en firma). La prioridad es sólo el orden en cadena y no hay compromiso-revelación ni verificación de que quien sella conoce el documento.
- Escenario de falla: LAB-M ve en la red un `SELLO_PROPUESTO` (o una `TX` con sello) con `doc_hash=H` de LAB-A, crea con su propio sello `umbral=1` sobre `H` ("Autor: M"), lo mina en el siguiente bloque y queda `prioritario: true` y con certificado válido. LAB-A queda como segundo sello del mismo documento. Esperado: quien primero conoce el documento (no sólo el hash) debe poder demostrarlo.
- Corrección propuesta: no difundir el `doc_hash` antes de que el sello esté completo y minable, o (mejor) esquema de compromiso-revelación: primero se sella `H(doc_hash || sal)` y luego se revela; como mínimo documentar la limitación y mostrar en la interfaz/certificado todos los sellos del mismo documento, no sólo el primero.

---

### P2-8. La dificultad mínima no está fijada por el consenso: se pueden acuñar créditos y saturar la cadena casi sin coste
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `models/pow.py:17` y `:35-42` (`DIF_MIN = 1`; sólo se exige que el bloque cumpla la dificultad que él mismo declara), `models/nodo_completo.py:40-47` (`trabajo`), `:196-200` (`_guardar_cadena` reescribe toda la cadena en cada bloque)
- Confianza: Seguro (regla); impacto económico depende del uso de los créditos
- Evidencia: `verificar_pow` acepta cualquier `dificultad` entre 1 y 6 declarada por el proponente; cada bloque da `recompensa` (10 créditos) al proponente que madura tras 6 confirmaciones. La interfaz sugiere dificultad 2 por defecto.
- Escenario de falla: un laboratorio autorizado (con su clave) mina continuamente bloques de dificultad 1 (16 intentos) con un sello `umbral=1` propio como transacción; en pocos segundos produce cientos de bloques válidos, cobra la recompensa de cada uno y llena `cadena.json` en todos los nodos (cada bloque reescribe todo el archivo y la cadena se envía completa en la sincronización). Esperado: un mínimo de dificultad por red, o recompensa/limitación por tasa, para que acuñar no sea gratis.
- Corrección propuesta: fijar `dificultad` mínima (o la exacta) en `parametros` del génesis y exigirla en `validar_bloque` y en `_chequeo_ligero`; límite de bloques por proponente por ventana de tiempo (p. ej. un bloque propio máximo cada N s respecto al timestamp); persistir la cadena de forma incremental.

---

### P2-9. Deduplicación de bloques por `hash` sin validar: un par puede "quemar" un bloque legítimo antes de que llegue
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `models/red_p2p.py:198-208` (`_clave_dedup`), `:620-636` (`_recibir_bloque`)
- Confianza: Posible (requiere que el atacante conozca el hash del bloque antes que la víctima)
- Evidencia: la clave de deduplicación de un `BLOQUE` es `"B:" + obj["hash"]`, tomada del propio mensaje, y se marca como vista **antes** de validar el bloque (`:624`). Si el bloque se rechaza, el hash queda en `_vistos` (hasta 10 000 entradas).
- Escenario de falla: un par malicioso, que recibe antes que la víctima un bloque válido de otro laboratorio, envía a la víctima un `BLOQUE` con el mismo `hash` y contenido basura. La víctima lo rechaza (una falta) pero deja marcado el hash; cuando llega el bloque verdadero por un par honrado, `_visto` devuelve `True` y se descarta en silencio sin pasar por `recibir_bloque` ni reenviarse. La víctima queda un bloque atrás hasta que otro bloque posterior active la sincronización. Esperado: sólo se marca como visto lo que ya se validó o se descartó por duplicado real.
- Corrección propuesta: calcular la clave con el contenido canónico completo (o marcar como visto sólo tras `recibir_bloque` aceptado/duplicado), y no usar el hash declarado por el par como identificador de deduplicación.

---

### P2-10. Saturación de los espacios compartidos (pendientes y sellos en firma) por un laboratorio malicioso
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `models/nodo_completo.py:289-290` (`MAX_PENDIENTES = 200`), `models/coordinador_sellos.py:22-23`, `:195-197`, `:268-270`, `:309-310` (`MAX_EN_FIRMA`, `MAX_HUERFANAS`)
- Confianza: Seguro
- Evidencia: cualquier laboratorio puede crear sellos válidos propios (`umbral=1`, `timestamp` distinto cada vez) que entran a los pendientes de todos (límite 200) y propuestas multifirma firmadas por sí mismo que ocupan `_en_firma` (límite 200, caducidad de 24 h). Las firmas "huérfanas" (`_huerfanas`) no caducan nunca y se acumulan hasta 200 con autor válido pero firma cualquiera (no se verifica hasta que llega la propuesta).
- Escenario de falla: LAB-M envía 200 sellos propios válidos o 200 propuestas: en los demás nodos `agregar_transaccion` responde "lista de pendientes llena" y `proponer` responde "demasiados sellos esperando firmas" durante horas; las huérfanas bloquean las firmas anticipadas legítimas hasta reiniciar. Cada propuesta, además, provoca una reescritura de `sellos_en_firma.json`.
- Corrección propuesta: tope por laboratorio proponente (p. ej. 10 en firma y 20 pendientes por origen), caducidad también para `_huerfanas`, y descartar propuestas de un laboratorio que supere su cuota.

---

### P2-11. Sin integridad ni cifrado del canal P2P tras el saludo
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `models/red_p2p.py:47-89` (`_Lector`), `:211-219` (`_enviar`), diseño del saludo (`:392-427`)
- Confianza: Seguro (diseño); la explotación exige estar en la ruta de red
- Evidencia: los mensajes posteriores al AUTH no llevan MAC ni van sobre TLS; el saludo sólo prueba la identidad al inicio.
- Escenario de falla: un nodo en la misma red local con ARP/DNS spoofing o en la ruta inyecta en un flujo establecido entre A y B una línea `{"tipo":"BYE"}` o JSON inválido: B cierra la conexión con A o le cuenta faltas hasta vetarlo (los bloques y transacciones siguen siendo autoverificables, así que no puede alterarlos). Impacto de disponibilidad en una red de laboratorio.
- Corrección propuesta: derivar una clave de sesión en el saludo (p. ej. X25519 firmada con las claves de identidad) y autenticar cada línea con HMAC, o envolver el transporte en TLS con pinning de claves del génesis.

---

### P2-12. Verificación de certificados sin acotar el tamaño de los encabezados (carga de CPU/memoria con un archivo de hasta 25 MB)
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `controllers/sellalo.py:390-421` (`_leer_subida` lee todo en memoria), `app.py:30` y `:38` (`MAX_CONTENT_LENGTH = 25 MiB`), `verificar_certificado.py:109-133`
- Confianza: Posible
- Evidencia: en modo nodo todo el servidor admite cuerpos de 25 MiB; `verificar` recorre sin tope cada encabezado, recalculando hash y verificando una firma Ed25519. Un certificado con decenas de miles de encabezados mantiene un hilo del servidor Flask ocupado varios segundos y cientos de MB de objetos JSON.
- Escenario de falla: el usuario abre un "certificado" recibido por correo en la interfaz; o un sitio externo lo envía con el CSRF de P2-1; el nodo se queda sin capacidad de respuesta unos segundos por petición. Esperado: límite razonable de encabezados.
- Corrección propuesta: reducir `MAX_CONTENT_LENGTH` de las rutas que no suben documentos (certificados: p. ej. 5 MiB) y limitar `len(encabezados)` (p. ej. 100 000) al principio de `_verificar`.

---

### P2-13. La clave privada sólo se "olvida" nominalmente y los parámetros de scrypt del archivo permiten pedir ~2 GiB
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `models/nodo_completo.py:226-233` (`bloquear`), `models/keystore.py:27` y `:116-119` (`N_MAX_ACEPTADO = 2**20`, `r` hasta 16, `p` hasta 4)
- Confianza: Posible (comprobar en una máquina de pruebas cuánta memoria reserva `cryptography` con `n=2**20, r=16`)
- Evidencia: `bloquear` pone `_claves = None` y registra "la clave se olvidó de la memoria"; en Python los bytes de la clave y el objeto de OpenSSL no se borran de forma determinista. El comentario del keystore dice que un archivo alterado "no puede pedir una cantidad absurda de memoria", pero `128·N·r` con `N=2**20` y `r=16` son 2 GiB.
- Escenario de falla: quien pueda escribir en `clave.json` (pero no en el resto) deja `n=2**20, r=16, p=4`: el siguiente `POST /desbloquear` consume gigas y minutos. Y un volcado de memoria del proceso tras "bloquear" aún puede contener la clave. Impacto bajo (requiere acceso local al disco o al proceso).
- Corrección propuesta: acotar `n·r` a lo que el programa genera (`n ≤ 2**16`, `r ≤ 8`, `p = 1`) y rechazar cualquier otro valor; reformular el mensaje de bloqueo ("se descartó la referencia a la clave") o guardar la clave privada en un `bytearray` que se sobrescribe al bloquear.

---

## Resumen

| id | título | categoría | severidad | ubicación |
|---|---|---|---|---|
| P2-1 | CSRF y DNS rebinding contra `/api/sellalo/*` | Seguridad | Alta | `controllers/entradas.py:17-33`, `controllers/sellalo.py:99-102`, `app.py:33-66` |
| P2-6 | El verificador acepta certificados de una red inventada y fechas elegidas por el emisor | Seguridad | Alta | `verificar_certificado.py:103-133,219-231`, `controllers/sellalo.py:412` |
| P2-2 | Saludo P2P: reto firmado sin atar a ambos extremos; suplantación por reenvío | Seguridad | Media | `models/red_p2p.py:305-306,396-411,467-471` |
| P2-3 | Veto de un laboratorio legítimo por faltas imputadas a un id sin autenticar | Seguridad | Media | `models/red_p2p.py:373,387,403,417` |
| P2-4 | Sin límite de conexiones, hilos ni tasa de mensajes | Seguridad | Media | `models/red_p2p.py:285-296,514-552,607-618` |
| P2-5 | Sincronización: memoria sin tope y validaciones largas por un par | Seguridad | Media | `models/red_p2p.py:566-568,585-590,660-686` |
| P2-7 | Los sellos se difunden antes de minarse: se puede robar la prioridad | Seguridad | Media | `models/coordinador_sellos.py:200,286`, `models/nodo_completo.py:607-621` |
| P2-8 | Dificultad mínima no fijada por consenso: acuñación y saturación casi gratis | Seguridad | Media | `models/pow.py:17,35-42`, `models/nodo_completo.py:196-200` |
| P2-9 | Deduplicación por `hash` declarado: se puede "quemar" un bloque legítimo | Seguridad | Baja | `models/red_p2p.py:198-208,620-636` |
| P2-10 | Saturación de pendientes y sellos en firma por un laboratorio | Seguridad | Baja | `models/nodo_completo.py:289`, `models/coordinador_sellos.py:22-23,195,268,309` |
| P2-11 | Sin integridad ni cifrado del canal P2P tras el saludo | Seguridad | Baja | `models/red_p2p.py:47-89,211-219` |
| P2-12 | Verificación de certificados sin tope de encabezados (25 MB) | Seguridad | Baja | `controllers/sellalo.py:390-421`, `app.py:30,38` |
| P2-13 | La clave privada no se borra de memoria; scrypt del archivo pide hasta 2 GiB | Seguridad | Baja | `models/nodo_completo.py:226-233`, `models/keystore.py:27,116-119` |

Revisado sin hallazgos: XSS en la interfaz (todo con `textContent`), inyección en `Content-Disposition` (el `doc_hash` se valida como hex), fugas de contraseña o clave privada en respuestas, bitácora o mensajes de error (no se encontraron), validación del almacén de claves (AES-GCM con AAD ligada a id y clave pública), carga de `cadena.json`/`pendientes.json`/`sellos_en_firma.json` (se revalidan y se descartan si están dañados), validación de transacciones y sellos (firma, formato, doble gasto y repeticiones).
