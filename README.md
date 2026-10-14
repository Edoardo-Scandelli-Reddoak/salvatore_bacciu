# Sito escursioni — Cala Brandinchi (Tavolara & Molara)

Sito dedicato alle escursioni in gommone con partenza dalla spiaggia di Cala Brandinchi,
San Teodoro (SS). Obiettivo: prenotazione diretta online con acconto, senza commissioni
delle piattaforme di terze parti, e posizionamento organico su Google.

## Stato

| | |
|---|---|
| Fase attuale | sito con prenotazione online e pannello prenotazioni, tutto in Django |
| Prossimo passo | chiavi Stripe del cliente (test, poi live), email di conferma, informativa privacy |

## Struttura

```
backend/    il sito vero: homepage con prenotazione online + pannello + API (Django, deploy su Railway)
mockup/     prima versione statica della homepage (Vercel), solo riferimento: non più aggiornata
```

Vedi [`mockup/README.md`](mockup/README.md) per la homepage e
[`backend/README.md`](backend/README.md) per regole di disponibilità, avvio in locale e deploy.

## Stack previsto

- **Backend**: Django + [Unfold](https://unfoldadmin.com/) per il pannello di gestione
  (pacchetti, prezzi, immagini, hero, FAQ, prenotazioni)
- **Pagamenti**: Stripe, acconto del 30% alla prenotazione
- **Frontend**: template Django, CSS senza framework (i token sono già in `mockup/assets/css/style.css`)

## Nota sui contenuti

Foto, logo, prezzi, orari e stagione sono quelli del cliente. Recensioni, telefono, email
e P.IVA sono ancora segnaposto da sostituire prima della messa online.
