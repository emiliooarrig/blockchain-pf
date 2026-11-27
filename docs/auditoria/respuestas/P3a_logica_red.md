# P3a · Errores de lógica y manejo de excepciones: red, nodo, coordinador y scripts

Módulos revisados: `models/nodo_completo.py`, `models/red_p2p.py`, `models/coordinador_sellos.py`,
`models/ataques_sellalo.py`, `controllers/sellalo.py`, `app.py`, `scripts/inicializar_red.py`,
`scripts/lanzar_red_local.py`, `scripts/crear_identidad.py`, `scripts/demo_e2e.py`.
Método: lectura completa de cada módulo, contrastada con `models/bloque.py`, `models/multifirma.py`,
`models/validacion.py` y `models/errores.py` (nota: `ErrorEstado` hereda de `ErrorEntrada`). No se modificó nada del repositorio.

Zonas revisadas sin hallazgo: la persistencia atómica y la carga de `nodo_completo.py`, la selección de cadena y la
reorganización (`_recibir_cadena`, `_depurar`), el bucle de minado y su cancelación por cambio de punta, el
manejo de `ErrorEntrada/ErrorEstado` en `ataques_sellalo.ejecutar` y `crear_identidad.py`.

---

### P3a-1. Un cliente sin autenticar puede acumular faltas contra la identidad (o la IP) de un laboratorio y vetarlo
- Categoría: Seguridad
- Severidad: Alta
- Ubicación: `models/red_p2p.py:392-427` (en especial 403 y 413-420), `models/red_p2p.py:368-390`, `models/red_p2p.py:172-185`, `models/red_p2p.py:293`, `models/red_p2p.py:328`
- Confianza: Seguro
- Evidencia: en `_saludo_entrante`, `par.id = msg["nodo"]` se asigna con el HELLO, antes de probar la clave. Después `_leer_saludo(par, "AUTH")` y la verificación del reto hacen `self._sumar_falta(par.id or par.ip, ...)` y `self._sumar_falta(par.id, "firma de reto inválida")`. `_sumar_falta` veta la clave a las 5 faltas (`FALTAS_PARA_VETO`), y `_validar_datos_hello` rechaza a cualquier `pid` vetado ("par vetado temporalmente"). Los HELLO inválidos y los saludos vencidos suman además faltas a la IP (`par.ip`), y `_aceptar` descarta toda conexión de una IP vetada.
- Escenario de falla: un atacante con acceso TCP al puerto P2P conoce el id (`LAB-B`, adivinable) y el hash del génesis (visible en `/estado`). Abre 5 conexiones, envía un HELLO válido con `"nodo":"LAB-B"` y no manda AUTH (o manda una firma basura). El nodo víctima registra 5 faltas contra `LAB-B` y lo veta 60 s: el LAB-B real ya no puede conectarse (ni la víctima conectar con él). Repetible indefinidamente. En la red local de la demo todos los nodos comparten la IP 127.0.0.1, así que 5 saludos vencidos (cualquier sonda que abra el puerto y se quede callada) vetan la IP y el nodo descarta TODAS las conexiones entrantes de la malla local durante 60 s. Esperado: sólo contar faltas contra una identidad ya autenticada.
- Corrección propuesta: no usar `par.id` como clave de faltas hasta que `par.autenticado` sea True; antes de la autenticación, contar sólo por IP (con tope y sin vetar loopback ni IPs de pares ya conocidos). En `_validar_datos_hello` no rechazar por veto de identidad hasta comprobar la firma del reto.

### P3a-2. El contador de faltas nunca decae y cuenta como falta errores legítimos de pares honestos
- Categoría: Error de lógica
- Severidad: Media
- Ubicación: `models/red_p2p.py:172-185`, `models/red_p2p.py:620-648`, `models/nodo_completo.py:280-321`
- Confianza: Seguro
- Evidencia: `_faltas[clave]` sólo se reinicia al llegar a 5 (`self._faltas.pop`); nunca baja con el tiempo ni con mensajes correctos. `_recibir_tx` convierte `ErrorEntrada/ErrorEstado` en `_Falta`, y `agregar_transaccion` lanza esos errores para casos que no son culpa del par: "ya está en la lista de pendientes", "ya está en la cadena", "saldo insuficiente" y "La lista de pendientes está llena (200)". `_recibir_bloque` convierte en `_Falta` el estado "rechazado", que incluye "timestamp más de 120 s en el futuro" (desfase de reloj).
- Escenario de falla: con 200 pendientes, cada TX válida que difunda un par honesto suma una falta; a la quinta se cierra la conexión con BYE y se veta 60 s. Igual con 5 rechazos espaciados durante horas (los contadores no expiran): un par honesto con el reloj 3 minutos adelantado, o que retransmite una TX ya minada llegada por otro camino, termina vetado. Con `/ataques` en destino `red` (`ataques_sellalo.ejecutar`) la quinta demostración en toda la vida del proceso expulsa al propio nodo de sus pares. Esperado: errores benignos sin falta, y faltas con ventana temporal.
- Corrección propuesta: distinguir en `_recibir_tx`/`_recibir_bloque` entre "inválido por construcción" (firma, formato, hash) y "no aplicable ahora" (duplicada, ya en cadena, pendientes llena, saldo, futuro), que sólo se registre en bitácora. Guardar las faltas como marcas de tiempo y contar sólo las de los últimos N minutos.

### P3a-3. No existe reconexión automática: una caída de enlace, un veto o un `BYE` dejan la malla degradada de forma permanente
- Categoría: Procedimiento incompleto
- Severidad: Media
- Ubicación: `controllers/sellalo.py:63-80`, `models/red_p2p.py:514-552`, `models/red_p2p.py:221-241`
- Confianza: Seguro
- Evidencia: la búsqueda de `.conectar(` en el código de producción sólo encuentra `ContextoNodo._conectar_inicial` (una vez, al desbloquear, un único intento por par; el fallo va a la bitácora) y la ruta manual `POST /pares`. El servidor cierra pares por PING sin PONG (`tiempo_sin_respuesta`), por faltas, por error de envío, etc., y nunca vuelve a intentarlo.
- Escenario de falla: un corte de red de más de 12 s cierra el enlace y, al volver la red, los nodos siguen aislados: cada uno mina su rama y los bloques nuevos no se propagan hasta que un humano reconecte por la interfaz. Lo mismo ocurre con un par que no estaba escuchando cuando el otro se desbloqueó (único intento fallido). Esperado: reintentos periódicos con retroceso hacia los pares configurados mientras el nodo esté desbloqueado.
- Corrección propuesta: un hilo de mantenimiento en `ContextoNodo` (o en `ServidorP2P`) que cada pocos segundos intente `conectar` a los pares configurados que no estén en `_pares` ni vetados, con retroceso exponencial.

### P3a-4. La deduplicación `_visto` ocurre antes de validar y usa un identificador que declara el propio par; permite censurar bloques y descartar para siempre reenvíos legítimos
- Categoría: Error de lógica
- Severidad: Media
- Ubicación: `models/red_p2p.py:187-208`, `models/red_p2p.py:620-648`
- Confianza: Seguro
- Evidencia: `_recibir_bloque` y `_recibir_tx` hacen `if self._visto(self._clave_dedup(...)): return` antes de llamar al nodo. Para BLOQUE la clave es `"B:" + obj["hash"]`, el campo que escribe el par, sin comprobar que sea el hash real del contenido. La marca no se retira cuando el bloque o la TX resultan rechazados.
- Escenario de falla: (a) un laboratorio malicioso (autenticado) que recibe el bloque legítimo `H` envía antes a la víctima un bloque basura con `"hash": H`: la víctima lo marca visto, lo rechaza (falta) y, cuando llega el bloque verdadero `H` de pares honestos, lo ignora en silencio; el nodo queda en la punta anterior hasta que llegue un bloque posterior que lo obligue a sincronizar (si la red deja de minar, se queda atrás). (b) Una TX que llega antes que el bloque que la financia se rechaza por saldo insuficiente y queda marcada: al reenviarse con fondos, se ignora. (c) Un bloque rechazado por "timestamp en el futuro" no se reconsidera cuando el reloj local lo alcanza. Esperado: marcar como visto sólo lo ya aceptado.
- Corrección propuesta: calcular `hash_bloque(bloque)` y usar ese valor (no el declarado) en la clave; mover la marca a después de la validación y sólo para resultados "aceptado"/"duplicado". Para TX usar el id calculado (`_id_tx`) y marcar tras aceptarla.

### P3a-5. Un sello multifirma completo se borra de "en firma" antes de entrar a pendientes; si no entra, se pierde y la respuesta es engañosa
- Categoría: Error de lógica
- Severidad: Media
- Ubicación: `models/coordinador_sellos.py:221-230`, `models/coordinador_sellos.py:279-288`, `models/coordinador_sellos.py:320-329`, `models/coordinador_sellos.py:150-160`, `controllers/sellalo.py:311-318`
- Confianza: Seguro
- Evidencia: en `firmar`, `_procesar_propuesto` y `_procesar_firma`, al alcanzar el umbral se hace `del self._en_firma[...]` / `pop` y se `_guardar()` ANTES de llamar a `_a_pendientes`. Éste captura `ErrorEntrada` (incluye `ErrorEstado`) y `ErrorValidacion`, deja un evento y devuelve False; nadie vuelve a poner el sello en `_en_firma`. En `firmar`, ese False se traduce en `estado = "en_firma"` y la ruta responde "Firma agregada (2/2)." aunque el sello ya no existe en el nodo.
- Escenario de falla: lista de pendientes llena (200) o sello rechazado por `revisar_sello` en ese instante: la última firma completa el sello, éste desaparece de "sellos en firma" y no está en pendientes, el usuario ve "Firma agregada (2/2)" y no hay forma de reintentar (`firmar` responde "no está esperando firmas"). Si este laboratorio era el que reunía las firmas, pierde el sello. Esperado: el sello conserva su lugar en `_en_firma` hasta que entre a pendientes o a la cadena y la respuesta indica "completo, pendiente de espacio".
- Corrección propuesta: no borrar de `_en_firma` al completar; llamar a `_a_pendientes` y dejar que `_limpiar` lo retire cuando `_ya_resuelto` sea True. Devolver un estado distinto cuando `_a_pendientes` falle.

### P3a-6. Topes globales de sellos en firma y de firmas huérfanas: se pueden agotar y la firma huérfana se puede sobrescribir sin verificarla
- Categoría: Seguridad
- Severidad: Media
- Ubicación: `models/coordinador_sellos.py:21-24`, `models/coordinador_sellos.py:258-278`, `models/coordinador_sellos.py:303-311`
- Confianza: Seguro
- Evidencia: `MAX_EN_FIRMA = 200` y `MAX_HUERFANAS = 200` son globales (sin cuota por par). Las huérfanas no caducan ni se persisten (`_huerfanas` sólo se vacía con `pop(sid)` al llegar la propuesta) y se guardan sin verificar la firma: `self._huerfanas.setdefault(sid, {})[autor] = firma` sobrescribe la anterior del mismo autor.
- Escenario de falla: un laboratorio de la red (autenticado) envía 200 propuestas propias válidas (firma como proponente) con `timestamp` reciente: todos los nodos las guardan 24 h en disco y `_procesar_propuesto` descarta las legítimas con "demasiados sellos esperando firmas"; en el origen, `proponer` lanza `ErrorEstado`. Del mismo modo, 200 `SELLO_FIRMA` con ids falsos llenan `_huerfanas` hasta reiniciar el proceso, y una `SELLO_FIRMA` basura con el `autor` de otro laboratorio reemplaza a la firma real que llegó adelantada: al llegar la propuesta, `agregar_firma` falla y esa firma no se vuelve a emitir (el gossip es de una sola vez), así que el sello queda corto de firmas hasta caducar. Esperado: cuotas por par/laboratorio y TTL o verificación de lo huérfano.
- Corrección propuesta: cuota por `par_id` y por `laboratorio` en `_en_firma`; en `_huerfanas` guardar varias firmas por autor con marca de tiempo y TTL (p. ej. 10 min), sin sobrescribir una existente.

### P3a-7. Se aceptan nombres de host en la interfaz y en `--pares`, pero `ServidorP2P.conectar` sólo admite IP
- Categoría: Error de lógica
- Severidad: Baja
- Ubicación: `controllers/sellalo.py:258-274` (265-269), `app.py:69-80`, `models/red_p2p.py:433-436`
- Confianza: Seguro
- Evidencia: `conectar_par` valida con `ipaddress.ip_address(ip)` y, si falla, acepta lo que cumpla `RE_HOST`; `parsear_pares` acepta cualquier `host`. Pero `conectar` hace `ipaddress.ip_address(str(ip).strip())` y lanza `ErrorEntrada("IP inválida: ...")` para cualquier nombre.
- Escenario de falla: `POST /pares {"ip": "localhost", "puerto": 6002}` o `--pares localhost:6002` pasa la validación del controlador y siempre falla con "IP inválida" (en `--pares` sólo queda en la bitácora). Esperado: aceptar y resolver el nombre, o rechazarlo desde la primera validación con un mensaje coherente.
- Corrección propuesta: en `conectar` resolver con `socket.getaddrinfo` cuando no sea una IP literal, o quitar `RE_HOST` y exigir IP en las tres entradas.

### P3a-8. Sin límite de conexiones entrantes sin autenticar (un hilo por conexión)
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `models/red_p2p.py:285-296`, `models/red_p2p.py:351-366`
- Confianza: Posible
- Evidencia: `_aceptar` lanza un hilo por cada conexión y `_conexiones` no tiene tope ni cuota por IP; cada una vive hasta `tiempo_saludo` (5 s) o más si manda bytes lentos.
- Escenario de falla: miles de conexiones simultáneas desde una IP no vetada consumen hilos y descriptores del proceso Flask (el veto por saludo vencido sólo se aplica tras 5 faltas, a posteriori). Comprobar con un cliente que abra ~5000 sockets y midiendo hilos y respuesta de `/estado`.
- Corrección propuesta: tope global de conexiones pendientes de saludo (p. ej. 32) y por IP (p. ej. 4); rechazar el exceso con `close()` inmediato.

### P3a-9. `cadena_intacta` del ataque da falso negativo si la punta avanza legítimamente durante el ataque
- Categoría: Error de lógica
- Severidad: Baja
- Ubicación: `models/ataques_sellalo.py:179-181`
- Confianza: Seguro
- Evidencia: `intacta = nodo.punta == punta or not rechazado`, con `punta` tomada antes de fabricar el ataque.
- Escenario de falla: con el minado continuo activo (o un bloque honesto recibido de un par) entre la captura y la comparación, la punta cambia por una razón legítima: el ataque fue rechazado (`rechazado=True`) pero `intacta=False`, y el guion (`demo_e2e.paso8_ataque`, que exige `r["cadena_intacta"]`) informa que la cadena fue alterada. Esperado: la cadena sigue intacta si la punta anterior sigue en ella.
- Corrección propuesta: `intacta = punta in nodo._hashes` bajo `nodo.lock` (o un método `contiene(hash)`), en vez de comparar con la punta actual.

### P3a-10. `lanzar_red_local.py` reutiliza un génesis de otra configuración y no pide la contraseña al ampliar la red
- Categoría: Error de lógica
- Severidad: Baja
- Ubicación: `scripts/lanzar_red_local.py:46-65`, `scripts/lanzar_red_local.py:98-103`
- Confianza: Seguro
- Evidencia: `preparar` crea las identidades que falten, pero el génesis sólo se crea `if not os.path.exists(ruta_genesis)`. En `main`, la contraseña sólo se pide si no existe `LAB-A/clave.json`.
- Escenario de falla: tras `--labs 3`, ejecutar `--labs 4` conserva el génesis de 3 laboratorios; como `LAB-A/clave.json` existe no se pide contraseña y `preparar` aborta con "Falta la contraseña para crear las identidades (usa --contrasena-env)" aunque haya terminal. Con `--contrasena-env`, crea `LAB-D` pero su nodo falla con "El nodo «LAB-D» no existe en el génesis". Esperado: detectar que el génesis no coincide con las identidades y avisar.
- Corrección propuesta: comparar `genesis["cuentas"]` con los ids de `nodos`; si difiere, abortar indicando usar otra `--carpeta` o borrar el génesis. Pedir contraseña cuando falte cualquier identidad, no sólo la primera.

### P3a-11. `demo_e2e.py`: procesos huérfanos y trazas si falla el arranque; sólo se captura `AssertionError`
- Categoría: Manejo de excepciones
- Severidad: Baja
- Ubicación: `scripts/demo_e2e.py:549-558`, `scripts/demo_e2e.py:147-155`, `scripts/demo_e2e.py:173-185`
- Confianza: Seguro
- Evidencia: `red = RedLocal(...)` y `red.lanzar_todos()` están antes del `try/finally` que llama a `red.cerrar()`. `RedLocal.__init__` llama a `crear_almacen`, que lanza `ErrorClave` si la carpeta ya tiene `clave.json`. El `try` de `main` sólo captura `AssertionError`.
- Escenario de falla: si el segundo nodo no arranca (`AssertionError("El nodo LAB-B no arrancó")`), el primero queda como proceso huérfano ocupando sus puertos y el programa termina con traza. Con `--carpeta` ya usada termina con `ErrorClave` sin explicación. Una caída de red o una respuesta no JSON durante el guion (`URLError`, `KeyError`, `ValueError` en `Cliente.subir`) también sale con traza, no con el "FALLÓ EL GUION" prometido en la cabecera. Esperado: cerrar siempre lo lanzado y explicar el fallo.
- Corrección propuesta: mover la construcción de `RedLocal`, `lanzar_todos` y el guion dentro del mismo `try/finally`; capturar `(AssertionError, OSError, ValueError, KeyError, ErrorEntrada)` e imprimir "FALLÓ EL GUION: ...".

### P3a-12. Paso 8 de la demo: espera fija de 0,8 s y comprobación que puede satisfacerse con rechazos previos
- Categoría: Error de lógica
- Severidad: Baja
- Ubicación: `scripts/demo_e2e.py:431-434`
- Confianza: Posible
- Evidencia: `time.sleep(0.8)` y luego `rechazos = [... e["tipo"] == "rechazo" and "Bloque" in e["texto"]]` sobre toda la bitácora de B y C, sin compararla con lo que tenían antes del ataque.
- Escenario de falla: en una máquina lenta el rechazo llega después de 0,8 s y el paso falla sin motivo real; en otra, un rechazo de bloque anterior hace que el paso pase aunque el ataque no llegara. Comprobar guardando el máximo `n` de la bitácora antes de atacar.
- Corrección propuesta: guardar el último `n` de la bitácora antes del ataque y usar `esperar` para exigir un rechazo con número mayor.

### P3a-13. El desbloqueo de claves (scrypt) se ejecuta con el candado del nodo tomado
- Categoría: Otro
- Severidad: Baja
- Ubicación: `models/nodo_completo.py:213-224` (219)
- Confianza: Posible
- Evidencia: `desbloquear` hace `with self.lock: ... abrir_almacen(self.ruta_clave, contrasena)`, que deriva la clave con scrypt (costoso a propósito). `self.lock` también lo toman `publico()`, `recibir_bloque`, `agregar_transaccion` y `resumen()`.
- Escenario de falla: cada intento de contraseña (incluidos los fallidos, sin límite de intentos en `POST /desbloquear`) detiene el nodo mientras dura scrypt: no se procesan bloques ni PING (`resumen()` espera) y `/estado` se congela. Un cliente con acceso a la API local puede mantener el nodo detenido repitiendo contraseñas erróneas. Medir el tiempo de `abrir_almacen` en la máquina de la demo.
- Corrección propuesta: derivar la clave fuera del candado (`claves = abrir_almacen(...)` antes de `with self.lock`) y comprobar dentro sólo el estado y la clave pública.

### P3a-14. Un bloque sin enlazar con PoW mínimo (dificultad 1) provoca sincronizaciones completas con el par
- Categoría: Seguridad
- Severidad: Baja
- Ubicación: `models/nodo_completo.py:391-408`, `models/red_p2p.py:633-634`, `models/red_p2p.py:651-686`
- Confianza: Posible
- Evidencia: para un bloque que no enlaza, `_chequeo_ligero` sólo comprueba formato, hash propio y PoW (no timestamp, proponente ni firma) y devuelve "sincronizar"; `_recibir_bloque` llama a `_iniciar_sync`, que pide la cadena desde el bloque 1 y la valida entera.
- Escenario de falla: un par autenticado que mina a dificultad 1 (trivial) un bloque con `numero` mayor que la altura cada pocos segundos hace que la víctima descargue y valide la cadena completa del par una y otra vez (`par.sincronizando` vuelve a False al terminar). La cadena resultante no se adopta si tiene menos trabajo, y el par sólo suma falta si anunciaba más trabajo (`par.trabajo > resumen()["trabajo"]`). Comprobar con dos nodos y un script que envíe estos bloques.
- Corrección propuesta: limitar a una sincronización por par cada N segundos y sumar falta cuando una cadena completa descargada no mejora la propia tras haberla provocado un bloque suelto.

### P3a-15. Conexiones simultáneas entre dos nodos pueden dejar ambas descartadas
- Categoría: Error de lógica
- Severidad: Baja
- Ubicación: `models/red_p2p.py:335-345`, `models/red_p2p.py:429-484`, `controllers/sellalo.py:74-80`
- Confianza: Posible
- Evidencia: en `conectar`, el nodo registra la conexión saliente (`_registrar`, línea 472) antes de enviar AUTH. Si en ese momento ya registró en `_pares` a ese id, su `_registrar` rechaza la entrante del otro lado con "par ya conectado" (`_rechazar` cierra con HELLO_REJECT).
- Escenario de falla: dos nodos con `--pares` mutuos desbloqueados casi a la vez: A registra A→B y rechaza B→A, B registra B→A y rechaza A→B; ambas conexiones mueren y, por P3a-3, nadie reintenta. Comprobar con dos nodos que ejecuten `conectar` el uno al otro con `threading.Barrier`.
- Corrección propuesta: desempate determinista en `_registrar` (se conserva la conexión iniciada por el id menor), además del reintento de P3a-3.

### P3a-16. `/estado` resuelve el nombre del equipo (`gethostbyname_ex`) en cada petición
- Categoría: Otro
- Severidad: Baja
- Ubicación: `controllers/sellalo.py:197-209`, `controllers/sellalo.py:222`
- Confianza: Posible
- Evidencia: `estado()` llama a `_direcciones_locales()`, que ejecuta `socket.gethostbyname_ex(socket.gethostname())` y abre un socket UDP en cada consulta; la interfaz consulta `/estado` periódicamente.
- Escenario de falla: con un DNS roto o lento, cada sondeo espera la resolución (segundos en Windows) y el panel se vuelve lento aunque el nodo esté sano. Comprobar midiendo `/estado` con DNS bloqueado.
- Corrección propuesta: calcular las direcciones al arrancar o cachearlas (p. ej. 60 s).

### P3a-17. El certificado se emite sin exigir las confirmaciones del génesis
- Categoría: Procedimiento incompleto
- Severidad: Baja
- Ubicación: `controllers/sellalo.py:379-387`, `models/certificado.py:28-49`
- Confianza: Posible
- Evidencia: `certificado(doc_hash)` llama a `generar_certificado(nodo.cadena, doc_hash)`, que acepta un sello en el último bloque (0 confirmaciones) aunque la red declara `confirmaciones = 6`. En `verificar_certificado.py` sólo se calcula y muestra el número de confirmaciones (no se vio ningún umbral que lo exija).
- Escenario de falla: un laboratorio sella, mina y descarga el certificado de inmediato; una reorganización posterior (como la partición del paso 9 de la demo) descarta el bloque y el certificado ya entregado deja de corresponder a la cadena ganadora. Comprobar en `verificar_certificado.py` si hay umbral mínimo. Esperado: advertir o negar el certificado hasta tener las confirmaciones requeridas.
- Corrección propuesta: en la ruta, comparar `nodo.altura - numero` con `confirmaciones` y devolver 409 (o incluir un indicador `confirmado: false` en la respuesta).

---

## Tabla resumen

| Id | Título | Categoría | Severidad | Ubicación |
|----|--------|-----------|-----------|-----------|
| P3a-1 | Faltas y vetos contra identidad/IP sin autenticar | Seguridad | Alta | `models/red_p2p.py:392-427`, `:368-390`, `:172-185`, `:293` |
| P3a-2 | Faltas sin decaimiento y por errores legítimos | Error de lógica | Media | `models/red_p2p.py:172-185`, `:620-648` |
| P3a-3 | Sin reconexión automática | Procedimiento incompleto | Media | `controllers/sellalo.py:63-80`, `models/red_p2p.py:514-552` |
| P3a-4 | Dedup `_visto` antes de validar y con hash declarado | Error de lógica | Media | `models/red_p2p.py:187-208`, `:620-648` |
| P3a-5 | Sello completo se borra antes de entrar a pendientes | Error de lógica | Media | `models/coordinador_sellos.py:221-230`, `:279-288`, `:320-329` |
| P3a-6 | Topes globales de sellos en firma y huérfanas agotables | Seguridad | Media | `models/coordinador_sellos.py:21-24`, `:258-278`, `:303-311` |
| P3a-7 | Hostnames aceptados pero `conectar` exige IP | Error de lógica | Baja | `controllers/sellalo.py:265-269`, `app.py:69-80`, `models/red_p2p.py:433-436` |
| P3a-8 | Sin tope de conexiones sin autenticar | Seguridad | Baja | `models/red_p2p.py:285-296`, `:351-366` |
| P3a-9 | `cadena_intacta` falso negativo | Error de lógica | Baja | `models/ataques_sellalo.py:179-181` |
| P3a-10 | `lanzar_red_local` reutiliza génesis ajeno | Error de lógica | Baja | `scripts/lanzar_red_local.py:46-65`, `:98-103` |
| P3a-11 | `demo_e2e` deja procesos huérfanos y sólo captura AssertionError | Manejo de excepciones | Baja | `scripts/demo_e2e.py:549-558`, `:147-155`, `:173-185` |
| P3a-12 | Paso 8 con espera fija y chequeo débil | Error de lógica | Baja | `scripts/demo_e2e.py:431-434` |
| P3a-13 | scrypt bajo el candado del nodo | Otro | Baja | `models/nodo_completo.py:213-224` |
| P3a-14 | Bloque sin enlazar con PoW mínimo provoca sincronizaciones | Seguridad | Baja | `models/nodo_completo.py:391-408`, `models/red_p2p.py:633-686` |
| P3a-15 | Conexiones simultáneas se descartan mutuamente | Error de lógica | Baja | `models/red_p2p.py:335-345`, `:429-484` |
| P3a-16 | DNS en cada `/estado` | Otro | Baja | `controllers/sellalo.py:197-209`, `:222` |
| P3a-17 | Certificado sin exigir confirmaciones | Procedimiento incompleto | Baja | `controllers/sellalo.py:379-387` |
