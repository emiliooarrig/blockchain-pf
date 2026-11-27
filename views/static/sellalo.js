// Interfaz del nodo Sellalo. Sin dependencias. Todo el contenido que viene del servidor (títulos, investigadores,
// ids de nodos remotos…) se inserta con textContent/createTextNode vía h(); no se usa innerHTML con datos externos.
(() => {
  "use strict";

  const { $, h, corto, fecha, hora, num, lista, mostrar, hashCeros, toast, api, marca, msgRuta, aviso, renderEncabezado: encabezadoComun } = window.Sellalo;

  // ---------------------------------------------------------------- estado de la interfaz
  const ui = { est: null, clavesDif: "", ocupados: new Set(), abiertos: new Set(), detalles: new Map(), hashPrio: "",
               clavesAutores: "", clavesBloques: "", clavesBitacora: "", tiposBitacora: new Set(),
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
    refrescarClave();
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
    encabezadoComun(e);
    $("#enc-red").textContent = e.red.nombre;
    $("#enc-genesis").textContent = corto(e.red.hash_genesis, 12);
    $("#enc-genesis").setAttribute("title", e.red.hash_genesis);
  }

  function renderBanda(e, msgError) {
    const b = $("#banda");
    if (msgError) { b.className = "sync-banner offline"; b.textContent = msgError; mostrar(b, true); return; }
    if (e && bloqueado()) {
      b.className = "sync-banner";
      b.textContent = "El nodo está bloqueado: desbloquéalo en Identidad para firmar, minar y conectarte a la red.";
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

  // ---- dificultad de la red (C9): vigente, estimación de tiempo, propuestas en firma e historial de ajustes
  function duracion(s) {
    if (!isFinite(s)) return "un tiempo enorme";
    if (s < 1) return "menos de 1 s";
    if (s < 90) return `${Math.round(s)} s`;
    if (s < 5400) return `${Math.round(s / 60)} min`;
    if (s < 129600) return `${(s / 3600).toFixed(1).replace(".", ",")} h`;
    return `${num(Math.round(s / 86400))} días`;
  }
  function tiempoEsperado(d, hs) {
    const hashes = 16 ** d;
    const base = `~16^${d} = ${num(hashes)} hashes por bloque`;
    return hs > 0 ? `${base} (≈ ${duracion(hashes / hs)} a ${num(Math.round(hs))} hashes/s)`
      : `${base}; inicia el minado para estimar los segundos con la velocidad de esta PC`;
  }
  function renderDificultad(e) {
    const d = e.dificultad;
    if (!d) return;
    const fija = d.vigente != null;
    mostrar($("#dif-sin-fija"), !fija);
    mostrar($("#dif-contenido"), fija);
    if (!fija) return;
    const hs = Number((e.nodo.estadisticas || {}).hashes_por_s) || 0;
    $("#dif-vigente").textContent = String(d.vigente);
    $("#dif-genesis").textContent = d.genesis !== d.vigente ? `(génesis: ${d.genesis})` : "(la del génesis)";
    $("#dif-tiempo").textContent = `Tiempo esperado por bloque: ${tiempoEsperado(d.vigente, hs)}.`;
    const sel = $("#in-dif-nueva");
    if (!sel.dataset.listo) {
      sel.dataset.listo = "1";
      sel.value = String(Math.min(d.maximo, d.vigente + 1 <= d.maximo ? d.vigente + 1 : d.vigente - 1));
      sel.addEventListener("change", () => renderDificultad(ui.est));
    }
    const nueva = Number(sel.value);
    $("#dif-nueva-tiempo").textContent = nueva === d.vigente ? "Elige una dificultad distinta de la vigente."
      : `Con ${nueva}: ${tiempoEsperado(nueva, hs)}.`;
    $("#dif-ayuda").textContent = `Un ajuste necesita la firma de más de la mitad de los laboratorios (${d.umbral} de ${d.laboratorios.length}); `
      + "una vez firmado se mina como cualquier transacción y rige desde el bloque siguiente.";
    const prop = $("#btn-dif-proponer");
    prop.dataset.motivo = nueva === d.vigente ? "La dificultad elegida ya es la vigente." : "";
    ponerDeshabilitado("btn-dif-proponer", "Desbloquea el nodo para firmar el ajuste.", prop.dataset.motivo);
    const clave = JSON.stringify([d.vigente, d.en_firma, d.ajustes, bloqueado()]);
    if (clave === ui.clavesDif) return;
    ui.clavesDif = clave;
    $("#dif-firma-count").textContent = d.en_firma.length;
    const filas = d.en_firma.map((a) => {
      const partes = [h("span", {}, h("strong", {}, `${d.vigente} → ${a.dificultad}`), h("span", { class: "small muted" }, ` · propone ${a.proponente}`)),
        h("span", { class: "chip" }, `${a.firmas.length}/${a.umbral} firmas`),
        h("span", { class: "small muted" }, `Firmaron: ${a.firmas.join(", ") || "nadie"}`)];
      if (!a.firmado_por_mi) {
        const btn = h("button", { class: "btn btn-small", type: "button" }, "Firmar");
        if (bloqueado()) { btn.disabled = true; btn.title = "Desbloquea el nodo para firmar."; }
        btn.setAttribute("aria-label", `Firmar el ajuste de dificultad ${d.vigente} a ${a.dificultad}`);
        btn.addEventListener("click", () => { btn.disabled = true; enviar(null, `/dificultad/${encodeURIComponent(a.id)}/firmar`, { metodo: "POST", json: {} }); });
        partes.push(btn);
      }
      return h("li", { class: "col" }, partes);
    });
    $("#dif-en-firma").replaceChildren(...(filas.length ? filas : [h("li", { class: "empty" }, "No hay propuestas esperando firmas.")]));
    $("#dif-hist-count").textContent = d.ajustes.length;
    const hist = d.ajustes.slice().reverse().map((a) => h("li", { class: "col" },
      h("span", {}, h("strong", {}, `${a.dificultad_anterior} → ${a.dificultad}`), h("span", { class: "small muted" }, ` · en el bloque #${a.numero}, rige desde el #${a.numero + 1}`)),
      h("span", { class: "small muted" }, `Propuso ${a.proponente} · firmaron ${a.firmantes.join(", ")}`)));
    $("#dif-historial").replaceChildren(...(hist.length ? hist : [h("li", { class: "empty" }, "Todavía no se ha ajustado la dificultad.")]));
  }

  function renderMinado(e) {
    const n = e.nodo, st = n.estadisticas || {};
    $("#pend-count").textContent = n.pendientes.length;
    const pend = n.pendientes.map((p) => (p.tipo === "ajuste_dificultad"
      ? h("li", {}, h("span", {}, h("span", { class: "chip chip-warn" }, "ajuste"), ` dificultad → ${p.dificultad}`), h("span", { class: "small muted" }, `${p.proponente} · ${p.firmas} firmas`))
      : p.tipo === "sello"
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
    if (tx && tx.tipo === "ajuste_dificultad") {
      const firmantes = Object.keys(tx.firmas || {}).sort();
      return h("div", { class: "entry" },
        h("span", { class: "chip chip-warn" }, "ajuste de dificultad"), " ", h("strong", {}, `nueva dificultad ${tx.dificultad}`),
        h("div", {}, `Propuso ${tx.proponente} · firmaron ${firmantes.join(", ")} (${firmantes.length})`),
        h("div", { class: "small muted" }, "Rige desde el bloque siguiente."));
    }
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
  }

  function render(e) {
    renderEncabezado(e); renderBanda(e); renderRed(e); renderFormularios(e); renderFirmas(e);
    renderDificultad(e); renderMinado(e); renderCadena(e); renderCuentas(e); renderBitacora(e); renderBotones(e);
    renderConsistencia(e); renderPersistencia(e); renderConsenso(e);
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
      if (tic % 3 === 0) refrescarClave();
      tic++;
    }
    setTimeout(ciclo, 1000);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) actualizar(); });

  // ---------------------------------------------------------------- formularios
  $("#form-dif").addEventListener("submit", (ev) => {
    ev.preventDefault();
    enviar($("#btn-dif-proponer"), "/dificultad/proponer", { metodo: "POST", json: { dificultad: Number($("#in-dif-nueva").value) } });
  });

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

  $("#filtro-bitacora").addEventListener("change", () => { ui.clavesBitacora = ""; if (ui.est) renderBitacora(ui.est); });

  // ================================================================ Rúbrica en la interfaz
  const sinDato = (v) => v === undefined || v === null;

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

  // ---- R3 · panel de la clave (se consulta en cada ciclo y tras cada acción)
  let claveEnCurso = false;
  async function refrescarClave() {
    if (claveEnCurso) return;
    claveEnCurso = true;
    try { renderClave(await api("/clave")); } finally { claveEnCurso = false; }
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

  function tablaAjuste(a) {
    const firmas = Array.isArray(a.firmas) ? a.firmas : [];
    const validas = firmas.filter((f) => f.firmo && f.valida).length;
    return h("div", { class: "mf-tabla" },
      h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Laboratorio"), h("th", {}, "Firmó"), h("th", {}, "Firma válida"))),
        h("tbody", {}, firmas.map((f) => h("tr", { class: f.firmo && f.valida === false ? "row-bad" : "" },
          h("td", { class: "mono" }, f.autor), h("td", {}, marca(!!f.firmo, "firmó", "no firmó")), h("td", {}, f.firmo ? marca(!!f.valida) : marca(null)))))),
      h("p", { class: "small" }, h("span", { class: `chip ${a.alcanzado ? "chip-ok" : "chip-bad"}` }, `${validas} de ${a.necesarias} necesarias`), a.alcanzado ? " mayoría alcanzada" : " mayoría NO alcanzada",
        h("span", { class: "small muted" }, ` · dificultad ${a.dificultad_anterior ?? "–"} → ${a.dificultad}`))));
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
    for (const t of txs) if (t.ajuste) partes.push(h("div", { class: "mf-bloque" }, h("p", { class: "small" }, h("strong", {}, `Ajuste de dificultad ${corto(t.id, 12)}`, " · mayoría")), tablaAjuste(t.ajuste)));
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
      d.primer_error ? h("span", { class: "small" }, ` · primer error: ${typeof d.primer_error === "string" ? d.primer_error
        : `bloque #${d.primer_error.bloque ?? "?"} (${d.primer_error.comprobacion ?? "?"}): ${d.primer_error.motivo ?? ""}`}`) : null));
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
    renderVerificacion(r, false); refrescarClave();
  });
  $("#form-simular").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = $("#btn-simular"); btn.disabled = true;
    const r = await api("/verificacion/simular", { metodo: "POST", json: { tipo: $("#in-sim-tipo").value, bloque: Number($("#in-sim-bloque").value) } });
    btn.disabled = false;
    renderVerificacion(r, true);
    if (!r.ok) toast(msgRuta(r, "La simulación"), "error");
    refrescarClave();
  });

  // ---------------------------------------------------------------- barra de grupos (pegajosa)
  const enlacesGrupo = [...document.querySelectorAll(".grupos-lista a")];
  const grupoDe = {};
  enlacesGrupo.forEach((a) => a.dataset.secciones.split(" ").forEach((s) => { grupoDe[`seccion-${s}`] = a; }));
  function marcarGrupo(a) {
    enlacesGrupo.forEach((x) => { if (x === a) x.setAttribute("aria-current", "true"); else x.removeAttribute("aria-current"); });
    const sel = $("#ir-a");
    if (sel && a) sel.value = a.getAttribute("href").slice(1);
  }
  if ("IntersectionObserver" in window) {
    const visibles = new Set();
    const obs = new IntersectionObserver((entradas) => {
      entradas.forEach((en) => { if (en.isIntersecting) visibles.add(en.target.id); else visibles.delete(en.target.id); });
      const primera = Object.keys(grupoDe).find((id) => visibles.has(id));     // orden del documento
      if (primera) marcarGrupo(grupoDe[primera]);
    }, { rootMargin: "-90px 0px -55% 0px" });
    Object.keys(grupoDe).forEach((id) => { const s = document.getElementById(id); if (s) obs.observe(s); });
  }
  $("#ir-a").addEventListener("change", (ev) => {
    const s = document.getElementById(ev.currentTarget.value);
    if (s) { s.scrollIntoView({ behavior: "smooth", block: "start" }); history.replaceState(null, "", `#${s.id}`); }
  });

  ciclo();
})();

