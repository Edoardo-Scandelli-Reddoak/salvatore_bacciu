import json
from datetime import date, datetime, time, timedelta
from unittest import mock

from django.test import Client
from django.utils import timezone

from prenotazioni.models import Prenotazione

from .base import BaseTest


class ApiTest(BaseTest):
    def post(self, **dati):
        corpo = {"data": self.giorno.isoformat(), "uscita": "mattino", "persone": 2,
                 "nome": "Mario Rossi", "telefono": "+39 333 0000000", "email": "mario@example.com",
                 "privacy": True}
        corpo.update(dati)
        return self.client.post("/api/prenotazioni/", json.dumps(corpo), content_type="application/json")

    def test_disponibilita(self):
        self.prenota(10)
        r = self.client.get("/api/disponibilita/", {"data": self.giorno.isoformat()})
        self.assertEqual(r.status_code, 200)
        mattino = next(u for u in r.json()["uscite"] if u["uscita"] == "mattino")
        self.assertEqual(mattino["posti_liberi"], 14)
        self.assertEqual(mattino["max_persone"], 12)
        self.assertEqual(mattino["prezzo_persona"], "80.00")
        self.assertIn("csrftoken", r.cookies)

    def test_disponibilita_fuori_stagione(self):
        r = self.client.get("/api/disponibilita/", {"data": date(self.giorno.year, 10, 10).isoformat()})
        self.assertFalse(r.json()["prenotabile"])
        self.assertEqual(r.json()["uscite"], [])

    def test_calendario(self):
        self.prenota(12)
        self.prenota(12)
        r = self.client.get("/api/calendario/", {"mese": f"{self.giorno.year}-07"})
        giorni = r.json()["giorni"]
        self.assertEqual(len(giorni), 31)
        self.assertEqual(giorni[self.giorno.isoformat()], {"mattino": 0, "pomeriggio": 12})

    def test_crea(self):
        r = self.post(persone=3)
        self.assertEqual(r.status_code, 201, r.content)
        p = Prenotazione.objects.get(codice=r.json()["codice"])
        self.assertEqual((p.canale, p.gommone, p.importo), ("sito", self.g1, 240))

    def test_crea_completa_409(self):
        self.prenota(10)
        self.prenota(10)
        r = self.post(persone=3)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["max_persone"], 2)

    def test_validazioni(self):
        self.assertEqual(self.post(email="non-una-mail").status_code, 400)
        self.assertEqual(self.post(nome="").status_code, 400)
        self.assertEqual(self.post(uscita="sera").status_code, 400)
        self.assertEqual(self.post(persone=0).status_code, 400)
        ieri = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.assertEqual(self.post(data=ieri).status_code, 400)
        self.assertEqual(Prenotazione.objects.count(), 0)

    def test_niente_esclusiva_dal_sito(self):
        r = self.post(esclusiva=True)
        p = Prenotazione.objects.get(codice=r.json()["codice"])
        self.assertFalse(p.esclusiva)

    def test_csrf_obbligatorio(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post("/api/prenotazioni/", "{}", content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_privacy_obbligatoria(self):
        r = self.post(privacy=False)
        self.assertEqual((r.status_code, r.json()["campo"]), (400, "privacy"))

    def test_campo_trappola(self):
        self.assertEqual(self.post(sito_web="http://spam.example").status_code, 400)
        self.assertEqual(Prenotazione.objects.count(), 0)

    def test_telefono_troppo_corto(self):
        self.assertEqual(self.post(telefono="123").json()["campo"], "telefono")

    def test_risposta_completa(self):
        j = self.post(persone=3).json()
        self.assertEqual((j["nome_uscita"], j["orario"], j["importo"], j["email"]), ("Mattino", "8:30", "240.00", "mario@example.com"))


class LimiteOrarioTest(ApiTest):
    """Il giorno stesso il sito smette di accettare un'uscita dopo l'ora limite (mattino 8:00)."""

    def adesso(self, ora):
        momento = timezone.make_aware(datetime.combine(self.giorno, ora))
        return mock.patch("prenotazioni.servizi.timezone.localtime", return_value=momento)

    def test_prima_del_limite_si_prenota(self):
        with self.adesso(time(7, 30)):
            self.assertEqual(self.post().status_code, 201)

    def test_dopo_il_limite_no(self):
        with self.adesso(time(9, 0)):
            r = self.post()
            self.assertEqual(r.status_code, 400)
            self.assertIn("chiuse", r.json()["errore"])
            # il pomeriggio invece è ancora aperto
            self.assertEqual(self.post(uscita="pomeriggio").status_code, 201)
            disp = {u["uscita"]: u for u in self.client.get("/api/disponibilita/", {"data": self.giorno.isoformat()}).json()["uscite"]}
            self.assertFalse(disp["mattino"]["prenotabile"])
            self.assertEqual(disp["mattino"]["max_persone"], 0)
            self.assertTrue(disp["pomeriggio"]["prenotabile"])
            cal = self.client.get("/api/calendario/", {"mese": f"{self.giorno:%Y-%m}"}).json()["giorni"]
            self.assertEqual(cal[self.giorno.isoformat()]["mattino"], 0)
