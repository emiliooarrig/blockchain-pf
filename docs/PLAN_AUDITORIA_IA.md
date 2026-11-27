# Plan del punto excepcional · Auditoría del código con IA (+1)

> **Estado:** borrador para aprobación. **No se ejecuta nada** hasta que se indique.
> Complementa a [PLAN_PROYECTO_FINAL.md](PLAN_PROYECTO_FINAL.md) (Fase 4).

## 1. Qué pide la rúbrica y cómo se cumple

| Requisito | Evidencia que se entregará |
|---|---|
| Usar una herramienta de IA para revisar **todo** el código | Lista de archivos auditados con su hash de commit (`git ls-files` en la etiqueta `auditoria-inicio`) y cobertura por pasada. |
| Detectar vulnerabilidades, procedimientos incompletos, errores de lógica, manejo deficiente de excepciones, código muerto o duplicado y otros defectos | Una pasada por categoría (§3) y hallazgos clasificados con esas mismas categorías. |
| Reporte de la IA con **instrucción usada y respuesta** | `docs/auditoria/prompts/*.md` (texto exacto) y `docs/auditoria/respuestas/*.md` (salida íntegra, sin editar). |
| **Correcciones aplicadas** a cada hallazgo o **justificación** de las no aplicadas | `docs/auditoria/HALLAZGOS.md` (tabla hallazgo → commit → prueba → estado) y un commit por corrección con el ID del hallazgo. |
| “Sin evidencia de correcciones no se otorga” | Diff entre `auditoria-inicio` y `auditoria-fin`, pruebas de regresión por hallazgo y una segunda pasada de la IA que confirma el cierre. |

## 2. Cuándo

Después de la Fase 3 (código funcional completo y probado) y **antes** de la documentación final, para que el reporte técnico ya incluya los resultados. Se congela el código con la etiqueta `auditoria-inicio`.

## 3. Herramientas e instrucciones

**Herramienta principal:** Claude Code (modelo Claude Opus 5.5). Se registra la versión de Claude Code y el modelo en el reporte.

Pasadas (cada una con su instrucción guardada **textual** antes de ejecutarla):

| # | Pasada | Cómo se ejecuta | Alcance |
|---|---|---|---|
| P1 | Auditoría integral de seguridad y calidad | Habilidad `security-audit` (OWASP adaptado + reporte FODA) con la instrucción maestra de §3.1 | Todo el repositorio |
| P2 | Revisión de seguridad | `/security-review` | Diff `main...auditoria-inicio` (todo lo nuevo del proyecto final) |
| P3 | Errores de lógica y excepciones | `/code-review high` sobre la rama completa + instrucción de §3.2 por módulo | `models/`, `controllers/`, `app.py`, `verificar_certificado.py`, `scripts/` |
| P4 | Código muerto y duplicado | Instrucción de §3.3 a un subagente de sólo lectura | Todo el repositorio, incluidos `views/static/*.js` |
| P5 | Verificación de cierre | `/code-review high` sobre el diff `auditoria-inicio...auditoria-fin` + instrucción de §3.4 | Sólo las correcciones |

> `/code-review max` o `ultra` (revisión multiagente en la nube, con costo) sólo si lo autorizas explícitamente.

**Apoyo no-IA (opcional, como contraste):** `pip-audit` (dependencias vulnerables), `bandit` (patrones inseguros en Python), `vulture` (código muerto). Sus salidas se adjuntan, pero los hallazgos que cuentan para el punto son los de la IA.

### 3.1 Instrucción maestra (P1)

```text
Eres un auditor de seguridad y calidad de software. Revisa TODO el código de este repositorio
(Python/Flask, JavaScript del navegador, scripts y pruebas) de un nodo blockchain de sellado de
documentos con PoW, red TCP entre nodos, firmas Ed25519, multifirma k-de-n, almacén de claves
cifrado (scrypt + AES-GCM) y certificados verificables con prueba Merkle.

Busca y reporta, con archivo:línea, severidad (crítica/alta/media/baja), evidencia y corrección
propuesta:
1. Vulnerabilidades de seguridad (manejo de claves y contraseñas, criptografía mal usada,
   validación de entradas HTTP y de mensajes TCP, denegación de servicio, deserialización,
   fuga de información en logs/respuestas, CSRF/XSS en la interfaz, condiciones de carrera).
2. Procedimientos incompletos (flujos que no terminan, estados que no se limpian, TODOs).
3. Errores de lógica (consenso, selección de cadena, reorganización, multifirma, Merkle,
   recompensas, saldos, prioridad del sello).
4. Manejo deficiente de excepciones (except demasiado amplios, errores tragados, tracebacks
   expuestos, estados inconsistentes tras un error).
5. Código muerto o duplicado.
6. Cualquier otro defecto (concurrencia, rendimiento, pruebas que no prueban nada).

No inventes hallazgos: si no estás seguro, márcalo como "posible" y explica qué habría que
comprobar. Termina con una tabla resumen y un análisis FODA.
```

### 3.2 Instrucción por módulo (P3)

```text
Revisa el módulo <ruta>. Para cada función: ¿qué entradas o estados la hacen fallar,
devolver un resultado incorrecto o dejar el sistema inconsistente? Da un caso concreto
(entrada → resultado esperado vs. obtenido). Revisa especialmente el manejo de excepciones
y los caminos de error. No reportes estilo.
```

### 3.3 Instrucción de código muerto y duplicado (P4)

```text
Enumera funciones, clases, rutas, constantes, estilos CSS y funciones JS que no se usan en
ningún lugar del repositorio (incluidas pruebas), y bloques de lógica duplicada entre el
simulador en memoria y la red real que deberían compartirse. Indica cómo lo comprobaste
(búsquedas realizadas).
```

### 3.4 Instrucción de verificación de cierre (P5)

```text
Para cada hallazgo de docs/auditoria/HALLAZGOS.md marcado como "corregido", revisa el
commit indicado y confirma si la corrección lo resuelve por completo, lo resuelve
parcialmente o introduce un defecto nuevo. Para los marcados como "no aplicado", evalúa si
la justificación es razonable.
```

## 4. Orquestación con subagentes

```
Congelar (etiqueta auditoria-inicio)
   │
   ├─ AU1 Auditor integral (P1)            ┐
   ├─ AU2 Seguridad del diff (P2)          │  en paralelo, sólo lectura
   ├─ AU3 Lógica/excepciones (P3, por módulo) │
   └─ AU4 Código muerto/duplicado (P4)     ┘
   │
   ▼
AU5 Consolidador → HALLAZGOS.md (dedup, IDs AUD-001…, categoría, severidad)
   │
   ▼
AU6 Verificador adversarial: intenta refutar cada hallazgo (reproduce con prueba o lo descarta)
   │
   ▼
Triaje (tú y yo): corregir / no aplicar con justificación
   │
   ▼
AU7…AUn Correctores (worktree, agrupados por módulo) → 1 commit por hallazgo + prueba de regresión
   │
   ▼
AU-final Verificación de cierre (P5) → etiqueta auditoria-fin → REPORTE_AUDITORIA.md
```

| Agente | Tipo | Hace | No hace |
|---|---|---|---|
| AU1–AU4 | Explore / general-purpose (sólo lectura) | Ejecuta su pasada con la instrucción guardada y escribe la respuesta íntegra en `docs/auditoria/respuestas/` | No modifica código |
| AU5 Consolidador | general-purpose | Une, deduplica y numera hallazgos; enlaza a la respuesta original de la IA | No decide qué se corrige |
| AU6 Verificador | general-purpose | Para cada hallazgo escribe una prueba que lo reproduzca o argumenta por qué es falso positivo | No corrige |
| AU7…AUn Correctores | general-purpose, worktree | Corrige un grupo de hallazgos del mismo módulo; commit `fix(AUD-012): …`; agrega la prueba de regresión del verificador | No toca hallazgos de otros grupos |
| AU-final | general-purpose | Ejecuta P5 y actualiza el estado en `HALLAZGOS.md` | — |

> Si prefieres que esto corra como un *workflow* multiagente automatizado, hay que pedirlo explícitamente; si no, lo orquesto con llamadas individuales a subagentes.

## 5. Estructura de la evidencia

```
docs/auditoria/
├── REPORTE_AUDITORIA.md      # resumen ejecutivo, herramienta, modelo, alcance, métricas, FODA
├── HALLAZGOS.md              # tabla maestra
├── prompts/P1_integral.md … P5_cierre.md
├── respuestas/P1_integral.md … P5_cierre.md   # salida íntegra de la IA
└── apoyo/ (pip-audit.txt, bandit.txt, vulture.txt)  # opcional
```

**Tabla de `HALLAZGOS.md`:**

| ID | Categoría | Severidad | Archivo:línea | Descripción | Fuente (pasada) | Decisión | Commit | Prueba de regresión | Verificado en P5 |
|---|---|---|---|---|---|---|---|---|---|
| AUD-001 | Seguridad | Alta | `models/keystore.py:42` | … | P1 | Corregido | `abc1234` | `tests/test_keystore.py::test_…` | Sí |
| AUD-002 | Código muerto | Baja | `views/static/app.js:310` | … | P4 | No aplicado: … | — | — | Justificación aceptada |

**Criterios para “no aplicar”** (se justifican por escrito): falso positivo demostrado por AU6; fuera de alcance de un proyecto académico (p. ej. TLS en la red local) con la mitigación documentada; o el costo supera el riesgo, con el riesgo residual explicado.

## 6. Métricas que incluirá el reporte

- Hallazgos por categoría y severidad; corregidos / no aplicados / falsos positivos.
- Pruebas antes y después (número y resultado de `pytest`).
- Líneas cambiadas entre `auditoria-inicio` y `auditoria-fin`.
- Hallazgos que la segunda pasada (P5) dio por cerrados.

## 7. Lista de verificación

- [ ] Instrucciones guardadas textuales **antes** de ejecutar cada pasada.
- [ ] Respuestas de la IA íntegras (sin recortar ni editar).
- [ ] Cada hallazgo con decisión, commit o justificación.
- [ ] Cada corrección con prueba de regresión y `pytest` verde.
- [ ] Etiquetas `auditoria-inicio` y `auditoria-fin` publicadas.
- [ ] Resumen de la auditoría incluido en el reporte técnico y en la presentación.
