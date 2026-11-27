# Estado de las correcciones de la auditoría con IA

> Corte al integrar la rama `proyecto-final` en `main`. Decisiones en [TRIAJE.md](TRIAJE.md); detalle de cada
> hallazgo en [HALLAZGOS.md](HALLAZGOS.md). Cada corrección tiene su commit `fix(AUD-0NN)` y una prueba de regresión
> que se vio fallar antes del arreglo (`tests/test_auditoria_g1.py`, `g2`, `g3`).

## Corregidos (17)

| Grupo | IDs | Detalle |
|---|---|---|
| G1 · red | AUD-001, 002, 008, 009, 011 | commits `fix(AUD-0NN)` en `models/red_p2p.py` y `models/nodo_completo.py` |
| G2 · API | AUD-003, 017, 032, 033 (parcial: SRI no aplica), 034, 035, 036, 037 | [correcciones/G2.md](correcciones/G2.md) |
| G3 · núcleo | AUD-004, 005, 006, 007 | commits `fix(AUD-0NN)` en el núcleo y el verificador |

Ajuste de integración: `/api/sellalo/certificado/verificar` pasa el génesis del nodo al verificador (AUD-005), y la
prueba `test_certificado_de_otra_red_se_reconoce` ahora exige que un certificado de otra red **no** sea válido.

## Sin código, con justificación (7)

AUD-015 y AUD-046 (documentar), AUD-023, 025, 030, 042, 047 (no aplicar) — justificación en [TRIAJE.md](TRIAJE.md).

## Pendientes (38)

La sesión que corregía G1 y G3 se interrumpió; su trabajo con commit está integrado y los cambios a medias quedaron
sin integrar en sus copias de trabajo (`blockchain-pf-wt/g1`: AUD-028 en curso; `blockchain-pf-wt/g3`: AUD-018 en curso).

| Grupo | IDs pendientes |
|---|---|
| G1 · red | AUD-010, 012, 013, 014, 016, 026, 027, 028, 029, 031 |
| G3 · núcleo | AUD-018, 019, 020, 021, 022, 038, 039, 040, 041, 043, 044, 045 |
| G4 · limpieza | AUD-024, 048, 049, 050, 051, 052, 053, 054, 055, 056, 057, 058, 059, 060, 061, 062 |

Falta además la pasada **P5** (verificación de cierre por la IA) y el reporte final `REPORTE_AUDITORIA.md`.
