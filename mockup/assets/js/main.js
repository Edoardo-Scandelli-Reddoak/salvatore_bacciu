/* Homepage mockup — interazioni minime, zero dipendenze.
   In produzione questo file resta praticamente identico:
   cambia solo la fetch del widget disponibilità verso l'endpoint Django. */

(() => {
  "use strict";

  /* --- header: stato "attaccato" allo scroll --------------------------- */
  const header = document.getElementById("header");
  const barra = document.getElementById("barraMobile");
  const wa = document.querySelector(".whatsapp");
  const soglia = 40;

  const onScroll = () => {
    const y = window.scrollY;
    header.classList.toggle("is-stuck", y > soglia);
    if (barra) barra.classList.toggle("is-on", y > window.innerHeight * 0.75);
    if (wa) wa.classList.toggle("is-on", y > window.innerHeight * 0.6);
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* --- menu mobile ------------------------------------------------------ */
  const burger = document.getElementById("burger");
  const menu = document.getElementById("menuMobile");

  const chiudiMenu = () => {
    header.classList.remove("is-open");
    menu.classList.remove("is-on");
    burger.setAttribute("aria-expanded", "false");
    document.body.style.overflow = "";
  };

  burger.addEventListener("click", () => {
    const aperto = menu.classList.toggle("is-on");
    header.classList.toggle("is-open", aperto);
    burger.setAttribute("aria-expanded", String(aperto));
    document.body.style.overflow = aperto ? "hidden" : "";
  });
  menu.querySelectorAll("a").forEach((a) => a.addEventListener("click", chiudiMenu));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && menu.classList.contains("is-on")) chiudiMenu();
  });

  /* --- reveal on scroll ------------------------------------------------- */
  const elementi = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (voci) => {
        voci.forEach((v, i) => {
          if (!v.isIntersecting) return;
          v.target.style.transitionDelay = `${Math.min(i * 70, 280)}ms`;
          v.target.classList.add("is-in");
          io.unobserve(v.target);
        });
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.12 }
    );
    elementi.forEach((el) => io.observe(el));
  } else {
    elementi.forEach((el) => el.classList.add("is-in"));
  }

  /* --- widget disponibilità -------------------------------------------- */
  const form = document.getElementById("formPrenota");
  const data = document.getElementById("f-data");
  const esito = document.getElementById("esito");
  const esitoData = document.getElementById("esitoData");

  // Stagione: 1 maggio – 30 settembre. Fuori stagione si propone la prossima.
  const pad = (n) => String(n).padStart(2, "0");
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const daIso = (s) => {
    const [a, m, g] = s.split("-").map(Number);
    return new Date(a, m - 1, g);
  };
  const oggi = new Date();
  oggi.setHours(0, 0, 0, 0);
  let annoStagione = oggi.getFullYear();
  if (oggi > new Date(annoStagione, 8, 30)) annoStagione += 1;
  const minData = oggi > new Date(annoStagione, 4, 1) ? oggi : new Date(annoStagione, 4, 1);
  const maxData = new Date(annoStagione, 8, 30);

  /* --- calendario ------------------------------------------------------- */
  const campoData = document.getElementById("f-data-btn");
  const cal = document.getElementById("calendario");
  const calGriglia = document.getElementById("calGriglia");
  const calMese = document.getElementById("calMese");
  const calPrec = document.getElementById("calPrec");
  const calSucc = document.getElementById("calSucc");
  let scelta = minData;
  let meseVisto = new Date(minData.getFullYear(), minData.getMonth(), 1);

  const scegli = (d) => {
    scelta = d;
    data.value = iso(d);
    campoData.textContent = d.toLocaleDateString("it-IT", {
      weekday: "short", day: "numeric", month: "long", year: "numeric",
    });
  };

  const disegna = () => {
    const a = meseVisto.getFullYear();
    const m = meseVisto.getMonth();
    calMese.textContent = meseVisto.toLocaleDateString("it-IT", { month: "long", year: "numeric" });
    calPrec.disabled = new Date(a, m, 1) <= new Date(minData.getFullYear(), minData.getMonth(), 1);
    calSucc.disabled = new Date(a, m + 1, 1) > maxData;
    calGriglia.innerHTML = "";
    const vuoti = (new Date(a, m, 1).getDay() + 6) % 7; // settimana da lunedì
    for (let i = 0; i < vuoti; i++) calGriglia.append(document.createElement("span"));
    const giorni = new Date(a, m + 1, 0).getDate();
    for (let g = 1; g <= giorni; g++) {
      const d = new Date(a, m, g);
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = g;
      b.dataset.iso = iso(d);
      b.setAttribute("aria-label", d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" }));
      b.setAttribute("aria-pressed", String(iso(d) === data.value));
      b.disabled = d < minData || d > maxData;
      b.tabIndex = iso(d) === data.value ? 0 : -1;
      calGriglia.append(b);
    }
    if (!calGriglia.querySelector('[tabindex="0"]')) {
      const primo = calGriglia.querySelector("button:not(:disabled)");
      if (primo) primo.tabIndex = 0;
    }
  };

  const apriCal = () => {
    meseVisto = new Date(scelta.getFullYear(), scelta.getMonth(), 1);
    disegna();
    cal.hidden = false;
    campoData.setAttribute("aria-expanded", "true");
    calGriglia.querySelector('[tabindex="0"]')?.focus();
  };
  const chiudiCal = (rifocalizza) => {
    if (cal.hidden) return;
    cal.hidden = true;
    campoData.setAttribute("aria-expanded", "false");
    if (rifocalizza) campoData.focus();
  };

  scegli(minData);
  campoData.addEventListener("click", () => (cal.hidden ? apriCal() : chiudiCal(false)));
  calPrec.addEventListener("click", () => {
    meseVisto = new Date(meseVisto.getFullYear(), meseVisto.getMonth() - 1, 1);
    disegna();
  });
  calSucc.addEventListener("click", () => {
    meseVisto = new Date(meseVisto.getFullYear(), meseVisto.getMonth() + 1, 1);
    disegna();
  });
  calGriglia.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b || b.disabled) return;
    scegli(daIso(b.dataset.iso));
    chiudiCal(true);
  });
  // frecce per muoversi tra i giorni, Esc per chiudere
  cal.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      chiudiCal(true);
      return;
    }
    const passi = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
    const attivo = document.activeElement.closest(".calendario__griglia button");
    if (!passi || !attivo) return;
    e.preventDefault();
    const d = daIso(attivo.dataset.iso);
    d.setDate(d.getDate() + passi);
    if (d < minData || d > maxData) return;
    if (d.getMonth() !== meseVisto.getMonth()) {
      meseVisto = new Date(d.getFullYear(), d.getMonth(), 1);
      disegna();
    }
    calGriglia.querySelectorAll("button").forEach((b) => (b.tabIndex = -1));
    const nuovo = calGriglia.querySelector(`[data-iso="${iso(d)}"]`);
    nuovo.tabIndex = 0;
    nuovo.focus();
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".campo--data")) chiudiCal(false);
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    // Produzione: GET /api/disponibilita/?pacchetto=&data=&pax=
    const d = daIso(data.value);
    esitoData.textContent =
      "— " + d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });
    esito.classList.add("is-on");
    esito.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  // "Prenota" sulle card: porta al widget con l'uscita già scelta
  const sceltaUscita = document.getElementById("f-esc");
  document.querySelectorAll("a[data-uscita]").forEach((a) =>
    a.addEventListener("click", () => (sceltaUscita.value = a.dataset.uscita))
  );

  /* --- accordion: una risposta aperta per volta ------------------------ */
  const domande = document.querySelectorAll(".faq details");
  domande.forEach((d) =>
    d.addEventListener("toggle", () => {
      if (!d.open) return;
      domande.forEach((altra) => {
        if (altra !== d) altra.open = false;
      });
    })
  );

  /* --- galleria: lightbox con frecce, tastiera e swipe ------------------ */
  const lightbox = document.getElementById("lightbox");
  const foto = [...document.querySelectorAll(".galleria__apri img")];
  if (lightbox && foto.length) {
    const lbImg = document.getElementById("lightboxImg");
    const lbTesto = document.getElementById("lightboxTesto");
    const lbConta = document.getElementById("lightboxConta");
    let corrente = 0;

    const mostra = (i) => {
      corrente = (i + foto.length) % foto.length;
      const f = foto[corrente];
      lbImg.src = f.currentSrc || f.src;
      lbImg.alt = f.alt;
      lbTesto.textContent = f.alt;
      lbConta.textContent = `${corrente + 1} / ${foto.length}`;
      lbImg.classList.remove("is-cambio");
      void lbImg.offsetWidth; // riavvia l'animazione
      lbImg.classList.add("is-cambio");
    };

    foto.forEach((f, i) =>
      f.closest("button").addEventListener("click", () => {
        mostra(i);
        lightbox.showModal();
        document.body.style.overflow = "hidden";
      })
    );
    lightbox.addEventListener("close", () => (document.body.style.overflow = ""));
    document.getElementById("lightboxChiudi").addEventListener("click", () => lightbox.close());
    document.getElementById("lightboxPrec").addEventListener("click", () => mostra(corrente - 1));
    document.getElementById("lightboxSucc").addEventListener("click", () => mostra(corrente + 1));
    // clic sullo sfondo scuro (fuori da foto e pulsanti) chiude
    lightbox.addEventListener("click", (e) => {
      if (e.target === lightbox || e.target.classList.contains("lightbox__figura")) lightbox.close();
    });
    lightbox.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") mostra(corrente - 1);
      if (e.key === "ArrowRight") mostra(corrente + 1);
    });
    // swipe orizzontale su touch
    let x0 = null;
    lightbox.addEventListener("touchstart", (e) => (x0 = e.touches[0].clientX), { passive: true });
    lightbox.addEventListener("touchend", (e) => {
      if (x0 === null) return;
      const dx = e.changedTouches[0].clientX - x0;
      if (Math.abs(dx) > 45) mostra(corrente + (dx < 0 ? 1 : -1));
      x0 = null;
    });
  }

  /* --- anni footer ------------------------------------------------------ */
  const anno = new Date().getFullYear();
  document.querySelectorAll("[data-anno]").forEach((el) => (el.textContent = anno));
})();
