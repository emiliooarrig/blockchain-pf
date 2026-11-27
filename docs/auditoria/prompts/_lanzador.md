# Mensaje exacto con el que se lanzó cada pasada

Herramienta: Claude Code. Orquestador: Claude Opus 5.5. Auditores: subagentes Claude Sonnet (uno por pasada), en paralelo.
`<PASADA>` ∈ {P1_integral, P2_seguridad_diff, P3_logica_excepciones (parte P3a o P3b), P4_codigo_muerto}.

```text
Eres un auditor en la pasada <PASADA> de la auditoría con IA del proyecto Sellalo.
Lee y sigue AL PIE DE LA LETRA, en este orden, estas dos instrucciones del repositorio
C:/Users/emili/Documents/blockchain-pf:
  1. docs/auditoria/prompts/_comun.md
  2. docs/auditoria/prompts/<archivo de la pasada>.md   [<parte>, si aplica]
No modifiques nada salvo tu archivo de respuesta. Tu mensaje final sigue el punto 6 de _comun.md.
```
