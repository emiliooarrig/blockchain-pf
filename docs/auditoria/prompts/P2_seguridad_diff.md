# P2 · Revisión de seguridad del diff del proyecto final

> Se ejecuta con las instrucciones de `_comun.md` antepuestas. Archivo de respuesta: `docs/auditoria/respuestas/P2_seguridad_diff.md`.
> Antes de empezar, carga la habilidad `security-review` si está disponible y sigue su método; si no lo está,
> dilo al inicio de tu respuesta y sigue esta instrucción directamente.

Revisa la seguridad de todos los cambios entre `main` y la etiqueta `auditoria-inicio`
(`git diff main...auditoria-inicio`): es todo el código nuevo del proyecto final.

Concéntrate en lo que un atacante podría explotar en la práctica:
- un par malicioso de la red P2P (mensajes TCP arbitrarios antes y después del saludo autenticado,
  cadenas y bloques manipulados, agotamiento de memoria/CPU/hilos/sockets);
- una página web maliciosa abierta en el mismo navegador que la interfaz del nodo (CSRF contra
  `/api/sellalo/*` en 127.0.0.1, DNS rebinding, XSS con títulos o nombres de otros nodos);
- un archivo manipulado en disco (almacén de claves, cadena, pendientes, sellos en firma, génesis);
- un certificado manipulado entregado al verificador independiente;
- fugas de la contraseña o de la clave privada (respuestas, bitácora, logs, excepciones, memoria persistida).

Para cada hallazgo explica el ataque paso a paso y su impacto real en este proyecto (un nodo académico
en una red local). No reportes riesgos teóricos sin un camino de explotación concreto.
