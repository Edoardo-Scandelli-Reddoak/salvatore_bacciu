"""
API JSON usata dal sito pubblico (stessa origine: il sito è servito da Django).

  GET  /api/disponibilita/?data=AAAA-MM-GG   posti per mattino e pomeriggio di quel giorno
  GET  /api/calendario/?mese=AAAA-MM         gruppo massimo prenotabile per ogni giorno del mese
  POST /api/prenotazioni/                    crea la prenotazione IN ATTESA e avvia il pagamento dell'acconto
  POST /api/pagamento/verifica/              esito del pagamento (dopo il checkout nella finestra)
  GET  /api/pagamento/esito/?sessione=cs_…   esito al ritorno da un metodo di pagamento con redirect
  POST /api/pagamento/annulla/               il cliente rinuncia: posti liberi subito
  POST /api/pagamento/simula/                solo sviluppo senza chiavi Stripe
  POST /stripe/webhook/                      notifiche firmate di Stripe

Il POST richiede il token CSRF: il cookie lo imposta la homepage (e la GET di
disponibilità), il sito lo rimanda nell'header X-CSRFToken.
"""

import calendar
import json
from datetime import date

import stripe
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import pagamenti, servizi
from .models import Fascia, Pagamento, Prenotazione


def errore(messaggio, status=400, **extra):
    return JsonResponse({"errore": messaggio, **extra}, status=status)


def _uscita_json(stato):
    f = stato.fascia
    motivo = servizi.motivo_non_prenotabile_online(stato.data, f)
    if motivo is None and stato.chiusa:
        motivo = "Uscita non disponibile in questa data."
    if motivo is None and stato.max_persone == 0:
        motivo = "Uscita al completo."
    return {
        "uscita": f.codice,
        "nome": f.nome,
        "orario": f.orario,
        "durata_ore": f.durata_ore,
        "prezzo_persona": str(f.prezzo_persona),
        "acconto_persona": str(f.acconto_persona),
        "prenotabile": motivo is None,
        "motivo": motivo,
        "chiusa": stato.chiusa,
        "posti_liberi": 0 if motivo else stato.posti_liberi,
        "max_persone": 0 if motivo else stato.max_persone,
    }


@require_GET
@ensure_csrf_cookie
def disponibilita(request):
    try:
        giorno = date.fromisoformat(request.GET.get("data", ""))
    except ValueError:
        return errore("Parametro «data» mancante o non valido (AAAA-MM-GG).")
    motivo = servizi.motivo_non_prenotabile_online(giorno)
    uscite = [] if motivo else [
        _uscita_json(servizi.stato_uscita(giorno, f)) for f in Fascia.objects.filter(attiva=True)
    ]
    return JsonResponse({"data": giorno.isoformat(), "prenotabile": motivo is None, "motivo": motivo, "uscite": uscite})


@require_GET
def calendario_mese(request):
    try:
        anno, mese = map(int, request.GET.get("mese", "").split("-"))
        inizio = date(anno, mese, 1)
    except ValueError:
        return errore("Parametro «mese» mancante o non valido (AAAA-MM).")
    fine = date(anno, mese, calendar.monthrange(anno, mese)[1])
    fasce = list(Fascia.objects.filter(attiva=True))
    giorni = {}
    for giorno, uscite in servizi.stati_periodo(inizio, fine, fasce):
        if servizi.motivo_non_prenotabile_online(giorno):
            continue
        giorni[giorno.isoformat()] = {u.fascia.codice: _uscita_json(u)["max_persone"] for u in uscite}
    return JsonResponse({"mese": f"{anno}-{mese:02d}", "giorni": giorni})


@require_POST
def crea_prenotazione(request):
    try:
        dati = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return errore("Corpo della richiesta non valido: serve JSON.")
    if not isinstance(dati, dict):
        return errore("Corpo della richiesta non valido: serve un oggetto JSON.")

    # Campo trappola: invisibile alle persone, i bot lo compilano
    if dati.get("sito_web"):
        return errore("Richiesta non valida.")

    try:
        giorno = date.fromisoformat(str(dati.get("data", "")))
    except ValueError:
        return errore("Data mancante o non valida.", campo="data")

    fascia = Fascia.objects.filter(codice=dati.get("uscita"), attiva=True).first()
    if fascia is None:
        return errore("Uscita non valida.", campo="uscita")

    motivo = servizi.motivo_non_prenotabile_online(giorno, fascia)
    if motivo:
        return errore(motivo, campo="data")

    try:
        persone = int(dati.get("persone"))
    except (TypeError, ValueError):
        return errore("Numero di persone non valido.", campo="persone")
    if persone < 1:
        return errore("Serve almeno una persona.", campo="persone")

    campi = {}
    for campo, etichetta, massimo in (("nome", "Nome e cognome", 120), ("telefono", "Telefono", 40), ("email", "Email", 254)):
        valore = str(dati.get(campo) or "").strip()
        if not valore:
            return errore(f"{etichetta}: campo obbligatorio.", campo=campo)
        campi[campo] = valore[:massimo]
    try:
        validate_email(campi["email"])
    except ValidationError:
        return errore("L'indirizzo email non sembra corretto.", campo="email")
    if sum(c.isdigit() for c in campi["telefono"]) < 6:
        return errore("Il numero di telefono non sembra corretto.", campo="telefono")

    if dati.get("privacy") is not True:
        return errore("Serve il consenso al trattamento dei dati per prenotare.", campo="privacy")

    url_ritorno = request.build_absolute_uri("/") + "?pagamento={CHECKOUT_SESSION_ID}"
    try:
        p, pagamento = pagamenti.avvia_pagamento(
            url_ritorno,
            data=giorno,
            fascia=fascia,
            persone=persone,
            note=str(dati.get("note") or "").strip()[:1000],
            **campi,
        )
    except servizi.PostiNonDisponibili as e:
        return errore(e.messaggio, status=409, max_persone=e.max_persone)
    except pagamenti.ErrorePagamento as e:
        return errore(e.messaggio, status=503)
    except ValidationError as e:
        return errore("; ".join(e.messages))

    return JsonResponse({**riepilogo(p), "pagamento": pagamento}, status=201)


def riepilogo(p):
    f = p.fascia
    pagato = p.totale_pagato()
    return {
        "codice": p.codice,
        "data": p.data.isoformat(),
        "uscita": f.codice,
        "nome_uscita": f.nome,
        "orario": f.orario,
        "durata_ore": f.durata_ore,
        "persone": p.persone,
        "importo": str(p.importo),
        "acconto": str(p.acconto_dovuto or 0),
        "pagato": str(pagato),
        "saldo": str(max(p.importo - pagato, 0)) if p.importo is not None else None,
        "nome": p.nome,
        "email": p.email,
        "confermata": not p.in_attesa,
    }


def _leggi_json(request):
    try:
        dati = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return {}
    return dati if isinstance(dati, dict) else {}


def _esito(p, esito):
    if esito == "rimborsato":
        return JsonResponse(
            {
                "stato": "rimborsato",
                "messaggio": "Il pagamento è arrivato quando i posti non erano più disponibili: "
                "ti abbiamo rimborsato l'acconto per intero. Scegli un'altra data o scrivici.",
            }
        )
    if p is None:
        return JsonResponse({"stato": "non_trovata"}, status=404)
    if p.in_attesa:
        return JsonResponse({"stato": "in_attesa", "scaduta": p.scaduta})
    return JsonResponse({"stato": "confermata", **riepilogo(p)})


@require_POST
def pagamento_verifica(request):
    """A pagamento finito il browser chiede l'esito (il webhook potrebbe non essere ancora arrivato)."""
    p = pagamenti.prenotazione_da_token(_leggi_json(request).get("token", ""))
    if p is None:
        return JsonResponse({"stato": "non_trovata"}, status=404)
    if p.in_attesa and not settings.PAGAMENTI_SIMULATI:
        try:
            trovata, esito = pagamenti.verifica_sessione(p)
        except stripe.StripeError:
            return JsonResponse({"stato": "in_attesa", "scaduta": p.scaduta})
        if esito == "rimborsato":
            return _esito(None, esito)
        p = trovata or p
        p.refresh_from_db()
    return _esito(p, "")


@require_GET
def pagamento_esito(request):
    """Ritorno da un metodo di pagamento con redirect: /?pagamento=cs_… (l'id di sessione fa da chiave)."""
    sessione_id = request.GET.get("sessione", "")
    p = Prenotazione.objects.filter(stripe_sessione=sessione_id).first() if sessione_id.startswith("cs_") else None
    if p is None:
        gia = Pagamento.objects.filter(stripe_sessione=sessione_id).select_related("prenotazione").first() if sessione_id else None
        return _esito(gia.prenotazione if gia else None, "")
    if p.in_attesa and not settings.PAGAMENTI_SIMULATI:
        try:
            trovata, esito = pagamenti.verifica_sessione(p)
        except stripe.StripeError:
            return JsonResponse({"stato": "in_attesa", "scaduta": p.scaduta})
        if esito == "rimborsato":
            return _esito(None, esito)
        p.refresh_from_db()
    return _esito(p, "")


@require_POST
def pagamento_annulla(request):
    p = pagamenti.prenotazione_da_token(_leggi_json(request).get("token", ""))
    if p is not None:
        pagamenti.annulla_attesa(p)
    return JsonResponse({"ok": True})


@require_POST
def pagamento_simula(request):
    if not settings.PAGAMENTI_SIMULATI:
        return errore("Non disponibile.", status=404)
    p = pagamenti.prenotazione_da_token(_leggi_json(request).get("token", ""))
    if p is None:
        return JsonResponse({"stato": "non_trovata"}, status=404)
    trovata, esito = pagamenti.simula_pagamento(p)
    if trovata:
        trovata.refresh_from_db()
    return _esito(trovata, esito)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Notifiche di Stripe. Si accettano solo se firmate con STRIPE_WEBHOOK_SECRET."""
    try:
        evento = stripe.Webhook.construct_event(
            request.body, request.headers.get("Stripe-Signature", ""), settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponse(status=400)

    tipo = evento["type"]
    sessione = evento["data"]["object"]
    if tipo in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        pagamenti.conferma_da_sessione(sessione)
    elif tipo in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        pagamenti.sessione_scaduta(sessione)
    return HttpResponse(status=200)
