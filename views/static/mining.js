// Solo presentación: consulta el estado que calcula Python y lo pinta en pantalla.
// Ningún hash, conexión ni lógica de minado se ejecuta en el navegador.
(function () {
  const section = document.getElementById("minado");
  if (!section) return;
  const url = section.dataset.statusUrl;
  const initial = {
    running: section.dataset.running === "true",
    connected: section.dataset.connected === "true",
    identity: section.dataset.identity,
    revision: Number(section.dataset.revision),
  };
  const showingVerify = section.dataset.verify === "true";
  const banner = document.getElementById("race-banner");
  const elapsed = document.getElementById("race-elapsed");
  const btnMine = document.getElementById("btn-mine");
  const btnStop = document.getElementById("btn-stop");
  const latency = document.getElementById("net-latency");
  const events = document.getElementById("net-events");
  const stale = document.getElementById("stale-banner");
  const fmt = (n) => Number(n).toLocaleString("en-US");
  let wasRunning = initial.running;

  document.getElementById("btn-refresh").addEventListener("click", () => window.location.reload());

  // No recargar si el usuario está escribiendo o viendo el resultado de una verificación.
  function userIsBusy() {
    if (showingVerify) return true;
    const active = document.activeElement;
    if (active && ["INPUT", "TEXTAREA"].includes(active.tagName)) return true;
    return [...document.querySelectorAll("#pendientes input, #pendientes textarea, #conexion input[name=ip]")]
      .some((el) => el.value.trim() !== "");
  }

  function refresh(hash) {
    if (userIsBusy()) {
      stale.hidden = false;
      return;
    }
    if (hash) window.location.hash = hash;
    window.location.reload();
  }

  function renderRace(race) {
    elapsed.textContent = race.elapsed;
    race.miners.forEach((m) => {
      const card = document.querySelector(`[data-miner="${m.name}"]`);
      if (!card) return;
      card.className = card.className.replace(/status-\S+/, `status-${m.status}`);
      card.querySelector('[data-field="status"]').textContent = m.status;
      card.querySelector('[data-field="nonce"]').textContent = fmt(m.nonce);
      card.querySelector('[data-field="attempts"]').textContent = fmt(m.attempts);
      card.querySelector('[data-field="hash_rate"]').textContent = fmt(m.hash_rate);
      card.querySelector('[data-field="last_hash"]').textContent = m.last_hash || "—";
    });
    if (race.message) {
      banner.textContent = race.message;
      banner.classList.add("show");
      banner.classList.toggle("win", Boolean(race.winner));
    }
    btnMine.disabled = true;
    btnStop.disabled = !race.running;
  }

  function renderNetwork(net) {
    if (latency && net.latency_ms !== null) latency.textContent = net.latency_ms;
    if (events) {
      events.replaceChildren(...net.events.map((ev) => {
        const li = document.createElement("li");
        const time = document.createElement("span");
        time.className = "mono";
        time.textContent = ev.time;
        li.append(time, " " + ev.text);
        return li;
      }));
    }
  }

  async function poll() {
    let delay = 1000;
    try {
      const res = await fetch(url, { cache: "no-store" });
      const { race, network, revision } = await res.json();
      renderNetwork(network);

      if (network.connected !== initial.connected || (network.identity || "") !== initial.identity) {
        return refresh("#conexion");
      }
      if (race.running) {
        renderRace(race);
        wasRunning = true;
        delay = 200;
      } else if (wasRunning) {
        renderRace(race);
        // Muestra el ganador un momento y recarga para ver el nuevo bloque de la cadena.
        return setTimeout(() => refresh("#minado"), 2000);
      } else if (revision !== initial.revision) {
        return refresh();
      }
    } catch (e) {
      delay = 2000;
    }
    setTimeout(poll, delay);
  }

  poll();
})();
