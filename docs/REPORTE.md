# Reporte: Sellalo, simulador de blockchain con Proof of Work y Proof of Stake

**Universidad Anáhuac México · Facultad de Ingeniería · Proyecto de entrega del examen de MT**
**Autor:** Emilio Arriaga Guzmán · **Video:** _[agregar liga del video]_ · **Repositorio:** rama `medi-termino`

## 1. Contexto: Sellalo

El simulador se presenta como **Sellalo**, una red de sellado de tiempo entre laboratorios de investigación pensada para demostrar prioridad científica. Es la continuación de nuestro proyecto anterior. La adaptación es **sólo visual**:

- cada **nodo** se muestra como un **laboratorio**;
- las monedas se llaman **créditos de sellado**;
- las recompensas por minar o validar se pagan en esos créditos.

La lógica, las reglas de validación, las rutas y las pruebas son exactamente las que pide la guía: transacciones firmadas con emisor, receptor, monto y timestamp; saldos; doble gasto; recompensas; apuestas y castigos. Así, el contexto no cambia ningún caso de la sección 5. En la interfaz los identificadores siguen siendo `N00`…`N19`, y los mensajes del servidor usan los términos de la guía (nodo, saldo, monto).

## 2. Diseño

La aplicación separa el núcleo (`models/`) de la web (`controllers/`, `views/`). Todo el consenso se puede ejecutar y probar sin Flask; las rutas sólo validan las entradas y llaman al núcleo. Hay dos simulaciones independientes en memoria, una por versión, y cada una tiene de 10 a 20 nodos.

- **Nodos y cuentas.** Cada nodo tiene un identificador (`N00`…`N19`), un par de claves Ed25519 derivado de la semilla, su propia copia de la cadena y el estado de cuentas que resulta de validarla. El bloque génesis registra la clave pública y el saldo inicial de cada cuenta, así que cualquier nodo puede verificar firmas y saldos usando sólo la cadena.
- **Transacciones.** `{emisor, receptor, monto, timestamp}` se serializa en JSON canónico (llaves ordenadas, sin espacios) y el emisor lo firma. Antes de entrar a la lista de pendientes se verifican el formato, que las cuentas existan, la firma, que la transacción no se haya incluido antes y el saldo disponible (saldo menos lo comprometido en pendientes y apuestas).
- **Bloque.** Tiene los campos mínimos de la guía y el `hash` es `SHA-256(json.dumps(campos sin "hash", sort_keys=True))`. PoW agrega `dificultad`. PoS agrega el comité con sus apuestas, el número de intento, los proponentes excluidos, los castigos, la firma del proponente y los votos firmados. Así, todo lo que pasó en una ronda queda en la cadena y se puede volver a verificar.
- **Validación y difusión.** Al recibir una cadena, cada nodo la valida completa desde el génesis: (a) hashes y enlaces, (b) firmas, saldos y doble gasto, (c) regla de consenso y (d) que sea más larga que la propia. Si falla cualquiera, la rechaza, conserva su cadena y el motivo queda en la bitácora. La verificación de firmas usa una caché porque es una función pura; cada nodo sigue revisando todas las firmas.
- **Robustez.** Cada mutación ocurre bajo un candado por red, y las acciones fuera de orden se rechazan con HTTP 409 y un mensaje claro (por ejemplo, minar dos veces o votar fuera de la etapa VOTACION). Las entradas inválidas reciben HTTP 400. Un manejador global garantiza que nunca se muestre un traceback. La interfaz sólo consulta el estado del servidor, así que recargar la página o abrir dos pestañas no cambia nada.
- **Reproducibilidad.** La semilla determina las claves, las transacciones aleatorias, el comité y las apuestas automáticas. En *modo reproducible* el reloj es lógico, así que con la misma semilla se obtienen los mismos hashes.

## 3. Proof of Work y regla de desempate

La simulación avanza por rondas en un hilo de fondo. En cada ronda, el minero `i` prueba `k` nonces de la secuencia `i, i+N, i+2N, …`, de modo que dos mineros nunca prueban el mismo nonce. Cada minero mina el bloque con su propio identificador como `proponente`, así que nadie puede quedarse con el nonce de otro. La interfaz muestra en vivo el nonce, los intentos y el último hash de cada minero.

**Desempate:** una ronda representa un intervalo de tiempo en el que todos los mineros trabajan en paralelo, así que todos terminan su turno de la ronda. Si dos o más encuentran un nonce válido en la misma ronda, **gana el de hash menor**. La regla es determinista y todos los nodos la pueden verificar, y la bitácora registra el empate. Con dificultad 1 o 2 los empates aparecen con frecuencia en la demostración.

Al haber ganador, todos se detienen. El ganador valida su propio bloque, lo agrega a su cadena y la difunde, y los demás nodos la validan completa. La recompensa del bloque `h` queda pendiente y se acredita cuando la cadena llega a `h + 6`. La interfaz muestra *x/6 confirmaciones* y distingue el saldo disponible de las recompensas pendientes. Un bloque que reclama una recompensa distinta a la del génesis se rechaza. Otros casos: pedir minar mientras ya se mina devuelve 409, un límite de rondas detiene una dificultad que no se resuelve a tiempo, y se puede cancelar en cualquier momento. La opción *Minar 10 bloques seguidos* genera transacciones automáticas si faltan y deja ver cómo maduran las primeras recompensas.

## 4. Proof of Stake y regla de castigo

La ronda es una máquina de estados: `APUESTAS → SORTEO → CANDIDATO → VOTACION → ACEPTADO / RECHAZADO`, con un estado `FALLIDA` cuando no quedan validadores. El comité son todos los nodos con saldo disponible o un subconjunto aleatorio reproducible. Cada validador apuesta `0 < aᵢ ≤ saldo disponible`, y esa cantidad queda bloqueada durante la ronda. El proponente se sortea con `sortear(validadores, hash_anterior, número, intento)` (intervalos acumulados, P(i) = aᵢ/A), construye el bloque con las transacciones pendientes y lo firma. Cada validador vota con peso igual a su apuesta y firma su voto. El bloque se acepta si `3V ≥ 2A`, por lo que una votación de exactamente 2/3 se acepta. Los validadores honestos votan según su propia validación del candidato; los deshonestos votan a favor de todo. Aunque un bloque inválido reúna los votos, los nodos lo rechazan al validarlo, y eso cuenta como rechazo.

Al aceptarse, el bloque se difunde, se paga la recompensa y se liberan las apuestas. Al rechazarse, el proponente es castigado, queda excluido y se repite el sorteo con los validadores restantes (`intento + 1`). Al validar el bloque final, cada nodo recalcula la secuencia completa de sorteos, revisa cada castigo y verifica todas las firmas.

**Regla de castigo.** Las dos reglas están implementadas y se elige en la interfaz: (A) `c = aₚ` o (B) `c = min(aₚ, ⌈α · valor de las transacciones⌉)`, con α entre 1 % y 100 %. **Por defecto usamos la regla A**, por estas razones:

1. **Disuasión independiente del monto.** Con la regla B, un fraude sobre transacciones de poco valor sale casi gratis (`c` muy pequeño), así que un atacante podría probar fraudes baratos muchas veces. Con la regla A, proponer un bloque inválido siempre cuesta toda la apuesta.
2. **El daño no se mide sólo en monto.** Un bloque con una firma falsa ataca la integridad de la cadena aunque la transacción sea pequeña.
3. **Simplicidad y verificabilidad.** El castigo sólo depende de la apuesta registrada en el bloque.

La regla B sigue disponible para mostrar un castigo proporcional y tolerante con errores menores; en ella `c ≥ 1`, de modo que el rechazo siempre tiene consecuencias. Los castigos de una ronda fallida no se pierden: se registran en el siguiente bloque aceptado y mientras tanto se descuentan del saldo disponible.

## 5. Casos contemplados

Cada caso responde con un mensaje claro en la interfaz, deja el sistema consistente y tiene al menos una prueba automática en `tests/` (174 pruebas en total, `pytest`).

| Ámbito | Casos |
|---|---|
| Entradas | N fuera de 10–20; montos negativos, cero, no numéricos, vacíos o decimales; emisor = receptor; nodos inexistentes; dificultad fuera de rango. |
| Transacciones | Firma alterada; firmada con la clave de otro nodo; saldo insuficiente; doble gasto en pendientes, dentro de un bloque y entre bloques (reenviar una transacción ya minada); pendientes vacías al minar o proponer. |
| Cadena | Hash alterado; `hash_anterior` alterado; cadena más corta; cadena mal formada; bloque intermedio reescrito y reminado (se rompe el enlace del siguiente); génesis ajeno. |
| PoW | Nonces disjuntos; dos ganadores en la misma ronda (gana el hash menor); minar mientras ya se mina; límite de rondas y cancelación; recompensa consultada antes de 6 confirmaciones; recompensa falsa; 10 bloques seguidos con conservación del dinero. |
| PoS | Ningún validador con saldo; apuesta cero, negativa o mayor al saldo; votación exactamente en 2/3 y por debajo; voto de un no validador y voto doble (en la ronda y dentro de un bloque); proponente deshonesto con las reglas A y B; ronda fallida; todos los validadores castigados hasta quedar sin saldo. |
| Aplicación | Reiniciar (incluso en pleno minado); recargar a mitad de una ronda; dos pestañas minando, votando o gastando a la vez; JSON mal formado, tipos incorrectos, rutas o métodos inexistentes y peticiones demasiado grandes, sin ningún error 500. |

El **laboratorio de casos** de la interfaz permite repetir en vivo los ataques a la cadena y a las transacciones: un nodo atacante envía una copia manipulada y todos los demás nodos la rechazan con su motivo.
