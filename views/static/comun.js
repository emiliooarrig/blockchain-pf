// Utilidades comunes de las vistas del nodo Sellalo (Nodo, Rúbrica, Auditoría). Sin dependencias. Todo el contenido que
// viene del servidor se inserta con textContent/createTextNode vía h(); no se usa innerHTML con datos.
(() => {
  "use strict";

  const API = "/api/sellalo";
  const $ = (s) => document.querySelector(s);

  function h(tag, attrs, ...hijos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === false || v == null) continue;
      if (k === "class") el.className = v;
      else el.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of hijos.flat()) {
      if (c == null || c === false) continue;
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  }
  const corto = (x, n = 10) => (typeof x === "string" && x.length > n + 1 ? `${x.slice(0, n)}…` : String(x ?? ""));
  const fecha = (t) => (typeof t === "number" ? new Date(t * 1000).toLocaleString("es") : "–");
  const hora = (t) => (typeof t === "number" ? new Date(t * 1000).toLocaleTimeString("es") : "");
  const num = (n) => (typeof n === "number" ? n.toLocaleString("es") : "0");
  const lista = (x) => (Array.isArray(x) ? x : x && typeof x === "object" ? Object.keys(x) : []);
  const mostrar = (el, v) => { el.hidden = !v; };

  // Hash con los ceros iniciales resaltados (igual que en el simulador).
  function hashCeros(hash) {
    const s = String(hash || "");
    const ceros = (s.match(/^0*/) || [""])[0];
    return h("span", { class: "mono hash-main" }, h("span", { class: "zeros" }, ceros), s.slice(ceros.length));
  }

  function toast(texto, tipo = "ok") {
    const cont = $("#toasts");
    if (!cont) return;
    const t = h("div", { class: `toast toast-${tipo}`, role: tipo === "error" ? "alert" : "status" }, texto);
    cont.append(t);
    setTimeout(() => t.classList.add("salir"), tipo === "error" ? 8000 : 4500);
    setTimeout(() => t.remove(), tipo === "error" ? 8600 : 5100);
  }

  async function api(ruta, { metodo = "GET", json, form } = {}) {
    const opt = { method: metodo, headers: {} };
    if (json !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(json); }
    if (form) opt.body = form;
    try {
      const r = await fetch(API + ruta, opt);
      let data = {};
      try { data = await r.json(); } catch { /* respuesta sin JSON */ }
      return { ok: r.ok && data.ok !== false, status: r.status, data };
    } catch {
      return { ok: false, status: 0, data: { error: "No se pudo contactar con el nodo." } };
    }
  }

  // ---- marcas y avisos
  const NS = "http://www.w3.org/2000/svg";
  function svgIco(ok) {
    const s = document.createElementNS(NS, "svg");
    for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: "14", height: "14", fill: "none", stroke: "currentColor",
      "stroke-width": "3", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false" })) s.setAttribute(k, v);
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", ok === null ? "M6 12h12" : ok ? "m5 12 5 5 9-10" : "M6 6l12 12M18 6 6 18");
    s.append(p);
    return s;
  }
  // Marca de comprobación (correcto / falla / sin dato) con texto para lectores de pantalla.
  function marca(ok, si = "Sí", no = "No") {
    const v = ok === null || ok === undefined ? null : !!ok;
    return h("span", { class: `marca ${v === null ? "marca-na" : v ? "marca-ok" : "marca-bad"}` }, svgIco(v), h("span", { class: "sr-only" }, v === null ? "Sin dato" : v ? si : no));
  }
  // Aviso discreto cuando una ruta responde 404/409/sin conexión.
  function msgRuta(r, que) {
    if (r.status === 404) return `${que}: este nodo aún no ofrece esta información (ruta no disponible).`;
    if (r.status === 409) return (r.data && r.data.error) || `${que}: todavía no hay datos.`;
    if (r.status === 0) return "No se pudo contactar con el nodo.";
    return (r.data && r.data.error) || `${que}: error ${r.status}.`;
  }
  const aviso = (t) => h("p", { class: "aviso", role: "status" }, t);

  // ---- encabezado común: laboratorio y estado compacto (candado, altura, n/n sincronizados)
  function renderEncabezado(e) {
    const n = e.nodo;
    const poner = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
    poner("enc-lab", n.id);
    const ins = $("#enc-estado");
    if (ins) {
      ins.classList.toggle("is-open", n.desbloqueado);
      ins.classList.toggle("is-locked", !n.desbloqueado);
      ins.classList.remove("badge-idle");
      poner("enc-estado-txt", n.desbloqueado ? "Desbloqueado" : "Bloqueado");
      const arco = $("#ico-arco");
      if (arco) arco.setAttribute("d", n.desbloqueado ? "M8 11V7a4 4 0 0 1 7.5-2" : "M8 11V7a4 4 0 0 1 8 0v4");
    }
    const alt = $("#enc-altura");
    if (alt) { alt.textContent = `altura ${n.altura}`; alt.setAttribute("title", `Punta de la cadena: ${n.punta}`); }
    const k = e.consistencia, sync = $("#enc-sync");
    if (sync && k) {
      sync.textContent = `${k.con_mi_punta}/${k.nodos} sincronizados`;
      sync.setAttribute("title", "Nodos de la red con la misma punta que este nodo");
      sync.classList.toggle("is-open", k.con_mi_punta === k.nodos);
      sync.classList.toggle("is-locked", k.con_mi_punta !== k.nodos);
    }
  }

  // Sondeo de /estado para las vistas que sólo lo leen (Rúbrica, Auditoría). `alRecibir(r)` recibe la respuesta cruda.
  function sondearEstado(alRecibir, cada = 3000) {
    let enCurso = false;
    async function una() {
      if (enCurso || document.hidden) return;
      enCurso = true;
      try {
        const r = await api("/estado");
        if (r.ok) renderEncabezado(r.data);
        if (alRecibir) alRecibir(r);
      } finally { enCurso = false; }
    }
    una();
    setInterval(una, cada);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) una(); });
  }

  window.Sellalo = { API, $, h, corto, fecha, hora, num, lista, mostrar, hashCeros, toast, api, svgIco, marca, msgRuta, aviso,
                     renderEncabezado, sondearEstado };
})();
