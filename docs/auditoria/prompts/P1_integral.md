# P1 · Auditoría integral de seguridad y calidad

> Se ejecuta con las instrucciones de `_comun.md` antepuestas. Archivo de respuesta: `docs/auditoria/respuestas/P1_integral.md`.
> Antes de empezar, carga la habilidad `anthropic-skills:security-audit` (OWASP adaptado + FODA) si está disponible
> y sigue su método; si no lo está, dilo al inicio de tu respuesta y sigue esta instrucción directamente.

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
