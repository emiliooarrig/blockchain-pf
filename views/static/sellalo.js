// Interfaz del nodo Sellalo. Sin dependencias. Todo el contenido que viene del servidor (títulos, investigadores,
// ids de nodos remotos…) se inserta con textContent/createTextNode vía h(); no se usa innerHTML con datos externos.
(() => {
  "use strict";

  const API = "/api/sellalo";
  const $ = (s) => document.querySelector(s);

  // ---------------------------------------------------------------- utilidades
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
    const t = h("div", { class: `toast toast-${tipo}`, role: tipo === "error" ? "alert" : "status" }, texto);
    $("#toasts").append(t);
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

  // ---------------------------------------------------------------- estado de la interfaz
  const ui = { est: null, ocupados: new Set(), abiertos: new Set(), detalles: new Map(), hashPrio: "",
               clavesAutores: "", clavesAtaques: "", clavesBloques: "", clavesBitacora: "", tiposBitacora: new Set(),
               limitesAplicados: false };

  function bloqueado() { return !(ui.est && ui.est.nodo && ui.est.nodo.desbloqueado); }

  // Ejecuta una acción de escritura: deshabilita el botón, muestra toast con el mensaje o el `error` del servidor.
  async function enviar(btn, ruta, opciones, alExito) {
    if (btn) { ui.ocupados.add(btn.id); btn.disabled = true; }
    const r = await api(ruta, opciones);
    if (btn) ui.ocupados.delete(btn.id);
    if (r.ok) toast(r.data.mensaje || "Hecho.", "ok");
    else toast(r.data.error || `Error ${r.status}`, "error");
    if (r.ok && alExito) alExito(r.data);
    await actualizar();
    return r;
  }

  // ---------------------------------------------------------------- render
  function ponerDeshabilitado(id, motivoBloqueo, extra) {
    const b = document.getElementById(id);
    if (!b || ui.ocupados.has(id)) return;
    const motivo = extra || (bloqueado() ? motivoBloqueo : "");
    b.disabled = !!motivo;
    if (motivo) b.setAttribute("title", motivo); else b.removeAttribute("title");
  }

  function renderEncabezado(e) {
    const n = e.nodo;
    $("#enc-lab").textContent = n.id;
    $("#enc-red").textContent = e.red.nombre;
    $("#enc-genesis").textContent = corto(e.red.hash_genesis, 12);
    $("#enc-genesis").setAttribute("title", e.red.hash_genesis);
    const ins = $("#enc-estado");
    ins.classList.toggle("is-open", n.desbloqueado);
    ins.classList.toggle("is-locked", !n.desbloqueado);
    ins.classList.remove("badge-idle");
    $("#enc-estado-txt").textContent = n.desbloqueado ? "Desbloqueado" : "Bloqueado";
    $("#ico-arco").setAttribute("d", n.desbloqueado ? "M8 11V7a4 4 0 0 1 7.5-2" : "M8 11V7a4 4 0 0 1 8 0v4");
    $("#enc-altura").textContent = `altura ${n.altura} · punta ${corto(n.punta, 8)}`;
    $("#enc-altura").setAttribute("title", n.punta);
  }

  function renderBanda(e, msgError) {
    const b = $("#banda");
    if (msgError) { b.className = "sync-banner offline"; b.textContent = msgError; mostrar(b, true); return; }
    if (e && bloqueado()) {
      b.className = "sync-banner";
      b.textContent = "El nodo está bloqueado: desbloquéalo en el paso 1 para firmar, minar y conectarte a la red.";
      mostrar(b, true);
    } else mostrar(b, false);
  }

  function estadoPar(p, n) {
    if (p.punta === n.punta) return ["sincronizado", "par-sinc"];
    if (p.altura < n.altura) return ["atrasado", "par-dif"];
    if (p.altura > n.altura) return ["adelantado", "par-dif"];
    return ["divergente", "par-div"];
  }

  function renderRed(e) {
    $("#red-ips").textContent = (e.red.direcciones || []).join(" · ") || "–";
    $("#red-puerto").textContent = e.red.puerto_p2p;
    $("#pares-count").textContent = e.pares.length;
    const filas = e.pares.map((p) => {
      const [txt, cls] = estadoPar(p, e.nodo);
      const btn = h("button", { class: "btn btn-ghost btn-small", type: "button" }, "Desconectar");
      btn.addEventListener("click", () => {
        btn.disabled = true;
        enviar(null, `/pares/${encodeURIComponent(p.id)}/desconectar`, { metodo: "POST", json: {} });
      });
      return h("tr", {},
        h("td", { class: "mono" }, p.id), h("td", { class: "mono" }, p.direccion),
        h("td", {}, typeof p.latencia_ms === "number" ? `${p.latencia_ms.toFixed(0)} ms` : "–"),
        h("td", {}, p.altura), h("td", { class: "mono", title: p.punta }, corto(p.punta, 8)),
        h("td", {}, h("span", { class: `estado-par ${cls}` }, txt), p.estado === "sincronizando" ? h("span", { class: "chip chip-warn" }, "sincronizando") : null),
        h("td", {}, btn));
    });
    $("#pares-cuerpo").replaceChildren(...(filas.length ? filas
      : [h("tr", {}, h("td", { colspan: 7, class: "muted" }, bloqueado() ? "Desbloquea el nodo para ver sus pares." : "Sin pares conectados."))]));
  }

  // Casillas de autores y receptor de transferencias: sólo se reconstruyen si cambia la lista de laboratorios.
  function renderFormularios(e) {
    const labs = e.laboratorios.map((l) => l.id);
    const clave = `${e.nodo.id}|${labs.join(",")}`;
    if (clave !== ui.clavesAutores) {
      ui.clavesAutores = clave;
      const marcados = new Set([...document.querySelectorAll("#autores-lista input:checked")].map((i) => i.value));
      $("#autores-lista").replaceChildren(...labs.map((id) => {
        const propio = id === e.nodo.id;
        const inp = h("input", { type: "checkbox", name: "autores", value: id });
        inp.checked = propio || marcados.has(id);
        inp.disabled = propio;
        return h("label", { class: "check" }, inp, propio ? `${id} (yo)` : id);
      }));
      const rec = $("#in-tx-receptor"), previo = rec.value;
      rec.replaceChildren(...labs.filter((id) => id !== e.nodo.id).map((id) => h("option", { value: id }, id)));
      if (previo) rec.value = previo;
    }
    actualizarUmbral();
    const cl = `${e.ataques.map((a) => a.id).join(",")}`;
    if (cl !== ui.clavesAtaques) {
      ui.clavesAtaques = cl;
      const sel = $("#in-ataque-tipo"), previo = sel.value;
      sel.replaceChildren(...e.ataques.map((a) => h("option", { value: a.id }, a.nombre)));
      if (previo) sel.value = previo;
    }
    if (!ui.limitesAplicados) {
      ui.limitesAplicados = true;
      const [min, max] = e.limites.dificultad;
      const d = $("#in-dif");
      d.min = min; d.max = max;
      $("#dif-rango").textContent = `(${min} a ${max})`;
      $("#in-sello-titulo").maxLength = e.limites.titulo;
      $("#in-sello-inv").maxLength = e.limites.investigador;
      $("#in-tx-monto").max = e.limites.monto_max;
    }
  }

  function actualizarUmbral() {
    const n = document.querySelectorAll("#autores-lista input:checked").length || 1;
    $("#umbral-max").textContent = n;
    const u = $("#in-sello-umbral");
    u.max = n;
    if (Number(u.value) > n) u.value = n;
  }

  function progreso(s) {
    const faltan = (s.autores || []).filter((a) => !(s.firmas || []).includes(a));
    return h("div", { class: "progreso" },
      h("span", { class: "chip" }, `${(s.firmas || []).length}/${s.umbral} firmas`),
      faltan.length ? h("span", { class: "small muted" }, `Faltan: ${faltan.join(", ")}`) : null);
  }

  function renderFirmas(e) {
    $("#sol-count").textContent = e.solicitudes.length;
    const sol = e.solicitudes.map((s) => {
      const btn = h("button", { class: "btn btn-small", type: "button" }, "Firmar");
      if (bloqueado()) { btn.disabled = true; btn.title = "Desbloquea el nodo para firmar."; }
      btn.addEventListener("click", () => { btn.disabled = true; enviar(null, `/sellos/${encodeURIComponent(s.id)}/firmar`, { metodo: "POST", json: {} }); });
      return h("li", { class: "col" },
        h("div", {}, h("strong", {}, s.titulo), h("span", { class: "small muted" }, ` · ${s.investigador} · propone ${s.laboratorio}`)),
        h("div", { class: "mono small wrap", title: s.doc_hash }, corto(s.doc_hash, 16)), progreso(s), h("div", {}, btn));
    });
    $("#solicitudes").replaceChildren(...(sol.length ? sol : [h("li", { class: "empty" }, "Nadie espera tu firma.")]));
    const propios = e.sellos_en_firma.filter((s) => s.laboratorio === e.nodo.id);
    $("#enfirma-count").textContent = propios.length;
    const mios = propios.map((s) => h("li", { class: "col" },
      h("div", {}, h("strong", {}, s.titulo), h("span", { class: "small muted" }, ` · ${s.investigador}`)),
      h("div", { class: "mono small wrap", title: s.doc_hash }, corto(s.doc_hash, 16)), progreso(s)));
    $("#enfirma").replaceChildren(...(mios.length ? mios : [h("li", { class: "empty" }, "No tienes sellos esperando firmas.")]));
  }

  function renderMinado(e) {
    const n = e.nodo, st = n.estadisticas || {};
    $("#pend-count").textContent = n.pendientes.length;
    const pend = n.pendientes.map((p) => (p.tipo === "sello"
      ? h("li", {}, h("span", {}, h("span", { class: "chip" }, "sello"), ` ${p.titulo}`), h("span", { class: "small muted" }, `${p.laboratorio} · ${p.firmas}/${p.umbral} firmas`))
      : h("li", {}, h("span", {}, h("span", { class: "chip chip-warn" }, "transferencia"), ` ${p.emisor} → ${p.receptor}`), h("span", { class: "mono" }, `${p.monto} cr.`))));
    $("#pendientes").replaceChildren(...(pend.length ? pend : [h("li", { class: "empty" }, "No hay pendientes.")]));
    const b = $("#minado-badge");
    b.textContent = n.minando ? "minando" : "detenido";
    b.className = `badge ${n.minando ? "badge-live" : "badge-idle"}`;
    $("#st-intentos").textContent = num(st.intentos);
    $("#st-hs").textContent = num(Math.round(st.hashes_por_s || 0));
    $("#st-nonce").textContent = num(st.nonce);
    $("#st-bloque").textContent = st.bloque || "–";
    $("#st-minados").textContent = num(st.bloques_minados);
    ponerDeshabilitado("btn-minar", "Desbloquea el nodo para minar.", n.minando ? "Ya hay un minado en curso." : "");
    ponerDeshabilitado("btn-detener", "", n.minando ? "" : "No hay minado en curso.");
  }

  // ---- cadena
  function txDetalle(tx) {
    if (tx && tx.doc_hash) {
      return h("div", { class: "entry" },
        h("span", { class: "chip" }, "sello"), " ", h("strong", {}, tx.titulo), h("span", { class: "muted" }, ` · ${tx.investigador}`),
        h("div", {}, `Laboratorio ${tx.laboratorio} · autores: ${(tx.autores || []).join(", ")}`),
        h("div", {}, `Firmas ${lista(tx.firmas).length}/${tx.umbral}: ${lista(tx.firmas).join(", ")}`),
        h("div", { class: "mono small", title: tx.doc_hash }, corto(tx.doc_hash, 24)));
    }
    if (tx && tx.emisor) {
      return h("div", { class: "entry" }, h("span", { class: "chip chip-warn" }, "transferencia"), ` ${tx.emisor} → ${tx.receptor}: `, h("strong", {}, `${tx.monto} créditos`));
    }
    return h("div", { class: "entry" }, h("span", { class: "chip chip-sin-apuesta" }, String((tx && tx.tipo) || "transacción")));
  }

  function cuerpoDetalle(numero) {
    const d = ui.detalles.get(numero);
    if (!d) return h("p", { class: "muted" }, "Cargando…");
    if (d.error) return h("p", { class: "muted" }, d.error);
    if (!d.txs.length) return h("p", { class: "muted" }, "Sin transacciones de usuario (sólo la recompensa del minero).");
    return h("div", {}, d.txs.map(txDetalle));
  }

  async function cargarDetalle(numero, contenedor) {
    if (ui.detalles.has(numero) && !ui.detalles.get(numero).error) return;
    const r = await api(`/bloques/${numero}`);
    const bloque = r.ok ? (r.data.bloque || r.data) : null;
    ui.detalles.set(numero, bloque && Array.isArray(bloque.transacciones)
      ? { txs: bloque.transacciones }
      : { error: (r.data && r.data.error) || "No se pudo cargar el detalle del bloque." });
    contenedor.replaceChildren(cuerpoDetalle(numero));
  }

  function renderCadena(e) {
    const bloques = e.nodo.ultimos_bloques;
    const clave = `${e.nodo.punta}|${e.nodo.altura}`;
    if (clave === ui.clavesBloques) return;
    ui.clavesBloques = clave;
    const req = e.nodo.confirmaciones;
    $("#cadena").replaceChildren(...bloques.map((b) => {
      const detalle = h("div", { class: "bloque-detalle" }, ui.abiertos.has(b.numero) ? cuerpoDetalle(b.numero) : null);
      const det = h("details", { class: "bloque" },
        h("summary", {},
          h("strong", {}, `#${b.numero}`), h("span", { class: "small muted" }, fecha(b.timestamp)),
          h("span", { class: "small" }, `Minero ${b.proponente || "–"} · dif. ${b.dificultad ?? "–"} · ${b.transacciones} tx`),
          b.numero === 0
            ? h("span", { class: "chip" }, "génesis")
            : h("span", { class: `chip ${b.confirmaciones >= req ? "chip-ok" : "chip-warn"}` }, `${Math.min(b.confirmaciones, req)}/${req} conf.`),
          hashCeros(b.hash)),
        detalle);
      if (ui.abiertos.has(b.numero)) det.open = true;
      det.addEventListener("toggle", () => {
        if (det.open) { ui.abiertos.add(b.numero); detalle.replaceChildren(cuerpoDetalle(b.numero)); cargarDetalle(b.numero, detalle); }
        else ui.abiertos.delete(b.numero);
      });
      if (det.open) cargarDetalle(b.numero, detalle);
      return det;
    }));
  }

  function renderCuentas(e) {
    $("#cuentas-cuerpo").replaceChildren(...e.nodo.cuentas.map((c) => h("tr", { class: c.id === e.nodo.id ? "papel-proponente" : "" },
      h("td", { class: "mono" }, c.id + (c.id === e.nodo.id ? " (yo)" : "")), h("td", {}, c.saldo), h("td", {}, c.disponible), h("td", {}, c.pendiente_recompensa))));
  }

  function renderBitacora(e) {
    const sel = $("#filtro-bitacora");
    for (const ev of e.nodo.bitacora) {
      if (!ui.tiposBitacora.has(ev.tipo)) { ui.tiposBitacora.add(ev.tipo); sel.append(h("option", { value: ev.tipo }, ev.tipo)); }
    }
    const filtro = sel.value;
    const ultimo = e.nodo.bitacora.length ? e.nodo.bitacora[e.nodo.bitacora.length - 1].n : 0;
    const clave = `${ultimo}|${filtro}`;
    if (clave === ui.clavesBitacora) return;
    ui.clavesBitacora = clave;
    const evs = e.nodo.bitacora.filter((ev) => !filtro || ev.tipo === filtro).slice().reverse();
    $("#bitacora").replaceChildren(...(evs.length ? evs.map((ev) => h("li", { class: `ev-${String(ev.tipo).replace(/[^a-z0-9_-]/gi, "")}` },
      h("span", { class: "mono ev-time" }, hora(ev.t)), h("span", { class: "ev-tag" }, ev.tipo), h("span", {}, ev.texto)))
      : [h("li", {}, h("span", {}, ""), h("span", {}, ""), h("span", { class: "muted" }, "Sin eventos."))]));
  }

  function renderBotones(e) {
    const bl = bloqueado();
    ponerDeshabilitado("btn-desbloquear", "", bl ? "" : "El nodo ya está desbloqueado.");
    ponerDeshabilitado("btn-bloquear", "", bl ? "El nodo ya está bloqueado." : "");
    ponerDeshabilitado("btn-conectar", "Desbloquea el nodo para conectarte a otros pares.");
    ponerDeshabilitado("btn-sellar", "Desbloquea el nodo para firmar el sello.");
    ponerDeshabilitado("btn-tx", "Desbloquea el nodo para firmar la transferencia.");
    ponerDeshabilitado("btn-ataque", "Desbloquea el nodo para lanzar ataques (se firman con su clave).");
  }

  function render(e) {
    renderEncabezado(e); renderBanda(e); renderRed(e); renderFormularios(e); renderFirmas(e);
    renderMinado(e); renderCadena(e); renderCuentas(e); renderBitacora(e); renderBotones(e);
  }

  // ---------------------------------------------------------------- sondeo
  let enCurso = false;
  async function actualizar() {
    if (enCurso) return;
    enCurso = true;
    try {
      const r = await api("/estado");
      if (r.ok) { ui.est = r.data; render(r.data); }
      else if (r.status === 409) renderBanda(null, r.data.error || "Este proceso no es un nodo Sellalo.");
      else renderBanda(null, r.data.error || "Sin conexión con el nodo; reintentando…");
    } finally { enCurso = false; }
  }
  function ciclo() {
    if (!document.hidden) actualizar();
    setTimeout(ciclo, 1000);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) actualizar(); });

  // ---------------------------------------------------------------- formularios
  $("#form-desbloquear").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const campo = $("#in-contrasena");
    const contrasena = campo.value;
    campo.value = "";                      // nunca se conserva ni se guarda en el navegador
    enviar($("#btn-desbloquear"), "/desbloquear", { metodo: "POST", json: { contrasena } });
  });
  $("#btn-bloquear").addEventListener("click", (ev) => enviar(ev.currentTarget, "/bloquear", { metodo: "POST", json: {} }));

  $("#form-par").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const ip = $("#in-par-ip").value.trim(), puerto = Number($("#in-par-puerto").value);
    enviar($("#btn-conectar"), "/pares", { metodo: "POST", json: { ip, puerto } });
  });

  $("#autores-lista").addEventListener("change", actualizarUmbral);
  $("#form-sello").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget;
    const fd = new FormData();
    const archivo = $("#in-sello-archivo").files[0];
    if (archivo) fd.append("archivo", archivo);
    fd.append("titulo", $("#in-sello-titulo").value);
    fd.append("investigador", $("#in-sello-inv").value);
    fd.append("umbral", $("#in-sello-umbral").value);
    document.querySelectorAll("#autores-lista input:checked").forEach((i) => fd.append("autores", i.value));
    enviar($("#btn-sellar"), "/sellos", { metodo: "POST", form: fd }, (d) => {
      const s = d.sello || {};
      const box = $("#sello-resultado");
      box.className = "resultado ok";
      box.replaceChildren(
        h("p", {}, h("strong", {}, "Hash del documento (doc_hash):")), h("p", { class: "mono" }, s.doc_hash || ""),
        h("p", {}, "Estado: ", h("span", { class: "chip" }, s.estado === "pendiente" ? "pendiente de minado" : "en firma"),
          ` · firmas ${lista(s.firmas).length || s.firmas || 0}/${s.umbral}`));
      mostrar(box, true);
      f.elements.archivo.value = ""; f.elements.titulo.value = ""; f.elements.investigador.value = "";
    });
  });

  $("#form-minar").addEventListener("submit", (ev) => {
    ev.preventDefault();
    enviar($("#btn-minar"), "/minar", { metodo: "POST", json: { dificultad: Number($("#in-dif").value), continuo: $("#in-continuo").checked } });
  });
  $("#btn-detener").addEventListener("click", (ev) => enviar(ev.currentTarget, "/minar/detener", { metodo: "POST", json: {} }));
  $("#form-tx").addEventListener("submit", (ev) => {
    ev.preventDefault();
    enviar($("#btn-tx"), "/transferencias", { metodo: "POST", json: { receptor: $("#in-tx-receptor").value, monto: Number($("#in-tx-monto").value) } },
      () => { $("#in-tx-monto").value = ""; });
  });

  // ---- prioridad
  function bloqueSello(s, etiqueta) {
    return h("div", { class: "sello-item" },
      h("p", {}, h("span", { class: `chip ${s.prioritario ? "chip-ok" : ""}` }, etiqueta), " ", h("strong", {}, s.titulo)),
      h("p", { class: "small" }, `Investigador: ${s.investigador} · laboratorio ${s.laboratorio}`),
      h("p", { class: "small" }, `Autores: ${(s.autores || []).join(", ")}`),
      h("p", { class: "small" }, `Bloque #${s.numero} · ${fecha(s.fecha_bloque)} · `,
        h("span", { class: `chip ${s.confirmado ? "chip-ok" : "chip-warn"}` }, `${Math.min(s.confirmaciones, s.requeridas)}/${s.requeridas} confirmaciones`)));
  }

  $("#form-prioridad").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const archivo = $("#in-prio-archivo").files[0], hashTxt = $("#in-prio-hash").value.trim();
    const fd = new FormData();
    if (archivo) fd.append("archivo", archivo); else fd.append("doc_hash", hashTxt);
    const btn = $("#btn-prio");
    btn.disabled = true;
    const r = await api("/prioridad", { metodo: "POST", form: fd });
    btn.disabled = false;
    const box = $("#prio-resultado");
    if (!r.ok) { box.className = "resultado bad"; box.replaceChildren(h("p", {}, r.data.error || "No se pudo consultar.")); mostrar(box, true); return; }
    ui.hashPrio = r.data.doc_hash;
    $("#btn-cert").disabled = !r.data.sellos.length;
    const [primero, ...resto] = r.data.sellos;
    box.className = `resultado ${primero ? "ok" : ""}`;
    box.replaceChildren(
      h("p", { class: "mono small" }, r.data.doc_hash),
      primero ? h("p", {}, h("strong", { class: "ok-text" }, "Documento sellado.")) : h("p", {}, h("strong", {}, "El documento no está sellado en esta cadena.")),
      primero ? bloqueSello(primero, "Prioridad") : null,
      resto.length ? h("h3", { class: "subhead" }, `Sellos posteriores (${resto.length})`) : null,
      ...resto.map((s) => bloqueSello(s, "Posterior")));
    mostrar(box, true);
  });
  $("#in-prio-hash").addEventListener("input", () => { ui.hashPrio = ""; $("#btn-cert").disabled = !/^[0-9a-fA-F]{64}$/.test($("#in-prio-hash").value.trim()); });
  $("#in-prio-archivo").addEventListener("change", () => { ui.hashPrio = ""; $("#btn-cert").disabled = true; });

  $("#btn-cert").addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    const hash = ui.hashPrio || $("#in-prio-hash").value.trim().toLowerCase();
    if (!/^[0-9a-f]{64}$/.test(hash)) { toast("Consulta primero el documento para conocer su hash.", "error"); return; }
    btn.disabled = true;
    try {
      const r = await fetch(`${API}/certificado/${hash}`);
      if (!r.ok) {
        let d = {}; try { d = await r.json(); } catch { /* sin JSON */ }
        toast(d.error || "No se pudo generar el certificado.", "error");
        return;
      }
      const url = URL.createObjectURL(await r.blob());
      const a = h("a", { href: url, download: `certificado-${hash.slice(0, 8)}.json` });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      toast("Certificado descargado.", "ok");
    } catch { toast("No se pudo contactar con el nodo.", "error"); } finally { btn.disabled = false; }
  });

  $("#form-verificar").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData();
    const cert = $("#in-ver-cert").files[0], doc = $("#in-ver-doc").files[0];
    if (cert) fd.append("certificado", cert);
    if (doc) fd.append("documento", doc);
    const btn = $("#btn-verificar");
    btn.disabled = true;
    const r = await api("/certificado/verificar", { metodo: "POST", form: fd });
    btn.disabled = false;
    const box = $("#ver-resultado"), d = r.data;
    if (!r.ok && d.valido === undefined) { box.className = "resultado bad"; box.replaceChildren(h("p", {}, d.error || "No se pudo verificar.")); mostrar(box, true); return; }
    const res = d.resumen;
    const detalle = typeof d.detalle === "string" ? d.detalle : null;   // si es un objeto, ya lo cubre `resumen`
    box.className = `resultado ${d.valido ? "ok" : "bad"}`;
    box.replaceChildren(
      h("p", {}, h("strong", { class: d.valido ? "ok-text" : "bad-text" }, d.valido ? "Certificado válido" : "Certificado NO válido")),
      h("p", {}, d.motivo),
      detalle ? h("p", { class: "small muted" }, detalle) : null,
      res ? h("dl", { class: "kv" },
        h("dt", {}, "Título"), h("dd", {}, res.titulo ?? "–"), h("dt", {}, "Investigador"), h("dd", {}, res.investigador ?? "–"),
        h("dt", {}, "Laboratorio"), h("dd", {}, res.laboratorio ?? "–"), h("dt", {}, "Autores"), h("dd", {}, (res.autores || []).join(", ") || "–"),
        h("dt", {}, "Bloque"), h("dd", {}, res.bloque ?? "–"), h("dt", {}, "Fecha"), h("dd", {}, res.fecha || "–"),
        h("dt", {}, "Confirmaciones"), h("dd", {}, res.confirmaciones ?? "–")) : null,
      h("p", {}, d.misma_red ? h("span", { class: "chip chip-ok" }, "De esta misma red") : h("span", { class: "chip chip-warn" }, "De otra red (génesis distinto)")));
    mostrar(box, true);
  });

  // ---- ataques
  $("#form-ataque").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = $("#btn-ataque");
    ui.ocupados.add(btn.id); btn.disabled = true;
    const r = await api("/ataques", { metodo: "POST", json: { tipo: $("#in-ataque-tipo").value, destino: $("#in-ataque-destino").value } });
    ui.ocupados.delete(btn.id);
    const box = $("#ataque-resultado"), d = r.data;
    if (!r.ok) { box.className = "resultado bad"; box.replaceChildren(h("p", {}, d.error || "No se pudo ejecutar el ataque.")); mostrar(box, true); toast(d.error || "No se pudo ejecutar el ataque.", "error"); actualizar(); return; }
    box.className = `resultado ${d.rechazado ? "ok" : "bad"}`;
    box.replaceChildren(
      h("p", {}, h("strong", { class: d.rechazado ? "ok-text" : "bad-text" }, d.rechazado ? "Ataque rechazado por la validación" : "El ataque NO fue rechazado")),
      d.mensaje ? h("p", {}, d.mensaje) : null,
      (d.motivos || []).length ? h("ul", {}, d.motivos.map((m) => h("li", {}, m))) : null,
      h("p", { class: "small" }, d.cadena_intacta ? "Tu cadena quedó intacta." : "Atención: la cadena cambió.",
        typeof d.enviados === "number" ? ` Enviado a ${d.enviados} par(es).` : ""));
    mostrar(box, true);
    actualizar();
  });

  $("#filtro-bitacora").addEventListener("change", () => { ui.clavesBitacora = ""; if (ui.est) renderBitacora(ui.est); });

  ciclo();
})();
