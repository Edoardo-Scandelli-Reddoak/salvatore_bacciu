# Homepage — mockup statico

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
| Escursioni | 3 pacchetti + esclusiva, con prezzo "da" e posti residui |
| La rotta | Itinerario a 5 tappe: risponde a "dove mi porti?" e vale molto per la SEO locale |
| Gommone privato | Il prodotto a margine più alto, con CTA a preventivo |
| Lo stabilimento | Il vantaggio competitivo reale: si parte dalla spiaggia, non dal porto |
| Galleria / video | Spazio per il materiale professionale già disponibile |
| Recensioni | Prova sociale (testi dimostrativi, da collegare a Google Business Profile) |
| FAQ | Meno telefonate + schema FAQPage per Google |
| Contatti | Mappa, WhatsApp, stagionalità |

## Da sostituire prima della messa online

- **Foto**: le immagini in `assets/img/` vengono da Wikimedia Commons (vedi `assets/img/CREDITS.md`)
  e servono solo a far vedere l'impaginato. Vanno rimpiazzate con il materiale dello studio.
- **Nome e logo**: "Cala Brandinchi" è un segnaposto — da decidere insieme al dominio.
- **Prezzi, orari, durate, numero di telefono, P.IVA**: valori di esempio.
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
