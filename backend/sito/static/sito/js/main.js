/* Homepage — interazioni dell'interfaccia (header, menu, reveal, galleria, FAQ).
   Zero dipendenze. La prenotazione vive in prenotazione.js. */

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

  /* --- widget e prenotazione: vedi prenotazione.js -------------------- */

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
