/* Prenotazione online — widget dell'hero, calendario disponibilità, finestra in 3 passi.
   Parla con l'API Django (stessa origine):
     GET  /api/calendario/?mese=AAAA-MM   gruppo massimo per giorno e uscita → giorni pieni barrati
     GET  /api/disponibilita/?data=…      posti delle uscite di un giorno
     POST /api/prenotazioni/              crea la prenotazione (header X-CSRFToken)
   Zero dipendenze. */

(() => {
  "use strict";

  const script = document.currentScript;
  const API = {
    disponibilita: script.dataset.apiDisponibilita,
    calendario: script.dataset.apiCalendario,
    prenota: script.dataset.apiPrenota,
    verifica: script.dataset.apiVerifica,
    esito: script.dataset.apiEsito,
    annulla: script.dataset.apiAnnulla,
    simula: script.dataset.apiSimula,
  };
  const [STAGIONE_INIZIO, STAGIONE_FINE] = script.dataset.stagione.split("|"); // "05-01", "09-30"

  /* --- utilità ---------------------------------------------------------- */
  const pad = (n) => String(n).padStart(2, "0");
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const daIso = (s) => {
    const [a, m, g] = s.split("-").map(Number);
    return new Date(a, m - 1, g);
  };
  const chiaveMese = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
  const dataLunga = (d) =>
    d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const dataBreve = (d) =>
    d.toLocaleDateString("it-IT", { weekday: "short", day: "numeric", month: "long", year: "numeric" });
  const euro = (n) =>
    new Intl.NumberFormat("it-IT", {
      style: "currency", currency: "EUR", maximumFractionDigits: Number.isInteger(n) ? 0 : 2,
    }).format(n);
  const persone = (n) => `${n} person${n === 1 ? "a" : "e"}`;
  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const cookie = (nome) => {
    const m = document.cookie.match(new RegExp(`(?:^|; )${nome}=([^;]*)`));
    return m ? decodeURIComponent(m[1]) : "";
  };

  // Primo e ultimo giorno prenotabile: da oggi (o dall'inizio stagione) a fine stagione
  const limiti = (() => {
    const oggi = new Date();
    oggi.setHours(0, 0, 0, 0);
    const [mi, gi] = STAGIONE_INIZIO.split("-").map(Number);
    const [mf, gf] = STAGIONE_FINE.split("-").map(Number);
    let anno = oggi.getFullYear();
    if (oggi > new Date(anno, mf - 1, gf)) anno += 1;
    const inizio = new Date(anno, mi - 1, gi);
    return { min: oggi > inizio ? oggi : inizio, max: new Date(anno, mf - 1, gf) };
  })();

  /* --- disponibilità del mese (con cache) ------------------------------- */
  const mesi = new Map(); // "AAAA-MM" → Promise<{ "AAAA-MM-GG": {mattino: max, pomeriggio: max} } | null>
  const caricaMese = (d) => {
    const k = chiaveMese(d);
    if (!mesi.has(k)) {
      mesi.set(
        k,
        fetch(`${API.calendario}?mese=${k}`, { headers: { Accept: "application/json" } })
          .then((r) => (r.ok ? r.json() : Promise.reject(r)))
          .then((j) => j.giorni)
          .catch(() => {
            mesi.delete(k); // si riprova al prossimo giro; intanto nessun giorno viene bloccato
            return null;
          })
      );
    }
    return mesi.get(k);
  };

  /* --- calendario riutilizzabile ---------------------------------------- */
  // root = [data-calendario]. Con un .campo__valore è un menu a comparsa, altrimenti è sempre aperto.
  // `ammesso(datiGiorno)` dice se un giorno va bene per la ricerca corrente (es. posti per 4 persone).
  class Calendario {
    constructor(root, { ammesso, alCambio }) {
      this.root = root;
      this.ammesso = ammesso;
      this.alCambio = alCambio || (() => {});
      this.input = root.querySelector('input[type="hidden"]');
      this.valore = root.querySelector(".campo__valore");
      this.pannello = this.valore ? root.querySelector(".calendario") : root;
      this.griglia = root.querySelector("[data-cal-griglia]");
      this.etichettaMese = root.querySelector("[data-cal-mese]");
      this.prec = root.querySelector("[data-cal-prec]");
      this.succ = root.querySelector("[data-cal-succ]");
      this.scelta = null;
      this.toccato = false; // l'utente ha scelto a mano: non spostiamo più la data da soli
      this.mese = new Date(limiti.min.getFullYear(), limiti.min.getMonth(), 1);
      this.dati = null;
      this.giro = 0;

      this.prec.addEventListener("click", () => this.vaiMese(-1));
      this.succ.addEventListener("click", () => this.vaiMese(1));
      this.griglia.addEventListener("click", (e) => {
        const b = e.target.closest("button");
        if (!b || b.disabled) return;
        this.toccato = true;
        this.imposta(daIso(b.dataset.iso));
        if (this.valore) this.chiudi(true);
      });
      this.griglia.addEventListener("keydown", (e) => this.tastiera(e));

      if (this.valore) {
        this.valore.addEventListener("click", () => (this.pannello.hidden ? this.apri() : this.chiudi(false)));
        this.pannello.addEventListener("keydown", (e) => {
          if (e.key === "Escape") {
            e.stopPropagation();
            this.chiudi(true);
          }
        });
        document.addEventListener("click", (e) => {
          if (!this.root.contains(e.target)) this.chiudi(false);
        });
      }
    }

    get data() {
      return this.scelta;
    }

    imposta(d, { silenzioso = false } = {}) {
      this.scelta = d;
      this.input.value = d ? iso(d) : "";
      if (this.valore) this.valore.textContent = d ? dataBreve(d) : "Scegli la data";
      if (d) this.mese = new Date(d.getFullYear(), d.getMonth(), 1);
      this.disegna();
      if (!silenzioso) this.alCambio(d);
    }

    // Giorno selezionabile? undefined = dati del mese non ancora arrivati
    statoGiorno(d) {
      if (d < limiti.min || d > limiti.max) return "fuori";
      if (!this.dati) return "ok";
      const g = this.dati[iso(d)];
      if (!g) return "fuori";
      return this.ammesso(g) ? "ok" : "pieno";
    }

    async disegna() {
      const giro = ++this.giro;
      const a = this.mese.getFullYear();
      const m = this.mese.getMonth();
      this.etichettaMese.textContent = this.mese.toLocaleDateString("it-IT", { month: "long", year: "numeric" });
      this.prec.disabled = new Date(a, m, 1) <= new Date(limiti.min.getFullYear(), limiti.min.getMonth(), 1);
      this.succ.disabled = new Date(a, m + 1, 1) > limiti.max;

      this.dati = null;
      this.renderGriglia();
      const dati = await caricaMese(this.mese);
      if (giro !== this.giro) return; // nel frattempo si è cambiato mese
      this.dati = dati;
      this.renderGriglia();
    }

    renderGriglia() {
      const a = this.mese.getFullYear();
      const m = this.mese.getMonth();
      const focus = this.griglia.contains(document.activeElement) ? document.activeElement.dataset.iso : null;
      this.griglia.innerHTML = "";
      this.griglia.setAttribute("aria-busy", String(!this.dati));
      const vuoti = (new Date(a, m, 1).getDay() + 6) % 7; // settimana da lunedì
      for (let i = 0; i < vuoti; i++) this.griglia.append(document.createElement("span"));
      const scelto = this.scelta ? iso(this.scelta) : null;
      let tabbabile = null;
      for (let g = 1; g <= new Date(a, m + 1, 0).getDate(); g++) {
        const d = new Date(a, m, g);
        const stato = this.statoGiorno(d);
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = g;
        b.dataset.iso = iso(d);
        b.disabled = stato !== "ok";
        if (stato === "pieno") b.classList.add("is-pieno");
        b.setAttribute("aria-pressed", String(iso(d) === scelto));
        b.setAttribute(
          "aria-label",
          d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" }) +
            (stato === "pieno" ? " — nessun posto per il gruppo" : "")
        );
        b.tabIndex = -1;
        if (iso(d) === scelto && !b.disabled) tabbabile = b;
        this.griglia.append(b);
      }
      (tabbabile || this.griglia.querySelector("button:not(:disabled)"))?.setAttribute("tabindex", "0");
      // preventScroll: il ridisegno non deve interrompere uno scorrimento in corso
      if (focus) this.griglia.querySelector(`[data-iso="${focus}"]`)?.focus({ preventScroll: true });
    }

    vaiMese(delta) {
      this.mese = new Date(this.mese.getFullYear(), this.mese.getMonth() + delta, 1);
      this.disegna();
    }

    tastiera(e) {
      const passi = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
      const attivo = e.target.closest("button[data-iso]");
      if (!passi || !attivo) return;
      e.preventDefault();
      const d = daIso(attivo.dataset.iso);
      d.setDate(d.getDate() + passi);
      if (d < limiti.min || d > limiti.max) return;
      const vai = () => {
        const b = this.griglia.querySelector(`[data-iso="${iso(d)}"]`);
        if (!b) return;
        this.griglia.querySelectorAll("button").forEach((x) => (x.tabIndex = -1));
        b.tabIndex = 0;
        b.focus();
      };
      if (d.getMonth() !== this.mese.getMonth()) {
        this.mese = new Date(d.getFullYear(), d.getMonth(), 1);
        this.disegna(); // la griglia è subito disegnata; il focus resta al nuovo arrivo dei dati
      }
      vai();
    }

    apri() {
      this.mese = new Date((this.scelta || limiti.min).getFullYear(), (this.scelta || limiti.min).getMonth(), 1);
      this.pannello.hidden = false;
      this.valore.setAttribute("aria-expanded", "true");
      this.disegna().then(() => this.griglia.querySelector('[tabindex="0"]')?.focus());
    }

    chiudi(rifocalizza) {
      if (!this.valore || this.pannello.hidden) return;
      this.pannello.hidden = true;
      this.valore.setAttribute("aria-expanded", "false");
      if (rifocalizza) this.valore.focus();
    }

    // Primo giorno libero per la ricerca corrente a partire da `da` (scorre i mesi fino a fine stagione)
    async primoLibero(da = limiti.min) {
      let d = da < limiti.min ? limiti.min : da;
      while (d <= limiti.max) {
        const dati = await caricaMese(d);
        if (!dati) return null;
        const fine = new Date(d.getFullYear(), d.getMonth() + 1, 0);
        for (; d <= fine && d <= limiti.max; d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1)) {
          const g = dati[iso(d)];
          if (g && this.ammesso(g)) return d;
        }
      }
      return null;
    }

    // Finché l'utente non sceglie a mano, la data proposta è il primo giorno con posto per la ricerca
    async riallinea() {
      if (this.toccato && this.scelta) return this.disegna();
      const d = await this.primoLibero();
      if (d) this.imposta(d, { silenzioso: true });
      else this.disegna();
    }
  }

  /* --- widget dell'hero ------------------------------------------------- */
  const form = document.getElementById("formPrenota");
  const selUscita = document.getElementById("f-esc");
  const selPax = document.getElementById("f-pax");
  const btnCerca = form.querySelector('button[type="submit"]');
  const esito = document.getElementById("prenotaEsito");
  const nomeUscita = (codice) => selUscita.querySelector(`option[value="${codice}"]`)?.textContent.split(" · ")[0] || codice;

  const calHero = new Calendario(form.querySelector("[data-calendario]"), {
    ammesso: (g) => (g[selUscita.value] ?? 0) >= Number(selPax.value),
    alCambio: () => (esito.hidden = true),
  });
  calHero.imposta(limiti.min, { silenzioso: true });
  calHero.riallinea();
  const cambioRicerca = () => {
    esito.hidden = true;
    calHero.riallinea();
  };
  selUscita.addEventListener("change", cambioRicerca);
  selPax.addEventListener("change", cambioRicerca);

  // "Vedi disponibilità": controlla SOLO l'uscita scelta. Se c'è posto si va dritti ai dati.
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = calHero.data;
    const n = Number(selPax.value);
    const codice = selUscita.value;
    if (!data) {
      calHero.apri();
      return;
    }
    btnCerca.disabled = true;
    const testo = btnCerca.textContent;
    btnCerca.textContent = "Verifico…";
    esito.hidden = true;
    try {
      const r = await fetch(`${API.disponibilita}?data=${iso(data)}`, { headers: { Accept: "application/json" } });
      if (!r.ok) throw r;
      const j = await r.json();
      const u = j.uscite.find((x) => x.uscita === codice);
      if (u && u.prenotabile && u.max_persone >= n) {
        finestra.apri(u, data, n);
      } else {
        mostraEsito(u, j, data, n, codice);
      }
    } catch {
      esitoMsg("Non riusciamo a verificare i posti in questo momento. Controlla la connessione e riprova.", "errore");
    } finally {
      btnCerca.disabled = false;
      btnCerca.textContent = testo;
    }
  });

  function esitoMsg(html, tipo = "avviso") {
    esito.className = `prenota__esito prenota__esito--${tipo}`;
    esito.innerHTML = html;
    esito.hidden = false;
  }

  // Solo quando l'uscita scelta non ha posto: il motivo e al massimo due alternative concrete
  async function mostraEsito(u, giorno, data, n, codice) {
    const quando = `${nomeUscita(codice).toLowerCase()} di ${esc(dataBreve(data))}`;
    let motivo;
    if (!giorno.prenotabile) motivo = esc(giorno.motivo);
    else if (!u || !u.prenotabile) motivo = `Per il ${quando}: ${esc(u ? u.motivo : "uscita non disponibile.")}`;
    else motivo = `Per il ${quando} c'è posto per al massimo ${persone(u.max_persone)} insieme, non per ${n}.`;

    const alternative = [];
    const altra = (giorno.uscite || []).find((x) => x.uscita !== codice && x.prenotabile && x.max_persone >= n);
    if (altra) {
      alternative.push(
        `<button type="button" class="prenota__alt" data-alt-uscita="${esc(altra.uscita)}">${esc(altra.nome)} dello stesso giorno · ${esc(altra.orario)}</button>`
      );
    }
    const prossimo = await calHero.primoLibero(new Date(data.getFullYear(), data.getMonth(), data.getDate() + 1));
    if (prossimo) {
      alternative.push(
        `<button type="button" class="prenota__alt" data-alt-data="${iso(prossimo)}">${esc(nomeUscita(codice))} di ${esc(dataBreve(prossimo))}</button>`
      );
    }
    esitoMsg(
      `<p>${motivo}</p>` +
        (alternative.length
          ? `<p class="prenota__alt-titolo">Disponibile invece:</p><div class="prenota__alt-lista">${alternative.join("")}</div>`
          : "<p>Scrivici su WhatsApp: vediamo insieme cosa si può fare.</p>")
    );
    mesi.clear(); // i dati del calendario potevano essere vecchi
    calHero.disegna();
  }

  esito.addEventListener("click", (e) => {
    const b = e.target.closest(".prenota__alt");
    if (!b) return;
    if (b.dataset.altUscita) selUscita.value = b.dataset.altUscita;
    if (b.dataset.altData) {
      calHero.toccato = true;
      calHero.imposta(daIso(b.dataset.altData), { silenzioso: true });
    }
    esito.hidden = true;
    form.requestSubmit();
  });

  /* --- pulsanti "Prenota" della pagina ---------------------------------- */
  // Portano al widget: data-prenota="mattino" imposta l'uscita, poi si apre il calendario
  document.querySelectorAll("[data-prenota]").forEach((a) =>
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const menu = document.getElementById("menuMobile");
      if (menu?.classList.contains("is-on")) document.getElementById("burger").click();
      if (a.dataset.prenota && selUscita.querySelector(`option[value="${a.dataset.prenota}"]`)) {
        selUscita.value = a.dataset.prenota;
        cambioRicerca();
      }
      form.closest(".prenota").scrollIntoView({ behavior: "smooth", block: "end" });
      // il calendario si apre a scorrimento finito, così resta in vista
      setTimeout(() => calHero.apri(), 650);
    })
  );

  /* --- finestra: dati, pagamento dell'acconto, conferma ---------------- */
  const dlg = document.getElementById("prenotazione");
  const el = (id) => document.getElementById(id);
  const ui = {
    titolo: el("prenTitolo"),
    passi: dlg.querySelectorAll("[data-passo]"),
    indicatori: dlg.querySelectorAll("[data-passo-ind]"),
    riepilogo: el("prenRiepilogo"),
    form: el("prenForm"),
    msg: el("prenMsg"),
    conferma: el("prenConferma"),
    acconto: el("prenAcconto"),
    saldoNota: el("prenSaldoNota"),
    timer: el("prenTimer"),
    stripe: el("prenStripe"),
    simulato: el("prenSimulato"),
    simula: el("prenSimula"),
    msgPaga: el("prenMsgPaga"),
    annullaPaga: el("prenAnnullaPaga"),
    codice: el("prenCodice"),
    riepilogoFine: el("prenRiepilogoFine"),
  };
  const TITOLI = { 2: "I tuoi dati", 3: "Paga l'acconto", 4: "Ci vediamo in spiaggia!" };
  const postJson = (url, corpo) =>
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": cookie("csrftoken") },
      credentials: "same-origin",
      body: JSON.stringify(corpo),
      keepalive: true,
    });

  // Stripe.js si carica solo quando serve, sempre da js.stripe.com (requisito PCI)
  let stripeJs = null;
  const caricaStripe = () =>
    (stripeJs ||= new Promise((ok, ko) => {
      const s = document.createElement("script");
      s.src = "https://js.stripe.com/endive/stripe.js";
      s.onload = ok;
      s.onerror = () => {
        stripeJs = null;
        ko(new Error("Stripe.js non caricato"));
      };
      document.head.append(s);
    }));

  const finestra = {
    passo: 2,
    scelta: null, // { u (uscita dall'API), data, persone }
    pagamento: null, // risposta di /api/prenotazioni/: token, scadenza, modo…
    checkout: null, // istanza Stripe incorporata
    orologio: null,

    apri(u, data, n) {
      this.scelta = { u, data, persone: n };
      ui.riepilogo.innerHTML = this.riepilogoHtml(u, data, n, { conPosti: true });
      ui.msg.hidden = true;
      ui.conferma.textContent = this.testoConferma();
      this.vai(2);
      if (!dlg.open) dlg.showModal();
      document.body.style.overflow = "hidden";
      setTimeout(() => el("p-nome").focus(), 60);
    },

    vai(n) {
      this.passo = n;
      ui.passi.forEach((s) => (s.hidden = Number(s.dataset.passo) !== n));
      ui.indicatori.forEach((li) => {
        const k = Number(li.dataset.passoInd);
        if (k === n) li.setAttribute("aria-current", "step");
        else li.removeAttribute("aria-current");
        li.classList.toggle("is-fatto", k < n);
      });
      ui.titolo.textContent = TITOLI[n];
      dlg.querySelector(".pren__box").scrollTop = 0;
    },

    riepilogoHtml(u, d, n, { conPosti = false, pagato = null } = {}) {
      const prezzo = Number(u.prezzo_persona);
      const totale = prezzo * n;
      const acconto = Number(u.acconto_persona) * n;
      const versato = pagato ?? acconto;
      return `
        <div><span>Data</span><b>${esc(dataLunga(d))}</b></div>
        <div><span>Uscita</span><b>${esc(u.nome)} · partenza ${esc(u.orario)}${u.durata_ore ? ` · ${u.durata_ore} ore` : ""}</b></div>
        <div><span>Persone</span><b>${n}</b></div>
        <div><span>Totale</span><b>${euro(totale)}</b><small>${euro(prezzo)} × ${n}</small></div>
        <div><span>${pagato === null ? "Acconto online" : "Acconto pagato"}</span><b>${euro(versato)}</b><small>${euro(Number(u.acconto_persona))} × ${n}</small></div>
        <div><span>Saldo all'imbarco</span><b>${euro(Math.max(totale - versato, 0))}</b></div>
        ${conPosti ? `<p class="pren__posti">${u.posti_liberi <= 5 ? `Ultimi ${u.posti_liberi} posti` : "Posti disponibili"} per questa uscita</p>` : ""}`;
    },

    messaggio(nodo, testo, html = false) {
      nodo.className = `pren__messaggio pren__messaggio--errore${nodo === ui.msg ? " pren__campo--largo" : ""}`;
      if (html) nodo.innerHTML = testo;
      else nodo.textContent = testo;
      nodo.hidden = false;
    },

    errori() {
      const f = ui.form;
      const campi = [
        [f.nome, (v) => v.trim().length >= 2, "Scrivi nome e cognome."],
        [f.telefono, (v) => (v.match(/\d/g) || []).length >= 6, "Serve un numero di telefono valido: ci serve per contattarti in caso di meteo."],
        [f.email, (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim()), "L'indirizzo email non sembra corretto."],
        [f.privacy, () => f.privacy.checked, "Per prenotare serve il consenso al trattamento dei dati."],
      ];
      campi.forEach(([c]) => c.removeAttribute("aria-invalid"));
      const sbagliato = campi.find(([c, ok]) => !ok(c.type === "checkbox" ? "" : c.value));
      if (!sbagliato) return null;
      sbagliato[0].setAttribute("aria-invalid", "true");
      sbagliato[0].focus();
      return sbagliato[2];
    },

    // Passo 2 → blocca i posti e avvia il pagamento
    async invia() {
      const errore = this.errori();
      if (errore) return this.messaggio(ui.msg, errore);
      const f = ui.form;
      const { u, data, persone: n } = this.scelta;
      ui.conferma.disabled = true;
      ui.conferma.textContent = "Blocco i posti…";
      ui.msg.hidden = true;
      try {
        const r = await postJson(API.prenota, {
          data: iso(data),
          uscita: u.uscita,
          persone: n,
          nome: f.nome.value.trim(),
          telefono: f.telefono.value.trim(),
          email: f.email.value.trim(),
          note: f.note.value.trim(),
          sito_web: f.sito_web.value,
          privacy: f.privacy.checked,
        });
        const j = await r.json().catch(() => ({}));
        mesi.clear(); // i posti sono cambiati: il calendario va ricaricato
        if (r.status === 201) {
          this.pagamento = j.pagamento;
          await this.passoPagamento();
        } else if (r.status === 409) {
          this.messaggio(
            ui.msg,
            `Nel frattempo i posti sono cambiati: ${esc(j.errore || "l'uscita è al completo.")} ` +
              '<button type="button" class="pren__link" data-pren-modifica>Scegli un\'altra data o uscita</button>',
            true
          );
        } else if (r.status === 403) {
          this.messaggio(ui.msg, "La sessione è scaduta. Ricarica la pagina e riprova.");
        } else {
          const campo = j.campo && f.elements[j.campo];
          if (campo) {
            campo.setAttribute("aria-invalid", "true");
            campo.focus();
          }
          this.messaggio(ui.msg, j.errore || "Qualcosa non è andato. Riprova tra poco.");
        }
      } catch {
        this.messaggio(ui.msg, "Connessione non riuscita: la prenotazione non è partita. Riprova.");
      } finally {
        ui.conferma.disabled = false;
        ui.conferma.textContent = this.testoConferma();
      }
    },

    testoConferma() {
      if (!this.scelta) return "Continua al pagamento";
      return `Continua al pagamento · ${euro(Number(this.scelta.u.acconto_persona) * this.scelta.persone)}`;
    },

    async passoPagamento() {
      const { u, persone: n } = this.scelta;
      const acconto = Number(this.pagamento.acconto);
      ui.acconto.textContent = euro(acconto);
      ui.saldoNota.textContent = `Il resto, ${euro(Math.max(Number(u.prezzo_persona) * n - acconto, 0))}, lo paghi all'imbarco.`;
      ui.msgPaga.hidden = true;
      ui.stripe.innerHTML = "";
      ui.simulato.hidden = true;
      this.vai(3);
      // il server tiene i posti un minuto in più (margine richiesto da Stripe): al cliente si mostra il tempo sicuro
      this.avviaTimer(new Date(new Date(this.pagamento.scade_il).getTime() - 60000));

      if (this.pagamento.modo === "simulato") {
        ui.simula.textContent = `Simula pagamento riuscito · ${euro(acconto)}`;
        ui.simulato.hidden = false;
        return;
      }
      ui.stripe.innerHTML = '<div class="pren__carico"></div>';
      try {
        await caricaStripe();
        const stripe = window.Stripe(this.pagamento.chiave_pubblica);
        const segreto = this.pagamento.client_secret;
        this.checkout = await stripe.createEmbeddedCheckoutPage({
          fetchClientSecret: async () => segreto,
          onComplete: () => this.verifica(),
        });
        ui.stripe.innerHTML = "";
        this.checkout.mount(ui.stripe);
      } catch {
        ui.stripe.innerHTML = "";
        this.messaggio(ui.msgPaga, "Il modulo di pagamento non si è caricato. Controlla la connessione e riprova, oppure scrivici.");
      }
    },

    avviaTimer(scadenza) {
      clearInterval(this.orologio);
      const tick = () => {
        const resto = Math.max(0, scadenza - Date.now());
        const m = Math.floor(resto / 60000);
        const s = Math.floor((resto % 60000) / 1000);
        ui.timer.innerHTML = `Posti bloccati per te ancora <b>${m}:${pad(s)}</b>`;
        if (resto <= 0) {
          clearInterval(this.orologio);
          this.chiudiCheckout();
          this.pagamento = null;
          ui.simulato.hidden = true;
          ui.timer.textContent = "";
          this.messaggio(
            ui.msgPaga,
            'Il tempo per pagare è scaduto e i posti sono stati liberati. <button type="button" class="pren__link" data-pren-riprova>Riprova</button>',
            true
          );
        }
      };
      tick();
      this.orologio = setInterval(tick, 1000);
    },

    chiudiCheckout() {
      try {
        this.checkout?.destroy?.();
      } catch {
        /* già smontato */
      }
      this.checkout = null;
    },

    // A pagamento finito chiede l'esito al server (che a sua volta chiede a Stripe)
    async verifica(tentativo = 0) {
      if (!this.pagamento) return;
      try {
        const r = await postJson(API.verifica, { token: this.pagamento.token });
        const j = await r.json();
        if (j.stato === "confermata") return this.fatto(j);
        if (j.stato === "rimborsato") return this.messaggio(ui.msgPaga, j.messaggio);
      } catch {
        /* si riprova */
      }
      if (tentativo < 8) setTimeout(() => this.verifica(tentativo + 1), 1500);
      else this.messaggio(ui.msgPaga, "Il pagamento è stato ricevuto ma la conferma tarda ad arrivare. Ti scriveremo noi; se hai dubbi contattaci su WhatsApp.");
    },

    async simula() {
      ui.simula.disabled = true;
      try {
        const r = await postJson(API.simula, { token: this.pagamento.token });
        const j = await r.json();
        if (j.stato === "confermata") this.fatto(j);
        else this.messaggio(ui.msgPaga, j.messaggio || "Simulazione non riuscita.");
      } finally {
        ui.simula.disabled = false;
      }
    },

    // Il cliente rinuncia (pulsante o chiusura della finestra): i posti si liberano subito
    rinuncia() {
      clearInterval(this.orologio);
      this.chiudiCheckout();
      if (this.pagamento) postJson(API.annulla, { token: this.pagamento.token }).catch(() => {});
      this.pagamento = null;
      mesi.clear();
      calHero.disegna();
    },

    fatto(j) {
      clearInterval(this.orologio);
      this.chiudiCheckout();
      this.pagamento = null;
      const base = this.scelta?.u || {};
      const u = {
        ...base,
        nome: j.nome_uscita,
        orario: j.orario,
        durata_ore: j.durata_ore,
        prezzo_persona: Number(j.importo) / j.persone,
        acconto_persona: Number(j.acconto) / j.persone,
      };
      ui.codice.textContent = j.codice;
      ui.riepilogoFine.innerHTML = this.riepilogoHtml(u, daIso(j.data), j.persone, { pagato: Number(j.pagato) });
      this.vai(4);
      mesi.clear();
      calHero.disegna();
      if (!dlg.open) dlg.showModal();
    },
  };

  ui.form.addEventListener("submit", (e) => {
    e.preventDefault();
    finestra.invia();
  });
  ui.form.addEventListener("input", (e) => e.target.removeAttribute("aria-invalid"));
  ui.simula.addEventListener("click", () => finestra.simula());
  ui.annullaPaga.addEventListener("click", () => {
    finestra.rinuncia();
    finestra.vai(2);
  });
  dlg.addEventListener("click", (e) => {
    if (e.target.closest("[data-pren-chiudi]") || e.target === dlg) dlg.close();
    if (e.target.closest("[data-pren-riprova]")) {
      ui.msgPaga.hidden = true;
      finestra.vai(2);
    }
    if (e.target.closest("[data-pren-modifica]")) {
      dlg.close();
      // si torna al widget con le scelte di prima: data, uscita e persone restano impostate
      form.closest(".prenota").scrollIntoView({ behavior: "smooth", block: "end" });
      calHero.disegna();
    }
  });
  dlg.addEventListener("close", () => {
    document.body.style.overflow = "";
    if (finestra.passo === 3) {
      finestra.rinuncia();
      finestra.vai(2);
    }
    if (finestra.passo === 4) {
      ui.form.reset();
      finestra.vai(2);
    }
  });
  /* --- ritorno da un metodo di pagamento con redirect (/?pagamento=cs_…) --- */
  const sessioneRitorno = new URLSearchParams(location.search).get("pagamento");
  if (sessioneRitorno) {
    history.replaceState(null, "", location.pathname + location.hash);
    fetch(`${API.esito}?sessione=${encodeURIComponent(sessioneRitorno)}`, { headers: { Accept: "application/json" } })
      .then((r) => r.json())
      .then((j) => {
        if (j.stato === "confermata") finestra.fatto(j);
        else if (j.stato === "rimborsato") esitoMsg(esc(j.messaggio), "errore");
        else esitoMsg("Il pagamento non risulta completato: la prenotazione non è stata confermata. Puoi riprovare.", "errore");
      })
      .catch(() => {});
  }
})();
