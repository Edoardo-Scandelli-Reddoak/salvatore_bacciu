/* Form prenotazione del pannello: mentre si compilano data, uscita, persone, esclusiva
   e gommone mostra l'occupazione dell'uscita e avvisa subito se il gruppo non entra.
   Il controllo vero resta al salvataggio (PrenotazioneForm.clean). */

// Django mette gli script di Media nell'<head>: si parte quando il form esiste
document.addEventListener("DOMContentLoaded", () => {
  "use strict";

  const campo = (nome) => document.getElementById(`id_${nome}`);
  const persone = campo("persone");
  if (!persone) return;

  const urlVerifica = location.pathname.replace(/(add|\d+\/change)\/?$/, "verifica/");
  const pk = (location.pathname.match(/\/(\d+)\/change\/?$/) || [])[1] || "";

  const box = document.createElement("div");
  box.className = "cb-verifica";
  box.setAttribute("role", "status");
  box.setAttribute("aria-live", "polite");
  box.hidden = true;
  const fieldset = persone.closest("fieldset") || persone.closest("form");
  fieldset.append(box);

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const valori = () => ({
    data: campo("data")?.value || "",
    fascia: campo("fascia")?.value || "",
    persone: persone.value || "",
    esclusiva: campo("esclusiva")?.checked ? "1" : "",
    gommone: campo("gommone")?.value || "",
    pk,
  });

  let ultimo = "";
  let giro = 0;
  async function verifica() {
    const v = valori();
    const chiave = JSON.stringify(v);
    if (chiave === ultimo) return;
    ultimo = chiave;
    if (!v.data || !v.fascia || !v.persone) {
      box.hidden = true;
      return;
    }
    const mio = ++giro;
    let j;
    try {
      const r = await fetch(`${urlVerifica}?${new URLSearchParams(v)}`, { headers: { Accept: "application/json" }, credentials: "same-origin" });
      j = await r.json();
    } catch {
      return;
    }
    if (mio !== giro) return;
    if (!j.completo) {
      box.hidden = true;
      return;
    }
    const barre = j.gommoni
      .map((g) => {
        const perc = Math.min(100, Math.round((g.occupati * 100) / g.capienza));
        return `<div class="cb-verifica-riga"><span>${esc(g.nome)}</span>
          <span class="cb-barra${g.chiuso ? " cb-barra--chiusa" : ""}"><i style="width:${perc}%"></i></span>
          <b>${g.chiuso ? "chiuso" : `${g.occupati}/${g.capienza}`}</b></div>`;
      })
      .join("");
    let esito;
    let tipo;
    const n = `${esc(persone.value)} person${persone.value === "1" ? "a" : "e"}`;
    if (j.ok && j.spostata) {
      tipo = "avviso";
      esito = `<p class="cb-verifica-esito cb-verifica-esito--avviso"><span class="material-symbols-outlined">warning</span>
        Sul gommone di prima ${n} non ci stanno più: salvando passano sul <b>${esc(j.gommone)}</b>.</p>`;
    } else if (j.ok) {
      tipo = "ok";
      esito = `<p class="cb-verifica-esito cb-verifica-esito--ok"><span class="material-symbols-outlined">check_circle</span>
        C'è posto: ${n} sul <b>${esc(j.gommone)}</b>.</p>`;
    } else {
      tipo = "errore";
      esito = `<p class="cb-verifica-esito cb-verifica-esito--errore"><span class="material-symbols-outlined">error</span>${esc(j.errore)} Così non si può salvare.</p>`;
    }
    box.className = `cb-verifica is-${tipo}`;
    box.innerHTML = `<p class="cb-verifica-titolo">Posti per ${esc(j.uscita)}${j.chiusa ? "" : ` · ${j.posti_liberi} liberi, max ${j.max_persone} insieme`}</p>${barre}${esito}`;
    box.hidden = false;
    persone.toggleAttribute("aria-invalid", !j.ok);
  }

  // Eventi + controllo periodico: il selettore data di Unfold non sempre emette "change"
  document.addEventListener("input", verifica);
  document.addEventListener("change", verifica);
  setInterval(verifica, 700);
  verifica();
});
