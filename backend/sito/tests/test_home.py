from decimal import Decimal

from django.test import TestCase

from prenotazioni.models import Fascia


class HomeTest(TestCase):
    def test_homepage(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("csrftoken", r.cookies)
        self.assertContains(r, 'data-prenota="mattino"')
        self.assertContains(r, 'id="prenotazione"')
        self.assertContains(r, 'data-api-prenota="/api/prenotazioni/"')
        self.assertContains(r, "12 persone")
        # nessun pezzo di template lasciato come testo (es. commenti {# #} su più righe)
        for residuo in ("{%", "%}", "{#", "#}", "{{", "}}"):
            self.assertNotContains(r, residuo)

    def test_prezzi_e_orari_dal_pannello(self):
        Fascia.objects.filter(codice="mattino").update(prezzo_persona=Decimal("85"), orario="8:45")
        r = self.client.get("/")
        self.assertContains(r, "85 €")
        self.assertContains(r, "Partenza 8:45")
        self.assertNotContains(r, "80 €")
        self.assertContains(r, "da</small><b>70 €")  # barra mobile: prezzo più basso

    def test_uscita_disattivata_sparisce(self):
        Fascia.objects.filter(codice="pomeriggio").update(attiva=False)
        r = self.client.get("/")
        self.assertNotContains(r, 'data-prenota="pomeriggio"')
        self.assertNotContains(r, 'value="pomeriggio"')
