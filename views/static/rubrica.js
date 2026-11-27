// Vista Rúbrica: tablero R1–R8 y ★ (de /api/sellalo/rubrica) y recorrido del caso de uso (de estado.recorrido).
// Todo dato del servidor entra con h()/textContent; sin innerHTML.
(() => {
  "use strict";
  const { $, h, marca, msgRuta, aviso, api, sondearEstado } = window.Sellalo;

  const ESTADOS = { demostrado: ["chip-ok", "demostrado"], parcial: ["chip-warn", "parcial"], pendiente: ["chip-pend", "pendiente"] };
  // Secciones de la vista Nodo a las que lleva «Ver». Lo que no está aquí (p. ej. seccion-entrega) no tiene botón.
  const SECCIONES_NODO = new Set(["identidad", "red", "sellar", "firmas", "minado", "consenso", "cadena", "verificacion", "prioridad", "cuentas"]);

  function destino(seccion) {
    if (typeof seccion !== "string" || !seccion.startsWith("seccion-")) return null;
    const nombre = seccion.slice(8);
    if (nombre === "ataques") return "/ataques";
    if (nombre === "auditoria") return "/auditoria";
    if (nombre === "recorrido") return "#seccion-recorrido";
    return SECCIONES_NODO.has(nombre) ? `/#${seccion}` : null;
  }

  function renderRubrica(r) {
    const grid = $("#rubrica-grid"), cuenta = $("#rubrica-cuenta");
    if (!r.ok) { cuenta.textContent = "sin datos"; grid.replaceChildren(aviso(msgRuta(r, "La rúbrica"))); return; }
    const cr = Array.isArray(r.data.criterios) ? r.data.criterios : [];
    const n = cr.filter((c) => c.estado === "demostrado").length;
    cuenta.textContent = `${n} de ${cr.length || 9} criterios demostrados`;
    cuenta.className = `badge ${n === cr.length && n > 0 ? "badge-ok" : "badge-idle"}`;
    grid.replaceChildren(...cr.map((c) => {
      const [cls, txt] = ESTADOS[c.estado] || ESTADOS.pendiente;
      const ev = Array.isArray(c.evidencias) ? c.evidencias : [];
      const ruta = destino(c.seccion);
      return h("article", { class: `crit crit-${String(c.estado).replace(/[^a-z]/g, "")}`, "aria-label": `${c.id} ${c.nombre}` },
        h("header", {}, h("span", { class: "crit-id" }, c.id === "EX" ? "★" : c.id), h("h3", {}, c.nombre),
          h("span", { class: "small muted" }, `${c.puntos ?? "–"} pt`)),
        h("span", { class: `chip ${cls}` }, txt),
        h("ul", { class: "evidencias" }, ev.map((x) => h("li", {}, marca(x.ok, "cumplido", "no cumplido"), h("span", {}, x.texto)))),
        ruta ? h("a", { class: "btn btn-ghost btn-small", href: ruta, "aria-label": `Ver la sección de ${c.id}` }, "Ver") : null);
    }));
  }

  function renderRecorrido(e) {
    const ol = $("#recorrido-lista");
    const pasos = Array.isArray(e.recorrido) ? e.recorrido : null;
    if (!pasos) { ol.replaceChildren(h("li", { class: "muted" }, "Este nodo aún no informa el recorrido.")); return; }
    ol.replaceChildren(...pasos.map((p, i) => h("li", { class: `paso ${p.hecho ? "paso-ok" : ""}` },
      h("span", { class: "paso-num", "aria-hidden": "true" }, i + 1),
      h("div", {}, h("strong", {}, p.texto, " ", p.hecho ? h("span", { class: "chip chip-ok" }, marca(true, "hecho"), "hecho") : h("span", { class: "chip chip-pend" }, "pendiente")),
        p.detalle ? h("div", { class: "small muted" }, p.detalle) : null))));
  }

  let rubricaEnCurso = false;
  async function refrescarRubrica() {
    if (rubricaEnCurso || document.hidden) return;
    rubricaEnCurso = true;
    try { renderRubrica(await api("/rubrica")); } finally { rubricaEnCurso = false; }
  }

  sondearEstado((r) => {
    if (r.ok) renderRecorrido(r.data);
    else $("#recorrido-lista").replaceChildren(h("li", { class: "muted" }, msgRuta(r, "El recorrido")));
  });
  refrescarRubrica();
  setInterval(refrescarRubrica, 3000);
})();
