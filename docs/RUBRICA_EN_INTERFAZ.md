# La rúbrica en la interfaz web · auditoría y diseño

> 2026-11-27. Objetivo: que **cada proceso de la rúbrica final** (`rubrica_proyecto_blockchain.pdf`) se pueda **ver** en la
> página del nodo Sellalo (`/` en modo nodo), no sólo comprobar en pruebas o en la terminal.

## 1. Auditoría: qué se ve hoy y qué falta

| Rubro | Proceso que pide la rúbrica | Hoy en la interfaz | Brecha |
|---|---|---|---|
| R1 Técnica adicional (multifirma) | Técnica completa y funcional | Sellar con autores/umbral (§3), co-firmas con progreso j/k (§4), firmas en el detalle del bloque | No se ve **qué firma de qué autor se verificó** ni por qué el sello es válido (≥ k firmas válidas de autores). |
| R2 Métodos de verificación | Verifica firmas, hashes e integridad de bloques y transacciones; rechaza datos alterados | Laboratorio de ataques (§8) muestra rechazos; chips de validez inexistentes | No hay una vista que **recalcule y muestre cada comprobación** (hash, enlace, Merkle, PoW, firma del minero, firma de cada tx, multifirma) ni que muestre en rojo **qué comprobación falla** en una copia alterada. |
| R3 Salvaguarda de la clave privada | Cifrada o derivada de contraseña; nunca en claro | Formulario de desbloqueo (§1) | No se ve **cómo** está protegida: formato del almacén, scrypt (N, r, p), AES-256-GCM, AAD, que no hay clave en claro, intentos fallidos. |
| R4 Consenso funcional | Valida bloques nuevos y resuelve conflictos entre cadenas | Minado en vivo (§5), bitácora | No se ven la **regla de consenso**, la **dificultad de red**, el **trabajo acumulado** ni las **reorganizaciones** (bifurcación resuelta, bloques descartados, tx devueltas a pendientes). `publico()` no expone `dificultad_red` y `/minar` sin dificultad falla. |
| R5 Distribución de la cadena | Réplica en varios nodos sincronizados y consistentes | Tabla de pares con estado sincronizado/atrasado/divergente (§2) | Falta un **indicador de consistencia** de la red (cuántos nodos tienen la misma punta) y la **persistencia** de la copia local (archivo, última escritura, errores). |
| R6 Agregado particular (certificado) | Funcionalidad original que aporta valor | Prioridad, descargar y verificar certificado (§7) | La verificación sólo muestra válido/no válido + motivo; no se ven los **pasos** (génesis, encabezados, multifirma, **camino Merkle** hoja → raíz, documento). |
| R7 Solución del problema | Resuelve el caso de uso de principio a fin, con demostración | Todas las secciones por separado | No hay un **recorrido** que muestre el avance del caso de uso completo (los 9 pasos del guion) con evidencia en vivo. |
| R8 Entrega | Repositorio con instrucciones; reporte y presentación | Nada | No se ve el estado de los **entregables** (README, requirements, pruebas, reporte, presentación, guía de demo). |
| ★ Punto excepcional | Auditoría con IA: hallazgos y correcciones | Nada | No se ven los **hallazgos**, su decisión, su commit de corrección y su prueba. |

## 2. Diseño

Arriba de la página, un **tablero "Rúbrica"** con una tarjeta por criterio (R1–R8 y ★): estado en vivo
(`demostrado` / `parcial` / `pendiente`), evidencias con ✓/✗ y un enlace a la sección que lo demuestra.
Secciones nuevas o ampliadas:

| Rubro | Visualización |
|---|---|
| R1 | En cada sello (pendientes, en firma, detalle de bloque, prioridad): tabla **autor → firmó / firma válida** y "k de n alcanzado". |
| R2 | Sección **Verificación de integridad**: botón *Auditar mi copia* → tabla por bloque con una columna por comprobación (✓/✗) y el detalle de cada transacción; formulario *Simular alteración* (tipo + bloque) → la misma tabla sobre una **copia** alterada, con la comprobación que falla en rojo y la confirmación de que la cadena real no cambió. |
| R3 | Panel **Protección de la clave** en Identidad: metadatos públicos del almacén y contadores de desbloqueo. |
| R4 | Panel **Consenso**: regla, dificultad fija de la red, trabajo acumulado propio y de cada par, historial de reorganizaciones y de bloques rechazados. |
| R5 | Indicador **Consistencia de la red** (n/n nodos con la misma punta) y panel de **persistencia**. |
| R6 | Resultado de verificación con **pasos** y **diagrama del camino Merkle**. |
| R7 | **Recorrido del caso de uso**: 10 pasos con ✓ calculados del estado real del nodo. |
| R8 | Tarjeta **Entrega** con la lista de entregables y su estado. |
| ★ | Sección **Auditoría con IA**: conteos por decisión y severidad, tabla filtrable de hallazgos con su commit y prueba. |

## 3. Contrato de API (C8) — prefijo `/api/sellalo`

Todas responden `{ok: true, ...}`; nunca exponen la contraseña ni la clave privada.

### `GET /rubrica`
```json
{"ok": true, "criterios": [
  {"id": "R1", "nombre": "Técnica adicional: multifirma k-de-n", "puntos": 1, "estado": "demostrado|parcial|pendiente",
   "evidencias": [{"texto": "2 sellos multifirma (k ≥ 2) en la cadena", "ok": true}], "seccion": "seccion-firmas"}
]}
```
Ids: `R1`…`R8`, `EX`. El estado se calcula del nodo en vivo (cadena, pares, contadores de la sesión, archivos del repositorio).

### `GET /verificacion` y `POST /verificacion/simular`
`POST` recibe `{tipo, bloque}` con `tipo` ∈ `transaccion` (cambia un dato de una tx), `firma_tx`, `hash`, `enlace`, `merkle`,
`firma_minero`, `multifirma` (quita una firma de un sello), `nonce`. Opera sobre una **copia**; la cadena real no cambia.
```json
{"ok": true, "valida": true, "duracion_ms": 12, "copia_alterada": false, "alteracion": null,
 "bloques": [{"numero": 1, "hash": "…", "ok": true,
   "comprobaciones": {"hash": true, "enlace": true, "merkle": true, "pow": true, "firma_minero": true, "transacciones": true},
   "transacciones": [{"indice": 0, "tipo": "sello|transferencia", "id": "…", "ok": true, "firma": true,
                      "multifirma": {"autores": ["LAB-A","LAB-B","LAB-C"], "umbral": 2,
                                     "firmas": [{"autor": "LAB-A", "firmo": true, "valida": true}], "alcanzado": true}}],
   "errores": []}],
 "primer_error": null}
```
Cada comprobación se evalúa por separado (no se detiene en el primer error). En `simular`, `copia_alterada: true`,
`alteracion: {tipo, bloque, descripcion}`, y `cadena_real_intacta: true`.

### `GET /clave`
```json
{"ok": true, "archivo": "data/LAB-A/clave.json", "formato": "sellalo-clave", "version": 1, "id": "LAB-A",
 "clave_publica": "…", "kdf": {"alg": "scrypt", "n": 32768, "r": 8, "p": 1, "largo": 32, "bytes_sal": 16},
 "cifrado": {"alg": "AES-256-GCM", "bytes_nonce": 12, "bytes_texto_cifrado": 48},
 "aad": "sellalo-clave|<id>|<clave pública>", "clave_en_claro_en_disco": false, "desbloqueado": true,
 "intentos_fallidos": 0, "espera_s": 0}
```

### `GET /estado` (ampliado)
- `nodo.dificultad_red` (int o `null`), `nodo.trabajo` (int).
- `nodo.consenso`: `{"regla": "…", "reorganizaciones": [{"t", "de", "altura_antes", "altura_despues", "punta_antes", "punta_despues", "bloques_descartados", "tx_devueltas"}], "bloques_rechazados": n, "cadenas_rechazadas": n}`.
- `nodo.persistencia`: `{"archivo_cadena", "bytes", "ultima_escritura", "error"}`.
- `pares[].trabajo` (ya existe) y `consistencia`: `{"nodos": n, "con_mi_punta": m}`.
- `sesion`: contadores `{certificados_emitidos, certificados_validos, certificados_invalidos, prioridad_consultas, ataques_rechazados, verificaciones, simulaciones}`.
- `recorrido`: lista de 10 pasos `{id, texto, hecho: bool, detalle}`: desbloquear · conectar ≥ 2 pares · proponer sello multifirma · alcanzar el umbral · minar el bloque · replicar (todos con la misma punta) · consultar prioridad · emitir certificado · verificar certificado válido · detectar una alteración (simulación o ataque rechazado).

### `POST /certificado/verificar` (ampliado)
Agrega `pasos: [{"paso": "génesis|encabezados|sello|multifirma|merkle|documento", "ok": bool, "detalle": "…"}]` y
`merkle: {"hoja", "raiz", "camino": [{"lado", "hash", "resultado"}]}` (resultado = hash intermedio tras cada paso).

### `GET /auditoria`
Lee `docs/auditoria/estado.json` (generado por `scripts/estado_auditoria.py` a partir de `HALLAZGOS.md`, `TRIAJE.md` y los
commits `fix(AUD-0NN)`):
```json
{"ok": true, "generado": "…", "resumen": {"total": 62, "por_decision": {}, "por_severidad": {}, "por_estado": {}},
 "hallazgos": [{"id": "AUD-001", "titulo": "…", "severidad": "Alta", "categoria": "…", "grupo": "G1-red",
                "decision": "C|CP|NA|D|RE", "estado": "corregido|pendiente|justificado|resuelto_por_eliminacion",
                "commits": ["bf9b938"], "prueba": "tests/test_auditoria_g1.py::test_aud_001_…"}]}
```

### `GET /entrega`
```json
{"ok": true, "entregables": [{"nombre": "README con instalación y ejecución", "archivo": "README.md", "existe": true, "detalle": "…"}]}
```
README, requirements, pruebas (número de archivos `tests/test_*.py`), reporte técnico (`docs/REPORTE_FINAL.md`), presentación
(`docs/PRESENTACION.md` o `.pdf`/`.pptx` en `docs/`), guía de demo (`docs/GUIA_DEMO.md` o `scripts/demo_e2e.py`),
evidencia por rubro (`docs/EVIDENCIA_RUBRICA.md`). Lo que no exista se muestra como **pendiente** (nunca se inventa).
