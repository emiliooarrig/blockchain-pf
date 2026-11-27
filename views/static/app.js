// Interfaz: sólo consulta el estado que calcula el servidor (fetch periódico) y envía acciones.
// Ningún hash, firma ni regla de consenso se calcula en el navegador.
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const fmt = (n) => (n === null || n === undefined ? "—" : Number(n).toLocaleString("es-MX"));
  const corto = (h, n = 10) => (h ? `${h.slice(0, n)}…${h.slice(-4)}` : "—");
  const hora = (t) => new Date(t * 1000).toLocaleTimeString("es-MX", { hour12: false });
  const fecha = (t) => new Date(t * 1000).toLocaleString("es-MX", { hour12: false });

  function h(tag, attrs, ...hijos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "dataset") Object.assign(el.dataset, v);
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const hijo of hijos.flat()) {
      if (hijo === null || hijo === undefined || hijo === false) continue;
      el.append(hijo instanceof Node ? hijo : String(hijo));
    }
    return el;
  }

  const ui = {
    version: "pow",
    estado: null,
    cadenaClave: "",
    nodosFirma: "",
    casosListos: false,
    timer: null,
    ocupado: false,
  };

  // ---------------------------------------------------------------- red
  async function pedir(ruta, opciones) {
    try {
      const res = await fetch(`/api/${ui.version}${ruta}`, { cache: "no-store", ...opciones });
      const json = await res.json().catch(() => ({ ok: false, error: `Respuesta inválida del servidor (HTTP ${res.status}).` }));
      return json;
    } catch (e) {
      return { ok: false, error: "No hay conexión con el servidor." };
    }
  }

  async function enviar(ruta, cuerpo, boton) {
    if (boton) boton.disabled = true;
    const r = await pedir(ruta, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo || {}),
    });
    aviso(r.ok ? r.mensaje : r.error, r.ok ? (r.rechazado ? "caso" : "ok") : "error");
    if (boton) boton.disabled = false;
    await actualizar();
    return r;
  }

  function aviso(texto, tipo) {
    const t = h("div", { class: `toast toast-${tipo}`, role: "status" }, texto);
    $("#toasts").append(t);
    setTimeout(() => t.classList.add("salir"), tipo === "error" || tipo === "caso" ? 7000 : 4000);
    setTimeout(() => t.remove(), tipo === "error" || tipo === "caso" ? 7600 : 4600);
  }

  function formulario(form) {
    const datos = {};
    for (const el of form.elements) {
      if (!el.name) continue;
      datos[el.name] = el.type === "checkbox" ? el.checked : el.value.trim();
    }
    return datos;
  }

  // ---------------------------------------------------------------- ciclo de consulta
  async function actualizar() {
    clearTimeout(ui.timer);
    const r = await pedir("/estado");
    let espera = 1000;
    if (r.ok) {
      $("#sync-banner").classList.remove("offline");
      ui.estado = r;
      render(r);
      if (r.motor.minando) espera = 250;
      await actualizarCadena(r);
    } else {
      const b = $("#sync-banner");
      b.className = "sync-banner offline";
      b.textContent = r.error;
      espera = 2000;
    }
    ui.timer = setTimeout(actualizar, espera);
  }

  // ---------------------------------------------------------------- render general
  function render(e) {
    document.title = "Sellalo · Proof of Work";

    if (ui.primeraVez !== false) {
      const f = $("#form-red");
      for (const k of ["n", "semilla", "saldo_inicial", "recompensa"]) f.elements[k].value = e.parametros[k];
      f.elements.reproducible.checked = e.parametros.reproducible;
      ui.primeraVez = false;
    }

    renderResumen(e);
    renderSelects(e);
    renderPendientes(e);
    renderSync(e);
    renderNodos(e);
    renderPow(e);
    renderCasos(e);
    renderRecompensas(e);
    renderBitacora(e);
  }

  function renderResumen(e) {
    const p = e.parametros;
    const filas = [
      ["Consenso", "Proof of Work"],
      ["Laboratorios", p.n],
      ["Semilla", `${p.semilla}${p.reproducible ? " · reloj simulado" : ""}`],
      ["Recompensa", `${p.recompensa} créditos (se acreditan tras 6 confirmaciones)`],
      ["Altura", e.altura],
    ];
    $("#red-resumen").replaceChildren(...filas.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]));
  }

  function renderSelects(e) {
    const firma = e.nodos.map((n) => n.id).join(",");
    if (firma === ui.nodosFirma) return;
    ui.nodosFirma = firma;
    const opciones = (extra) => [...(extra || []), ...e.nodos.map((n) => h("option", { value: n.id }, n.id))];
    const f = $("#form-tx");
    f.elements.emisor.replaceChildren(...opciones());
    f.elements.receptor.replaceChildren(...opciones());
    if (e.nodos.length > 1) f.elements.receptor.value = e.nodos[1].id;
    $("#cadena-nodo").replaceChildren(...opciones());
    $("#ataque-nodo").replaceChildren(...opciones([h("option", { value: "" }, "Automático")]));
  }

  function renderPendientes(e) {
    $("#pend-count").textContent = e.pendientes.length;
    const lista = $("#pendientes");
    if (!e.pendientes.length) {
      lista.replaceChildren(h("li", { class: "empty" }, "Sin transacciones pendientes. Crea una para poder minar o proponer un bloque."));
      return;
    }
    lista.replaceChildren(...e.pendientes.map((tx, i) => h("li", {},
      h("span", { class: "tx-main" }, h("strong", {}, `${tx.emisor} → ${tx.receptor}`), ` · ${fmt(tx.monto)}`,
        i < e.max_tx_por_bloque ? null : h("span", { class: "chip" }, "siguiente bloque")),
      h("span", { class: "mono small muted" }, `firma ${corto(tx.firma, 16)}`))));
  }

  function renderSync(e) {
    const todos = e.sincronizados === e.nodos.length;
    const badge = $("#sync-badge");
    badge.className = `badge ${todos ? "badge-ok" : "badge-bad"}`;
    badge.textContent = `${todos ? e.nodos.length : e.sincronizados}/${e.nodos.length} laboratorios sincronizados`;
    const banner = $("#sync-banner");
    banner.className = `sync-banner ${todos ? "ok" : "bad"}`;
    banner.replaceChildren(
      h("strong", {}, todos ? "Red sincronizada" : "Red desincronizada"),
      ` · altura ${e.altura} · último hash `, h("span", { class: "mono" }, corto(e.ultimo_hash, 16)),
      ` · ${e.pendientes.length} pendientes`);
  }

  function renderNodos(e) {
    const cols = ["Laboratorio", "Altura", "Hash del último bloque", "Sincronía", "Créditos disponibles", "Recompensas pendientes", "Último rechazo"];
    const head = $("#nodos-head");
    if (!head.children.length) head.replaceChildren(...cols.map((c) => h("th", {}, c)));
    const filas = e.nodos.map((n) => {
      const celdas = [
        h("td", {}, h("strong", {}, n.id)),
        h("td", { class: "mono" }, n.altura),
        h("td", { class: "mono small", title: n.ultimo_hash }, corto(n.ultimo_hash, 14)),
        h("td", {}, h("span", { class: `dot ${n.sincronizado ? "dot-ok" : "dot-bad"}` }), n.sincronizado ? "sí" : "no"),
        h("td", { class: "mono" }, fmt(n.disponible)),
        h("td", { class: "mono" }, n.pendiente_recompensa ? h("span", { class: "chip chip-warn" }, `${fmt(n.pendiente_recompensa)} pendiente`) : "—"),
        h("td", { class: "small muted", title: n.ultimo_rechazo }, n.ultimo_rechazo ? n.ultimo_rechazo.slice(0, 70) : "—"),
      ];
      return h("tr", { class: n.sincronizado ? "" : "row-bad" }, ...celdas);
    });
    $("#tabla-nodos tbody").replaceChildren(...filas);
  }

  // ---------------------------------------------------------------- minado
  function renderPow(e) {
    const m = e.motor;
    const badge = $("#pow-badge");
    badge.className = `badge ${m.minando ? "badge-live" : "badge-idle"}`;
    badge.textContent = m.minando ? `minando · ronda ${m.ronda}` : "inactivo";
    $("#btn-minar").disabled = m.minando;
    document.querySelector('[data-accion="minar-10"]').disabled = m.minando;
    $("#btn-cancelar").disabled = !m.minando;
    const msg = $("#pow-mensaje");
    msg.textContent = m.mensaje || "Crea transacciones y pulsa «Iniciar minado».";
    msg.className = `race-banner show ${m.ultimo && !m.minando ? "win" : ""}`;
    const meta = [];
    if (m.bloque !== null) meta.push(`Bloque #${m.bloque}`, `dificultad ${m.config.dificultad}`, `k = ${m.config.nonces_por_ronda}`, `ronda ${m.ronda} / ${fmt(m.config.max_rondas)}`);
    if (m.serie.total > 1) meta.push(`serie ${m.serie.hechos}/${m.serie.total}`);
    const total = m.mineros.reduce((s, x) => s + x.intentos, 0);
    if (m.mineros.length) meta.push(`${fmt(total)} intentos en total`);
    $("#pow-meta").textContent = meta.join(" · ");

    const grid = $("#mineros");
    if (grid.children.length !== m.mineros.length) {
      grid.replaceChildren(...m.mineros.map((x) => h("div", { class: "miner", dataset: { id: x.id } },
        h("div", { class: "miner-head" }, h("span", { class: "avatar" }, x.indice),
          h("div", {}, h("strong", {}, x.id), h("div", { class: "miner-status", dataset: { f: "estado" } }))),
        h("dl", { class: "miner-stats" },
          h("div", {}, h("dt", {}, "Nonce"), h("dd", { class: "mono", dataset: { f: "nonce" } })),
          h("div", {}, h("dt", {}, "Intentos"), h("dd", { class: "mono", dataset: { f: "intentos" } }))),
        h("div", { class: "mono hash-box", dataset: { f: "hash" } }))));
    }
    m.mineros.forEach((x, i) => {
      const card = grid.children[i];
      card.className = `miner status-${x.estado}`;
      card.querySelector('[data-f="estado"]').textContent = x.estado;
      card.querySelector('[data-f="nonce"]').textContent = fmt(x.nonce);
      card.querySelector('[data-f="intentos"]').textContent = fmt(x.intentos);
      const hb = card.querySelector('[data-f="hash"]');
      const d = m.config.dificultad;
      if (x.ultimo_hash) {
        const ceros = x.ultimo_hash.match(/^0*/)[0].length;
        hb.replaceChildren(h("span", { class: ceros >= d ? "zeros" : "zeros-partial" }, x.ultimo_hash.slice(0, ceros)), x.ultimo_hash.slice(ceros, 40) + "…");
      } else hb.textContent = "—";
    });
  }

  // ---------------------------------------------------------------- cadena
  async function actualizarCadena(e) {
    const sel = $("#cadena-nodo");
    const nodo = sel.value || (e.nodos[0] && e.nodos[0].id);
    const nodoInfo = e.nodos.find((n) => n.id === nodo);
    const clave = `${nodo}|${nodoInfo ? nodoInfo.ultimo_hash : ""}|${e.revision}`;
    if (clave === ui.cadenaClave) return;
    const r = await pedir(`/cadena?nodo=${encodeURIComponent(nodo)}`);
    if (!r.ok) return;
    ui.cadenaClave = clave;
    const cont = $("#cadena");
    const bloques = r.bloques.flatMap((b, i) => (i ? [h("div", { class: "link", "aria-hidden": "true" }, "→"), bloque(b)] : [bloque(b)]));
    const extra = r.desde > 0 ? [h("div", { class: "chain-more" }, `… ${r.desde} bloque(s) anteriores`)] : [];
    cont.replaceChildren(...extra, ...bloques);
    cont.scrollLeft = cont.scrollWidth;
  }

  function campo(k, v, cls) {
    return [h("dt", {}, k), h("dd", { class: cls || "" }, v)];
  }

  function bloque(b) {
    const genesis = b.numero === 0;
    const d = b.dificultad || 0;
    const ceros = genesis ? 0 : (b.hash.match(/^0*/)[0].length >= d && d ? d : 0);
    const campos = [
      ...campo("Timestamp", fecha(b.timestamp)),
      ...campo("Proponente", genesis ? "—" : b.proponente),
    ];
    if (!genesis && b.dificultad !== undefined) campos.push(...campo("Dificultad / nonce", `${b.dificultad} / ${fmt(b.nonce)}`, "mono"));
    if (!genesis) campos.push(...campo("Recompensa", fmt(b.recompensa), "mono"));
    if (genesis) campos.push(...campo("Laboratorios", `${Object.keys(b.cuentas).length} · ${fmt(Object.values(b.cuentas)[0].saldo)} créditos c/u`));

    const detalles = [];
    if (b.transacciones.length) {
      detalles.push(h("details", { class: "entries" }, h("summary", {}, `${b.transacciones.length} transacción(es) firmada(s)`),
        ...b.transacciones.map((tx) => h("div", { class: "entry" }, h("strong", {}, `${tx.emisor} → ${tx.receptor}`), ` · ${fmt(tx.monto)}`,
          h("div", { class: "mono small muted" }, `firma ${corto(tx.firma, 20)}`)))));
    }
    return h("article", { class: `block ${genesis ? "block-genesis" : ""}` },
      h("header", { class: "block-head" }, h("h3", {}, genesis ? "Génesis #0" : `Bloque #${b.numero}`)),
      h("dl", { class: "block-fields" }, ...campos),
      h("div", { class: "hash-label" }, "hash_anterior"),
      h("div", { class: "mono hash-box" }, b.hash_anterior),
      h("div", { class: "hash-label" }, "hash (SHA-256)"),
      h("div", { class: "mono hash-box hash-main" }, h("span", { class: "zeros" }, b.hash.slice(0, ceros)), b.hash.slice(ceros)),
      b.firma_minero ? [h("div", { class: "hash-label" }, "Firma del minero"), h("div", { class: "mono hash-box" }, corto(b.firma_minero, 28))] : null,
      ...detalles);
  }

  // ---------------------------------------------------------------- casos, recompensas y bitácora
  function renderCasos(e) {
    if (ui.casosListos) return;
    ui.casosListos = true;
    const boton = (c) => h("button", {
      class: "btn btn-ghost btn-case", type: "button",
      onclick: (ev) => enviar("/ataques", { tipo: c.id, nodo: $("#ataque-nodo").value }, ev.currentTarget),
    }, c.nombre);
    $("#casos-cadena").replaceChildren(...e.ataques.cadena.map(boton));
    $("#casos-tx").replaceChildren(...e.ataques.transaccion.map(boton));
  }

  function renderRecompensas(e) {
    const filas = e.recompensas.slice(-12).reverse();
    $("#tabla-recompensas tbody").replaceChildren(...(filas.length ? filas.map((r) => h("tr", {},
      h("td", {}, `#${r.numero}`), h("td", {}, r.nodo), h("td", { class: "mono" }, fmt(r.monto)),
      h("td", { class: "mono" }, r.requeridas ? `${r.confirmaciones}/${r.requeridas}` : "inmediata"),
      h("td", {}, h("span", { class: `chip ${r.estado === "acreditada" ? "chip-ok" : "chip-warn"}` }, r.estado))))
      : [h("tr", {}, h("td", { colspan: 5, class: "muted" }, "Aún no hay bloques."))]));
  }

  function renderBitacora(e) {
    const log = $("#bitacora");
    const ultimo = e.bitacora.length ? e.bitacora[e.bitacora.length - 1].n : 0;
    if (Number(log.dataset.ultimo) === ultimo) return;
    log.dataset.ultimo = ultimo;
    log.replaceChildren(...e.bitacora.slice().reverse().map((ev) => h("li", { class: `ev-${ev.tipo}` },
      h("span", { class: "mono ev-time" }, hora(ev.t)), h("span", { class: "ev-tag" }, ev.tipo), h("span", {}, ev.texto))));
  }

  // ---------------------------------------------------------------- eventos
  $("#cadena-nodo").addEventListener("change", () => { ui.cadenaClave = ""; actualizar(); });

  $("#form-red").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget;
    const d = formulario(f);
    const clave = f.elements.contrasena.value;          // sin recortar: los espacios cuentan
    if (clave) d.contrasena = clave; else delete d.contrasena;
    enviar("/simulacion", d, ev.submitter).then((r) => { f.elements.contrasena.value = ""; if (r.ok) { ui.nodosFirma = ""; ui.cadenaClave = ""; } });
  });
  $("#form-tx").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget;
    enviar("/transacciones", formulario(f), ev.submitter).then((r) => { if (r.ok) f.elements.monto.value = ""; });
  });
  $("#form-minar").addEventListener("submit", (ev) => {
    ev.preventDefault();
    enviar("/minar", formulario(ev.currentTarget), ev.submitter);
  });

  const acciones = {
    "tx-aleatoria": () => ["/transacciones/aleatoria", { cantidad: 3 }],
    "minar-10": () => ["/minar", { ...formulario($("#form-minar")), bloques: 10, auto_transacciones: true }],
    "cancelar-minado": () => ["/minar/cancelar", {}],
  };
  document.querySelectorAll("[data-accion]").forEach((b) => b.addEventListener("click", (ev) => {
    const [ruta, cuerpo] = acciones[b.dataset.accion]();
    enviar(ruta, cuerpo, ev.currentTarget);
  }));

  // Enlace al nodo Sellalo: sólo si este proceso es un nodo (en modo simulador la ruta responde 409).
  fetch("/api/sellalo/estado", { cache: "no-store" })
    .then((r) => { if (r.ok) $("#enlace-nodo").hidden = false; })
    .catch(() => {});

  ui.primeraVez = true;
  actualizar();
})();
