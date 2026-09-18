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

  if (data) {
    const oggi = new Date();
    const iso = (d) => d.toISOString().slice(0, 10);
    data.min = iso(oggi);
    data.value = iso(new Date(oggi.getTime() + 86400000));
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    // Produzione: GET /api/disponibilita/?pacchetto=&data=&pax=
    const d = data.value ? new Date(data.value) : new Date();
    esitoData.textContent =
      "— " + d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });
    esito.classList.add("is-on");
    esito.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

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

  /* --- anni footer ------------------------------------------------------ */
  const anno = new Date().getFullYear();
  document.querySelectorAll("[data-anno]").forEach((el) => (el.textContent = anno));
})();
