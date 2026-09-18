# Sito escursioni — Cala Brandinchi (Tavolara & Molara)

Sito dedicato alle escursioni in gommone con partenza dalla spiaggia di Cala Brandinchi,
San Teodoro (SS). Obiettivo: prenotazione diretta online con acconto, senza commissioni
delle piattaforme di terze parti, e posizionamento organico su Google.

## Stato

| | |
|---|---|
| Fase attuale | proposta grafica della homepage |
| Prossimo passo | spec e impianto del progetto Django |

## Struttura

```
mockup/     proposta di homepage — HTML/CSS/JS statici, nessuna build
```

Vedi [`mockup/README.md`](mockup/README.md) per come aprirla, la direzione grafica
e la mappatura verso i template Django.

## Stack previsto

- **Backend**: Django + [Unfold](https://unfoldadmin.com/) per il pannello di gestione
  (pacchetti, prezzi, immagini, hero, FAQ, prenotazioni)
- **Pagamenti**: Stripe, acconto del 30% alla prenotazione
- **Frontend**: template Django, CSS senza framework (i token sono già in `mockup/assets/css/style.css`)

## Nota sui contenuti

Tutto ciò che è nel mockup è **materiale di lavoro**: foto placeholder (Wikimedia Commons,
attribuzioni in `mockup/assets/img/CREDITS.md`), prezzi, orari, recensioni e dati di contatto
sono segnaposto da sostituire prima della messa online.
