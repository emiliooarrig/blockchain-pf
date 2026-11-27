"""Tablero de la rúbrica final (contrato C8): recorrido del caso de uso, criterios R1-R8 + EX y entregables.

Todo se calcula del estado REAL (cadena del nodo, pares, contadores de la sesión, archivo del almacén, archivos del
repositorio). Nada se marca como demostrado sin evidencia: cada criterio es una lista de evidencias `{texto, ok}` y

    demostrado  todas las evidencias están en ok
    parcial     al menos una está en ok y alguna no
    pendiente   ninguna está en ok

Las evidencias que dependen de haber usado el nodo en vivo (sellar, minar, simular una alteración, emitir un
certificado...) quedan en false hasta que ocurra de verdad en esta sesión o en la cadena guardada; las del
repositorio (pruebas, documentos, verificador independiente) se comprueban leyendo los archivos.

El módulo no depende de Flask: las rutas de `controllers/sellalo.py` arman la «vista» (diccionario) y lo llaman.
"""
import json
import os
import re

from models.multifirma import es_sello

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RE_PRUEBA = re.compile(r"^\s*(?:async\s+)?def (test_\w+)", re.M)

SECCIONES = {"R1": "seccion-firmas", "R2": "seccion-verificacion", "R3": "seccion-identidad",
             "R4": "seccion-consenso", "R5": "seccion-red", "R6": "seccion-prioridad", "R7": "seccion-recorrido",
             "R8": "seccion-entrega", "EX": "seccion-auditoria"}


def analizar_cadena(cadena: list, nodo_id: str) -> dict:
    """Conteos de la copia local: sellos multifirma (umbral >= 2), bloques que los contienen y trabajo propio."""
    sellos, con_sello, propios = 0, 0, 0
    for b in cadena[1:]:
        n = sum(1 for tx in b.get("transacciones", []) if es_sello(tx) and tx.get("umbral", 0) >= 2)
        sellos += n
        con_sello += 1 if n else 0
        propios += 1 if b.get("proponente") == nodo_id else 0
    return {"sellos_multifirma": sellos, "bloques_con_multifirma": con_sello, "bloques_propios": propios,
            "bloques": len(cadena) - 1}


def _paso(id_, texto, hecho, detalle):
    return {"id": id_, "texto": texto, "hecho": bool(hecho), "detalle": detalle}


def recorrido(v: dict) -> list[dict]:
    """Los 10 pasos del caso de uso, calculados del estado real. `v` es la vista armada por la ruta.

    1 desbloquear     el nodo está desbloqueado ahora, o ya firmó bloques de la cadena (necesitó su clave).
    2 conectar        hay >= 2 pares conectados ahora mismo.
    3 proponer        existe un sello multifirma (umbral >= 2): en firma, en pendientes o en la cadena.
    4 umbral          algún sello multifirma ya reunió las firmas del umbral (en pendientes, en un bloque, o en
                      firma con faltan = 0).
    5 minar           la cadena contiene un bloque con un sello multifirma.
    6 replicar        hay >= 2 nodos (yo y mis pares), todos con la misma punta, y la altura es >= 1.
    7 prioridad       se consultó la prioridad de un documento en esta sesión (contador `prioridad_consultas`).
    8 emitir          se emitió un certificado en esta sesión (`certificados_emitidos`).
    9 verificar       se verificó un certificado y resultó válido (`certificados_validos`).
    10 alteración     se detectó una alteración en esta sesión: una simulación cuya copia alterada resultó inválida
                      (`tipos_simulados`) o un ataque rechazado (`ataques_rechazados`)."""
    nodo, an, ses = v["nodo"], v["cadena"], v["sesion"]
    pend_multi = [p for p in nodo["pendientes"] if p["tipo"] == "sello" and p["umbral"] >= 2]
    firma_multi = [s for s in v["en_firma"] if s.get("umbral", 0) >= 2]
    cons = v["consistencia"]
    n_pares = len(v["pares"])
    ok1 = nodo["desbloqueado"] or an["bloques_propios"] > 0
    ok3 = an["sellos_multifirma"] > 0 or bool(pend_multi) or bool(firma_multi)
    ok4 = an["sellos_multifirma"] > 0 or bool(pend_multi) or any(s.get("faltan", 1) == 0 for s in firma_multi)
    ok6 = cons["nodos"] >= 2 and cons["con_mi_punta"] == cons["nodos"] and nodo["altura"] >= 1
    return [
        _paso("desbloquear", "Desbloquear el nodo con la contraseña", ok1,
              "nodo desbloqueado" if nodo["desbloqueado"] else
              (f"bloqueado ahora, pero firmó {an['bloques_propios']} bloque(s) de la cadena" if ok1 else "bloqueado")),
        _paso("conectar", "Conectar con al menos 2 pares", n_pares >= 2, f"{n_pares} par(es) conectado(s)"),
        _paso("proponer", "Proponer un sello multifirma", ok3,
              f"{an['sellos_multifirma']} en cadena, {len(pend_multi)} en pendientes, {len(firma_multi)} en firma"),
        _paso("umbral", "Alcanzar el umbral de firmas", ok4,
              "algún sello multifirma reunió las firmas del umbral" if ok4 else "ningún sello multifirma completo"),
        _paso("minar", "Minar el bloque con el sello", an["bloques_con_multifirma"] > 0,
              f"{an['bloques_con_multifirma']} bloque(s) con sello multifirma"),
        _paso("replicar", "Replicar: todos los nodos con la misma punta", ok6,
              f"{cons['con_mi_punta']} de {cons['nodos']} nodo(s) con mi punta (altura {nodo['altura']})"),
        _paso("prioridad", "Consultar la prioridad de un documento", ses["prioridad_consultas"] > 0,
              f"{ses['prioridad_consultas']} consulta(s) en esta sesión"),
        _paso("emitir", "Emitir un certificado", ses["certificados_emitidos"] > 0,
              f"{ses['certificados_emitidos']} certificado(s) emitido(s) en esta sesión"),
        _paso("verificar", "Verificar un certificado válido", ses["certificados_validos"] > 0,
              f"{ses['certificados_validos']} verificación(es) válida(s) en esta sesión"),
        _paso("alteracion", "Detectar una alteración", v["tipos_simulados"] or ses["ataques_rechazados"] > 0,
              f"{len(v['tipos_simulados'])} tipo(s) de alteración simulada(s) y detectada(s), "
              f"{ses['ataques_rechazados']} ataque(s) rechazado(s)"),
    ]


# ---------------------------------------------------------------- repositorio
def _existe(ruta: str, raiz: str = RAIZ) -> bool:
    return os.path.isfile(os.path.join(raiz, ruta))


def _primero(candidatos, raiz: str = RAIZ) -> str | None:
    return next((c for c in candidatos if _existe(c, raiz)), None)


def contar_pruebas(raiz: str | None = None) -> tuple[int, int]:
    """(archivos tests/test_*.py, funciones test_*) contados leyendo el repositorio."""
    raiz = raiz or RAIZ
    carpeta = os.path.join(raiz, "tests")
    archivos = pruebas = 0
    try:
        nombres = sorted(n for n in os.listdir(carpeta) if n.startswith("test_") and n.endswith(".py"))
    except OSError:
        return 0, 0
    for nombre in nombres:
        archivos += 1
        try:
            with open(os.path.join(carpeta, nombre), encoding="utf-8") as f:
                pruebas += len(RE_PRUEBA.findall(f.read()))
        except OSError:
            pass
    return archivos, pruebas


def _lineas(ruta: str, raiz: str = RAIZ) -> list[str]:
    try:
        with open(os.path.join(raiz, ruta), encoding="utf-8") as f:
            return f.read().splitlines()
    except OSError:
        return []


def entregables(raiz: str | None = None) -> list[dict]:
    """Lista de entregables con `existe` real. Lo que no exista se muestra pendiente: nunca se inventa.
    El reporte del medio término (`docs/REPORTE.md`) NO cuenta como reporte técnico final."""
    raiz = raiz or RAIZ
    lista = []

    def agregar(nombre, candidatos, principal, detalle_si, detalle_no):
        hallado = _primero(candidatos, raiz)
        lista.append({"nombre": nombre, "archivo": hallado or principal, "existe": hallado is not None,
                      "detalle": detalle_si(hallado) if hallado else detalle_no})

    lineas = _lineas("README.md", raiz)
    texto = "\n".join(lineas).lower()
    agregar("README con instalación y ejecución", ["README.md"], "README.md",
            lambda _: f"{len(lineas)} líneas; instalación: {'sí' if 'instal' in texto else 'no'}; "
                      f"ejecución: {'sí' if 'ejecut' in texto or 'python app.py' in texto else 'no'}",
            "No existe README.md")
    reqs = [x for x in _lineas("requirements.txt", raiz) if x.strip() and not x.startswith("#")]
    agregar("Dependencias (requirements)", ["requirements.txt"], "requirements.txt",
            lambda _: f"{len(reqs)} dependencia(s) declarada(s)", "No existe requirements.txt")
    archivos, pruebas = contar_pruebas(raiz)
    lista.append({"nombre": "Pruebas automáticas", "archivo": "tests/", "existe": archivos > 0,
                  "detalle": f"{archivos} archivo(s) test_*.py y {pruebas} función(es) de prueba"
                             if archivos else "No hay pruebas en tests/"})
    agregar("Reporte técnico final", ["docs/REPORTE_FINAL.md"], "docs/REPORTE_FINAL.md",
            lambda r: f"{len(_lineas(r, raiz))} líneas",
            "Pendiente: docs/REPORTE.md es el reporte del medio término, no el final")
    agregar("Presentación", ["docs/PRESENTACION.md", "docs/PRESENTACION.pdf", "docs/PRESENTACION.pptx"],
            "docs/PRESENTACION.md", lambda r: "entregada", "Pendiente: no hay presentación en docs/")
    agregar("Guía de demostración", ["docs/GUIA_DEMO.md", "scripts/demo_e2e.py"], "docs/GUIA_DEMO.md",
            lambda r: ("guion automatizado de 10 pasos" if r.endswith(".py") else "guía escrita"),
            "Pendiente: no hay guía de demo ni script")
    agregar("Evidencia por rubro", ["docs/EVIDENCIA_RUBRICA.md"], "docs/EVIDENCIA_RUBRICA.md",
            lambda r: f"{len(_lineas(r, raiz))} líneas", "Pendiente: docs/EVIDENCIA_RUBRICA.md")
    agregar("Auditoría con IA (hallazgos y correcciones)", ["docs/auditoria/HALLAZGOS.md"],
            "docs/auditoria/HALLAZGOS.md", lambda r: "hallazgos, triaje y estado documentados",
            "Pendiente: docs/auditoria/HALLAZGOS.md")
    return lista


def leer_auditoria(raiz: str | None = None) -> dict | None:
    """Contenido de docs/auditoria/estado.json o None si no existe o no es JSON válido."""
    raiz = raiz or RAIZ
    try:
        with open(os.path.join(raiz, "docs", "auditoria", "estado.json"), encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) and isinstance(datos.get("hallazgos"), list) else None
    except (OSError, ValueError, RecursionError):
        return None


# ---------------------------------------------------------------- criterios
def _ev(texto, ok):
    return {"texto": texto, "ok": bool(ok)}


def _estado(evidencias: list[dict]) -> str:
    ok = sum(1 for e in evidencias if e["ok"])
    return "demostrado" if ok == len(evidencias) else ("parcial" if ok else "pendiente")


def _criterio(id_, nombre, puntos, evidencias):
    return {"id": id_, "nombre": nombre, "puntos": puntos, "estado": _estado(evidencias), "evidencias": evidencias,
            "seccion": SECCIONES[id_]}


def _pruebas_de(raiz: str, *archivos: str) -> int:
    total = 0
    for nombre in archivos:
        try:
            with open(os.path.join(raiz, "tests", nombre), encoding="utf-8") as f:
                total += len(RE_PRUEBA.findall(f.read()))
        except OSError:
            pass
    return total


def criterios(v: dict, raiz: str | None = None) -> list[dict]:
    """Criterios R1-R8 y EX. Condición de cada estado (siempre «todas / alguna / ninguna» de las evidencias):

    R1 multifirma      sello multifirma (umbral >= 2) en la cadena; las firmas de TODOS los sellos de la cadena se
                       verifican (auditoría detallada); alteración `multifirma` simulada o ataque
                       `multifirma_incompleta` rechazado; pruebas de multifirma en el repositorio.
    R2 verificación    la auditoría detallada de mi copia (>= 1 bloque) es válida; se simuló y detectó al menos una
                       alteración; pruebas de validación en el repositorio.
    R3 clave           el almacén existe y no hay clave en claro en disco (comprobado contra la clave real si el
                       nodo está desbloqueado); scrypt (N >= 2^15) + AES-256-GCM; el nodo se desbloqueó con la
                       contraseña; se rechazó al menos una contraseña incorrecta.
    R4 consenso        PoW con dificultad fija de la red; bloques con PoW verificado en la cadena; el nodo rechazó
                       bloques o cadenas inválidos; resolvió un conflicto (reorganización con bloques descartados).
    R5 distribución    >= 2 pares conectados; todos con mi punta; copia local persistida sin errores de escritura.
    R6 certificado     se emitió un certificado; se verificó uno válido; se detectó uno alterado/inválido; el
                       verificador independiente está en el repositorio.
    R7 solución        los 10 pasos del recorrido (cada uno es una evidencia).
    R8 entrega         cada entregable (README, requirements, pruebas, reporte final, presentación, guía, evidencia).
    EX auditoría IA    estado.json generado; hallazgos con decisión; al menos un hallazgo corregido con commit y
                       prueba; ningún hallazgo corregible sigue pendiente."""
    raiz = raiz or RAIZ
    nodo, an, ses, ver = v["nodo"], v["cadena"], v["sesion"], v["verificacion"]
    clave, cons, aud = v["clave"], v["consistencia"], v["auditoria"]
    simulados, ataques = v["tipos_simulados"], v["tipos_ataques_rechazados"]
    firmas_ok = all(t["ok"] for b in ver["bloques"] for t in b["transacciones"] if t["tipo"] == "sello")
    out = []
    out.append(_criterio("R1", "Técnica adicional: multifirma k-de-n", 1, [
        _ev(f"{an['sellos_multifirma']} sello(s) multifirma (umbral ≥ 2) en la cadena", an["sellos_multifirma"] > 0),
        _ev("Las firmas y el umbral de todos los sellos de la cadena se verifican", an["sellos_multifirma"] > 0
            and firmas_ok),
        _ev("Se detectó un sello con firmas por debajo del umbral (simulación o ataque)",
            "multifirma" in simulados or "multifirma_incompleta" in ataques),
        _ev(f"{_pruebas_de(raiz, 'test_multifirma.py')} pruebas de multifirma en el repositorio",
            _pruebas_de(raiz, "test_multifirma.py") > 0)]))
    out.append(_criterio("R2", "Métodos de verificación", 1, [
        _ev(f"Auditoría de mi copia, comprobación por comprobación en {len(ver['bloques'])} bloque(s): "
            f"{'válida' if ver['valida'] else 'INVÁLIDA'}", ver["valida"] and an["bloques"] >= 1),
        _ev(f"Alteraciones simuladas y detectadas: {', '.join(sorted(simulados)) or 'ninguna aún'}",
            bool(simulados)),
        _ev("Pruebas de validación de bloques y transacciones en el repositorio",
            _pruebas_de(raiz, "test_cadena.py", "test_transacciones.py", "test_adversarial.py") > 0)]))
    kdf, cif = clave.get("kdf") or {}, clave.get("cifrado") or {}
    out.append(_criterio("R3", "Salvaguarda de la clave privada", 1, [
        _ev("Almacén cifrado en disco y sin clave privada en claro", clave["disponible"]
            and clave.get("clave_en_claro_en_disco") is False),
        _ev(f"scrypt (N={kdf.get('n')}) + {cif.get('alg')}", clave["disponible"]
            and kdf.get("alg") == "scrypt" and (kdf.get("n") or 0) >= 2 ** 15 and cif.get("alg") == "AES-256-GCM"),
        _ev("El nodo se desbloqueó con la contraseña", nodo["desbloqueado"]),
        _ev(f"{clave['rechazados']} contraseña(s) incorrecta(s) rechazada(s)", clave["rechazados"] > 0)]))
    con = nodo["consenso"]
    reorgs = [r for r in con["reorganizaciones"] if r["bloques_descartados"] > 0]
    out.append(_criterio("R4", "Consenso funcional (Proof of Work)", 1, [
        _ev(f"PoW con dificultad de red acordada (génesis o ajuste co-firmado): {nodo['dificultad_red']}", nodo["dificultad_red"] is not None),
        # Informativa: no exige haber ajustado la dificultad (el criterio no se vuelve más difícil de cumplir).
        _ev(f"Ajustes de dificultad co-firmados aplicados: {len(nodo.get('ajustes') or [])}", True),
        _ev("Bloques con prueba de trabajo verificada en la cadena", an["bloques"] >= 1
            and all(b["comprobaciones"]["pow"] for b in ver["bloques"])),
        _ev(f"Rechazó {con['bloques_rechazados']} bloque(s) y {con['cadenas_rechazadas']} cadena(s) inválidos",
            con["bloques_rechazados"] + con["cadenas_rechazadas"] > 0),
        _ev(f"{len(reorgs)} conflicto(s) resuelto(s) con reorganización", bool(reorgs))]))
    pers = nodo["persistencia"]
    out.append(_criterio("R5", "Distribución de la cadena", 1, [
        _ev(f"{len(v['pares'])} par(es) conectado(s)", len(v["pares"]) >= 2),
        _ev(f"{cons['con_mi_punta']} de {cons['nodos']} nodo(s) con la misma punta",
            cons["nodos"] >= 2 and cons["con_mi_punta"] == cons["nodos"]),
        _ev(f"Copia local persistida ({pers['bytes']} bytes) sin errores de escritura",
            bool(pers["bytes"]) and pers["error"] is None)]))
    out.append(_criterio("R6", "Agregado particular: certificado de prioridad verificable offline", 1, [
        _ev(f"{ses['certificados_emitidos']} certificado(s) emitido(s) en esta sesión", ses["certificados_emitidos"] > 0),
        _ev(f"{ses['certificados_validos']} certificado(s) verificado(s) como válido(s)", ses["certificados_validos"] > 0),
        _ev(f"{ses['certificados_invalidos']} certificado(s) alterado(s) o inválido(s) detectado(s)",
            ses["certificados_invalidos"] > 0),
        _ev("Verificador independiente (verificar_certificado.py) en el repositorio",
            _existe("verificar_certificado.py", raiz))]))
    pasos = v["recorrido"]
    out.append(_criterio("R7", "Solución del problema (caso de uso de principio a fin)", 2,
                         [_ev(f"{p['texto']}: {p['detalle']}", p["hecho"]) for p in pasos]))
    out.append(_criterio("R8", "Entrega", 2,
                         [_ev(f"{e['nombre']}: {e['detalle']}", e["existe"]) for e in v["entregables"]]))
    if aud is None:
        ev_aud = [_ev("docs/auditoria/estado.json no existe: ejecuta scripts/estado_auditoria.py", False)]
    else:
        r = aud.get("resumen", {})
        por = r.get("por_estado", {})
        corregidos = [h for h in aud["hallazgos"] if h.get("estado") == "corregido" and h.get("commits")]
        con_prueba = [h for h in corregidos if h.get("prueba")]
        pendientes = por.get("pendiente", 0)
        ev_aud = [_ev(f"{r.get('total', 0)} hallazgos documentados con su decisión", r.get("total", 0) > 0),
                  _ev(f"{len(con_prueba)} corrección(es) con commit y prueba de regresión", bool(con_prueba)),
                  _ev(f"{pendientes} hallazgo(s) todavía pendiente(s) de corregir", pendientes == 0)]
    out.append(_criterio("EX", "Punto excepcional: auditoría del código con IA", 1, ev_aud))
    return out
