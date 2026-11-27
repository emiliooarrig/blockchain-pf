# P3 · Errores de lógica y manejo de excepciones (por módulo)

> Se ejecuta con las instrucciones de `_comun.md` antepuestas, en dos partes paralelas:
> - **P3a** → respuesta en `docs/auditoria/respuestas/P3a_logica_red.md`. Módulos: `models/nodo_completo.py`,
>   `models/red_p2p.py`, `models/coordinador_sellos.py`, `models/ataques_sellalo.py`, `controllers/sellalo.py`, `app.py`,
>   `scripts/inicializar_red.py`, `scripts/lanzar_red_local.py`, `scripts/crear_identidad.py`, `scripts/demo_e2e.py`.
> - **P3b** → respuesta en `docs/auditoria/respuestas/P3b_logica_nucleo.md`. Módulos: `models/bloque.py`,
>   `models/validacion.py`, `models/pow.py`, `models/pos.py`, `models/red.py`, `models/simulador.py`, `models/ataques.py`,
>   `models/multifirma.py`, `models/keystore.py`, `models/cripto.py`, `models/merkle.py`, `models/certificado.py`,
>   `verificar_certificado.py`, `controllers/api.py`, `controllers/entradas.py`.

Para cada módulo de tu parte aplica esta instrucción:

Revisa el módulo <ruta>. Para cada función: ¿qué entradas o estados la hacen fallar,
devolver un resultado incorrecto o dejar el sistema inconsistente? Da un caso concreto
(entrada → resultado esperado vs. obtenido). Revisa especialmente el manejo de excepciones
y los caminos de error. No reportes estilo.
