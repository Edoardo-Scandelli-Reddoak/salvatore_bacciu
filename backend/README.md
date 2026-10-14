# Sito e prenotazioni — Django + Unfold

Un unico progetto Django serve:

| Indirizzo | Cosa c'è |
|---|---|
| `/` | il sito pubblico (app `sito`) con la prenotazione online |
| `/admin/` | il pannello con cui il proprietario gestisce le prenotazioni (app `prenotazioni`) |
| `/api/` | l'API usata dal sito |

## Regole di disponibilità

- Ogni giorno ci sono due **uscite**: mattino (partenza 8:30, 5 ore, 80 €) e pomeriggio
  (partenza 14:00, 4 ore, 70 €). Si modificano da *Configurazione → Uscite*.
- Ci sono due **gommoni** da 12 posti più lo skipper (*Configurazione → Gommoni*).
- Un gruppo **non viene mai diviso** su due gommoni.
- **Assegnazione automatica (best fit)**: tra i gommoni in cui il gruppo entra si sceglie
  quello con meno posti liberi, a parità quello con `ordine` più basso. Effetti:
  - si riempie il primo gommone prima di aprire il secondo;
  - se sul primo ci sono 10/12 e arriva un gruppo da 3, va direttamente sul secondo;
  - un gruppo da 2 che arriva dopo riempie i 2 posti rimasti sul primo.
- Se il gruppo non entra in nessun gommone la prenotazione è **rifiutata**, sia dal sito
  sia dal pannello. «Max N insieme» nel calendario è il gruppo più grande ancora prenotabile.
- **Esclusiva**: richiede un gommone vuoto e lo occupa per intero. Il prezzo va inserito a mano.
- **Chiusure** (*Configurazione → Chiusure*): una giornata, una sola uscita o un solo gommone
  (meteo, manutenzione). Se ci sono già prenotazioni il pannello avvisa di gestirle.
- Le prenotazioni non hanno uno stato da gestire. Quelle dal sito restano **in attesa** solo
  mentre il cliente paga l'acconto, al massimo 30 minuti, poi si confermano o spariscono da sole.
  Quelle dal pannello nascono confermate. Per annullarne una la si
  **elimina** (dal dettaglio o con l'azione «Elimina» nell'elenco) e i posti tornano liberi.
- **Stagione**: il sito accetta prenotazioni dal 1° maggio al 30 settembre
  (`STAGIONE_INIZIO` / `STAGIONE_FINE` in `config/settings.py`). Dal pannello si può
  inserire anche fuori stagione.

Il controllo dei posti e il salvataggio avvengono nella stessa transazione, con un lock
sulla riga dell'uscita (`SELECT … FOR UPDATE`). Due prenotazioni simultanee per la stessa
uscita non possono superare la capienza. È verificato su Postgres da
`tests/test_concorrenza.py` (40 richieste in parallelo su 24 posti → 24 accettate).

Tutta la logica sta in `prenotazioni/servizi.py`; admin e API la usano senza duplicarla.

## Prenotazione dal sito

Tutto in `sito/static/sito/js/prenotazione.js`, senza dipendenze. La finestra è in
`sito/templates/sito/_prenotazione.html`.

1. **Widget dell'hero**: il cliente sceglie uscita, data e persone.
   - Il calendario (`/api/calendario/`) barra i giorni in cui il gruppo non entra in
     quell'uscita.
   - Finché il cliente non sceglie una data, viene proposto il primo giorno libero.
2. **I pulsanti «Prenota»** delle card, «Prenota ora» nell'header e la barra mobile portano
   al widget e aprono il calendario. Le card impostano anche la loro uscita.
3. **«Vedi disponibilità»** controlla *solo* l'uscita scelta (`/api/disponibilita/`).
   - **Se c'è posto** si apre subito la finestra con il riepilogo (data, uscita, persone,
     totale) e i campi da compilare: nome, telefono, email, note e consenso privacy. Non ci
     sono altre scelte da fare.
   - **Se non c'è posto** il widget spiega il motivo («posto per al massimo 2 persone
     insieme», «al completo», «prenotazioni chiuse per oggi»). Propone al massimo due
     alternative cliccabili: l'altra uscita dello stesso giorno e il primo giorno libero per
     la stessa uscita.
4. **Conferma** con il codice di prenotazione e le istruzioni per il giorno dell'uscita.

Se tra l'apertura della finestra e l'invio qualcun altro prende gli ultimi posti, il server
risponde 409: la finestra lo spiega e «Modifica la scelta» riporta al widget.

Prezzi, orari, durate e uscite attive arrivano dal pannello (*Configurazione → Uscite*):
modificarli lì aggiorna anche la homepage. Il campo «prenotabile online fino alle» chiude
le prenotazioni dal sito per il giorno stesso dopo quell'ora (mattino 8:00, pomeriggio 13:30;
si cambia dal pannello).

## Pagamento dell'acconto (Stripe)

Per prenotare dal sito si paga online un **acconto per persona** (20 €, *Configurazione → Uscite*);
il resto si salda all'imbarco. Logica in `prenotazioni/pagamenti.py`.

1. «Continua al pagamento» crea la prenotazione **in attesa** e **blocca i posti per 30 minuti**
   (il minimo che Stripe accetta per una sessione). Poi apre il pagamento Stripe **dentro la
   finestra del sito** (Checkout `ui_mode: embedded_page`): carta, Apple Pay, Google Pay.
2. La prenotazione diventa **confermata solo quando Stripe conferma il pagamento**, in due modi:
   - il **webhook** `checkout.session.completed`, firmato da Stripe;
   - la verifica che il browser chiede al server a pagamento finito, che a sua volta chiede
     a Stripe. Serve nel caso il webhook tardi.

   Le due vie sono **idempotenti**: lo stesso pagamento non viene mai registrato due volte.
3. **Se il cliente chiude la finestra** o annulla, i posti si liberano subito. **Se lascia
   scadere il tempo**, la prenotazione in attesa smette di contare e il webhook
   `checkout.session.expired` la elimina.

Casi limite gestiti, entrambi con **rimborso automatico** e movimenti registrati:
- pagamento arrivato *dopo* la scadenza, quando i posti li ha presi qualcun altro;
- prenotazione eliminata dal pannello mentre il cliente pagava.

**Cosa registra il backend.** Ogni movimento di denaro è una riga di *Pagamenti* con:
- tipo: acconto, saldo o rimborso;
- metodo: Stripe, contanti, POS o bonifico;
- importo, data e ora, chi l'ha registrato;
- per Stripe, gli id di sessione, pagamento e rimborso.

Se si elimina una prenotazione **i movimenti restano**, con codice e nome del cliente.
Nella prenotazione: totale, pagato, **da incassare all'imbarco**, data di conferma.

**Dal pannello**, nel dettaglio di una prenotazione:
- **«Registra incasso»**: saldo all'imbarco o acconto ricevuto fuori dal sito (contanti,
  POS, bonifico). Propone già l'importo da incassare.
- **«Rimborsa con Stripe»**: restituisce al cliente fino a quanto pagato online. Dopo, se
  serve, si elimina la prenotazione.

**Senza chiavi Stripe, in sviluppo** (`DJANGO_DEBUG=1`) il pagamento è **simulato**: stesso
flusso, con un pulsante «Simula pagamento riuscito» al posto del modulo Stripe. In produzione
la simulazione non è mai attiva.

## Il pannello

| Pagina | A cosa serve |
|---|---|
| Oggi e prossimi giorni | Le due uscite di oggi (persone a bordo, posti liberi) e i 14 giorni successivi. Fuori stagione mostra l'inizio della prossima. |
| Calendario disponibilità | Un mese per volta: per ogni giorno e uscita, posti liberi e riempimento di ciascun gommone. |
| Uscita (clic su una cella) | Lista d'imbarco divisa per gommone con nomi, persone, telefoni, note. Si stampa. Da qui si aggiunge una prenotazione già impostata su quel giorno e quell'uscita. |
| Nuova prenotazione | Per chi prenota al telefono, su WhatsApp o di persona. Il gommone si può lasciare vuoto (assegnazione automatica) o scegliere a mano. **Mentre si compila**, sotto i campi dell'uscita compare l'occupazione dei gommoni. Il riquadro è verde se c'è posto, arancione se il gruppo verrà spostato su un altro gommone, rosso se non entra: in quel caso il salvataggio è rifiutato con lo stesso messaggio. |
| Pagamenti | Tutti i movimenti di denaro, anche di prenotazioni poi eliminate. Filtri per data, tipo e metodo. |
| Tutte le prenotazioni | Colonne: data uscita, uscita, gommone, cliente, persone, canale e **data della prenotazione**. Ricerca per nome, telefono, email o codice; filtri per data, uscita, gommone e canale. |

Modificando una prenotazione già esistente, se il gruppo sta ancora sul suo gommone resta
lì. Se non ci sta più (per esempio sono aumentate le persone) viene spostato e il pannello
lo segnala.

## Avvio in locale

Serve Python 3.12.

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DJANGO_DEBUG=1           # SQLite in locale, chiave di sviluppo
python manage.py migrate        # crea anche le 2 uscite e i 2 gommoni
python manage.py createsuperuser
python manage.py runserver      # sito: http://127.0.0.1:8000/  ·  pannello: /admin/
```

Test: `DJANGO_DEBUG=1 python manage.py test prenotazioni`.
I 2 test di concorrenza girano solo su Postgres:

```bash
docker run -d --rm --name pg -e POSTGRES_PASSWORD=prova -p 55432:5432 postgres:16-alpine
DJANGO_DEBUG=1 DATABASE_URL=postgres://postgres:prova@127.0.0.1:55432/postgres python manage.py test prenotazioni
```

## Deploy su Railway

1. Nuovo progetto da GitHub, **Root Directory: `backend`** (la radice del repo contiene anche il mockup).
2. Aggiungi un database **PostgreSQL** al progetto e, nel servizio Django, crea la variabile
   `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`.
3. Variabili del servizio:
   - `DJANGO_SECRET_KEY`: stringa lunga e casuale, ad esempio
     `python -c "import secrets; print(secrets.token_urlsafe(50))"`
   - `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS`: solo per un dominio personalizzato
     (es. `prenotazioni.dominio.it` e `https://prenotazioni.dominio.it`). Il dominio
     `*.up.railway.app` è aggiunto in automatico.
4. Genera un dominio pubblico (*Settings → Networking*).
5. **Stripe**, prima con le chiavi di **test**, poi con quelle **live**:
   - `STRIPE_SECRET_KEY` (`sk_…`) e `STRIPE_PUBLISHABLE_KEY` (`pk_…`), da *Sviluppatori → Chiavi API*;
   - nella dashboard Stripe crea un endpoint webhook (*Workbench → Webhooks*) verso
     `https://<dominio>/stripe/webhook/` con gli eventi `checkout.session.completed`,
     `checkout.session.async_payment_succeeded`, `checkout.session.expired`,
     `checkout.session.async_payment_failed`;
   - copia il segreto di firma dell'endpoint (`whsec_…`) in `STRIPE_WEBHOOK_SECRET`.
6. Crea l'utente del proprietario:
   `railway run python manage.py createsuperuser` (oppure dalla shell del servizio).

`railway.json` fa il resto:

| Fase | Cosa fa |
|---|---|
| build | `collectstatic` |
| pre-deploy | `migrate` |
| avvio | gunicorn |
| healthcheck | `/salute/` |

I file statici sono serviti da whitenoise.

## API per il sito

| | |
|---|---|
| `GET /api/disponibilita/?data=2027-07-15` | per mattino e pomeriggio: `posti_liberi`, `max_persone`, `chiusa`, prezzo e orario. Imposta anche il cookie CSRF. |
| `GET /api/calendario/?mese=2027-07` | per ogni giorno prenotabile: `{"mattino": max_persone, "pomeriggio": max_persone}`. `0` = completo o chiuso: serve a disattivare i giorni nel calendario del sito. |
| `POST /api/prenotazioni/` | JSON `{data, uscita, persone, nome, telefono, email, note, privacy: true}`. Header `X-CSRFToken` (il cookie lo imposta la homepage). Crea la prenotazione **in attesa** e restituisce `pagamento`: `token`, scadenza, acconto e, con Stripe, `client_secret` e chiave pubblica. Risposte: `201`; `409` se non c'è posto (con `max_persone`); `400` per dati non validi (con `campo`); `503` se Stripe non risponde. |
| `POST /api/pagamento/verifica/` | `{token}`: esito del pagamento (`confermata`, `in_attesa`, `rimborsato`). |
| `GET /api/pagamento/esito/?sessione=cs_…` | esito al ritorno da un metodo di pagamento con redirect. |
| `POST /api/pagamento/annulla/` | `{token}`: il cliente rinuncia, posti liberati subito. |
| `POST /api/pagamento/simula/` | `{token}`: solo in sviluppo senza chiavi Stripe. |
| `POST /stripe/webhook/` | notifiche di Stripe, accettate solo con firma valida. |

Dal sito non si prenota l'esclusiva: si gestisce su contatto, dal pannello.

## Cosa manca

- **Prova con chiavi Stripe di test vere.** Il flusso è verificato con il pagamento simulato
  e le chiamate sono validate con `stripe-mock`. Il modulo Stripe dentro la finestra si vede
  solo con chiavi reali.
- **Email di conferma** al cliente e notifica al proprietario.
- **Informativa privacy** (Iubenda): il link nel form di prenotazione oggi punta a `#`.

## Traduzioni

Unfold non include l'italiano. Le sue stringhe sono tradotte in
`locale/it/LC_MESSAGES/django.po`. Dopo una modifica si ricompila con
`python locale/compila.py` (non serve gettext).
