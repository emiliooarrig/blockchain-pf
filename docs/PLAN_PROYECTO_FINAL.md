# Plan del proyecto final · Sellalo (Blockchain)

> **Estado:** borrador para aprobación. **No se ejecuta nada** hasta que se indique.
> **Rúbrica de referencia:** `rubrica_proyecto_blockchain.pdf` (10 pts + 1 excepcional).
> **Plan aparte del punto excepcional:** [PLAN_AUDITORIA_IA.md](PLAN_AUDITORIA_IA.md).

---

## 0. Decisiones tomadas

> **2026-11-27: se eliminó Proof of Stake de todo el sistema; el único consenso es Proof of Work** (simulador y red
> Sellalo). Se retiraron `models/pos.py`, la pestaña V2 del simulador, sus rutas y sus pruebas. Donde este plan
> menciona PoS (código base, laboratorio de consenso, R4, M-5) describe el punto de partida o lo descartado.

| Tema | Decisión |
|---|---|
| Código base | **Fusionar**: partir de `origin/medi-termino` (Sellalo: PoW + PoS en ese momento, Ed25519, 174 pruebas, validación completa) y **portar la capa TCP/IP de `main`** (LabChain) para que la cadena se replique en procesos/PCs reales. |
| Técnica adicional | **Multifirma k-de-n** aplicada a la co-autoría de un sello. |
| Problema a resolver | **Sellado de prioridad científica**: un laboratorio registra el hash de un documento, sus co-autores lo firman y la red lo sella con fecha verificable. Deja de ser “solo visual” (como en el medio término). |
| Agregado particular | **Certificado de prioridad verificable offline**: archivo con prueba de inclusión Merkle + encabezados de bloque, que un script independiente verifica sin confiar en ningún nodo. |

### Arquitectura resultante (dos modos en la misma aplicación)

1. **Red Sellalo (producto final):** cada proceso es un **nodo completo** (un laboratorio) con su propio almacén de claves cifrado, su copia de la cadena en disco y un servidor TCP. Los nodos (≥ 3) se conectan en malla en una o varias PCs. Consenso **PoW con cadena de mayor trabajo acumulado**. Aquí viven los sellos multifirma y los certificados.
2. **Laboratorio de consenso (lo del medio término):** el simulador en memoria de 10–20 nodos (sólo PoW desde 2026-11-27; la pestaña PoS se eliminó) se conserva como página educativa. Comparte el núcleo (`cripto`, `bloque`, `validacion`, `pow`).

> PoS se **eliminó** del sistema (2026-11-27) y la mejora M-5 quedó descartada (ver §6). La rúbrica pide un mecanismo de consenso; PoW en la red real y en el simulador lo cubre.

### Preguntas pendientes para el profesor (no bloquean el arranque)

1. ¿Las técnicas marcadas con **(2)** (anillo, poscuántico, conocimiento cero) valen 2 pts? Si sí, evaluar agregar una (ver M-1).
2. Formato y extensión del **reporte técnico** y duración de la **presentación**; ¿se pide video?
3. **Fecha de entrega** (el calendario de §5 está en días relativos, D-n).
4. ¿Qué evidencia espera del punto excepcional además del reporte y las correcciones? (ver plan aparte).

---

## 1. Diagnóstico por rubro

Leyenda: ✅ cubierto · 🟡 parcial · ❌ no cubierto. “MT” = rama `medi-termino`; “main” = LabChain TCP/IP.

| # | Rubro (pts) | Estado actual | Brecha | Acción del plan | Mejora opcional |
|---|---|---|---|---|---|
| R1 | **Técnica adicional** (1) | ❌ Ninguna en MT ni en main. | Falta una técnica completa y funcional. | **Multifirma k-de-n** en el sello (§3.1). | M-1: firma de anillo o ZK si valen 2 pts. |
| R2 | **Métodos de verificación** (1) | ✅ MT: hash de bloque recalculado, enlace, firmas Ed25519, saldo/doble gasto, consenso, cadena completa desde el génesis, laboratorio de ataques. main: raíz de Merkle. | No hay raíz de Merkle en MT; los bloques PoW no van firmados por el minero; no se verifica la cadena guardada en disco al arrancar; los mensajes TCP no se autentican. | Raíz de Merkle + encabezado separado; firma del proponente también en PoW; validación del archivo al cargar; handshake autenticado; verificación de multifirma y de certificados (§3.2). | Botón “Auditar mi copia” por nodo con informe de qué se verificó. |
| R3 | **Salvaguarda de la clave privada** (1) | ❌ MT: `ParClaves` deriva la clave de `sha256(f"{semilla}|...|nodo|{i}")` — cualquiera con la semilla (pública, en la UI y en el código) reconstruye la clave. main: no hay claves. | Equivale a clave en el código. | **Almacén de claves cifrado**: clave aleatoria, cifrada con AES-256-GCM bajo una clave derivada de contraseña con scrypt (§3.3). | Cambio de contraseña; bloqueo automático por inactividad. |
| R4 | **Consenso funcional** (1) | ✅ MT: PoW por rondas (nonces disjuntos, desempate por hash menor, 6 confirmaciones); el PoS del medio término se eliminó el 2026-11-27 y el único consenso es PoW. main: PoW real entre 2 PCs con desempate. | En red real hay que resolver *forks* entre N nodos y reorganizaciones. | PoW en red con regla de **mayor trabajo acumulado**, desempate por hash menor, reorganización con devolución de sellos huérfanos a pendientes (§3.4). | Ajuste automático de dificultad por tiempo de bloque. |
| R5 | **Distribución de la cadena** (1) | 🟡 MT: 10–20 nodos **en memoria** (un solo proceso). main: réplica real, pero solo 2 PCs. | Falta réplica real en ≥ 3 nodos independientes con sincronización y persistencia. | Red TCP en malla de N nodos, *gossip* con deduplicación, sincronización al conectar/reconectar, persistencia por nodo y panel de consistencia (§3.5). | Descubrimiento de pares por lista semilla; reconexión automática. |
| R6 | **Agregado particular** (1) | 🟡 MT/main tienen “verificar prioridad” dentro del nodo (requiere confiar en él). | No hay una funcionalidad original verificable fuera del sistema. | **Certificado de prioridad verificable offline** (§3.6). | Versión imprimible (HTML/PDF) del certificado. |
| R7 | **Solución del problema** (2) | 🟡 La narrativa existe, pero en MT el sellado es “solo visual” (las transacciones son transferencias de créditos). | El flujo real de sellado multiautor no existe de punta a punta. | Flujo completo: registrar → co-firmar → minar → replicar → certificar → verificar → disputa de prioridad (§3.7). | Búsqueda por hash/título y línea de tiempo por laboratorio. |
| R8 | **Entrega** (2) | 🟡 README de MT completo para el simulador; `docs/REPORTE.md` del medio término. Sin instrucciones de red multi-nodo ni presentación. | README, reporte y presentación del proyecto final. | README de instalación limpia + guía de red local y multi-PC; reporte técnico; presentación; guion de demo (§3.8). | Script de un solo comando que levanta 3 nodos locales. |
| ★ | **Punto excepcional** (+1) | ❌ | Auditoría con IA + evidencias de corrección. | Ver [PLAN_AUDITORIA_IA.md](PLAN_AUDITORIA_IA.md). | — |

---

## 2. Preparación (Fase 0 — la hago yo, secuencial)

1. **Rama de trabajo:** la rama local `medi-termino` está 2 commits detrás de `origin/medi-termino`.
   `git fetch` → `git switch -c proyecto-final origin/medi-termino`. Los PDFs de la rúbrica y la guía se quedan sin seguimiento (o se mueven a `docs/referencias/` si así lo decides).
2. **Línea base:** `pip install -r requirements.txt` y `pytest` → registrar cuántas pruebas pasan (se esperan 174). Cualquier falla previa se anota antes de tocar código.
3. **Contratos congelados** en `docs/diseno/CONTRATOS.md`, para que los subagentes trabajen en paralelo sin chocar:
   - **Bloque v2:** `encabezado = {numero, timestamp, hash_anterior, raiz_merkle, nonce, dificultad, proponente, recompensa, ...}`; `hash = SHA-256(JSON canónico del encabezado)`; `transacciones` fuera del encabezado y amarradas por `raiz_merkle`; `firma_proponente` sobre el hash.
   - **Transacción `sello`:** `{tipo:"sello", doc_hash, titulo, investigador, autores:[ids], umbral:k, timestamp, firmas:{id: firma}}`; los firmantes firman la serialización canónica sin `firmas`.
   - **Almacén de claves:** formato JSON (ver §3.3).
   - **Protocolo de red v2:** mensajes y campos (ver §3.5).
   - **Certificado:** formato JSON versionado (ver §3.6).
4. **Interfaces Python** (firmas de funciones vacías con docstring) para `keystore`, `merkle`, `multifirma`, `red_p2p`, `certificado`, de modo que cada subagente implemente contra ellas.

---

## 3. Diseño por rubro

### 3.1 R1 · Multifirma k-de-n (técnica adicional)

**Caso de uso:** un artículo tiene co-autores en distintos laboratorios; el sello sólo es válido si **al menos k de los n autores listados** lo firman con su clave privada.

- `models/multifirma.py`: `mensaje_sello(sello) -> bytes`, `firmar_sello(sello, claves) -> firma`, `verificar_multifirma(sello, registro_claves) -> (ok, motivo)`.
- Reglas de validación (todas con mensaje claro y prueba):
  - `1 ≤ k ≤ n ≤ 5`; autores sin repetir y registrados en la red;
  - cada firma corresponde a un autor listado y es válida para **ese** sello (no reutilizable en otro);
  - firmas de no autores, duplicadas o alteradas → se descartan y, si no se alcanza k, el sello se rechaza;
  - el sello no entra al *mempool* ni a un bloque hasta tener k firmas válidas; mientras tanto está en **“esperando firmas (j/k)”**.
- Flujo en red: el laboratorio que registra difunde `SELLO_PROPUESTO`; cada nodo co-autor ve una solicitud en su UI, el operador desbloquea su clave (§3.3) y firma; la firma viaja como `SELLO_FIRMA`. Al llegar a k, el sello pasa a pendientes.
- Demostración: sello 2-de-3 entre tres PCs/nodos; intento con una firma alterada; intento con firma de un laboratorio que no es autor.

### 3.2 R2 · Métodos de verificación (ya cubierto → reforzar)

Se conserva todo lo de MT y se agrega:

1. **Raíz de Merkle** (portar `merkle_root` de `main:models/crypto.py`) + **prueba de inclusión** (`camino_merkle(tx_ids, i)` y `verificar_camino`). Necesaria también para el certificado.
2. **Encabezado separado:** el hash del bloque se calcula sobre el encabezado; alterar una transacción cambia la raíz de Merkle y rompe el hash.
3. **Firma del proponente en PoW** (en el medio término sólo la tenía PoS, ya eliminado): el minero firma el hash; evita que alguien se atribuya un bloque ajeno.
4. **Validación al arrancar:** el nodo revalida su `data/<nodo>/cadena.json` completo; si está corrupto o alterado, lo rechaza, lo renombra a `.corrupto` y se resincroniza con sus pares.
5. **Mensajes de red autenticados:** reto-respuesta firmado con Ed25519 en el `HELLO`; cada bloque/sello recibido se valida completo antes de aceptarse o reenviarse.
6. **Laboratorio de ataques ampliado** a la red real: un nodo “malicioso” envía cadena con transacción alterada, firma falsa, multifirma incompleta, raíz de Merkle falsa, cadena más corta, génesis ajeno → todos los honestos la rechazan y lo registran en la bitácora.

### 3.3 R3 · Salvaguarda de la clave privada

- `models/keystore.py`:
  - **Generación:** `Ed25519PrivateKey.generate()` (aleatoria, `os.urandom`), **nunca** derivada de la semilla de la simulación.
  - **Cifrado:** `clave = scrypt(contraseña, sal=16 B aleatorios, n=2^15, r=8, p=1, 32 B)` → AES-256-GCM (`cryptography`) con *nonce* de 12 B y el `id` del nodo como datos asociados.
  - **Archivo** `data/<nodo>/clave.json`: `{version, id, clave_publica, kdf:{alg, sal, n, r, p}, cifrado:{alg, nonce, texto_cifrado}}`. Sin la clave en claro en ningún lugar.
  - **Desbloqueo:** por contraseña en la terminal (`getpass`) al arrancar o desde la UI (formulario POST a `127.0.0.1`). Contraseña incorrecta → la etiqueta GCM falla → mensaje claro, sin traceback. Contraseña mínima de 10 caracteres.
  - **Nodo bloqueado:** puede validar y sincronizar, pero no firmar, minar ni co-firmar.
  - La contraseña y la clave descifrada **nunca** se registran en logs, bitácora, respuestas JSON ni `/estado`.
- `scripts/crear_identidad.py`: crea el almacén de un laboratorio y muestra sólo su clave pública.
- **Simulador en memoria (10–20 nodos):** sus claves se generan aleatorias por sesión y se guardan cifradas en memoria con una contraseña de sesión; la semilla sigue controlando sólo el azar (transacciones, sorteos, comités), no las claves. Se ajustan las pruebas que dependían de claves reproducibles.
- `.gitignore`: `data/`, `*.key`, `clave.json`. Revisar historial con `git log -p | grep -i private` para confirmar que nunca se subió una clave.
- Pruebas: contraseña incorrecta, archivo alterado (texto cifrado o sal), versión desconocida, contraseña corta, que `/estado` y la bitácora no contengan la clave.

### 3.4 R4 · Consenso funcional (ya cubierto → llevar a red real)

- PoW en cada nodo con un hilo de minado cancelable (`threading.Event`), reutilizando `preparar_hasher` de MT.
- Al recibir un bloque válido para la misma altura, el minero local se detiene y empieza sobre la nueva punta.
- **Selección de cadena:** válida → **mayor trabajo acumulado** (`Σ 16^dificultad`) → hash de punta menor. Determinista: todos los nodos eligen la misma.
- **Reorganización:** al adoptar una cadena competidora, los sellos de los bloques descartados que no estén en la nueva cadena vuelven a pendientes (lógica de `main:models/blockchain.py:sync_with`).
- Recompensa del minero con 6 confirmaciones (se conserva de MT).
- Pruebas: dos nodos minan la misma altura → convergen; partición de red con minado en ambos lados → al reconectar todos adoptan la de más trabajo y ningún sello se pierde.

### 3.5 R5 · Distribución de la cadena

- `models/red_p2p.py` (evolución de `main:models/network.py`, hoy limitado a 2 PCs):
  - Malla de **N pares** (mínimo 3 en la demo): lista de pares por `--pares ip:puerto,...` o conexión manual desde la UI.
  - Protocolo v2 (JSON por línea): `HELLO/HELLO_ACK` (con reto firmado, hash del génesis, altura, trabajo), `PING/PONG`, `INV` (anuncio de hash de bloque o sello), `GET_BLOQUES/BLOQUES` (sincronización por rangos), `BLOQUE`, `SELLO_PROPUESTO`, `SELLO_FIRMA`, `BYE`.
  - *Gossip* con deduplicación por hash; límite de tamaño de mensaje; lectura con tiempo límite; un par que envía datos inválidos repetidamente queda vetado temporalmente.
  - Al conectar o reconectar: si el par anuncia más trabajo, se piden los bloques faltantes y se valida la cadena completa antes de adoptarla.
- **Persistencia por nodo** en `data/<nodo>/` (cadena, pendientes, sellos esperando firmas) con escritura atómica (`os.replace`, como en `main`).
- **Génesis compartido:** `scripts/inicializar_red.py` toma las claves públicas de los laboratorios y genera `red/genesis.json`, que se copia a todas las PCs. Un nodo con otro génesis es rechazado en el `HELLO`.
- **UI:** tabla de pares con altura, hash de punta, trabajo, latencia y “sincronizado / atrasado / divergente”.
- `scripts/lanzar_red_local.py`: levanta 3–4 nodos en `127.0.0.1` con puertos y carpetas distintas.
- Pruebas: 3 nodos reales en sockets locales dentro de pytest; caída y regreso de un nodo; mensaje mal formado; génesis ajeno.

### 3.6 R6 · Certificado de prioridad verificable offline (agregado)

- `GET /api/sellos/<doc_hash>/certificado` produce `certificado-<hash8>.json`:
  `{version, doc_hash, sello (con firmas), camino_merkle, encabezado_del_bloque, encabezados_siguientes (confirmaciones), hash_genesis, claves_publicas_de_autores}`.
- `verificar_certificado.py` **independiente** (sólo `hashlib` + `cryptography`, sin importar el proyecto):
  1. `SHA-256(archivo)` == `doc_hash`;
  2. multifirma k-de-n válida con las claves del certificado;
  3. camino Merkle → `raiz_merkle` del encabezado;
  4. hash del encabezado correcto y bajo la dificultad; firma del proponente;
  5. encabezados siguientes enlazados (cuenta confirmaciones);
  6. imprime fecha del sello, autores, bloque y confirmaciones, o el motivo exacto del rechazo.
- También en la UI: “Verificar certificado” (sube archivo + certificado).
- Pruebas: certificado válido; documento con 1 byte distinto; firma alterada; camino Merkle alterado; encabezado alterado; certificado de otra red.
- **Por qué es original:** convierte el sello en una prueba portable — un revisor de revista o un juez puede comprobar la prioridad sin acceso a la red ni confiar en el nodo que lo emitió (idea de cliente ligero/SPV aplicada al caso de uso).

### 3.7 R7 · Solución del problema de punta a punta

**Problema:** demostrar que un equipo de investigación tenía un resultado en una fecha, con co-autoría verificable, sin depender de una autoridad central.

**Guion de demostración (3 nodos: Lab A, Lab B, Lab C):**
1. Inicializar la red (identidades cifradas con contraseña, génesis compartido) y conectar los 3 nodos.
2. Lab A sube `resultado.pdf`, autores A+B+C, umbral 2-de-3 → estado “esperando firmas 1/2”.
3. Lab B desbloquea su clave y co-firma → el sello pasa a pendientes y se difunde.
4. Minado PoW: un nodo gana, el bloque se replica; los 3 muestran la misma altura y hash.
5. Descargar el certificado y verificarlo offline con `verificar_certificado.py`.
6. Alterar un byte del PDF → la verificación falla con motivo claro.
7. **Disputa de prioridad:** Lab C intenta sellar el mismo `doc_hash` después → la red lo acepta como registro posterior, pero la consulta de prioridad responde con el sello **más antiguo** y su bloque.
8. **Ataque:** un nodo envía una cadena con un sello alterado → los demás la rechazan (bitácora).
9. **Partición:** desconectar Lab C, minar en ambos lados, reconectar → convergen y ningún sello se pierde.

Se mantiene el modelo de privacidad: sólo el **hash** del documento sale de la PC; el contenido nunca se transmite (el hash se calcula en el nodo local del laboratorio).

### 3.8 R8 · Entrega

- **README** (reescrito): qué es Sellalo, requisitos (Python ≥ 3.10), instalación en máquina limpia, `pytest`, crear identidades, lanzar red local con un comando, red entre varias PCs (firewall, IPs), uso del certificado, tabla rubro → dónde se cumple (archivo y prueba), estructura, protocolo y API.
- **Reporte técnico** `docs/REPORTE_FINAL.md` (+ PDF): problema, arquitectura, formato de bloque v2, multifirma, almacén de claves, consenso y *forks*, distribución, certificado, pruebas, auditoría IA (resumen), limitaciones y trabajo futuro. Incluye liga al video si se pide.
- **Presentación** (10–12 diapositivas): problema → arquitectura → cada rubro con evidencia → demo en vivo → auditoría IA → conclusiones.
- **Guion de demo** `docs/GUIA_DEMO.md` con tiempos y plan B (red local en una sola PC si falla la red del salón).
- Merge a `main` por *pull request* desde `proyecto-final` (sólo cuando lo indiques).

---

## 4. Orquestación con subagentes

### 4.1 Principios

- **Contratos primero** (Fase 0): los subagentes trabajan en paralelo contra interfaces congeladas; nadie cambia un contrato sin pasar por mí.
- **Aislamiento:** cada subagente de implementación trabaja en su propio *worktree* (`isolation: "worktree"`) para no pisarse; yo integro y resuelvo conflictos.
- **Definición de terminado** común: código + pruebas pytest verdes + sin regresiones en las 174 pruebas existentes (ajustadas donde el contrato cambió) + nota corta de qué rubro cubre y cómo demostrarlo.
- Cada subagente recibe: rubro objetivo, contrato, archivos que puede tocar, archivos que **no** puede tocar y criterios de aceptación.
- Yo reviso cada entrega (diff + pruebas) antes de integrarla.

### 4.2 Fases y agentes

```
Fase 0  (yo)          Rama, línea base, contratos, interfaces
           │
Fase 1  (paralelo)    A1 Núcleo cripto ─┐
                      A2 Red P2P ───────┼──► Fase 2  A4 Integración del caso de uso
                      A3 Certificado ───┘                │
                                                  Fase 3  A5 QA adversarial  ║  A6 UI (en paralelo)
                                                         │
                                                  Fase 4  Auditoría IA (plan aparte)
                                                         │
                                                  Fase 5  A7 Documentación y presentación
                                                         │
                                                  Fase 6  (yo) Revisión final, ensayo de demo, PR
```

| Agente | Tipo | Rubros | Entradas | Archivos a crear/modificar | Criterios de aceptación |
|---|---|---|---|---|---|
| **A1 · Núcleo criptográfico** | general-purpose, worktree | R1, R2, R3 | Contratos de bloque v2, sello y keystore | `models/keystore.py`, `models/merkle.py`, `models/multifirma.py`, `models/cripto.py`, `models/bloque.py`, `models/validacion.py`, `scripts/crear_identidad.py`, `tests/test_keystore.py`, `tests/test_multifirma.py`, `tests/test_merkle.py` | Clave nunca en claro en disco/log; scrypt+AES-GCM; multifirma con todos los casos de §3.1; bloque v2 con raíz de Merkle y firma del proponente; las pruebas de MT pasan (ajustadas). |
| **A2 · Red P2P** | general-purpose, worktree | R4, R5 | Protocolo v2; `main:models/network.py` como referencia | `models/red_p2p.py`, `models/nodo_completo.py` (persistencia, selección de cadena, reorganización), `scripts/inicializar_red.py`, `scripts/lanzar_red_local.py`, `tests/test_red_p2p.py` | 3 nodos en sockets locales convergen; partición y reconexión; *fork* resuelto por trabajo; mensajes mal formados no tumban el nodo; génesis ajeno rechazado. |
| **A3 · Certificado** | general-purpose, worktree | R6 | Contrato de certificado y de Merkle | `models/certificado.py`, `verificar_certificado.py` (raíz, independiente), `tests/test_certificado.py` | Verificador corre sin importar el proyecto; los 6 casos de §3.6 dan el resultado correcto con motivo claro. |
| **A4 · Integración del caso de uso** | general-purpose | R7 | Entregas de A1–A3 integradas | `controllers/sellos.py`, `controllers/red.py`, `app.py` (modo nodo: `--nodo`, `--pares`, `--puerto-p2p`, `--datos`), flujo de co-firma, prioridad por sello más antiguo | Guion §3.7 pasos 1–9 funciona por API; ninguna ruta devuelve 500 con datos mal formados. |
| **A5 · QA adversarial** | general-purpose | R2, R4, R5, R7 | Rama integrada | `tests/test_e2e_red.py` (3 procesos reales), `tests/test_ataques_red.py`, reporte de fallas | Script e2e reproducible; cada ataque de §3.2-6 rechazado; reporta bugs a A4/yo en lugar de corregir código ajeno sin coordinación. |
| **A6 · Interfaz** | general-purpose | R5, R6, R7 | API de A4 | `views/templates/index.html`, `views/static/app.js`, `styles.css` | Pestañas “Red Sellalo” y “Laboratorio de consenso”; desbloqueo de clave; solicitudes de co-firma; tabla de pares; certificado (descargar/verificar); la UI no calcula firmas. |
| **A7 · Documentación** | general-purpose | R8 | Código final + reporte de auditoría | `README.md`, `docs/REPORTE_FINAL.md`, `docs/GUIA_DEMO.md`, guion de presentación | README probado en una carpeta limpia (venv nuevo); tabla rubro → evidencia; reporte con decisiones justificadas. |
| **Verificador de rúbrica** | Explore (sólo lectura) | Todos | Rúbrica + rama final | — (entrega un informe) | Para cada rubro: dónde está la evidencia, cómo demostrarlo en ≤ 1 min y qué podría restar puntos. |

> Los agentes de auditoría se definen en [PLAN_AUDITORIA_IA.md](PLAN_AUDITORIA_IA.md).

### 4.3 Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| Cambiar el formato del bloque rompe muchas de las 174 pruebas de MT. | Lo hace un solo agente (A1) y se actualiza la suite en el mismo cambio; A2/A3 usan el contrato, no la implementación. |
| Red del salón bloquea puertos o separa clientes. | Plan B: 3–4 nodos en una sola PC (`lanzar_red_local.py`); llevar un *router*/*hotspot* propio. |
| Firewall de Windows/macOS al abrir el puerto P2P. | Pasos documentados en el README y en la guía de demo. |
| Condiciones de carrera entre hilo de minado, hilo de red y Flask. | Un candado por nodo (como en MT); pruebas e2e con minado concurrente. |
| El tiempo no alcanza. | Prioridad: R3 → R1 → R5/R4 → R7 → R6 → R8 → ★. Lo opcional (§6) sólo al final. |
| Que se considere que el agregado es la técnica “QR compartido”. | El certificado no usa QR; si se agrega QR, que sea sólo un enlace de descarga y no se presente como técnica. |

---

## 5. Calendario sugerido (relativo a la entrega D)

| Días | Fase | Resultado |
|---|---|---|
| D-14 | 0 | Rama, línea base, contratos |
| D-13 a D-10 | 1 | A1, A2, A3 en paralelo |
| D-9 a D-8 | 2 | Integración del caso de uso |
| D-7 a D-6 | 3 | QA adversarial + UI |
| D-5 a D-4 | 4 | Auditoría IA y correcciones |
| D-3 a D-2 | 5 | README, reporte, presentación |
| D-1 | 6 | Ensayo de demo en 2–3 PCs, PR a `main` |

---

## 6. Mejoras opcionales (fuera del alcance base)

| ID | Mejora | Rubro | Esfuerzo |
|---|---|---|---|
| M-1 | Segunda técnica: **firma de anillo** (sellado anónimo dentro de un grupo de laboratorios) o **prueba ZK Schnorr** de posesión de la clave, si el profesor confirma que valen 2 pts. | R1 | Medio–alto |
| M-2 | **Shamir** para respaldar la clave privada en 3 partes (2 necesarias). Refuerza R3 y sería una 2.ª técnica. | R1/R3 | Bajo–medio |
| M-3 | Alta de nuevos laboratorios mediante transacción de registro aprobada por multifirma de los existentes. | R1/R7 | Medio |
| M-4 | Ajuste automático de dificultad. | R4 | Bajo |
| M-5 | ~~PoS sobre la red real (comité y votos por TCP).~~ **Descartada:** PoS se eliminó del sistema el 2026-11-27. | R4 | — |
| M-6 | Certificado imprimible (HTML/PDF). | R6 | Bajo |

---

## 7. Lista de verificación final (antes de entregar)

- [ ] `pytest` verde en un venv limpio; número de pruebas reportado en el README.
- [ ] Ningún archivo con clave privada en el repositorio ni en el historial.
- [ ] Demo §3.7 ensayada completa en ≥ 2 PCs y en una sola PC (plan B).
- [ ] Cada rubro tiene en el README: archivo(s), prueba(s) y paso de la demo que lo evidencia.
- [ ] Punto excepcional: reporte de la IA (instrucción + respuesta), tabla de hallazgos → corrección/justificación, commits enlazados.
- [ ] Reporte técnico y presentación en el formato que pida el profesor.
- [ ] PR `proyecto-final → main` revisado.
