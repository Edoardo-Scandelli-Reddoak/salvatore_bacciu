# Homepage — mockup statico

> **Non più aggiornato.** Dal 07/10/2026 la homepage vive in Django: `backend/sito/`
> (template, CSS, JS e immagini), con prezzi e orari presi dal pannello e la prenotazione
> collegata all'API. Questo mockup resta come riferimento grafico e anteprima su Vercel.

Proposta di homepage per il sito escursioni di Salvatore Bacciu (Cala Brandinchi, San Teodoro).
È HTML/CSS/JS puro, senza build: serve a validare **direzione grafica, struttura e gerarchia dei contenuti**
prima di scrivere il progetto Django.

## Come guardarlo

```bash
cd mockup && python3 -m http.server 8777
# poi apri http://localhost:8777
```

## Direzione grafica

Palette blu / azzurro / sabbia, nessun accento caldo. I token sono in `:root`:
sabbia `#FDFBF7` e `#F7F1E8` per i fondi, blu `#17608F` (CTA) e `#0B2B45` (sezioni scure e footer),
azzurro `#5AB4DC` e `#EFF7FB` per accenti e superfici chiare. Tipografia: Plus Jakarta Sans (400–800),
titoli in peso 800 con tracking stretto. Attenzione: le virgole del font sono molto larghe (0,39 em),
quindi nei titoli display si evitano.

## Cosa c'è dentro

| Blocco | Ruolo |
|---|---|
| Hero + widget disponibilità | La prenotazione è il primo elemento della pagina, non un bottone in fondo |
| Striscia fiducia | Le 4 obiezioni che bloccano l'acquisto (dove si parte, quanti siamo, cosa è incluso, come pago) |
| Le offerte | Uscita del mattino (5 h, 80 €), del pomeriggio (4 h, 70 €) e gommone in esclusiva (prezzo su richiesta) |
| La rotta | Partenza e rientro a Cala Brandinchi, in mezzo Tavolara, Molara, Capo Coda Cavallo: risponde a "dove mi porti?" e vale molto per la SEO locale |
| Gommone in esclusiva | Il prodotto a margine più alto, approfondito con CTA a preventivo |
| Lo stabilimento | Il vantaggio competitivo reale: si parte dalla spiaggia, non dal porto |
| Galleria | Foto professionali del cliente, con lightbox (frecce, tastiera, swipe) |
| Recensioni | Prova sociale (testi dimostrativi, da collegare a Google Business Profile) |
| FAQ | Meno telefonate + schema FAQPage per Google |
| Contatti | Mappa, WhatsApp, stagionalità |

## Da sostituire prima della messa online

Foto e logo sono già quelli del cliente (vedi `assets/img/CREDITS.md`).

- **Numero di telefono, email, P.IVA**: valori di esempio. Prezzi, orari, durate e stagione sono quelli comunicati dal cliente (07/10/2026).
- **Offerte**: oggi sono tre (mattino, pomeriggio, esclusiva su richiesta). Quando arriveranno i pacchetti previsti per la
  prossima stagione va cambiata una riga di CSS (`.griglia-esc`, numero di colonne).
- **Recensioni**: testi di esempio.

## Mappatura verso Django

I blocchi sono già pensati come template parziali:

```
templates/
  base.html
  partials/header.html      ← .header + .menu-mobile
  partials/footer.html
  home.html                 ← le sezioni, in ordine
  partials/card_escursione.html   ← ripetuta con {% for p in pacchetti %}
```

Contenuti gestibili dal pannello Unfold: hero (occhiello/titolo/testo/immagine), pacchetti
(titolo, descrizione, durata, orari, prezzo, foto, tag "la più richiesta"), tappe della rotta,
galleria, FAQ, dati di contatto. Il widget dell'hero chiamerà `GET /api/disponibilita/`.
