"""
Acconto online con Stripe Checkout (ui_mode «embedded_page»: il pagamento si apre dentro il sito).

Flusso:
1. `avvia_pagamento` crea la prenotazione con i posti BLOCCATI (`scade_il` = ora + 30 min)
   e una sessione di Checkout per persone × acconto.
2. Il cliente paga nella finestra del sito.
3. La prenotazione diventa confermata SOLO quando lo dice Stripe: webhook
   `checkout.session.completed`, oppure `verifica_sessione` chiamata dal browser a pagamento
   finito (utile se il webhook tarda). Entrambe passano da `conferma_pagamento`, che è
   idempotente: lo stesso pagamento non viene mai registrato due volte.
4. Se il cliente non paga, alla scadenza i posti tornano liberi da soli (una prenotazione con
   `scade_il` passato non conta più) e il webhook `checkout.session.expired` la elimina.

Casi limite:
- pagamento arrivato dopo la scadenza del blocco e posti nel frattempo presi → rimborso automatico;
- prenotazione eliminata dal pannello mentre il cliente pagava → rimborso automatico.

Senza chiavi Stripe, in sviluppo (DEBUG) il pagamento è simulato: stesso flusso, nessuna chiamata a Stripe.
"""

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

import stripe
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

from . import servizi
from .models import Pagamento, Prenotazione

log = logging.getLogger(__name__)

SALE_TOKEN = "prenotazione-pagamento"


class ErrorePagamento(Exception):
    def __init__(self, messaggio):
        super().__init__(messaggio)
        self.messaggio = messaggio


def _client():
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY)


def _campo(oggetto, nome, default=None):
    """Legge un campo da un oggetto Stripe o da un dizionario."""
    if oggetto is None:
        return default
    try:
        valore = oggetto[nome]
    except (KeyError, TypeError):
        valore = getattr(oggetto, nome, default)
    return default if valore is None else valore


def centesimi(importo):
    return int((Decimal(importo) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def euro(cent):
    return (Decimal(cent) / 100).quantize(Decimal("0.01"))


# Il browser riceve un token firmato per agire sulla SUA prenotazione in attesa
# (verificare, annullare, simulare): il solo codice non basta.
def token_per(prenotazione):
    return signing.dumps(prenotazione.pk, salt=SALE_TOKEN)


def prenotazione_da_token(token):
    try:
        pk = signing.loads(token, salt=SALE_TOKEN, max_age=60 * 60 * 6)
    except signing.BadSignature:
        return None
    return Prenotazione.objects.filter(pk=pk).first()


# --------------------------------------------------------------------------
# 1. Avvio
# --------------------------------------------------------------------------


def avvia_pagamento(url_ritorno, **dati):
    """
    Crea la prenotazione in attesa (posti bloccati) e la sessione di pagamento.
    Restituisce (prenotazione, dati per il browser). Solleva PostiNonDisponibili o ErrorePagamento.
    """
    scadenza = timezone.now() + timedelta(minutes=settings.PAGAMENTO_BLOCCO_MINUTI, seconds=60)
    with transaction.atomic():
        p = Prenotazione(**dati, canale=Prenotazione.Canale.SITO)
        p.full_clean(exclude=["gommone"])
        servizi.assegna_gommone(p)  # lock sull'uscita: due clienti non bloccano gli stessi posti
        servizi.completa_importo(p)
        p.acconto_dovuto = p.fascia.acconto_persona * p.persone
        p.scade_il = scadenza
        p.save()

    base = {"token": token_per(p), "scade_il": scadenza.isoformat(), "acconto": str(p.acconto_dovuto)}
    if settings.PAGAMENTI_SIMULATI:
        return p, {**base, "modo": "simulato"}

    try:
        sessione = _client().v1.checkout.sessions.create(
            params={
                "mode": "payment",
                "ui_mode": "embedded_page",
                "redirect_on_completion": "if_required",
                "return_url": url_ritorno,
                "submit_type": "book",
                "locale": "it",
                "customer_email": p.email,
                "client_reference_id": p.codice,
                "expires_at": int(scadenza.timestamp()),
                "line_items": [
                    {
                        "quantity": p.persone,
                        "price_data": {
                            "currency": "eur",
                            "unit_amount": centesimi(p.fascia.acconto_persona),
                            "product_data": {
                                "name": f"Acconto escursione {p.fascia.nome.lower()} · {p.data:%d/%m/%Y}",
                                "description": f"Prenotazione {p.codice}. Il saldo si paga all'imbarco a Cala Brandinchi.",
                            },
                        },
                    }
                ],
                "metadata": {"prenotazione": str(p.pk), "codice": p.codice},
                "payment_intent_data": {
                    "description": f"Acconto prenotazione {p.codice}",
                    "metadata": {"prenotazione": str(p.pk), "codice": p.codice},
                },
            },
            options={"idempotency_key": f"checkout-{p.codice}"},
        )
    except stripe.StripeError as e:
        log.exception("Creazione sessione Stripe fallita per %s", p.codice)
        p.delete()  # libera subito i posti
        raise ErrorePagamento("Il pagamento online non è disponibile in questo momento. Riprova tra poco o scrivici.") from e

    p.stripe_sessione = sessione.id
    p.save(update_fields=["stripe_sessione"])
    return p, {
        **base,
        "modo": "stripe",
        "client_secret": sessione.client_secret,
        "chiave_pubblica": settings.STRIPE_PUBLISHABLE_KEY,
    }


# --------------------------------------------------------------------------
# 2. Conferma (webhook o browser) — idempotente
# --------------------------------------------------------------------------


def conferma_pagamento(prenotazione_id, sessione_id, importo, payment_intent):
    """
    Registra l'acconto e conferma la prenotazione. Restituisce (prenotazione o None, esito)
    con esito in: "confermata", "gia_registrato", "rimborsato".
    """
    with transaction.atomic():
        # Prima il lock sulla prenotazione, POI il controllo «già registrato»: se webhook e
        # browser arrivano insieme, il secondo aspetta il primo e trova il pagamento già scritto.
        # of=("self",): si blocca solo la riga della prenotazione. Senza, Postgres rifiuta il FOR UPDATE
        # per via del join esterno sul gommone (può essere vuoto) dovuto all'ordinamento del modello.
        p = (
            Prenotazione.objects.select_for_update(of=("self",))
            .select_related("fascia")
            .filter(pk=prenotazione_id)
            .first()
        )
        gia = Pagamento.objects.filter(stripe_sessione=sessione_id).select_related("prenotazione").first()
        if gia:
            return gia.prenotazione, "gia_registrato"
        if p is not None and p.scaduta:
            # Il blocco è scaduto ma il cliente ha pagato: va bene solo se i posti ci sono ancora
            try:
                servizi.assegna_gommone(p)
            except servizi.PostiNonDisponibili:
                _rimborso_automatico(p, None, sessione_id, importo, payment_intent, "posti presi da altri dopo la scadenza")
                p.delete()
                return None, "rimborsato"
        if p is None:
            _rimborso_automatico(None, prenotazione_id, sessione_id, importo, payment_intent, "prenotazione eliminata durante il pagamento")
            return None, "rimborsato"

        Pagamento.objects.create(
            prenotazione=p,
            tipo=Pagamento.Tipo.ACCONTO,
            metodo=Pagamento.Metodo.STRIPE,
            importo=importo,
            stripe_sessione=sessione_id,
            stripe_pagamento=payment_intent or "",
            registrato_da="Stripe",
        )
        p.scade_il = None
        p.confermata_il = timezone.now()
        p.save(update_fields=["scade_il", "confermata_il", "gommone", "aggiornata_il"])
        return p, "confermata"


def _rimborso_automatico(p, prenotazione_id, sessione_id, importo, payment_intent, motivo):
    rif = f"{p.codice} · {p.nome}" if p else f"prenotazione #{prenotazione_id} (eliminata)"
    log.warning("Rimborso automatico %s: %s", rif, motivo)
    rimborso_id = _rimborsa_su_stripe(payment_intent, importo, motivo)
    Pagamento.objects.create(
        riferimento=rif, tipo=Pagamento.Tipo.ACCONTO, metodo=Pagamento.Metodo.STRIPE, importo=importo,
        stripe_sessione=sessione_id, stripe_pagamento=payment_intent or "", registrato_da="Stripe",
    )
    Pagamento.objects.create(
        riferimento=rif, tipo=Pagamento.Tipo.RIMBORSO, metodo=Pagamento.Metodo.STRIPE, importo=importo,
        stripe_rimborso=rimborso_id, stripe_pagamento=payment_intent or "", registrato_da="Stripe",
        note=f"Rimborso automatico: {motivo}",
    )


def conferma_da_sessione(sessione):
    """Conferma a partire da una sessione Stripe (oggetto dell'evento o recuperata via API)."""
    if _campo(sessione, "payment_status") != "paid":
        return None, "non_pagato"
    metadata = _campo(sessione, "metadata", {})
    prenotazione_id = _campo(metadata, "prenotazione")
    if not prenotazione_id:
        return None, "sconosciuta"
    return conferma_pagamento(
        int(prenotazione_id),
        _campo(sessione, "id"),
        euro(_campo(sessione, "amount_total", 0)),
        _campo(sessione, "payment_intent"),
    )


def verifica_sessione(prenotazione):
    """Chiamata dal browser a pagamento finito: chiede a Stripe lo stato della sessione."""
    if not prenotazione.stripe_sessione:
        return prenotazione, "non_pagato"
    sessione = _client().v1.checkout.sessions.retrieve(prenotazione.stripe_sessione)
    return conferma_da_sessione(sessione)


def sessione_scaduta(sessione):
    """Webhook checkout.session.expired: il cliente non ha pagato, la prenotazione in attesa sparisce."""
    Prenotazione.objects.filter(stripe_sessione=_campo(sessione, "id"), scade_il__isnull=False).delete()


def annulla_attesa(prenotazione):
    """Il cliente chiude la finestra senza pagare: posti liberi subito."""
    if not prenotazione.in_attesa:
        return False
    if prenotazione.stripe_sessione and not settings.PAGAMENTI_SIMULATI:
        try:
            _client().v1.checkout.sessions.expire(prenotazione.stripe_sessione)
        except stripe.StripeError:
            # già scaduta o pagata nel frattempo: se è stata pagata, la conferma arriverà dal webhook
            log.info("Sessione %s non annullabile", prenotazione.stripe_sessione)
            return False
    prenotazione.delete()
    return True


def simula_pagamento(prenotazione):
    """Solo sviluppo senza chiavi: fa finta che Stripe abbia incassato l'acconto."""
    if not settings.PAGAMENTI_SIMULATI:
        raise ErrorePagamento("Pagamento simulato non disponibile.")
    return conferma_pagamento(
        prenotazione.pk, f"cs_simulata_{prenotazione.codice}", prenotazione.acconto_dovuto, f"pi_simulato_{prenotazione.codice}"
    )


# --------------------------------------------------------------------------
# 3. Pannello: rimborsi e movimenti registrati a mano
# --------------------------------------------------------------------------


def rimborsabile_stripe(prenotazione):
    pagato = Decimal("0")
    for p in prenotazione.pagamenti.filter(metodo=Pagamento.Metodo.STRIPE):
        pagato += -p.importo if p.tipo == Pagamento.Tipo.RIMBORSO else p.importo
    return max(pagato, Decimal("0"))


def _rimborsa_su_stripe(payment_intent, importo, motivo):
    if settings.PAGAMENTI_SIMULATI or not payment_intent or payment_intent.startswith("pi_simulato_"):
        return f"re_simulato_{timezone.now():%Y%m%d%H%M%S%f}"
    rimborso = _client().v1.refunds.create(
        params={"payment_intent": payment_intent, "amount": centesimi(importo), "metadata": {"motivo": motivo[:450]}}
    )
    return rimborso.id


@transaction.atomic
def rimborsa(prenotazione, importo, utente, motivo=""):
    """Restituisce al cliente (fino a) quanto pagato online, tramite Stripe."""
    importo = Decimal(importo)
    massimo = rimborsabile_stripe(prenotazione)
    if importo <= 0 or importo > massimo:
        raise ErrorePagamento(f"Si possono rimborsare al massimo {massimo} € pagati online.")
    acconto = prenotazione.pagamenti.filter(metodo=Pagamento.Metodo.STRIPE, tipo=Pagamento.Tipo.ACCONTO).first()
    try:
        rimborso_id = _rimborsa_su_stripe(acconto.stripe_pagamento if acconto else "", importo, motivo or "rimborso dal pannello")
    except stripe.StripeError as e:
        raise ErrorePagamento(f"Stripe ha rifiutato il rimborso: {e.user_message or e}") from e
    return Pagamento.objects.create(
        prenotazione=prenotazione, tipo=Pagamento.Tipo.RIMBORSO, metodo=Pagamento.Metodo.STRIPE, importo=importo,
        stripe_rimborso=rimborso_id, stripe_pagamento=acconto.stripe_pagamento if acconto else "",
        registrato_da=utente, note=motivo,
    )


def registra_movimento(prenotazione, tipo, metodo, importo, utente, note=""):
    if Decimal(importo) <= 0:
        raise ErrorePagamento("L'importo deve essere maggiore di zero.")
    return Pagamento.objects.create(
        prenotazione=prenotazione, tipo=tipo, metodo=metodo, importo=importo, registrato_da=utente, note=note
    )
