import hashlib
import hmac
import json
import time
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import stripe
from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from prenotazioni import pagamenti, servizi
from prenotazioni.models import Pagamento, Prenotazione

from .base import BaseTest


class PagamentoBase(BaseTest):
    def crea(self, persone=2, uscita="mattino", **extra):
        corpo = {
            "data": self.giorno.isoformat(), "uscita": uscita, "persone": persone, "nome": "Anna Verdi",
            "telefono": "+39 333 1112222", "email": "anna@example.com", "privacy": True,
        }
        corpo.update(extra)
        return self.client.post("/api/prenotazioni/", json.dumps(corpo), content_type="application/json")

    def post(self, url, **corpo):
        return self.client.post(url, json.dumps(corpo), content_type="application/json")


class FlussoSimulatoTest(PagamentoBase):
    """Senza chiavi Stripe (sviluppo) il flusso è identico, il pagamento è simulato."""

    def test_prenotazione_nasce_in_attesa_e_blocca_i_posti(self):
        r = self.crea(persone=4)
        self.assertEqual(r.status_code, 201, r.content)
        j = r.json()
        self.assertEqual(j["pagamento"]["modo"], "simulato")
        self.assertEqual(j["pagamento"]["acconto"], "80.00")  # 4 × 20 €
        self.assertFalse(j["confermata"])
        p = Prenotazione.objects.get(codice=j["codice"])
        self.assertTrue(p.in_attesa)
        self.assertEqual(self.occupati(self.g1), 4)  # i posti sono già tenuti

    def test_pagamento_simulato_conferma(self):
        j = self.crea(persone=2).json()
        r = self.post("/api/pagamento/simula/", token=j["pagamento"]["token"])
        esito = r.json()
        self.assertEqual(esito["stato"], "confermata")
        self.assertEqual((esito["pagato"], esito["saldo"]), ("40.00", "120.00"))
        p = Prenotazione.objects.get(codice=j["codice"])
        self.assertFalse(p.in_attesa)
        self.assertIsNotNone(p.confermata_il)
        acconto = p.pagamenti.get()
        self.assertEqual((acconto.tipo, acconto.metodo, acconto.importo), ("acconto", "stripe", Decimal("40.00")))
        self.assertEqual(p.da_incassare(), Decimal("120.00"))

    def test_annulla_libera_subito_i_posti(self):
        j = self.crea(persone=12).json()
        self.assertEqual(self.occupati(self.g1), 12)
        self.post("/api/pagamento/annulla/", token=j["pagamento"]["token"])
        self.assertFalse(Prenotazione.objects.filter(codice=j["codice"]).exists())
        self.assertEqual(self.occupati(self.g1), 0)

    def test_token_falso_non_tocca_nulla(self):
        j = self.crea().json()
        self.post("/api/pagamento/annulla/", token="falso")
        self.assertEqual(self.post("/api/pagamento/simula/", token="falso").status_code, 404)
        self.assertTrue(Prenotazione.objects.filter(codice=j["codice"]).exists())

    def test_blocco_scaduto_non_occupa_piu_posti(self):
        j = self.crea(persone=12).json()
        Prenotazione.objects.filter(codice=j["codice"]).update(scade_il=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.occupati(self.g1), 0)
        self.assertEqual(self.crea(persone=12).status_code, 201)

    def test_due_clienti_non_bloccano_gli_stessi_posti(self):
        self.crea(persone=12)
        self.crea(persone=12)
        r = self.crea(persone=1)
        self.assertEqual(r.status_code, 409)


class ConfermaTest(PagamentoBase):
    def in_attesa(self, persone=2):
        p = Prenotazione.objects.get(codice=self.crea(persone=persone).json()["codice"])
        return p

    def test_idempotente(self):
        p = self.in_attesa()
        for _ in range(3):
            pagamenti.conferma_pagamento(p.pk, "cs_test_1", Decimal("40"), "pi_1")
        self.assertEqual(Pagamento.objects.filter(stripe_sessione="cs_test_1").count(), 1)
        p.refresh_from_db()
        self.assertEqual(p.totale_pagato(), Decimal("40"))

    def test_pagamento_tardivo_con_posti_ancora_liberi(self):
        p = self.in_attesa()
        Prenotazione.objects.filter(pk=p.pk).update(scade_il=timezone.now() - timedelta(minutes=5))
        trovata, esito = pagamenti.conferma_pagamento(p.pk, "cs_tardi", Decimal("40"), "pi_t")
        self.assertEqual(esito, "confermata")
        self.assertFalse(trovata.in_attesa)

    def test_pagamento_tardivo_senza_posti_viene_rimborsato(self):
        p = self.in_attesa(persone=12)
        Prenotazione.objects.filter(pk=p.pk).update(scade_il=timezone.now() - timedelta(minutes=5))
        self.prenota(12)
        self.prenota(12)  # nel frattempo l'uscita si è riempita
        trovata, esito = pagamenti.conferma_pagamento(p.pk, "cs_tardi", Decimal("240"), "pi_t")
        self.assertEqual((trovata, esito), (None, "rimborsato"))
        self.assertFalse(Prenotazione.objects.filter(pk=p.pk).exists())
        movimenti = Pagamento.objects.filter(stripe_pagamento="pi_t").order_by("tipo")
        self.assertEqual([(m.tipo, m.importo) for m in movimenti], [("acconto", Decimal("240")), ("rimborso", Decimal("240"))])
        self.assertIn(p.codice, movimenti[0].riferimento)

    def test_prenotazione_eliminata_durante_il_pagamento(self):
        p = self.in_attesa()
        pk = p.pk
        p.delete()
        trovata, esito = pagamenti.conferma_pagamento(pk, "cs_orfana", Decimal("40"), "pi_o")
        self.assertEqual(esito, "rimborsato")
        self.assertEqual(Pagamento.objects.filter(tipo="rimborso", stripe_pagamento="pi_o").count(), 1)

    def test_sessione_non_pagata_non_conferma(self):
        p = self.in_attesa()
        sessione = {"id": "cs_x", "payment_status": "unpaid", "metadata": {"prenotazione": str(p.pk)}, "amount_total": 4000}
        self.assertEqual(pagamenti.conferma_da_sessione(sessione), (None, "non_pagato"))
        p.refresh_from_db()
        self.assertTrue(p.in_attesa)


@override_settings(STRIPE_WEBHOOK_SECRET="whsec_prova")
class WebhookTest(PagamentoBase):
    def invia(self, evento, segreto="whsec_prova"):
        corpo = json.dumps(evento)
        ts = int(time.time())
        firma = hmac.new(segreto.encode(), f"{ts}.{corpo}".encode(), hashlib.sha256).hexdigest()
        return self.client.post(
            "/stripe/webhook/", corpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=f"t={ts},v1={firma}"
        )

    def evento(self, tipo, p, pagato=True):
        return {
            "id": "evt_1", "object": "event", "type": tipo,
            "data": {"object": {
                "id": "cs_wh_1", "object": "checkout.session", "payment_status": "paid" if pagato else "unpaid",
                "amount_total": 4000, "payment_intent": "pi_wh_1", "metadata": {"prenotazione": str(p.pk), "codice": p.codice},
            }},
        }

    def test_completed_conferma(self):
        p = Prenotazione.objects.get(codice=self.crea().json()["codice"])
        r = self.invia(self.evento("checkout.session.completed", p))
        self.assertEqual(r.status_code, 200)
        p.refresh_from_db()
        self.assertFalse(p.in_attesa)
        self.assertEqual(p.pagamenti.get().stripe_pagamento, "pi_wh_1")
        # Stripe ripete la notifica: nessun doppione
        self.invia(self.evento("checkout.session.completed", p))
        self.assertEqual(p.pagamenti.count(), 1)

    def test_firma_sbagliata_rifiutata(self):
        p = Prenotazione.objects.get(codice=self.crea().json()["codice"])
        r = self.invia(self.evento("checkout.session.completed", p), segreto="whsec_altro")
        self.assertEqual(r.status_code, 400)
        p.refresh_from_db()
        self.assertTrue(p.in_attesa)

    def test_expired_libera_i_posti(self):
        p = Prenotazione.objects.get(codice=self.crea(persone=6).json()["codice"])
        Prenotazione.objects.filter(pk=p.pk).update(stripe_sessione="cs_wh_1")
        self.invia(self.evento("checkout.session.expired", p, pagato=False))
        self.assertFalse(Prenotazione.objects.filter(pk=p.pk).exists())


def sessione_finta(**extra):
    return SimpleNamespace(id="cs_test_abc", client_secret="cs_test_abc_secret_xyz", **extra)


@override_settings(PAGAMENTI_SIMULATI=False, STRIPE_SECRET_KEY="sk_test_x", STRIPE_PUBLISHABLE_KEY="pk_test_x")
class StripeTest(PagamentoBase):
    """Modalità vera: le chiamate a Stripe sono sostituite da un client finto."""

    def test_crea_sessione_incorporata_con_i_parametri_giusti(self):
        client = mock.MagicMock()
        client.v1.checkout.sessions.create.return_value = sessione_finta()
        with mock.patch.object(pagamenti, "_client", return_value=client):
            j = self.crea(persone=3).json()
        params = client.v1.checkout.sessions.create.call_args.kwargs["params"]
        self.assertEqual(params["ui_mode"], "embedded_page")
        self.assertEqual(params["redirect_on_completion"], "if_required")
        self.assertEqual(params["line_items"][0]["quantity"], 3)
        self.assertEqual(params["line_items"][0]["price_data"]["unit_amount"], 2000)
        self.assertEqual(params["line_items"][0]["price_data"]["currency"], "eur")
        self.assertIn("{CHECKOUT_SESSION_ID}", params["return_url"])
        self.assertGreaterEqual(params["expires_at"] - time.time(), 30 * 60)  # minimo richiesto da Stripe
        self.assertEqual(j["pagamento"]["client_secret"], "cs_test_abc_secret_xyz")
        self.assertEqual(j["pagamento"]["chiave_pubblica"], "pk_test_x")
        self.assertEqual(Prenotazione.objects.get(codice=j["codice"]).stripe_sessione, "cs_test_abc")

    def test_errore_stripe_libera_i_posti(self):
        client = mock.MagicMock()
        client.v1.checkout.sessions.create.side_effect = stripe.APIConnectionError("rete giù")
        with mock.patch.object(pagamenti, "_client", return_value=client):
            r = self.crea(persone=12)
        self.assertEqual(r.status_code, 503)
        self.assertEqual(Prenotazione.objects.count(), 0)
        self.assertEqual(self.occupati(self.g1), 0)

    def test_verifica_dal_browser_chiede_a_stripe(self):
        client = mock.MagicMock()
        client.v1.checkout.sessions.create.return_value = sessione_finta()
        with mock.patch.object(pagamenti, "_client", return_value=client):
            j = self.crea().json()
            p = Prenotazione.objects.get(codice=j["codice"])
            client.v1.checkout.sessions.retrieve.return_value = {
                "id": "cs_test_abc", "payment_status": "paid", "amount_total": 4000,
                "payment_intent": "pi_abc", "metadata": {"prenotazione": str(p.pk)},
            }
            r = self.post("/api/pagamento/verifica/", token=j["pagamento"]["token"])
        self.assertEqual(r.json()["stato"], "confermata")
        self.assertEqual(r.json()["pagato"], "40.00")

    def test_esito_al_ritorno_con_redirect(self):
        client = mock.MagicMock()
        client.v1.checkout.sessions.create.return_value = sessione_finta()
        with mock.patch.object(pagamenti, "_client", return_value=client):
            p = Prenotazione.objects.get(codice=self.crea().json()["codice"])
            client.v1.checkout.sessions.retrieve.return_value = {
                "id": "cs_test_abc", "payment_status": "paid", "amount_total": 4000,
                "payment_intent": "pi_abc", "metadata": {"prenotazione": str(p.pk)},
            }
            r = self.client.get("/api/pagamento/esito/", {"sessione": "cs_test_abc"})
        self.assertEqual(r.json()["stato"], "confermata")

    def test_rimborso_dal_pannello_chiama_stripe(self):
        p = self.prenota(2)
        Pagamento.objects.create(prenotazione=p, tipo="acconto", metodo="stripe", importo=40, stripe_sessione="cs_r", stripe_pagamento="pi_r")
        client = mock.MagicMock()
        client.v1.refunds.create.return_value = SimpleNamespace(id="re_123")
        with mock.patch.object(pagamenti, "_client", return_value=client):
            pagamenti.rimborsa(p, Decimal("40"), "salvatore", "meteo")
        params = client.v1.refunds.create.call_args.kwargs["params"]
        self.assertEqual((params["payment_intent"], params["amount"]), ("pi_r", 4000))
        self.assertEqual(p.totale_pagato(), Decimal("0"))
        with self.assertRaises(pagamenti.ErrorePagamento):
            pagamenti.rimborsa(p, Decimal("1"), "salvatore")  # già rimborsato tutto


class PannelloPagamentiTest(PagamentoBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(User.objects.create_superuser("salvatore", "s@example.com", "password-di-prova"))

    def pagata(self, persone=2):
        p = self.prenota(persone)
        Pagamento.objects.create(prenotazione=p, tipo="acconto", metodo="stripe", importo=20 * persone, stripe_sessione=f"cs_{p.pk}")
        return p

    def test_elenco_mostra_pagato_e_da_incassare(self):
        self.pagata(2)
        r = self.client.get(reverse("admin:prenotazioni_prenotazione_changelist"))
        self.assertContains(r, "Da incassare")
        self.assertContains(r, "40 €")
        self.assertContains(r, "120 €")

    def test_registra_saldo(self):
        p = self.pagata(2)
        url = reverse("admin:prenotazioni_prenotazione_registra_incasso", args=[p.pk])
        r = self.client.post(url, {"incasso-_form_submitted": "1", "incasso-tipo": "saldo", "incasso-metodo": "contanti", "incasso-importo": "120", "incasso-note": ""}, HTTP_HX_REQUEST="true")
        self.assertEqual(r.headers.get("HX-Redirect"), reverse("admin:prenotazioni_prenotazione_change", args=[p.pk]))
        self.assertEqual(p.da_incassare(), Decimal("0"))
        self.assertEqual(p.pagamenti.get(tipo="saldo").registrato_da, "salvatore")

    def test_rimborso_simulato_dal_pannello(self):
        p = self.pagata(2)
        url = reverse("admin:prenotazioni_prenotazione_rimborsa_stripe", args=[p.pk])
        self.client.post(url, {"rimborso-_form_submitted": "1", "rimborso-importo": "40", "rimborso-motivo": "meteo"}, HTTP_HX_REQUEST="true")
        self.assertEqual(p.totale_pagato(), Decimal("0"))

    def test_eliminare_la_prenotazione_conserva_i_movimenti(self):
        p = self.pagata(2)
        codice = p.codice
        p.delete()
        movimento = Pagamento.objects.get()
        self.assertIsNone(movimento.prenotazione)
        self.assertIn(codice, movimento.riferimento)
        r = self.client.get(reverse("admin:prenotazioni_pagamento_changelist"))
        self.assertContains(r, codice)

    def test_filtri_pagamenti(self):
        saldata = self.pagata(2)
        Pagamento.objects.create(prenotazione=saldata, tipo="saldo", metodo="pos", importo=120)
        da_saldare = self.pagata(3)
        abbandonata = self.prenota(1)
        Prenotazione.objects.filter(pk=abbandonata.pk).update(scade_il=timezone.now() - timedelta(hours=1))
        url = reverse("admin:prenotazioni_prenotazione_changelist")
        self.assertNotContains(self.client.get(url), abbandonata.codice)  # di norma nascoste
        self.assertContains(self.client.get(url, {"pagamenti": "abbandonate"}), abbandonata.codice)
        r = self.client.get(url, {"pagamenti": "da_incassare"})
        self.assertContains(r, da_saldare.codice)
        self.assertNotContains(r, saldata.codice)
        self.assertContains(self.client.get(url, {"pagamenti": "saldate"}), saldata.codice)

    def test_lista_d_imbarco_con_importi(self):
        self.pagata(2)
        attesa = Prenotazione.objects.get(codice=self.crea(persone=1).json()["codice"])
        r = self.client.get(reverse("admin:prenotazioni_uscita", args=[self.giorno.isoformat(), self.mattino.pk]))
        self.assertContains(r, "Da incassare all")
        self.assertContains(r, "120 €")
        self.assertContains(r, "pagamento in corso")
        self.assertContains(r, attesa.nome)

    def test_pagine_si_aprono(self):
        p = self.pagata(2)
        for url in (
            reverse("admin:prenotazioni_prenotazione_change", args=[p.pk]),
            reverse("admin:prenotazioni_prenotazione_registra_incasso", args=[p.pk]),
            reverse("admin:prenotazioni_prenotazione_rimborsa_stripe", args=[p.pk]),
            reverse("admin:prenotazioni_pagamento_changelist"),
            reverse("admin:prenotazioni_pagamento_change", args=[p.pagamenti.get().pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_inserimento_dal_pannello_resta_confermato(self):
        p = self.prenota(2)
        self.assertFalse(p.in_attesa)
        self.assertIsNotNone(p.confermata_il)
        self.assertEqual(servizi.stato_uscita(self.giorno, self.mattino).posti_liberi, 22)
