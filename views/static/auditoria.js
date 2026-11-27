// Vista Auditoría IA: hallazgos de /api/sellalo/auditoria con conteos, filtros y tabla. Sin innerHTML.
(() => {
  "use strict";
  const { $, h, corto, msgRuta, aviso, api, sondearEstado } = window.Sellalo;

  const aud = { hallazgos: [] };
  function contar(arr, campo) { const m = {}; arr.forEach((x) => { const k = x[campo] || "–"; m[k] = (m[k] || 0) + 1; }); return m; }
  function llenarSelect(sel, valores, todos) {
    const previo = sel.value;
    sel.replaceChildren(h("option", { value: "" }, todos), ...[...new Set(valores)].filter(Boolean).sort().map((v) => h("option", { value: v }, v)));
    sel.value = previo;
  }
  function chipsConteo(titulo, mapa, claseDe) {
    return h("div", { class: "aud-grupo" }, h("h3", { class: "subhead" }, titulo),
      h("div", { class: "chips" }, Object.entries(mapa).map(([k, v]) => h("span", { class: `chip ${claseDe(k)}` }, `${k}: ${v}`))));
  }
  const claseEstado = (k) => (/corregido|resuelto/.test(k) ? "chip-ok" : /justificado/.test(k) ? "" : "chip-warn");
  const claseSev = (k) => (/cr[ií]tic|alta/i.test(k) ? "chip-bad" : /media/i.test(k) ? "chip-warn" : "");

  function pintarAuditoria() {
    const f = { e: $("#aud-f-estado").value, s: $("#aud-f-sev").value, g: $("#aud-f-grupo").value, t: $("#aud-f-texto").value.trim().toLowerCase() };
    const fil = aud.hallazgos.filter((x) => (!f.e || x.estado === f.e) && (!f.s || x.severidad === f.s) && (!f.g || x.grupo === f.g)
      && (!f.t || [x.id, x.titulo, x.categoria, (x.commits || []).join(" "), x.prueba].join(" ").toLowerCase().includes(f.t)));
    $("#aud-cuenta").textContent = `${fil.length} de ${aud.hallazgos.length} hallazgos`;
    $("#aud-cuerpo").replaceChildren(...(fil.length ? fil.map((x) => h("tr", {},
      h("td", { class: "mono" }, x.id), h("td", {}, x.titulo), h("td", {}, h("span", { class: `chip ${claseSev(x.severidad || "")}` }, x.severidad || "–")),
      h("td", {}, x.decision || "–"), h("td", {}, h("span", { class: `chip ${claseEstado(x.estado || "")}` }, String(x.estado || "–").replace(/_/g, " "))),
      h("td", { class: "mono small" }, (x.commits || []).map((c) => corto(c, 8)).join(", ") || "–"),
      h("td", { class: "mono small wrap" }, x.prueba || "–")))
      : [h("tr", {}, h("td", { colspan: 7, class: "muted" }, "Ningún hallazgo coincide con el filtro."))]));
  }

  async function cargarAuditoria() {
    const r = await api("/auditoria");
    const av = $("#aud-aviso");
    if (!r.ok) {
      av.replaceChildren(aviso(r.status === 409 ? ((r.data && r.data.error) || "La auditoría aún no está generada: falta docs/auditoria/estado.json (ejecuta scripts/estado_auditoria.py).") : msgRuta(r, "La auditoría")));
      $("#aud-resumen").replaceChildren(); $("#aud-filtros").hidden = true; $("#aud-tabla-wrap").hidden = true; $("#aud-cuenta").textContent = "";
      return;
    }
    av.replaceChildren();
    aud.hallazgos = Array.isArray(r.data.hallazgos) ? r.data.hallazgos : [];
    const res = r.data.resumen || {};
    $("#aud-resumen").replaceChildren(h("p", { class: "small" }, h("strong", {}, `${res.total ?? aud.hallazgos.length} hallazgos`), r.data.generado ? ` · generado ${r.data.generado}` : ""),
      chipsConteo("Por estado", res.por_estado || contar(aud.hallazgos, "estado"), claseEstado),
      chipsConteo("Por severidad", res.por_severidad || contar(aud.hallazgos, "severidad"), claseSev));
    llenarSelect($("#aud-f-estado"), aud.hallazgos.map((x) => x.estado), "Todos");
    llenarSelect($("#aud-f-sev"), aud.hallazgos.map((x) => x.severidad), "Todas");
    llenarSelect($("#aud-f-grupo"), aud.hallazgos.map((x) => x.grupo), "Todos");
    $("#aud-filtros").hidden = false; $("#aud-tabla-wrap").hidden = false;
    pintarAuditoria();
  }

  $("#aud-filtros").addEventListener("input", pintarAuditoria);
  $("#aud-filtros").addEventListener("submit", (ev) => ev.preventDefault());
  $("#btn-aud-recargar").addEventListener("click", cargarAuditoria);

  sondearEstado(null, 5000);      // sólo para el encabezado (candado, altura, sincronizados)
  cargarAuditoria();
})();
