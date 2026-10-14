from datetime import date

from django.test import TestCase
from django.utils import timezone

from prenotazioni import servizi
from prenotazioni.models import Fascia, Gommone, Prenotazione


class BaseTest(TestCase):
    """Usa le uscite e i gommoni creati dalla migrazione 0002 (2 × 12 posti)."""

    def setUp(self):
        self.giorno = date(timezone.localdate().year + 1, 7, 15)
        self.mattino = Fascia.objects.get(codice="mattino")
        self.pomeriggio = Fascia.objects.get(codice="pomeriggio")
        self.g1 = Gommone.objects.get(nome="Gommone 1")
        self.g2 = Gommone.objects.get(nome="Gommone 2")

    def prenota(self, persone, fascia=None, giorno=None, **extra):
        return servizi.crea_prenotazione(
            data=giorno or self.giorno,
            fascia=fascia or self.mattino,
            persone=persone,
            nome=extra.pop("nome", f"Gruppo da {persone}"),
            **extra,
        )

    def stato(self, fascia=None):
        return servizi.stato_uscita(self.giorno, fascia or self.mattino)

    def occupati(self, gommone, fascia=None):
        s = next(s for s in self.stato(fascia).gommoni if s.gommone == gommone)
        return s.occupati
