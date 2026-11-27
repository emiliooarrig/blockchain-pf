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
    refrescarRubrica();
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
    const difRed = e.nodo.dificultad_red;       // AUD-004: si el génesis fija la dificultad, el minero no la elige
    $("#dif-fija").hidden = difRed == null;
    $("#lbl-dif").hidden = difRed != null;
    if (difRed != null) $("#dif-fija-valor").textContent = String(difRed);
    $("#seccion-ataques").hidden = !e.laboratorio_ataques;     // AUD-017: sólo con --laboratorio-ataques
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
        h("div", { class: "mono small wrap", title: s.doc_hash }, corto(s.doc_hash, 16)), progreso(s), vistaMultifirma(s), h("div", {}, btn));
    });
    $("#solicitudes").replaceChildren(...(sol.length ? sol : [h("li", { class: "empty" }, "Nadie espera tu firma.")]));
    const propios = e.sellos_en_firma.filter((s) => s.laboratorio === e.nodo.id);
    $("#enfirma-count").textContent = propios.length;
    const mios = propios.map((s) => h("li", { class: "col" },
      h("div", {}, h("strong", {}, s.titulo), h("span", { class: "small muted" }, ` · ${s.investigador}`)),
      h("div", { class: "mono small wrap", title: s.doc_hash }, corto(s.doc_hash, 16)), progreso(s), vistaMultifirma(s)));
    $("#enfirma").replaceChildren(...(mios.length ? mios : [h("li", { class: "empty" }, "No tienes sellos esperando firmas.")]));
  }

  function renderMinado(e) {
    const n = e.nodo, st = n.estadisticas || {};
    $("#pend-count").textContent = n.pendientes.length;
    const pend = n.pendientes.map((p) => (p.tipo === "sello"
      ? h("li", {}, h("span", {}, h("span", { class: "chip" }, "sello"), ` ${p.titulo}`), h("span", { class: "small muted" }, `${p.laboratorio} · `), vistaMultifirma(p, true))
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
        h("div", {}, `Laboratorio ${tx.laboratorio}`), vistaMultifirma(tx),
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
    renderRecorrido(e); renderConsistencia(e); renderPersistencia(e); renderConsenso(e);
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
  let tic = 0;
  function ciclo() {
    if (!document.hidden) {
      actualizar();
      if (tic % 3 === 0) refrescarRubrica();
      if (tic % 20 === 0) { cargarEntrega(); }
      tic++;
    }
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
    enviar($("#btn-minar"), "/minar", { metodo: "POST", json: { ...($("#lbl-dif").hidden ? {} : { dificultad: Number($("#in-dif").value) }), continuo: $("#in-continuo").checked } });
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
      vistaMultifirma(s),
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
      pasosCertificado(d.pasos), diagramaMerkle(d.merkle),
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

  // ================================================================ Rúbrica en la interfaz
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
  const sinDato = (v) => v === undefined || v === null;

  // Aviso discreto cuando una ruta nueva responde 404/409/sin conexión.
  function msgRuta(r, que) {
    if (r.status === 404) return `${que}: este nodo aún no ofrece esta información (ruta no disponible).`;
    if (r.status === 409) return (r.data && r.data.error) || `${que}: todavía no hay datos.`;
    if (r.status === 0) return "No se pudo contactar con el nodo.";
    return (r.data && r.data.error) || `${que}: error ${r.status}.`;
  }
  const aviso = (t) => h("p", { class: "aviso", role: "status" }, t);

  // ---- R1 · componente común de multifirma: autores con marca si firmaron y «k de n».
  function vistaMultifirma(s, compacto) {
    if (!s) return null;
    const autores = Array.isArray(s.autores) ? s.autores : lista(s.autores);
    const umbral = s.umbral;
    let firmantes = null, cuantas = null;
    if (Array.isArray(s.firmas) || (s.firmas && typeof s.firmas === "object")) { firmantes = new Set(lista(s.firmas)); cuantas = firmantes.size; }
    else if (typeof s.firmas === "number") cuantas = s.firmas;
    const alcanzado = cuantas !== null && typeof umbral === "number" ? cuantas >= umbral : null;
    const chip = h("span", { class: `chip ${alcanzado ? "chip-ok" : alcanzado === false ? "chip-warn" : ""}`, title: "Firmas recogidas de las necesarias (k de n autores)" },
      cuantas !== null ? `${cuantas} de ${umbral ?? "?"} firmas` : `umbral ${umbral ?? "?"}`, autores.length ? ` · ${autores.length} autores` : "");
    if (compacto || !autores.length) return h("span", { class: "multifirma" }, chip);
    return h("div", { class: "multifirma" }, chip,
      h("ul", { class: "autores-firma", "aria-label": "Autores del sello" },
        autores.map((a) => h("li", {}, firmantes ? marca(firmantes.has(a), "firmó", "no ha firmado") : null, h("span", { class: "mono" }, a)))));
  }

  // ---- Tablero de rúbrica
  let rubricaEnCurso = false, claveEnCurso = false;
  async function refrescarRubrica() {
    if (!rubricaEnCurso) {
      rubricaEnCurso = true;
      try { renderRubrica(await api("/rubrica")); } finally { rubricaEnCurso = false; }
    }
    if (!claveEnCurso) {
      claveEnCurso = true;
      try { renderClave(await api("/clave")); } finally { claveEnCurso = false; }
    }
  }
  const ESTADOS = { demostrado: ["chip-ok", "demostrado"], parcial: ["chip-warn", "parcial"], pendiente: ["chip-pend", "pendiente"] };
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
      return h("article", { class: `crit crit-${String(c.estado).replace(/[^a-z]/g, "")}`, "aria-label": `${c.id} ${c.nombre}` },
        h("header", {}, h("span", { class: "crit-id" }, c.id === "EX" ? "★" : c.id), h("h3", {}, c.nombre),
          h("span", { class: "small muted" }, `${c.puntos ?? "–"} pt`)),
        h("span", { class: `chip ${cls}` }, txt),
        h("ul", { class: "evidencias" }, ev.map((x) => h("li", {}, marca(x.ok, "cumplido", "no cumplido"), h("span", {}, x.texto)))),
        c.seccion ? h("a", { class: "btn btn-ghost btn-small", href: `#${c.seccion}`, "aria-label": `Ver la sección de ${c.id}` }, "Ver") : null);
    }));
  }

  // ---- R7 · recorrido
  function renderRecorrido(e) {
    const ol = $("#recorrido-lista");
    const pasos = Array.isArray(e.recorrido) ? e.recorrido : null;
    if (!pasos) { ol.replaceChildren(h("li", { class: "muted" }, "Este nodo aún no informa el recorrido.")); return; }
    ol.replaceChildren(...pasos.map((p, i) => h("li", { class: `paso ${p.hecho ? "paso-ok" : ""}` },
      h("span", { class: "paso-num", "aria-hidden": "true" }, i + 1),
      h("div", {}, h("strong", {}, p.texto, " ", p.hecho ? h("span", { class: "chip chip-ok" }, marca(true, "hecho"), "hecho") : h("span", { class: "chip chip-pend" }, "pendiente")),
        p.detalle ? h("div", { class: "small muted" }, p.detalle) : null))));
  }

  // ---- R3 · clave
  function renderClave(r) {
    const c = $("#clave-contenido");
    if (!r.ok) { c.replaceChildren(aviso(msgRuta(r, "La protección de la clave"))); return; }
    const d = r.data, k = d.kdf || {}, ci = d.cifrado || {};
    const mem = k.n && k.r ? 128 * k.n * k.r : null;
    const memTxt = mem ? (mem >= 1048576 ? `${(mem / 1048576).toFixed(0)} MiB` : `${(mem / 1024).toFixed(0)} KiB`) : "–";
    const fila = (a, b) => [h("dt", {}, a), h("dd", { class: "mono wrap" }, b)];
    c.replaceChildren(h("dl", { class: "kv kv-plano" },
      fila("Archivo", d.archivo ?? "–"), fila("Formato", `${d.formato ?? "–"} v${d.version ?? "?"}`),
      fila("Derivación", `${k.alg ?? "scrypt"} · N=${k.n ?? "–"}, r=${k.r ?? "–"}, p=${k.p ?? "–"}`),
      fila("Memoria aprox. (128·N·r)", memTxt),
      fila("Cifrado", ci.alg ?? "AES-256-GCM"),
      fila("Sal / nonce / texto cifrado", `${k.bytes_sal ?? "–"} B / ${ci.bytes_nonce ?? "–"} B / ${ci.bytes_texto_cifrado ?? "–"} B`),
      fila("AAD", d.aad ?? "–"),
      h("dt", {}, "Clave privada en claro en disco"), h("dd", {}, h("span", { class: `chip ${d.clave_en_claro_en_disco ? "chip-bad" : "chip-ok"}` }, d.clave_en_claro_en_disco ? "sí" : "no")),
      h("dt", {}, "Estado"), h("dd", {}, h("span", { class: `chip ${d.desbloqueado ? "chip-ok" : "chip-warn"}` }, d.desbloqueado ? "desbloqueada (en memoria)" : "bloqueada")),
      fila("Intentos fallidos", String(d.intentos_fallidos ?? 0)),
      fila("Espera antes de reintentar", `${d.espera_s ?? 0} s`)));
  }

  // ---- R5 · consistencia y persistencia
  function renderConsistencia(e) {
    const c = $("#consistencia"), k = e.consistencia;
    if (!k) { c.replaceChildren(h("p", { class: "muted small" }, "Este nodo aún no informa la consistencia de la red.")); return; }
    const todos = k.con_mi_punta === k.nodos;
    c.className = `consistencia ${todos ? "cons-ok" : "cons-dif"}`;
    c.replaceChildren(h("p", { class: "small muted" }, "R5 · Consistencia de la red"),
      h("p", { class: "cons-grande" }, h("span", { class: "mono" }, `${k.con_mi_punta}/${k.nodos}`), " nodos con la misma punta"),
      h("p", { class: "small" }, todos ? "Todas las réplicas coinciden con mi cadena." : "Hay nodos atrasados o divergentes; se sincronizarán solos."));
  }
  function bytesTxt(b) { return typeof b !== "number" ? "–" : b > 1048576 ? `${(b / 1048576).toFixed(1)} MiB` : b > 1024 ? `${(b / 1024).toFixed(1)} KiB` : `${b} B`; }
  function renderPersistencia(e) {
    const p = e.nodo.persistencia, dl = $("#persistencia");
    if (!p) { dl.replaceChildren(h("dt", {}, "Estado"), h("dd", { class: "muted" }, "Sin información.")); return; }
    dl.replaceChildren(h("dt", {}, "Archivo"), h("dd", { class: "mono wrap" }, p.archivo_cadena || "–"),
      h("dt", {}, "Tamaño"), h("dd", {}, bytesTxt(p.bytes)),
      h("dt", {}, "Última escritura"), h("dd", {}, fecha(p.ultima_escritura)),
      h("dt", {}, "Error"), h("dd", {}, p.error ? h("span", { class: "chip chip-bad" }, p.error) : h("span", { class: "chip chip-ok" }, "ninguno")));
  }

  // ---- R4 · consenso
  function renderConsenso(e) {
    const n = e.nodo, c = n.consenso || {};
    if (c.regla) $("#consenso-regla").textContent = `Regla: ${c.regla}`;
    $("#cons-dif").textContent = sinDato(n.dificultad_red) ? "variable (sin fijar)" : `${n.dificultad_red} ceros hex`;
    const filas = [{ id: `${n.id} (yo)`, t: n.trabajo }, ...(e.pares || []).map((p) => ({ id: p.id, t: p.trabajo }))].filter((x) => typeof x.t === "number");
    const max = Math.max(1, ...filas.map((x) => x.t));
    $("#cons-trabajo").replaceChildren(...(filas.length ? filas.map((x) => {
      const barra = h("div", { class: "barra-rel" }), rel = h("div", { class: "barra" }, barra);
      barra.style.width = `${Math.max(2, Math.round((x.t / max) * 100))}%`;
      return h("div", { class: "barra-fila" }, h("span", { class: "mono small" }, x.id), rel, h("span", { class: "mono small" }, num(x.t)));
    }) : [h("p", { class: "muted small" }, "Sin datos de trabajo acumulado.")]));
    $("#cons-contadores").replaceChildren(h("dt", {}, "Bloques rechazados"), h("dd", { class: "mono" }, num(c.bloques_rechazados)),
      h("dt", {}, "Cadenas rechazadas"), h("dd", { class: "mono" }, num(c.cadenas_rechazadas)));
    const rs = Array.isArray(c.reorganizaciones) ? c.reorganizaciones.slice().reverse() : [];
    $("#reorg-count").textContent = rs.length;
    $("#reorg-lista").replaceChildren(...(rs.length ? rs.map((r) => h("li", { class: "col" },
      h("div", {}, h("strong", {}, `${r.altura_antes} → ${r.altura_despues}`), h("span", { class: "small muted" }, ` · ${hora(r.t)} · de ${r.de ?? "–"}`)),
      h("div", { class: "mono small wrap" }, h("span", { title: r.punta_antes }, corto(r.punta_antes, 8)), " → ", h("span", { title: r.punta_despues }, corto(r.punta_despues, 8))),
      h("div", { class: "small" }, `Bloques descartados: ${r.bloques_descartados ?? 0} · transacciones devueltas a pendientes: ${r.tx_devueltas ?? 0}`)))
      : [h("li", { class: "empty" }, "Sin reorganizaciones: la cadena no ha tenido bifurcaciones.")]));
  }

  // ---- R2 · verificación de integridad
  const TIPOS_SIM = [["transaccion", "Cambiar un dato de una transacción"], ["firma_tx", "Corromper la firma de una transacción"],
    ["hash", "Alterar el hash del bloque"], ["enlace", "Romper el enlace con el bloque anterior"], ["merkle", "Alterar la raíz Merkle"],
    ["firma_minero", "Falsificar la firma del minero"], ["multifirma", "Quitar una firma de un sello"], ["nonce", "Cambiar el nonce (prueba de trabajo)"]];
  const COMP = [["hash", "Hash"], ["enlace", "Enlace"], ["merkle", "Merkle"], ["pow", "PoW"], ["firma_minero", "Firma del minero"], ["transacciones", "Transacciones"]];

  function tablaMultifirma(m) {
    const firmas = Array.isArray(m.firmas) ? m.firmas : [];
    return h("div", { class: "mf-tabla" },
      h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Autor"), h("th", {}, "Firmó"), h("th", {}, "Firma válida"))),
        h("tbody", {}, (m.autores || []).map((a) => {
          const f = firmas.find((x) => x.autor === a) || {};
          return h("tr", { class: f.firmo && f.valida === false ? "row-bad" : "" }, h("td", { class: "mono" }, a), h("td", {}, marca(!!f.firmo, "firmó", "no firmó")), h("td", {}, f.firmo ? marca(!!f.valida) : marca(null)));
        })))),
      h("p", { class: "small" }, h("span", { class: `chip ${m.alcanzado ? "chip-ok" : "chip-bad"}` }, `${firmas.filter((f) => f.firmo && f.valida).length} de ${m.umbral} requeridas`), m.alcanzado ? " umbral alcanzado" : " umbral NO alcanzado"));
  }

  function detalleBloque(b) {
    const txs = Array.isArray(b.transacciones) ? b.transacciones : [];
    const partes = [];
    if ((b.errores || []).length) partes.push(h("ul", { class: "errores" }, b.errores.map((x) => h("li", {}, String(x)))));
    if (!txs.length) partes.push(h("p", { class: "muted small" }, "Sin transacciones."));
    else partes.push(h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", {}, h("tr", {}, h("th", {}, "#"), h("th", {}, "Tipo"), h("th", {}, "Id"), h("th", {}, "Firma"), h("th", {}, "Resultado"))),
      h("tbody", {}, txs.map((t) => h("tr", { class: t.ok === false ? "row-bad" : "" },
        h("td", {}, t.indice), h("td", {}, t.tipo), h("td", { class: "mono", title: t.id }, corto(t.id, 12)), h("td", {}, marca(t.firma)), h("td", {}, marca(t.ok))))))));
    for (const t of txs) if (t.multifirma) partes.push(h("div", { class: "mf-bloque" }, h("p", { class: "small" }, h("strong", {}, `Sello ${corto(t.id, 12)}`, " · multifirma")), tablaMultifirma(t.multifirma)));
    return h("div", { class: "detalle-verif" }, partes);
  }

  function tablaVerificacion(d) {
    const alt = d.alteracion;
    const cuerpos = (d.bloques || []).map((b) => {
      const det = h("tr", { class: "fila-detalle", hidden: true }, h("td", { colspan: 8 }, detalleBloque(b)));
      const btn = h("button", { class: "btn btn-ghost btn-small", type: "button", "aria-expanded": "false", "aria-label": `Detalle del bloque ${b.numero}` }, "Detalle");
      btn.addEventListener("click", () => { const abrir = det.hidden; det.hidden = !abrir; btn.setAttribute("aria-expanded", String(abrir)); btn.textContent = abrir ? "Ocultar" : "Detalle"; });
      const comp = b.comprobaciones || {};
      const tocado = alt && alt.bloque === b.numero;
      return h("tbody", {}, h("tr", { class: b.ok === false ? "row-bad" : "" },
        h("td", {}, h("strong", {}, `#${b.numero}`), " ", h("span", { class: "mono small", title: b.hash }, corto(b.hash, 8)), tocado ? h("span", { class: "chip chip-bad" }, "alterado") : null),
        COMP.map(([k, nombre]) => h("td", { class: comp[k] === false ? "celda-mal" : "" }, marca(comp[k], `${nombre} correcto`, `${nombre} falla`))),
        h("td", {}, btn)), det);
    });
    return h("div", { class: "table-wrap" }, h("table", { class: "table tabla-verif" },
      h("caption", { class: "sr-only" }, "Comprobaciones por bloque"),
      h("thead", {}, h("tr", {}, h("th", {}, "Bloque"), COMP.map(([, n]) => h("th", {}, n)), h("th", {}, h("span", { class: "sr-only" }, "Detalle")))),
      cuerpos));
  }

  function renderVerificacion(r, simulada) {
    const box = $("#verif-resultado"), d = r.data;
    if (!r.ok) { box.replaceChildren(aviso(msgRuta(r, "La verificación"))); return; }
    const partes = [];
    if (simulada || d.copia_alterada) {
      const a = d.alteracion || {};
      partes.push(h("p", { class: "aviso-sim", role: "status" }, h("strong", {}, "Copia alterada: rechazada. Tu cadena real no cambió."),
        a.descripcion ? ` ${a.descripcion}` : "", d.cadena_real_intacta === false ? " Atención: el servidor informa que la cadena cambió." : ""));
    }
    partes.push(h("p", { class: "verif-global" }, h("span", { class: `chip ${d.valida ? "chip-ok" : "chip-bad"}` }, d.valida ? "cadena válida" : "no válida"),
      h("span", { class: "small muted" }, ` ${typeof d.duracion_ms === "number" ? `${d.duracion_ms} ms` : ""} · ${(d.bloques || []).length} bloques`),
      d.primer_error ? h("span", { class: "small" }, ` · primer error: ${typeof d.primer_error === "string" ? d.primer_error : JSON.stringify(d.primer_error)}`) : null));
    partes.push(tablaVerificacion(d));
    box.replaceChildren(...partes);
  }

  // ---- R6 · pasos del certificado y camino Merkle
  function pasosCertificado(pasos) {
    if (!Array.isArray(pasos) || !pasos.length) return null;
    return h("div", {}, h("h3", { class: "subhead" }, "Pasos de la verificación"),
      h("ol", { class: "pasos-cert" }, pasos.map((p) => h("li", {}, marca(p.ok, "correcto", "falló"), h("strong", {}, p.paso), h("span", { class: "small muted" }, ` ${p.detalle || ""}`)))));
  }
  function nodoHash(rol, hash) {
    return h("span", { class: "mk-nodo" }, h("span", { class: "small muted" }, rol), h("span", { class: "mono", title: hash }, corto(hash, 10)));
  }
  function diagramaMerkle(m) {
    if (!m || !m.hoja) return null;
    const camino = Array.isArray(m.camino) ? m.camino : [];
    let actual = m.hoja;
    const filas = camino.map((p, i) => {
      const izq = /^(i|l)/i.test(String(p.lado));
      const par = nodoHash(`hermano (${izq ? "izquierda" : "derecha"})`, p.hash);
      const prev = nodoHash(i === 0 ? "hoja" : "acumulado", actual);
      actual = p.resultado;
      return h("li", { class: "mk-paso" }, h("span", { class: "mk-comb" }, izq ? [par, prev] : [prev, par]),
        h("span", { class: "mk-flecha", "aria-hidden": "true" }, "→"), nodoHash(`paso ${i + 1}`, p.resultado));
    });
    return h("div", { class: "merkle" }, h("h3", { class: "subhead" }, "Camino Merkle: hoja → raíz del bloque"),
      h("ol", { class: "mk" }, camino.length ? filas : [h("li", { class: "small muted" }, "Un solo elemento: la hoja es la raíz.")]),
      h("p", { class: "mk-raiz" }, nodoHash("hoja (hash de la transacción)", m.hoja), h("span", { class: "mk-flecha", "aria-hidden": "true" }, "⇒"),
        nodoHash("raíz del bloque", m.raiz), actual === m.raiz ? marca(true, "coincide con la raíz") : marca(false, "no coincide", "no coincide con la raíz")));
  }

  $("#in-sim-tipo").replaceChildren(...TIPOS_SIM.map(([v, t]) => h("option", { value: v }, t)));
  $("#btn-auditar").addEventListener("click", async (ev) => {
    const btn = ev.currentTarget; btn.disabled = true;
    const r = await api("/verificacion");
    btn.disabled = false;
    renderVerificacion(r, false); refrescarRubrica();
  });
  $("#form-simular").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = $("#btn-simular"); btn.disabled = true;
    const r = await api("/verificacion/simular", { metodo: "POST", json: { tipo: $("#in-sim-tipo").value, bloque: Number($("#in-sim-bloque").value) } });
    btn.disabled = false;
    renderVerificacion(r, true);
    if (!r.ok) toast(msgRuta(r, "La simulación"), "error");
    refrescarRubrica();
  });

  // ---- ★ Auditoría con IA
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
      av.replaceChildren(aviso(r.status === 409 ? "La auditoría aún no está generada: falta docs/auditoria/estado.json (ejecuta scripts/estado_auditoria.py)." : msgRuta(r, "La auditoría")));
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

  // ---- R8 · entrega
  async function cargarEntrega() {
    const r = await api("/entrega"), c = $("#entrega-contenido");
    if (!r.ok) { c.replaceChildren(aviso(msgRuta(r, "La entrega"))); return; }
    const ent = Array.isArray(r.data.entregables) ? r.data.entregables : [];
    c.replaceChildren(h("ul", { class: "entregables" }, ent.map((x) => h("li", {}, marca(x.existe, "existe", "pendiente"),
      h("div", {}, h("strong", {}, x.nombre), " ", h("span", { class: `chip ${x.existe ? "chip-ok" : "chip-pend"}` }, x.existe ? "existe" : "pendiente"),
        h("div", { class: "small muted" }, h("span", { class: "mono" }, x.archivo || ""), x.detalle ? ` · ${x.detalle}` : ""))))));
  }

  cargarAuditoria();
  cargarEntrega();
  ciclo();
})();

