// Vista Ataques: laboratorio de ataques (R2 verificación, R4 consenso). Sólo textContent/h(); sin innerHTML; historial en memoria.
(() => {
  "use strict";
  const { $, h, corto, hora, mostrar, toast, api, sondearEstado } = window.Sellalo;

  // Qué altera cada ataque (si el servidor no manda descripción).
  const ALTERA = {
    sello_alterado: "Cambia el título de un sello ya minado y rehace raíz, hash y firma: falla la cadena de hashes o la prueba de trabajo.",
    firma_falsa: "Altera la firma de una transferencia: la firma deja de verificar con la clave pública del emisor.",
    merkle_falsa: "Pone una raíz de Merkle que no corresponde a las transacciones del bloque.",
    cadena_corta: "Ofrece una cadena más corta que la honrada: el consenso conserva la más larga.",
    multifirma_incompleta: "Un sello 2-de-2 con una sola firma: no alcanza el umbral de autores.",
    firma_minero_ajena: "Un bloque que dice ser de otro laboratorio pero lo firma este nodo.",
  };
  const st = { claves: "", desbloqueado: false, activo: false, tipo: "", ultimo: null, historial: [] };

  const foto = (e) => ({ altura: e.nodo.altura, punta: e.nodo.punta, sync: `${e.consistencia.con_mi_punta}/${e.consistencia.nodos}` });
  function pintarFoto(pref, f) {
    $(`#${pref}-altura`).textContent = f ? String(f.altura) : "–";
    $(`#${pref}-punta`).textContent = f ? corto(f.punta, 10) : "–";
    $(`#${pref}-punta`).setAttribute("title", f ? f.punta : "");
    $(`#${pref}-sync`).textContent = f ? f.sync : "–";
  }

  function pintarCatalogo(lista) {
    const cont = $("#atq-catalogo");
    cont.replaceChildren(h("legend", {}, "Ataque"), ...lista.map((a, i) => {
      const inp = h("input", { type: "radio", name: "tipo", value: a.id, id: `atq-${a.id}` });
      if (a.id === st.tipo || (!st.tipo && i === 0)) { inp.checked = true; st.tipo = a.id; }
      inp.addEventListener("change", () => { st.tipo = a.id; });
      return h("label", { class: "atq-opcion", for: inp.id }, inp,
        h("span", {}, h("strong", {}, a.id.replace(/_/g, " ")), h("span", { class: "small muted atq-desc" }, a.descripcion || ALTERA[a.id] || a.nombre)));
    }));
  }

  function actualizarBoton() {
    const b = $("#btn-ataque");
    if (b.dataset.ocupado) return;
    b.disabled = !(st.activo && st.desbloqueado);
    b.title = !st.activo ? "El laboratorio está desactivado." : st.desbloqueado ? "" : "Desbloquea el nodo para lanzar ataques (se firman con su clave).";
  }

  function alEstado(r) {
    if (!r.ok) {
      st.activo = false;
      $("#seccion-ataques").hidden = true;
      $("#seccion-historial").hidden = true;
      actualizarBoton();
      return;
    }
    const e = r.data;
    st.activo = !!e.laboratorio_ataques;
    st.desbloqueado = !!e.nodo.desbloqueado;
    $("#atq-desactivado").hidden = st.activo;
    $("#seccion-ataques").hidden = !st.activo;
    $("#seccion-historial").hidden = !st.activo;
    const claves = (e.ataques || []).map((a) => a.id).join(",");
    if (claves !== st.claves) { st.claves = claves; pintarCatalogo(e.ataques || []); }
    st.ultimo = foto(e);
    if (!st.hizoAtaque) pintarFoto("atq-a", st.ultimo);
    actualizarBoton();
  }

  function filaHistorial(x) {
    const si = (b) => h("span", { class: `chip ${b ? "chip-ok" : "chip-bad"}` }, b ? "sí" : "no");
    return h("tr", {}, h("td", { class: "mono" }, hora(x.t)), h("td", {}, x.tipo), h("td", {}, x.destino === "red" ? "red" : "local"),
      h("td", {}, si(x.rechazado)), h("td", { class: "small" }, x.motivo || "–"),
      h("td", {}, typeof x.enviados === "number" ? String(x.enviados) : "–"), h("td", {}, si(x.intacta)));
  }
  function pintarHistorial() {
    $("#atq-historial").replaceChildren(...(st.historial.length ? st.historial.map(filaHistorial)
      : [h("tr", {}, h("td", { colspan: 7, class: "muted" }, "Aún no has lanzado ataques."))]));
  }

  $("#form-ataque").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = $("#btn-ataque"), destino = $("#in-ataque-destino").value, tipo = st.tipo;
    if (!tipo || btn.dataset.ocupado) return;
    btn.dataset.ocupado = "1"; btn.disabled = true;
    const antes = st.ultimo;
    st.hizoAtaque = true;
    pintarFoto("atq-a", antes);
    const r = await api("/ataques", { metodo: "POST", json: { tipo, destino } });
    delete btn.dataset.ocupado;
    const box = $("#ataque-resultado"), d = r.data || {};
    const despues = await api("/estado");
    if (despues.ok) { st.ultimo = foto(despues.data); pintarFoto("atq-d", st.ultimo); }
    actualizarBoton();
    if (!r.ok) {
      const msg = d.error || "No se pudo ejecutar el ataque.";
      box.className = "resultado bad"; box.replaceChildren(h("p", {}, msg)); mostrar(box, true); toast(msg, "error");
      return;
    }
    box.className = `resultado ${d.rechazado ? "ok" : "bad"}`;
    box.replaceChildren(
      h("p", {}, h("strong", { class: d.rechazado ? "ok-text" : "bad-text" }, d.rechazado ? "Ataque rechazado por la validación" : "El ataque NO fue rechazado")),
      d.mensaje ? h("p", {}, d.mensaje) : null,
      (d.motivos || []).length ? h("ul", {}, d.motivos.map((m) => h("li", {}, m))) : null,
      h("p", { class: "small" }, d.cadena_intacta ? "Tu cadena quedó intacta." : "Atención: la cadena cambió.",
        typeof d.enviados === "number" ? ` Enviado a ${d.enviados} par(es).` : ""));
    mostrar(box, true);
    const igual = antes && st.ultimo && antes.altura === st.ultimo.altura && antes.punta === st.ultimo.punta;
    $("#atq-igual").textContent = igual ? "La altura y la punta no cambiaron: la cadena honesta sigue igual."
      : "La cadena cambió entre antes y después (puede ser un bloque minado en paralelo).";
    st.historial.unshift({ t: Date.now() / 1000, tipo, destino, rechazado: !!d.rechazado, motivo: (d.motivos || [])[0] || d.mensaje || "",
      enviados: d.enviados, intacta: !!d.cadena_intacta });
    pintarHistorial();
  });

  sondearEstado(alEstado, 3000);
})();
