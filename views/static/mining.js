// Solo presentación: consulta el estado que calcula Python y lo pinta en pantalla.
// Ningún hash ni lógica de minado se ejecuta en el navegador.
(function () {
  const section = document.getElementById("minado");
  if (!section) return;
  const url = section.dataset.statusUrl;
  const banner = document.getElementById("race-banner");
  const elapsed = document.getElementById("race-elapsed");
  const btnMine = document.getElementById("btn-mine");
  const btnStop = document.getElementById("btn-stop");
  const fmt = (n) => Number(n).toLocaleString("en-US");

  function render(state) {
    elapsed.textContent = state.elapsed;
    state.miners.forEach((m) => {
      const card = document.querySelector(`[data-miner="${m.name}"]`);
      if (!card) return;
      card.className = card.className.replace(/status-\S+/, `status-${m.status}`);
      card.querySelector('[data-field="status"]').textContent = m.status;
      card.querySelector('[data-field="nonce"]').textContent = fmt(m.nonce);
      card.querySelector('[data-field="attempts"]').textContent = fmt(m.attempts);
      card.querySelector('[data-field="hash_rate"]').textContent = fmt(m.hash_rate);
      card.querySelector('[data-field="last_hash"]').textContent = m.last_hash || "—";
    });
    if (state.message) {
      banner.textContent = state.message;
      banner.classList.add("show");
      banner.classList.toggle("win", Boolean(state.winner));
    }
  }

  async function poll() {
    try {
      const res = await fetch(url, { cache: "no-store" });
      const state = await res.json();
      render(state);
      if (state.running) {
        setTimeout(poll, 200);
      } else {
        btnStop.disabled = true;
        // Recarga para mostrar el nuevo bloque que Python agregó a la cadena.
        setTimeout(() => { window.location.href = window.location.pathname + "#cadena"; window.location.reload(); }, 2500);
      }
    } catch (e) {
      setTimeout(poll, 1000);
    }
  }

  if (section.dataset.running === "true") {
    btnMine.disabled = true;
    poll();
  }
})();
