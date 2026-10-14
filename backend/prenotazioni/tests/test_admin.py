from unittest import mock

from django.contrib.auth.models import User
from django.urls import reverse

from prenotazioni.models import Chiusura, Prenotazione

from .base import BaseTest


class AdminTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.utente = User.objects.create_superuser("salvatore", "s@example.com", "password-di-prova")
        self.client.force_login(self.utente)
        self.url_add = reverse("admin:prenotazioni_prenotazione_add")

    def dati(self, **extra):
        d = {
            "data": self.giorno.strftime("%d/%m/%Y"),
            "fascia": self.mattino.pk,
            "persone": 2,
            "nome": "Prenotazione telefonica",
            "telefono": "333",
            "email": "",
            "note": "",
            "importo": "",
            "gommone": "",
            "canale": "telefono",
            # campi di gestione della tabella dei movimenti (inline), come li manda il browser
            "pagamenti-TOTAL_FORMS": "0",
            "pagamenti-INITIAL_FORMS": "0",
            "pagamenti-MIN_NUM_FORMS": "0",
            "pagamenti-MAX_NUM_FORMS": "1000",
        }
        d.update(extra)
        return d

    def test_pagine_si_aprono(self):
        self.prenota(5)
        Chiusura.objects.create(data=self.giorno, fascia=self.pomeriggio, motivo="Vento")
        for url in (
            reverse("admin:index"),
            reverse("admin:prenotazioni_disponibilita") + f"?mese={self.giorno:%Y-%m}",
            reverse("admin:prenotazioni_disponibilita"),
            reverse("admin:prenotazioni_uscita", args=[self.giorno.isoformat(), self.mattino.pk]),
            reverse("admin:prenotazioni_uscita", args=[self.giorno.isoformat(), self.pomeriggio.pk]),
            reverse("admin:prenotazioni_prenotazione_changelist"),
            self.url_add,
            self.url_add + f"?data={self.giorno:%d/%m/%Y}&fascia={self.mattino.pk}",
            reverse("admin:prenotazioni_chiusura_changelist"),
            reverse("admin:prenotazioni_gommone_changelist"),
            reverse("admin:prenotazioni_fascia_changelist"),
            reverse("admin:auth_user_changelist"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_inserimento_manuale_assegna_automaticamente(self):
        self.prenota(10)
        r = self.client.post(self.url_add, self.dati(persone=3))
        self.assertEqual(r.status_code, 302)
        p = Prenotazione.objects.get(nome="Prenotazione telefonica")
        self.assertEqual((p.gommone, p.importo, p.canale), (self.g2, 240, "telefono"))

    def test_inserimento_manuale_rifiutato_se_pieno(self):
        self.prenota(12)
        self.prenota(12)
        r = self.client.post(self.url_add, self.dati())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Uscita al completo")
        self.assertFalse(Prenotazione.objects.filter(nome="Prenotazione telefonica").exists())

    def test_gommone_scelto_che_non_basta(self):
        self.prenota(11)
        r = self.client.post(self.url_add, self.dati(gommone=self.g1.pk))
        self.assertContains(r, "restano 1 posti")

    def test_modifica_tiene_il_gommone_se_ci_sta(self):
        p = self.prenota(2)
        url = reverse("admin:prenotazioni_prenotazione_change", args=[p.pk])
        r = self.client.post(url, self.dati(nome=p.nome, persone=4, gommone=self.g1.pk))
        self.assertEqual(r.status_code, 302)
        p.refresh_from_db()
        self.assertEqual((p.persone, p.gommone), (4, self.g1))

    def test_modifica_sposta_se_non_ci_sta_piu(self):
        p = self.prenota(2)
        self.prenota(9)  # primo gommone: 11/12
        url = reverse("admin:prenotazioni_prenotazione_change", args=[p.pk])
        r = self.client.post(url, self.dati(nome=p.nome, persone=5, gommone=self.g1.pk), follow=True)
        p.refresh_from_db()
        self.assertEqual((p.persone, p.gommone), (5, self.g2))
        self.assertContains(r, "spostato su Gommone 2")

    def test_elimina_dall_elenco_libera_i_posti(self):
        p = self.prenota(12)
        url = reverse("admin:prenotazioni_prenotazione_changelist")
        r = self.client.post(url, {"action": "delete_selected", "_selected_action": [p.pk], "post": "yes"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Prenotazione.objects.filter(pk=p.pk).exists())
        self.assertEqual(self.stato().posti_liberi, 24)

    def test_niente_stato(self):
        r = self.client.get(self.url_add)
        self.assertNotContains(r, 'name="stato"')

    def test_colonna_prenotata_il(self):
        self.prenota(2)
        r = self.client.get(reverse("admin:prenotazioni_prenotazione_changelist"))
        self.assertContains(r, "Prenotata il")
        self.assertContains(r, "Data uscita")

    def test_menu_evidenzia_una_sola_voce(self):
        from django.conf import settings

        voci = {i["title"]: i["active"] for g in settings.UNFOLD["SIDEBAR"]["navigation"] for i in g["items"] if "active" in i}

        def attive(url):
            richiesta = self.client.get(url).wsgi_request
            return sorted(str(k) for k, f in voci.items() if f(richiesta))

        self.assertEqual(attive(reverse("admin:prenotazioni_disponibilita")), ["Calendario disponibilità"])
        self.assertEqual(
            attive(reverse("admin:prenotazioni_uscita", args=[self.giorno.isoformat(), self.mattino.pk])),
            ["Calendario disponibilità"],
        )
        self.assertEqual(attive(reverse("admin:prenotazioni_prenotazione_changelist")), ["Tutte le prenotazioni"])
        self.assertEqual(attive(self.url_add), ["Nuova prenotazione"])
        self.assertEqual(attive(reverse("admin:index")), ["Oggi e prossimi giorni"])


class VerificaDalVivoTest(AdminTest):
    """Il form chiede a /verifica/ se il gruppo entra, mentre lo si compila."""

    def verifica(self, **q):
        base = {"data": self.giorno.strftime("%d/%m/%Y"), "fascia": self.pomeriggio.pk, "persone": 2}
        base.update(q)
        return self.client.get(reverse("admin:prenotazioni_verifica"), base).json()

    def test_c_e_posto(self):
        self.prenota(9, fascia=self.pomeriggio)
        j = self.verifica(persone=3)
        self.assertEqual((j["ok"], j["gommone"], j["max_persone"]), (True, "Gommone 1", 12))
        self.assertEqual([g["occupati"] for g in j["gommoni"]], [9, 0])

    def test_gommone_scelto_che_non_basta(self):
        # Il caso dello screenshot: Gommone 1 già a 9/12, si chiedono 11 persone lì sopra
        self.prenota(9, fascia=self.pomeriggio)
        j = self.verifica(persone=11, gommone=self.g1.pk)
        self.assertFalse(j["ok"])
        self.assertIn("restano 3 posti", j["errore"])

    def test_modifica_conta_senza_se_stessa(self):
        p = self.prenota(3, fascia=self.pomeriggio)
        self.prenota(6, fascia=self.pomeriggio)
        j = self.verifica(persone=11, gommone=self.g1.pk, pk=p.pk)
        # senza se stessa sul Gommone 1 restano 6 occupati: 11 non ci stanno, ma il gommone
        # è quello di prima → si sposta sul Gommone 2
        self.assertEqual((j["ok"], j["gommone"], j["spostata"]), (True, "Gommone 2", True))

    def test_uscita_piena(self):
        self.prenota(12, fascia=self.pomeriggio)
        self.prenota(12, fascia=self.pomeriggio)
        j = self.verifica(persone=1)
        self.assertFalse(j["ok"])
        self.assertEqual(j["posti_liberi"], 0)

    def test_dati_incompleti(self):
        self.assertFalse(self.verifica(persone="")["completo"])
        self.assertFalse(self.verifica(data="non-una-data")["completo"])

    def test_salvataggio_rifiutato_con_messaggio_su_persone(self):
        self.prenota(9, fascia=self.pomeriggio)
        r = self.client.post(self.url_add, self.dati(fascia=self.pomeriggio.pk, persone=11, gommone=self.g1.pk))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "restano 3 posti")
        self.assertEqual(Prenotazione.objects.filter(nome="Prenotazione telefonica").count(), 0)

    def test_chiusura_avvisa_se_ci_sono_prenotazioni(self):
        self.prenota(3)
        r = self.client.post(
            reverse("admin:prenotazioni_chiusura_add"),
            {"data": self.giorno.strftime("%d/%m/%Y"), "fascia": "", "gommone": "", "motivo": "Mare mosso"},
            follow=True,
        )
        self.assertContains(r, "1 prenotazioni rientrano in questa chiusura")

    def test_dashboard_in_stagione_mostra_oggi(self):
        self.prenota(5)
        with mock.patch("prenotazioni.admin_views.timezone.localdate", return_value=self.giorno):
            r = self.client.get(reverse("admin:index"))
        self.assertContains(r, "5 a bordo")
        self.assertContains(r, "Prossimi 14 giorni")
        self.assertNotContains(r, "fuori stagione")

    def test_dashboard_fuori_stagione_mostra_la_prossima(self):
        fuori = self.giorno.replace(month=10, day=7)
        with mock.patch("prenotazioni.admin_views.timezone.localdate", return_value=fuori):
            r = self.client.get(reverse("admin:index"))
        self.assertContains(r, f"Inizio stagione: dal 1 maggio {fuori.year + 1}")
        self.assertNotContains(r, "a bordo")

    def test_interfaccia_in_italiano(self):
        r = self.client.get(reverse("admin:prenotazioni_prenotazione_changelist"))
        self.assertContains(r, "Filtri")
        self.assertNotContains(r, "Type to search")
