# P1 · Auditoría integral de seguridad y calidad — Sellalo

Fecha: 2026-11-25 · Rama `proyecto-final` · Alcance: todo el repositorio (Python/Flask, JS del navegador, scripts y pruebas) · Profundidad: profunda (revisión manual de los módulos críticos).

**Nota de método.** La habilidad `anthropic-skills:security-audit` estaba disponible y se cargó; se siguió su checklist (OWASP adaptado, buenas prácticas, calidad, FODA). Su "Paso 0" (preguntas al usuario) no se pudo ejecutar por ser una sesión no interactiva; se asumieron el alcance y la profundidad que fijan `_comun.md` y `P1_integral.md`, y contexto de desarrollo (sin datos reales). Herramientas: `pip-audit`, `gitleaks` y `vulture`/`pyflakes` **no están instalados** en el entorno, por lo que el análisis de dependencias fue manual (versiones instaladas: Flask 3.1.3, Werkzeug 3.1.9, cryptography 50.0.2) y los secretos/código muerto se buscaron con `git grep` y un script AST de lectura. No se ejecutó la suite de pruebas completa. Se comprobaron dos hipótesis con scripts de lectura (P1-5 confirmado ejecutando un bloque PoS forjado; el resto se verificó por lectura de código y de las pruebas existentes). No se modificó nada salvo este archivo.

## Resumen ejecutivo

El núcleo está bien trabajado: validación estricta de formato en bloques y transacciones, firmas Ed25519, prueba Merkle, almacén de claves scrypt + AES-GCM con AAD, escritura atómica y una suite de pruebas adversarial amplia. Los defectos importantes están en la **capa de confianza de la red** (consenso PoW sin piso de dificultad, autenticación P2P, selección de cadena) y en la **superficie HTTP del nodo** (sin autenticación ni CSRF). Hay además dos fallos de lógica de consenso/verificación que invalidan garantías anunciadas: el verificador de certificados da por "válido" un certificado de una red inventada, y el consenso PoS del simulador se puede forjar con un único nodo.

Conteo: **Alta 6 · Media 10 · Baja 12** (28 hallazgos, ninguno Crítico porque todos exigen una condición previa: ser laboratorio del génesis, tener el nodo desbloqueado o un navegador con el nodo abierto).

## Hallazgos (ordenados por severidad)

### P1-1. La dificultad PoW la elige el minero y el mínimo es 1: cualquier laboratorio reescribe la historia y crea saldo
- Categoría: Error de lógica
- Severidad: Alta
- Ubicación: `models/pow.py:17`, `models/pow.py:33-42`, `models/nodo_completo.py:40-47`, `models/nodo_completo.py:438-445`, `controllers/sellalo.py:323-328`
- Confianza: Seguro
- Evidencia: `DIF_MIN, DIF_MAX = 1, 6`; `verificar_pow` sólo exige que `dificultad` esté en ese rango y que el hash empiece con esa cantidad de ceros. `trabajo()` suma `16**dificultad` de lo que cada bloque *declara*. No hay dificultad de red, reajuste, mínimo en el génesis ni límite de profundidad de reorganización. El nodo mina por defecto con `dificultad=2` (256 hashes por bloque).
- Escenario de falla: un laboratorio malicioso (basta una clave del génesis) mina en su PC una cadena propia desde el génesis con bloques de dificultad 1–3 firmados sólo por él y la ofrece por P2P; si suma más trabajo que la honrada (p. ej. 1 000 bloques honrados a d=2 ≈ 256 000 hashes, segundos de CPU), todos los nodos la adoptan en `_recibir_cadena`. Resultado: desaparecen los sellos ajenos y puede re-sellar los mismos `doc_hash` quedando "primero" (la prioridad es el orden de cadena). Además cada bloque barato acuña `recompensa` créditos (inflación) usando transferencias o sellos triviales como relleno. Esperado: un coste de reescritura que dependa de una dificultad acordada por la red.
- Corrección propuesta: fijar `dificultad_minima` (y objetivo) en `parametros` del génesis, rechazar bloques por debajo en `verificar_pow` y en `_chequeo_ligero`; añadir reajuste de dificultad o al menos mínimo alto; limitar la profundidad de reorganización (p. ej. no aceptar una cadena que cambie bloques con más de `confirmaciones` de antigüedad salvo por trabajo muy superior) y puntos de control en el génesis.

### P1-2. API HTTP del nodo sin autenticación, sin protección CSRF ni comprobación de `Host`
- Categoría: Seguridad
- Severidad: Alta
- Ubicación: `app.py:25-46` (sin `before_request`/cabeceras), `controllers/entradas.py:17-33`, `controllers/sellalo.py:231-241`, `:259-275`, `:287-309`, `:323-328`, `:337-355`, `:426-437`
- Confianza: Seguro
- Evidencia: ninguna ruta de `/api/sellalo/*` exige credencial; `datos()` acepta también formularios `application/x-www-form-urlencoded` (`elif request.form`), que es una petición "simple" de navegador (sin preflight CORS). Una vez desbloqueado el nodo, `POST /api/sellalo/transferencias` firma con la clave del laboratorio. No se valida `Origin`/`Host`. Un `grep` de `csrf|origin|cors|samesite|after_request|X-Frame` no encuentra defensas.
- Escenario de falla: el investigador tiene su nodo desbloqueado en `127.0.0.1:5001` y abre una página maliciosa que envía un `<form method=post action="http://127.0.0.1:5001/api/sellalo/transferencias">` con `receptor=LAB-X&monto=100`: el nodo firma y difunde la transferencia. Igual con `/sellos` (sellar cualquier hash en su nombre), `/minar`, `/bloquear`, `/pares` (conectar a un host del atacante) y `/ataques` (P1-14). El *DNS rebinding* sortea además la restricción a `127.0.0.1` porque no se valida `Host`. Esperado: 403 sin un token/origen válido.
- Corrección propuesta: exigir un token por sesión (cabecera `X-Sellalo-Token` generada al arrancar y entregada sólo en la página `/`), rechazar peticiones cuyo `Origin`/`Referer` no coincida con el host del nodo, validar `Host` contra una lista, aceptar sólo `application/json` en las rutas que cambian estado, añadir `X-Frame-Options: DENY` / CSP `frame-ancestors 'none'` (clickjacking) y `SameSite` si algún día se usan cookies.

### P1-3. Veto de identidad suplantada antes de autenticar: cualquiera puede aislar a un laboratorio
- Categoría: Seguridad
- Severidad: Alta
- Ubicación: `models/red_p2p.py:403`, `:373`, `:418`, `:172-185`, `:328`
- Confianza: Seguro
- Evidencia: en `_saludo_entrante` se asigna `par.id = msg["nodo"]` (identidad *declarada*, sin probar) antes de leer el AUTH; si la firma del reto es inválida se ejecuta `self._sumar_falta(par.id, "firma de reto inválida")`, y las faltas del saludo también usan `par.id or par.ip`. A las 5 faltas `_vetos[par.id]` queda activo y `_validar_datos_hello` rechaza con "par vetado temporalmente" (`self.vetado(pid)`) al laboratorio real durante `segundos_veto` (60 s).
- Escenario de falla: un host cualquiera con acceso TCP al puerto P2P abre 5 conexiones, envía `HELLO` con `nodo="LAB-B"`, recibe el `HELLO_ACK` y manda un `AUTH` con basura (sin clave): el nodo víctima veta a "LAB-B". Repetido cada minuto, LAB-B queda desconectado de la víctima (y vía `conectar` saliente también, que usa `_validar_datos_hello`). Esperado: las faltas previas a la autenticación se acumulan sólo por IP; por identidad sólo cuando ya está probada.
- Corrección propuesta: antes de `_registrar`, usar `par.ip` como clave de faltas (no `par.id`); asignar `par.id` sólo tras verificar la firma del reto; no permitir que un par no autenticado afecte a `_vetos[<id>]`.

### P1-4. El verificador de certificados valida contra el génesis que trae el propio certificado
- Categoría: Seguridad
- Severidad: Alta
- Ubicación: `verificar_certificado.py:76-107`, `:186-191`, `:217-231`; `controllers/sellalo.py:403-422`
- Confianza: Seguro
- Evidencia: `genesis_esperado` es opcional (`None` por defecto). Con `None` el verificador acepta el `genesis` incluido en el JSON, comprueba que su hash es coherente, que los bloques enlazan con PoW (dificultad 1 basta) y que las firmas corresponden a las claves *de ese génesis*, e imprime "CERTIFICADO VÁLIDO". El endpoint web `/certificado/verificar` llama `verificar(cert, documento)` sin génesis y devuelve `valido=True`; la red sólo se señala aparte con `misma_red`.
- Escenario de falla: un tercero crea sus propias claves, un génesis propio, mina un bloque a dificultad 1, sella cualquier `doc_hash` con fecha arbitraria y entrega el certificado. `python verificar_certificado.py cert.json` responde "CERTIFICADO VÁLIDO" y exit 0. Esperado: sin una referencia de confianza (hash del génesis), no declarar "válido".
- Corrección propuesta: hacer `--genesis` obligatorio (o emitir "VÁLIDO sólo internamente; red no comprobada" con código de salida distinto), publicar el hash del génesis de la red en el README y en la salida, y en el endpoint devolver `valido=False` (o `valido="no_comprobado"`) cuando `misma_red` sea falso.

### P1-5. PoS: el comité de validadores y las apuestas los declara el propio proponente; un solo nodo forja bloques válidos
- Categoría: Error de lógica
- Severidad: Alta (simulador PoS)
- Ubicación: `models/pos.py:79-131`, `:134-157`, `models/validacion.py:48-54`
- Confianza: Seguro (reproducido)
- Evidencia: `verificar_pos` sólo exige que cada validador del bloque exista, tenga `apuesta > 0` y no supere su saldo; que el sorteo (con semilla pública) sobre *esa lista* elija al proponente y que los votos de *esa lista* sumen 2/3. Nada obliga a que el comité sea el conjunto de nodos con saldo ni un mínimo de participantes o de stake.
- Escenario de falla: reproducido con `Red("pos", n=10, …)`: el nodo N00 construye un bloque con `validadores=[{"id":"N00","apuesta":1}]`, firma la propuesta y vota a favor con su propia clave; `N03.recibir_cadena(...)` devuelve `(True, 'aceptada')`. Cualquier nodo puede así acuñar bloques/recompensas sin que nadie más participe. Esperado: rechazo (comité y pesos derivados del estado de la cadena).
- Corrección propuesta: derivar el comité de forma determinista y verificable del estado (p. ej. todos los nodos con saldo ≥ umbral, o muestra con semilla pública = `hash_anterior`) y comprobar en `verificar_pos` que `validadores` coincide; exigir quórum mínimo y calcular los pesos por saldo/stake del estado, no por lo que declara el bloque.

### P1-6. Selección de cadena inconsistente: un bloque con menos altura pero más trabajo se ignora y la sincronización sólo ocurre en el saludo
- Categoría: Error de lógica
- Severidad: Alta
- Ubicación: `models/nodo_completo.py:381-382`, `:369-397`; `models/red_p2p.py:501-503`, `:563-568`
- Confianza: Seguro (comportamiento por código); impacto depende de dificultades distintas entre mineros
- Evidencia: `_recibir_bloque` descarta como "duplicado" cualquier bloque con `numero < self.altura` (y los de igual altura con hash mayor), aunque pertenezca a una rama con **más trabajo acumulado**. La regla oficial (`_recibir_cadena`) compara trabajo, pero sólo se invoca si el bloque tiene `numero > altura` (o igual y hash menor). `_tras_saludo` es el único sitio que sincroniza por `trabajo` mayor; `_actualizar_resumen` (PING/PONG) actualiza `par.trabajo` sin disparar sincronización.
- Escenario de falla: A mina a d=4 (cadena de 5 bloques, trabajo 327 680); B mina a d=2 (100 bloques, trabajo 25 600). Los bloques nuevos de A tienen `numero` < altura de B y se ignoran en silencio; B nunca adopta la cadena con más trabajo hasta que se reconecte. Las dos redes quedan divididas, y el sello del mismo documento puede quedar "primero" en cadenas distintas. Esperado: converger a la cadena de mayor trabajo.
- Corrección propuesta: en `_recibir_bloque`, si el bloque declara trabajo suficiente (o el par anunció `trabajo` mayor en PING/PONG) pedir sincronización en vez de descartar por altura; disparar `_iniciar_sync` cuando `par.trabajo > resumen()["trabajo"]` tras cualquier actualización de resumen.

### P1-7. Autenticación P2P sin ligadura al canal: el reto sólo vincula la identidad firmante
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `models/red_p2p.py:305-306`, `:392-427`, `:466-471`
- Confianza: Posible
- Evidencia: cada extremo firma `f"{reto}|{nodo.id}"`, es decir, el reto *del otro* y su propio id; la firma no incluye la identidad del verificador, ni ambos retos, ni un identificador de sesión. Los mensajes posteriores (BLOQUE, TX, GET_BLOQUES…) no llevan MAC y el tráfico no está cifrado.
- Escenario de falla: un atacante M entre A y B (o que conecte a ambos) abre una conexión a A diciendo ser B y otra a B diciendo ser A, usando como `reto` hacia B el reto que A le entregó: B firma `reto_A|B`, que M reenvía como AUTH a A. M queda autenticado como "B" ante A (reflejo/relé) sin conocer la clave. Después M puede inyectar o filtrar mensajes en ese canal (bloques/TX siguen validándose por contenido, pero se pueden retener, reordenar o descartar: eclipse). Habría que comprobar en un laboratorio con tres procesos si la política "par ya conectado" lo impide en la práctica.
- Corrección propuesta: firmar `H(reto_propio ‖ reto_ajeno ‖ id_propio ‖ id_ajeno ‖ dirección)` con etiqueta de dominio, y/o cifrar el canal (Noise/TLS con las claves del génesis) y autenticar cada mensaje.

### P1-8. Deduplicación de BLOQUE por el `hash` que declara el emisor, antes de validar
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `models/red_p2p.py:198-208`, `:620-636`
- Confianza: Seguro
- Evidencia: `_clave_dedup("BLOQUE", obj)` devuelve `"B:" + obj["hash"]` sin recalcular el hash, y `_recibir_bloque` ejecuta `self._visto(...)` **antes** de `nodo.recibir_bloque`. El bloque falso se rechaza (falta al emisor), pero la clave ya quedó marcada como vista.
- Escenario de falla: un laboratorio malicioso M, par de A y B, ve llegar el bloque legítimo `X` (hash `h`) y envía a B un bloque alterado con `hash=h` antes de que llegue el legítimo; B lo rechaza, pero cuando A le envía el verdadero lo ignora como "ya visto" y no lo reenvía. B se queda atrasado hasta el siguiente bloque (que dispara sync). Coste para M: una falta por intento. Esperado: marcar como visto sólo tras aceptar, o usar el hash recalculado.
- Corrección propuesta: llamar a `_visto` después de `recibir_bloque` con estado `aceptado`/`duplicado`, o calcular `hash_bloque(bloque)` para la clave.

### P1-9. Un sello multifirma completo se pierde si no entra a pendientes
- Categoría: Procedimiento incompleto
- Severidad: Media
- Ubicación: `models/coordinador_sellos.py:221-230`, `:279-288`, `:320-329`, `:150-160`
- Confianza: Seguro
- Evidencia: al alcanzar el umbral el sello se borra de `_en_firma` y se guarda (`del self._en_firma[...]`, `_guardar()`), y *después* se llama a `_a_pendientes`, que captura `ErrorEntrada`/`ErrorEstado` (lista de 200 llena, saldo, sello ya inválido) y devuelve `False`. No se reinserta ni se reintenta; `firmar()` incluso responde `estado: "en_firma"` aunque el sello ya no está en la lista.
- Escenario de falla: la lista de pendientes está llena (`MAX_PENDIENTES=200`) cuando llega la última firma: el sello completo desaparece de `sellos_en_firma.json`; la UI dice "en_firma" pero nadie puede volver a firmarlo ("no está esperando firmas") y hay que repetir todo el proceso. Esperado: conservarlo para reintentar.
- Corrección propuesta: sólo eliminar de `_en_firma` si `_a_pendientes` tuvo éxito; si falla por capacidad, dejarlo como "completo, pendiente de entrar" y reintentar en `_limpiar`.

### P1-10. Rechazos que dependen del estado local se cuentan como faltas del par honesto
- Categoría: Error de lógica
- Severidad: Media
- Ubicación: `models/red_p2p.py:638-648`, `:172-185`; `models/nodo_completo.py:289-290`, `:302-304`, `:305-311`
- Confianza: Posible (hay que comprobar con una red real y carga)
- Evidencia: `_recibir_tx` convierte en `_Falta` cualquier `ErrorEntrada/ErrorEstado` de `agregar_transaccion`, incluidos "lista de pendientes llena", "saldo insuficiente" (el estado local puede ir un bloque atrás), "ya está en la cadena" y "duplicada". Cinco faltas = veto 60 s del par (`_sumar_falta`).
- Escenario de falla: con 200 pendientes en un nodo (o tras una reorganización), un par honesto que retransmite transacciones válidas acumula faltas y queda vetado, fragmentando la red justo en momentos de carga. Esperado: sólo contar como falta lo que sea inválido *por sí mismo* (formato, firma), no por estado.
- Corrección propuesta: distinguir en `agregar_transaccion` errores estructurales de errores de capacidad/estado (excepciones distintas) y no penalizar los segundos.

### P1-11. Sin límite de conexiones entrantes ni de hilos antes del saludo
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `models/red_p2p.py:249-257`, `:285-296`, `:131`, `:174-180`
- Confianza: Seguro (código) / Posible (magnitud)
- Evidencia: `_aceptar` crea un hilo por conexión sin tope global ni por IP; el veto por IP sólo se consulta al aceptar y exige 5 faltas, así que 5 000 conexiones simultáneas desde una IP entran todas antes de cualquier veto. `_faltas` y `_vetos` (clave: IP o id) nunca se purgan (sólo se resetea al vetar o al consultar `vetado`).
- Escenario de falla: un host abre miles de sockets que no envían nada: cada uno retiene un hilo ≥5 s (tiempo de saludo) y el proceso se queda sin memoria/hilos; `_faltas` crece con IPs distintas. Esperado: tope de conexiones pendientes y por IP, y purga de contadores.
- Corrección propuesta: límite global y por IP de conexiones sin autenticar (p. ej. 32/4), cerrar de inmediato al excederlo, y expirar entradas antiguas de `_faltas`/`_vetos`.

### P1-12. Certificados emitidos y aceptados sin confirmaciones; "prioridad" no demostrable
- Categoría: Error de lógica
- Severidad: Media
- Ubicación: `models/certificado.py:28-49`, `verificar_certificado.py:134-137`, `:179-183`, `controllers/sellalo.py:380-388`
- Confianza: Seguro
- Evidencia: `generar_certificado` incluye el sello aunque esté en la punta (0 confirmaciones) y el verificador sólo exige `numero_bloque <= punta`; con 0 confirmaciones imprime "CERTIFICADO VÁLIDO". Además, el certificado prueba que el sello *existe* en una cadena, no que sea el más antiguo del documento (otros sellos del mismo `doc_hash` en bloques anteriores no se pueden excluir offline), y `resumen_certificado` lo presenta como certificado de prioridad.
- Escenario de falla: se emite un certificado de un sello recién minado; una reorganización (P1-1/P1-6) lo elimina; el titular conserva un certificado "válido". Esperado: umbral mínimo de confirmaciones (las 6 del génesis) para considerarlo definitivo, y texto que aclare que no acredita ser el primero.
- Corrección propuesta: negarse a generar (o marcar "provisional") certificados con menos de `confirmaciones`; incluir en el certificado los sellos anteriores conocidos del mismo documento o declarar la limitación; que el verificador exija `confirmaciones >= parametros.confirmaciones` para "válido definitivo".

### P1-13. Un laboratorio puede llenar los cupos de sellos en firma y de firmas huérfanas
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `models/coordinador_sellos.py:22-23`, `:195-196`, `:267-270`, `:309-310`
- Confianza: Seguro
- Evidencia: `MAX_EN_FIRMA=200` (24 h de caducidad) y `MAX_HUERFANAS=200` sin expiración: `_huerfanas[sid][autor]=firma` se guarda **sin verificar la firma** y sólo se retira cuando llega la propuesta. Cualquier par autenticado puede enviar 200 `SELLO_FIRMA` con `id_sello` aleatorios (basta que `autor` esté en el génesis).
- Escenario de falla: tras 200 firmas basura, las firmas legítimas que lleguen antes que su propuesta se descartan para siempre (hasta reiniciar) y el sello 2-de-2 no completa; con 200 propuestas válidas de un laboratorio se bloquean las propuestas de los demás durante 24 h ("Hay demasiados sellos esperando firmas").
- Corrección propuesta: cupo por laboratorio/par, expiración de huérfanas (p. ej. 10 min), verificar la firma al guardarla o ligarla a `(autor, sid)` con tope.

### P1-14. Endpoint de ataques de demostración activo en el nodo real: firma con la clave del laboratorio y difunde a la red
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `controllers/sellalo.py:426-437`, `models/ataques_sellalo.py:143-186`
- Confianza: Seguro
- Evidencia: con el nodo desbloqueado, `POST /api/sellalo/ataques` con `destino:"red"` fabrica bloques/transacciones inválidos **firmados con la clave real** y los envía a todos los pares; no hay interruptor de configuración que lo desactive.
- Escenario de falla: por CSRF (P1-2) o por un usuario curioso, el nodo envía 5 mensajes inválidos a cada par y estos lo vetan 60 s (P1-10) y registran faltas contra su identidad; en una red real eso degrada la reputación y la conectividad. Esperado: función de demostración desactivada salvo `--demo`.
- Corrección propuesta: registrar la ruta sólo con una opción explícita (`--habilitar-ataques`) y limitar `destino="red"` a redes de demostración.

### P1-15. Reloj del bloque manipulable hacia atrás: la "fecha" del certificado no es fiable
- Categoría: Error de lógica
- Severidad: Media
- Ubicación: `models/validacion.py:33`, `models/nodo_completo.py:345-346`, `verificar_certificado.py:123-133`, `:178`
- Confianza: Seguro
- Evidencia: el único control sobre `timestamp` es `>= timestamp del bloque anterior` (y `<= ahora + 120 s` sólo para bloques sueltos). Un minero puede usar exactamente el timestamp del bloque previo aunque hayan pasado horas. El verificador **ni siquiera** comprueba monotonía ni que sea posterior al génesis.
- Escenario de falla: tras un periodo sin actividad, un laboratorio mina su bloque con la fecha del anterior (horas antes) o, en un certificado fabricado, con cualquier fecha; el certificado muestra esa "Fecha del bloque". Esperado: tolerancia acotada respecto a la mediana de los últimos bloques y el reloj local, y verificador que compruebe orden temporal.
- Corrección propuesta: exigir `timestamp > mediana(últimos N)` y `<= ahora + margen`, y replicar la comprobación de monotonía en `verificar_certificado.py`.

### P1-16. Condición de carrera en el primer sello: el `doc_hash` es público antes de minarse (adelantamiento)
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `controllers/sellalo.py:287-309`, `models/coordinador_sellos.py:186-200`, `models/red_p2p.py:638-648`
- Confianza: Posible (es una limitación de diseño; habría que decidir si se acepta)
- Evidencia: el sello viaja en claro (TX / `SELLO_PROPUESTO`) con `doc_hash`, título e investigador antes de entrar a un bloque, y la prioridad es el orden de cadena.
- Escenario de falla: un nodo malicioso ve el `doc_hash` en pendientes, crea su propio sello con el mismo hash y lo mina a dificultad 1 en un bloque anterior (P1-1). Su sello queda "prioritario". Esperado: esquema commit-reveal (publicar `H(doc_hash‖sal)` y revelar después) o aceptar y documentar la limitación.
- Corrección propuesta: sello en dos fases (compromiso → revelación tras k bloques) o cifrar los metadatos hasta su inclusión.

### P1-17. Ataques de demostración del simulador minan hasta 3 M de hashes dentro del candado de la red
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `models/ataques.py:190-200`, `:55-70` (`atacar_cadena` bajo `red.lock`), `controllers/api.py:122-135`
- Confianza: Seguro
- Evidencia: `_minar` busca nonce hasta `LIMITE_MINADO_ATAQUE = 3_000_000` mientras `atacar_cadena` mantiene `red.lock`; con la dificultad del simulador en 5–6 puede ocupar varios segundos, bloqueando todas las demás peticiones de esa red. El endpoint no requiere autenticación.
- Escenario de falla: un cliente repite `POST /api/pow/ataques {"tipo":"recompensa_falsa"}` con dificultad 6 y mantiene la red bloqueada. Esperado: trabajo acotado o fuera del candado.
- Corrección propuesta: minar fuera del candado o limitar a dificultad ≤4 para estos casos.

### P1-18. Verificación de certificados sin límite de trabajo (DoS de CPU)
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `controllers/sellalo.py:390-422`, `verificar_certificado.py:109-137`, `app.py:38`
- Confianza: Posible
- Evidencia: el endpoint acepta hasta 25 MiB de JSON; cada encabezado se re-hashea y se verifica su firma Ed25519 (`_firma_ok` sin caché ni tope de encabezados).
- Escenario de falla: un certificado de ~25 MiB con decenas de miles de encabezados mantiene un hilo del servidor varios segundos por petición, sin autenticación. Esperado: tope de encabezados (p. ej. 100 000) y de tamaño menor para certificados.
- Corrección propuesta: limitar `len(encabezados)` y el tamaño del campo; medir tiempo máximo.

### P1-19. Descubrimiento y conexión a destinos arbitrarios desde `/pares` (escaneo interno)
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `controllers/sellalo.py:259-275`, `models/red_p2p.py:429-452`
- Confianza: Seguro
- Evidencia: `POST /api/sellalo/pares` abre una conexión TCP a cualquier IP/puerto y devuelve mensajes distintos ("No se pudo conectar…: Connection refused" / "no respondió al saludo"), lo que permite escanear la red interna desde el nodo (combinado con P1-2). Además `RE_HOST` admite nombres de host, pero `conectar` sólo acepta IP: un nombre válido pasa el controlador y falla después con "IP inválida" (validación inconsistente).
- Corrección propuesta: autenticar la ruta (P1-2), unificar la validación y no reflejar el motivo detallado.

### P1-20. Sin límite de intentos al desbloquear y scrypt ejecutado bajo el candado del nodo
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `controllers/sellalo.py:231-241`, `models/nodo_completo.py:213-224`, `models/keystore.py:25`
- Confianza: Seguro
- Evidencia: no hay contador ni espera entre intentos; `abrir_almacen` (scrypt N=2^15, ~100 ms y 32 MB) se ejecuta con `self.lock` tomado, bloqueando P2P y UI. N=2^15 queda por debajo de la recomendación actual (≥2^17) de OWASP.
- Escenario de falla: un cliente local/CSRF lanza intentos de contraseña en paralelo sin freno, y cada uno paraliza el nodo ~0,1 s. Esperado: retardo exponencial y scrypt fuera del candado.
- Corrección propuesta: limitar intentos/segundo, calcular la clave fuera de `self.lock`, subir N a 2^17 (el archivo ya guarda sus parámetros).

### P1-21. Manejo de errores en el almacén de claves: JSON profundamente anidado provoca excepción no controlada y parámetros KDF sin tope realista
- Categoría: Manejo de excepciones
- Severidad: Baja
- Ubicación: `models/keystore.py:96-122`, `:27`
- Confianza: Seguro (RecursionError) / Posible (memoria)
- Evidencia: `_leer` captura `(OSError, ValueError)`; `json.load` de un archivo con miles de `[` lanza `RecursionError` (subclase de `RuntimeError`) y escapa, por ejemplo al arrancar el nodo (`NodoCompleto.__init__` → `leer_publica`) con traceback. `N_MAX_ACEPTADO = 2**20` con `r ≤ 16` permite pedir ~2 GiB de scrypt a un archivo alterado.
- Corrección propuesta: capturar `RecursionError`, y acotar `n*r` (p. ej. ≤ 2^18·8).

### P1-22. Persistencia: errores de escritura tragados y reescritura completa bajo candado
- Categoría: Manejo de excepciones
- Severidad: Baja
- Ubicación: `models/nodo_completo.py:196-206`, `:328-343`, `models/coordinador_sellos.py:60-78`
- Confianza: Seguro
- Evidencia: `_guardar_cadena/_guardar_pendientes` sólo registran un evento en la bitácora si falla (`OSError`), pero el nodo continúa con la cadena en memoria adelantada respecto al disco; además se serializa y hace `fsync` de **toda** la cadena en cada bloque dentro de `self.lock` (O(n²) en I/O y bloqueo de P2P).
- Escenario de falla: disco lleno → el nodo sigue minando y difundiendo, y al reiniciar pierde bloques/sellos propios sin aviso visible fuera de la bitácora. Esperado: error visible y/o parada del minado.
- Corrección propuesta: propagar el error a `publico()` (estado "no persistente"), guardar de forma incremental (añadir bloque) y fuera del candado.

### P1-23. Difusión secuencial y bloqueante: un par lento retrasa a todos
- Categoría: Otro
- Severidad: Baja
- Ubicación: `models/red_p2p.py:211-219`, `:697-706`, `:535`
- Confianza: Seguro
- Evidencia: `difundir` envía uno por uno con `sendall` bajo `lock_envio` y timeout de socket de 10 s; se invoca desde el hilo de minado (`_emitir`) y desde hilos de recepción. Un par que no lee ocupa hasta 10 s por mensaje.
- Corrección propuesta: cola de salida por par con hilo propio y límite de tamaño.

### P1-24. Sin cabeceras de seguridad y fuentes externas sin SRI
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `views/templates/index.html:7-9`, `views/templates/sellalo.html:7-9`, `app.py` (sin `after_request`)
- Confianza: Seguro
- Evidencia: se cargan estilos de Google Fonts sin `integrity` ni CSP; no se envían `X-Content-Type-Options`, `Content-Security-Policy` ni `X-Frame-Options`. El JS evita `innerHTML` con datos externos (sí está bien: construye con `textContent`), por lo que no se halló XSS.
- Corrección propuesta: `after_request` con CSP restrictiva (`default-src 'self'`), alojar las fuentes localmente.

### P1-25. Coautores listados sin consentimiento cuando `umbral < n`
- Categoría: Error de lógica
- Severidad: Baja
- Ubicación: `models/multifirma.py:31-57`, `:93-124`, `controllers/sellalo.py:287-309`
- Confianza: Seguro (comportamiento) / Posible (si se considera defecto)
- Evidencia: un sello k-de-n es válido con `k` firmas, y `autores` puede incluir laboratorios que no firmaron (ni se enteraron: `umbral=1` con 5 autores se publica sin su intervención).
- Escenario de falla: LAB-A sella un documento con `autores=[A,B,C]`, `umbral=1`; el certificado atribuye autoría a B y C. Esperado: la UI/certificado debe distinguir "autores" de "firmantes".
- Corrección propuesta: mostrar y exigir en el certificado la lista de firmantes efectivos; documentar la semántica.

### P1-26. Crecimiento sin límite de certificados y de la cadena servida por HTTP
- Categoría: Otro
- Severidad: Baja
- Ubicación: `models/certificado.py:28-49`, `controllers/sellalo.py:380-388`, `models/red_p2p.py:27`
- Confianza: Posible
- Evidencia: el certificado incluye **todos** los encabezados de la cadena (~0,7 KiB c/u); a ~35 000 bloques supera los 25 MiB que el propio endpoint de verificación acepta, y `MAX_BLOQUES_SYNC = 200 000` se pasa de ese tope. Cada `GET /certificado/<hash>` recorre la cadena completa.
- Corrección propuesta: encabezados sólo desde el bloque del sello hasta la punta más una cadena de enlace compacta, o checkpoints.

### P1-27. Código muerto, importaciones sin uso y constantes duplicadas
- Categoría: Código muerto o duplicado
- Severidad: Baja
- Ubicación: `models/coordinador_sellos.py:18` (`firmar_sello`), `models/pow.py:10` (`time`), `models/keystore.py:164-167` (`cambiar_contrasena`, sólo en pruebas), `models/merkle.py` (`verificar_camino`, sólo pruebas; el verificador usa su copia `_camino_ok`), `models/red_p2p.py` (`faltas_de`, sólo pruebas), `controllers/sellalo.py:349-352` (clase `_Firmador` anónima para adaptar `nodo.firmar`); duplicados: `MARGEN_FUTURO` (120 en `nodo_completo.py:34` vs 600 en `coordinador_sellos.py:24`), `MAX_PENDIENTES` (`red.py:27` y `nodo_completo.py:33`), `TITULO_MAX/INVESTIGADOR_MAX` (`multifirma.py:12` y `controllers/sellalo.py:34`), `_rango` (`pow.py` y `red.py`), `ID_VALIDO` (`keystore.py:24` y `scripts/crear_identidad.py:21`), `_ok` (`api.py` y `sellalo.py`).
- Confianza: Seguro (análisis AST + `git grep`)
- Evidencia/Escenario: sin impacto funcional hoy; el riesgo es que una constante se cambie en un sitio y no en el otro (p. ej. el límite de autores 5 está en tres lugares: `multifirma.py`, `controllers/sellalo.py:190` y el JS).
- Corrección propuesta: importar la constante única; eliminar o mover a pruebas lo que sólo ellas usan. (La duplicación del verificador es *intencional* por su independencia y no se reporta.)

### P1-28. Dependencias sin fijar y herramientas de prueba mezcladas con las de ejecución
- Categoría: Otro
- Severidad: Baja
- Ubicación: `requirements.txt`
- Confianza: Seguro
- Evidencia: `flask>=3.0`, `cryptography>=42.0`, `pytest>=8.0` sin límite superior ni archivo de bloqueo; `pytest` se instala en producción. No hay CI ni auditoría de dependencias.
- Corrección propuesta: `requirements.txt` con versiones exactas (o `pip-compile`), `requirements-dev.txt` para `pytest`, y `pip-audit` en CI.

## Observaciones sin hallazgo (comprobadas y correctas)

- Secretos: `git grep` no halla claves ni contraseñas en el código; `clave.json`, `data/` y `*.key` están en `.gitignore`; no hay historial de `clave.json`. Las contraseñas de prueba están marcadas como fixture.
- Criptografía: Ed25519 vía `cryptography`, nonces y sales de `secrets`/`os.urandom`, AES-GCM con AAD ligado a `id|clave pública`, mensaje de error único para contraseña incorrecta o archivo alterado.
- Merkle: la duplicación del último nodo (riesgo CVE-2012-2459) no es explotable porque se rechazan transacciones y sellos repetidos en el bloque (`vistos`). Prueba de inclusión con tope de 64 pasos.
- XSS: `sellalo.js` construye el DOM con `textContent`; no se usa `innerHTML`/`eval`. Flask con `debug=False`; el manejador global no expone traceback (sólo el nombre del tipo de excepción).
- Entradas: el lector TCP acota líneas a 1 MiB, JSON anidado y números gigantes están cubiertos por `tests/test_adversarial.py`.

## Tabla resumen

| id | título | categoría | severidad | ubicación |
|---|---|---|---|---|
| P1-1 | Dificultad PoW autodeclarada, mínimo 1: reescritura de historia e inflación | Error de lógica | Alta | `models/pow.py:17,33-42`; `nodo_completo.py:40-47,438-445` |
| P1-2 | HTTP sin autenticación ni CSRF ni validación de `Host` | Seguridad | Alta | `app.py:25-46`; `controllers/entradas.py:17-33`; `controllers/sellalo.py` |
| P1-3 | Veto de identidad suplantada antes de autenticar | Seguridad | Alta | `models/red_p2p.py:403,418,328` |
| P1-4 | Verificador valida contra el génesis del propio certificado | Seguridad | Alta | `verificar_certificado.py:76-107,186-191`; `controllers/sellalo.py:403-422` |
| P1-5 | PoS: comité y apuestas declarados por el proponente | Error de lógica | Alta | `models/pos.py:79-157` |
| P1-6 | Selección de cadena: menos altura/más trabajo se ignora; sync sólo en saludo | Error de lógica | Alta | `models/nodo_completo.py:381-382`; `red_p2p.py:501-503,563-568` |
| P1-7 | Autenticación P2P sin ligadura al canal (relé) | Seguridad | Media | `models/red_p2p.py:305-306,392-427,466-471` |
| P1-8 | Deduplicación por hash declarado antes de validar | Seguridad | Media | `models/red_p2p.py:198-208,620-636` |
| P1-9 | Sello multifirma completo se pierde si no entra a pendientes | Procedimiento incompleto | Media | `models/coordinador_sellos.py:221-230,279-288,320-329` |
| P1-10 | Rechazos por estado local cuentan como faltas del par honesto | Error de lógica | Media | `models/red_p2p.py:638-648`; `nodo_completo.py:289-311` |
| P1-11 | Sin límite de conexiones/hilos antes del saludo; contadores sin purga | Seguridad | Media | `models/red_p2p.py:249-296,131,174-180` |
| P1-12 | Certificados sin confirmaciones; "prioridad" no demostrable | Error de lógica | Media | `models/certificado.py:28-49`; `verificar_certificado.py:134-183` |
| P1-13 | Cupos de sellos en firma y firmas huérfanas llenables | Seguridad | Media | `models/coordinador_sellos.py:22-23,195-196,267-270,309-310` |
| P1-14 | Ataques de demostración activos en el nodo real | Seguridad | Media | `controllers/sellalo.py:426-437`; `models/ataques_sellalo.py:143-186` |
| P1-15 | Timestamp de bloque manipulable hacia atrás; verificador sin monotonía | Error de lógica | Media | `models/validacion.py:33`; `verificar_certificado.py:123-133,178` |
| P1-16 | `doc_hash` público antes de minar (adelantamiento) | Seguridad | Media | `controllers/sellalo.py:287-309`; `coordinador_sellos.py:186-200` |
| P1-17 | Ataques del simulador minan hasta 3 M hashes bajo el candado | Seguridad | Baja | `models/ataques.py:190-200` |
| P1-18 | Verificación de certificados sin tope de trabajo | Seguridad | Baja | `controllers/sellalo.py:390-422`; `verificar_certificado.py:109-137` |
| P1-19 | `/pares` conecta a cualquier IP/puerto; validación de host inconsistente | Seguridad | Baja | `controllers/sellalo.py:259-275`; `red_p2p.py:429-452` |
| P1-20 | Sin límite de intentos de desbloqueo; scrypt bajo candado; N bajo | Seguridad | Baja | `controllers/sellalo.py:231-241`; `nodo_completo.py:213-224`; `keystore.py:25` |
| P1-21 | `RecursionError` sin capturar en el almacén; parámetros KDF sin tope realista | Manejo de excepciones | Baja | `models/keystore.py:96-122,27` |
| P1-22 | Errores de escritura tragados; reescritura completa bajo candado | Manejo de excepciones | Baja | `models/nodo_completo.py:196-206,328-343` |
| P1-23 | Difusión secuencial y bloqueante | Otro | Baja | `models/red_p2p.py:211-219,697-706` |
| P1-24 | Sin cabeceras de seguridad; fuentes externas sin SRI | Seguridad | Baja | `views/templates/*.html:7-9`; `app.py` |
| P1-25 | Coautores sin consentimiento con `umbral < n` | Error de lógica | Baja | `models/multifirma.py:31-57,93-124` |
| P1-26 | Certificado y sincronización crecen sin límite (>25 MiB) | Otro | Baja | `models/certificado.py:28-49`; `red_p2p.py:27` |
| P1-27 | Código muerto, importaciones sin uso y constantes duplicadas | Código muerto o duplicado | Baja | ver detalle |
| P1-28 | Dependencias sin fijar; `pytest` en requisitos de ejecución | Otro | Baja | `requirements.txt` |

## FODA

### Fortalezas
- Validación estricta y uniforme de bloques, transacciones y sellos (`revisar_campos`, `revisar_transaccion`, `revisar_sello`): conjuntos de campos exactos, tipos con `type(v) is int`, `NaN/Infinity` descartados, doble gasto dentro y entre bloques.
- Almacén de claves bien diseñado: scrypt + AES-256-GCM con AAD, escritura atómica con permisos 0600, mensaje único ante error de contraseña, nunca se muestra la clave privada (`ParClaves.__repr__`, `publico()`).
- Autenticación P2P mutua con reto firmado por identidad del génesis, límites de línea (1 MiB), faltas/veto, y callbacks siempre fuera del candado del nodo (evita interbloqueos).
- Suite de pruebas amplia y adversarial (≈1 000 líneas de `test_adversarial.py`, e2e con procesos reales, pruebas del verificador independiente).
- Verificador de certificados independiente (sin importar `models/`), con tope de pasos Merkle y dificultad acotada.
- Interfaz sin `innerHTML` con datos externos; manejador global de errores sin traceback.

### Debilidades
- Confianza de consenso: dificultad libre con piso 1 y sin límite de reorganización (P1-1), selección de cadena incoherente (P1-6), PoS sin comité verificable (P1-5).
- Superficie HTTP sin autenticación/CSRF/`Host` (P1-2) y endpoints destructivos de demostración siempre activos (P1-14).
- Defensas P2P que castigan identidades no probadas (P1-3) o a pares honestos (P1-10), sin topes de conexiones (P1-11).
- Garantía de certificados débil: sin referencia de red, sin confirmaciones, sin ordenación temporal (P1-4, P1-12, P1-15).

### Oportunidades
- Mover la dificultad mínima, el reajuste y las confirmaciones al génesis (un solo cambio da protección contra P1-1, P1-12 y P1-6).
- Añadir un token CSRF y un `before_request` de `Origin/Host` (30–40 líneas) que cierre P1-2, P1-14 y P1-19 de una vez.
- CI con `pytest`, `pip-audit`, `bandit` y un pequeño *fuzz* de mensajes P2P; archivo de dependencias bloqueado.
- Cifrar y autenticar el canal P2P con las claves ya existentes del génesis (Noise/TLS mutuo).
- Documentar el modelo de amenazas (red cerrada de laboratorios conocidos) y la semántica de "prioridad".

### Amenazas
- Un laboratorio del génesis comprometido o deshonesto (modelo de amenaza "insider") puede reescribir historia y adelantarse en prioridades con coste de CPU mínimo.
- Páginas web o scripts locales (CSRF/DNS rebinding) contra un nodo desbloqueado; el desbloqueo prolongado deja la clave en memoria.
- Redes no confiables: el tráfico P2P sin cifrado permite observación y manipulación a nivel de canal.
- Certificados presentados como prueba legal/académica con una verificación que, tal como está, no demuestra pertenencia a la red ni prioridad.
