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
    version: location.hash === "#pos" ? "pos" : "pow",
    estado: null,
    cadenaClave: "",
    nodosFirma: "",
    casosVersion: "",
    validadoresFirma: "",
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
      if (r.consenso === "pow" && r.motor.minando) espera = 250;
      await actualizarCadena(r);
    } else {
      const b = $("#sync-banner");
      b.className = "sync-banner offline";
      b.textContent = r.error;
      espera = 2000;
    }
    ui.timer = setTimeout(actualizar, espera);
  }

  function cambiarVersion(v) {
    ui.version = v;
    history.replaceState(null, "", `#${v}`);
    ui.cadenaClave = ui.nodosFirma = ui.casosVersion = ui.validadoresFirma = "";
    ui.estado = null;
    ui.primeraVez = true;
    $("#cadena").replaceChildren();
    actualizar();
  }

  // ---------------------------------------------------------------- render general
  function render(e) {
    document.querySelectorAll(".tab").forEach((t) => {
      const activo = t.dataset.version === e.consenso;
      t.classList.toggle("is-active", activo);
      t.setAttribute("aria-selected", activo);
    });
    $("#panel-pow").hidden = e.consenso !== "pow";
    $("#panel-pos").hidden = e.consenso !== "pos";
    document.title = `Sellalo · ${e.consenso === "pow" ? "Proof of Work" : "Proof of Stake"}`;

    if (ui.primeraVez !== false) {
      const f = $("#form-red");
      for (const k of ["n", "semilla", "saldo_inicial", "recompensa"]) f.elements[k].value = e.parametros[k];
      f.elements.reproducible.checked = e.parametros.reproducible;
      if (e.consenso === "pos") {
        const c = e.motor.config, fp = $("#form-pos-config");
        for (const k of ["tam_comite", "regla", "alfa_pct", "fraude"]) fp.elements[k].value = c[k];
      }
      ui.primeraVez = false;
    }

    renderResumen(e);
    renderSelects(e);
    renderPendientes(e);
    renderSync(e);
    renderNodos(e);
    if (e.consenso === "pow") renderPow(e);
    else renderPos(e);
    renderCasos(e);
    renderRecompensas(e);
    renderBitacora(e);
  }

  function renderResumen(e) {
    const p = e.parametros;
    const filas = [
      ["Consenso", e.consenso === "pow" ? "Proof of Work" : "Proof of Stake"],
      ["Laboratorios", p.n],
      ["Semilla", `${p.semilla}${p.reproducible ? " · reloj simulado" : ""}`],
      ["Recompensa", e.consenso === "pow" ? `${p.recompensa} créditos (se acreditan tras 6 confirmaciones)` : `${p.recompensa} créditos (se pagan al aceptar el bloque)`],
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
    const pow = e.consenso === "pow";
    const cols = pow
      ? ["Laboratorio", "Altura", "Hash del último bloque", "Sincronía", "Créditos disponibles", "Recompensas pendientes", "Último rechazo"]
      : ["Laboratorio", "Altura", "Hash del último bloque", "Sincronía", "Créditos", "Bloqueado / castigado", "Disponible", "Comportamiento"];
    const head = $("#nodos-head");
    if (head.dataset.version !== e.consenso) {
      head.replaceChildren(...cols.map((c) => h("th", {}, c)));
      head.dataset.version = e.consenso;
    }
    const filas = e.nodos.map((n) => {
      const celdas = [
        h("td", {}, h("strong", {}, n.id)),
        h("td", { class: "mono" }, n.altura),
        h("td", { class: "mono small", title: n.ultimo_hash }, corto(n.ultimo_hash, 14)),
        h("td", {}, h("span", { class: `dot ${n.sincronizado ? "dot-ok" : "dot-bad"}` }), n.sincronizado ? "sí" : "no"),
      ];
      if (pow) {
        celdas.push(
          h("td", { class: "mono" }, fmt(n.disponible)),
          h("td", { class: "mono" }, n.pendiente_recompensa ? h("span", { class: "chip chip-warn" }, `${fmt(n.pendiente_recompensa)} pendiente`) : "—"),
          h("td", { class: "small muted", title: n.ultimo_rechazo }, n.ultimo_rechazo ? n.ultimo_rechazo.slice(0, 70) : "—"));
      } else {
        celdas.push(
          h("td", { class: "mono" }, fmt(n.saldo)),
          h("td", { class: "mono" }, n.retenido ? fmt(n.retenido) : "—"),
          h("td", { class: "mono" }, fmt(n.disponible)),
          h("td", {}, h("button", {
            class: `btn btn-small ${n.deshonesto ? "btn-danger is-on" : "btn-ghost"}`, type: "button",
            title: "Si lo sortean, propone un bloque inválido",
            onclick: (ev) => enviar(`/nodos/${n.id}/deshonesto`, { deshonesto: !n.deshonesto }, ev.currentTarget),
          }, n.deshonesto ? "Deshonesto" : "Honesto")));
      }
      return h("tr", { class: n.sincronizado ? "" : "row-bad" }, ...celdas);
    });
    $("#tabla-nodos tbody").replaceChildren(...filas);
  }

  // ---------------------------------------------------------------- PoW
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

  // ---------------------------------------------------------------- PoS
  function renderPos(e) {
    const m = e.motor, r = m.ronda;
    const etapa = r ? r.estado : "SIN RONDA";
    const badge = $("#pos-badge");
    badge.className = `badge ${r && ["ACEPTADO"].includes(etapa) ? "badge-ok" : r && ["RECHAZADO", "FALLIDA"].includes(etapa) ? "badge-bad" : r && etapa !== "CANCELADA" ? "badge-live" : "badge-idle"}`;
    badge.textContent = r ? `ronda ${r.id} · bloque #${r.numero} · ${etapa}` : "sin ronda";

    const orden = m.estados;
    const idx = r ? orden.indexOf(etapa) : -1;
    $("#pos-stepper").replaceChildren(...orden.map((s, i) => {
      let cls = "";
      if (r && s === etapa) cls = s === "RECHAZADO" ? "is-bad" : s === "ACEPTADO" ? "is-ok" : "is-current";
      else if (r && idx > i && i < 4) cls = "is-done";
      return h("li", { class: cls }, s);
    }));

    const activa = r && ["APUESTAS", "SORTEO", "CANDIDATO", "VOTACION", "RECHAZADO"].includes(etapa);
    const habilitar = {
      "pos-ronda": !activa, "pos-apuestas": etapa === "APUESTAS", "pos-sortear": ["APUESTAS", "SORTEO", "RECHAZADO"].includes(etapa),
      "pos-candidato": etapa === "CANDIDATO", "pos-votacion": etapa === "VOTACION", "pos-cerrar": etapa === "VOTACION",
      "pos-auto": true, "pos-cancelar": activa,
    };
    for (const [k, v] of Object.entries(habilitar)) document.querySelector(`[data-accion="${k}"]`).disabled = !v;

    const msg = $("#pos-mensaje");
    let texto = r ? r.mensaje : "";
    if (!texto) texto = !r ? "Inicia una ronda para elegir el comité de laboratorios validadores." : {
      APUESTAS: "Registra las apuestas (manual en la tabla o automáticas) y luego sortea el proponente.",
      CANDIDATO: `Proponente sorteado: ${r.proponente}. Ahora construye el bloque candidato.`,
      VOTACION: "Los validadores revisan el candidato y votan (manual en la tabla o automática).",
    }[etapa] || "";
    if (m.castigos_pendientes.length) texto += ` · ${m.castigos_pendientes.length} castigo(s) de rondas fallidas por registrar.`;
    msg.textContent = texto;
    msg.className = `race-banner show ${etapa === "ACEPTADO" ? "win" : ["RECHAZADO", "FALLIDA"].includes(etapa) ? "lose" : ""}`;

    const meter = $("#vote-meter");
    if (r && r.votacion.total) {
      const v = r.votacion, pct = (100 * v.a_favor) / v.total;
      meter.replaceChildren(
        h("div", { class: "meter" }, h("span", { class: "meter-fill", style: `width:${pct}%` }), h("span", { class: "meter-mark", title: "2/3" })),
        h("div", { class: "small" }, `A favor V = ${fmt(v.a_favor)} de A = ${fmt(v.total)} (${pct.toFixed(1)}%) · se requiere 3V ≥ 2A (V ≥ ${fmt(v.umbral)}) · ${v.emitidos}/${v.esperados} votos emitidos`));
    } else meter.replaceChildren();

    renderValidadores(r);
    renderCandidato(r);
  }

  function renderValidadores(r) {
    const tbody = $("#tabla-validadores tbody");
    const firma = JSON.stringify(r ? [r.id, r.estado, r.intento, r.validadores] : null);
    if (firma === ui.validadoresFirma || tbody.contains(document.activeElement)) return;
    ui.validadoresFirma = firma;
    if (!r) {
      tbody.replaceChildren(h("tr", {}, h("td", { colspan: 7, class: "muted" }, "Sin ronda en curso.")));
      return;
    }
    tbody.replaceChildren(...r.validadores.map((v) => {
      const acciones = [];
      if (r.estado === "APUESTAS") {
        const input = h("input", { type: "number", min: 1, max: v.disponible + (v.apuesta || 0), placeholder: "monto", class: "input-small", "aria-label": `Apuesta de ${v.id}` });
        acciones.push(input, h("button", { class: "btn btn-small", type: "button", onclick: (ev) => enviar("/pos/apostar", { nodo: v.id, monto: input.value }, ev.currentTarget) }, "Apostar"));
      }
      if (r.estado === "VOTACION" && v.voto === null && ["validador", "proponente"].includes(v.papel)) {
        acciones.push(
          h("button", { class: "btn btn-small", type: "button", onclick: (ev) => enviar("/pos/votar", { nodo: v.id, a_favor: true }, ev.currentTarget) }, "A favor"),
          h("button", { class: "btn btn-small btn-danger", type: "button", onclick: (ev) => enviar("/pos/votar", { nodo: v.id, a_favor: false }, ev.currentTarget) }, "En contra"));
      }
      const voto = v.voto === null ? "—" : h("span", { class: `chip ${v.voto ? "chip-ok" : "chip-bad"}`, title: v.evaluacion || "" }, v.voto ? "a favor" : "en contra");
      return h("tr", { class: `papel-${v.papel.replace(" ", "-")}` },
        h("td", {}, h("strong", {}, v.id)),
        h("td", { class: "mono" }, fmt(v.disponible)),
        h("td", { class: "mono" }, v.apuesta ? fmt(v.apuesta) : "—"),
        h("td", { class: "mono" }, v.probabilidad === null ? "—" : `${v.probabilidad}%`),
        h("td", {}, h("span", { class: `chip chip-${v.papel.replace(" ", "-")}` }, v.papel + (v.castigo ? ` (−${fmt(v.castigo)})` : ""))),
        h("td", {}, voto, v.evaluacion && v.evaluacion !== "válido" ? h("div", { class: "small muted" }, v.evaluacion.slice(0, 80)) : null),
        h("td", { class: "acciones" }, ...acciones));
    }));
  }

  function renderCandidato(r) {
    const cont = $("#pos-candidato");
    const hist = $("#pos-historial");
    if (!r || !r.candidato) cont.replaceChildren();
    else {
      const c = r.candidato;
      cont.replaceChildren(h("div", { class: "candidate" },
        h("h3", {}, `Bloque candidato #${r.numero} · proponente ${r.proponente} · intento ${r.intento}`),
        r.sorteo ? h("p", { class: "small muted" }, `Sorteo: r = ${r.sorteo.r} mod A = ${fmt(r.sorteo.A)} → ${r.proponente} (probabilidad ${r.sorteo.probabilidad}%)`) : null,
        h("p", { class: "small" }, "Hash de la propuesta ", h("span", { class: "mono" }, corto(c.hash_propuesta, 18)), " · firma del proponente ", h("span", { class: "mono" }, corto(c.firma_proponente, 18)), c.castigos ? ` · registra ${c.castigos} castigo(s)` : ""),
        h("ul", { class: "tx-list compact" }, ...c.transacciones.map((tx) => h("li", {}, h("strong", {}, `${tx.emisor} → ${tx.receptor}`), ` · ${fmt(tx.monto)} · `, h("span", { class: "mono small muted" }, `firma ${corto(tx.firma, 12)}`))))));
    }
    if (!r || !r.historial.length) hist.replaceChildren();
    else hist.replaceChildren(h("h3", { class: "subhead" }, "Intentos de esta ronda"), h("ol", { class: "history" },
      ...r.historial.map((x) => h("li", { class: x.resultado === "ACEPTADO" ? "ok" : "bad" },
        h("strong", {}, `Intento ${x.intento} · ${x.proponente}: ${x.resultado}`), x.castigo ? ` · castigo ${fmt(x.castigo)}` : "", h("div", { class: "small" }, x.motivo)))));
  }

  // ---------------------------------------------------------------- cadena
  async function actualizarCadena(e) {
    const sel = $("#cadena-nodo");
    const nodo = sel.value || (e.nodos[0] && e.nodos[0].id);
    const nodoInfo = e.nodos.find((n) => n.id === nodo);
    const clave = `${e.consenso}|${nodo}|${nodoInfo ? nodoInfo.ultimo_hash : ""}|${e.revision}`;
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
    if (!genesis && b.votos) campos.push(...campo("Nonce", "0 (PoS)", "mono"));
    if (!genesis) campos.push(...campo("Recompensa", fmt(b.recompensa), "mono"));
    if (genesis) campos.push(...campo("Laboratorios", `${Object.keys(b.cuentas).length} · ${fmt(Object.values(b.cuentas)[0].saldo)} créditos c/u`));

    const detalles = [];
    if (b.transacciones.length) {
      detalles.push(h("details", { class: "entries" }, h("summary", {}, `${b.transacciones.length} transacción(es) firmada(s)`),
        ...b.transacciones.map((tx) => h("div", { class: "entry" }, h("strong", {}, `${tx.emisor} → ${tx.receptor}`), ` · ${fmt(tx.monto)}`,
          h("div", { class: "mono small muted" }, `firma ${corto(tx.firma, 20)}`)))));
    }
    if (b.votos) {
      const favor = b.votos.filter((v) => v.a_favor).reduce((s, v) => s + v.peso, 0);
      const total = b.validadores.filter((v) => !b.excluidos.includes(v.id)).reduce((s, v) => s + v.apuesta, 0);
      detalles.push(h("details", { class: "entries" }, h("summary", {}, `Votos: ${fmt(favor)} de ${fmt(total)} a favor · intento ${b.intento}`),
        h("div", { class: "small muted" }, `Comité: ${b.validadores.map((v) => `${v.id}(${v.apuesta})`).join(", ")}`),
        b.excluidos.length ? h("div", { class: "small" }, `Excluidos por rechazo: ${b.excluidos.join(", ")}`) : null,
        ...b.votos.map((v) => h("div", { class: "entry small" }, `${v.validador} · peso ${fmt(v.peso)} · `, h("span", { class: v.a_favor ? "ok-text" : "bad-text" }, v.a_favor ? "a favor" : "en contra")))));
      if (b.castigos.length) {
        detalles.push(h("details", { class: "entries" }, h("summary", {}, `${b.castigos.length} castigo(s) registrados`),
          ...b.castigos.map((c) => h("div", { class: "entry small" }, `${c.validador}: −${fmt(c.monto)} (regla ${c.regla}, apuesta ${fmt(c.apuesta)})`, h("div", { class: "muted" }, c.motivo)))));
      }
    }
    return h("article", { class: `block ${genesis ? "block-genesis" : ""}` },
      h("header", { class: "block-head" }, h("h3", {}, genesis ? "Génesis #0" : `Bloque #${b.numero}`)),
      h("dl", { class: "block-fields" }, ...campos),
      h("div", { class: "hash-label" }, "hash_anterior"),
      h("div", { class: "mono hash-box" }, b.hash_anterior),
      h("div", { class: "hash-label" }, "hash (SHA-256)"),
      h("div", { class: "mono hash-box hash-main" }, h("span", { class: "zeros" }, b.hash.slice(0, ceros)), b.hash.slice(ceros)),
      b.firma_proponente ? [h("div", { class: "hash-label" }, "Firma del proponente"), h("div", { class: "mono hash-box" }, corto(b.firma_proponente, 28))] : null,
      ...detalles);
  }

  // ---------------------------------------------------------------- casos, recompensas y bitácora
  function renderCasos(e) {
    if (ui.casosVersion === e.consenso) return;
    ui.casosVersion = e.consenso;
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
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => cambiarVersion(t.dataset.version)));
  window.addEventListener("hashchange", () => {
    const v = location.hash === "#pos" ? "pos" : "pow";
    if (v !== ui.version) cambiarVersion(v);
  });
  $("#cadena-nodo").addEventListener("change", () => { ui.cadenaClave = ""; actualizar(); });

  $("#form-red").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const d = formulario(ev.currentTarget);
    enviar("/simulacion", d, ev.submitter).then((r) => { if (r.ok) { ui.nodosFirma = ui.validadoresFirma = ""; ui.cadenaClave = ""; } });
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
  $("#form-pos-config").addEventListener("submit", (ev) => {
    ev.preventDefault();
    enviar("/pos/config", formulario(ev.currentTarget), ev.submitter);
  });

  const acciones = {
    "tx-aleatoria": () => ["/transacciones/aleatoria", { cantidad: 3 }],
    "minar-10": () => ["/minar", { ...formulario($("#form-minar")), bloques: 10, auto_transacciones: true }],
    "cancelar-minado": () => ["/minar/cancelar", {}],
    "pos-ronda": () => ["/pos/ronda", {}],
    "pos-apuestas": () => ["/pos/apuestas-automaticas", {}],
    "pos-sortear": () => ["/pos/sortear", {}],
    "pos-candidato": () => ["/pos/candidato", {}],
    "pos-votacion": () => ["/pos/votacion-automatica", {}],
    "pos-cerrar": () => ["/pos/cerrar", {}],
    "pos-auto": () => ["/pos/ronda-automatica", {}],
    "pos-cancelar": () => ["/pos/cancelar", {}],
  };
  document.querySelectorAll("[data-accion]").forEach((b) => b.addEventListener("click", (ev) => {
    const [ruta, cuerpo] = acciones[b.dataset.accion]();
    enviar(ruta, cuerpo, ev.currentTarget);
  }));

  ui.primeraVez = true;
  actualizar();
})();
