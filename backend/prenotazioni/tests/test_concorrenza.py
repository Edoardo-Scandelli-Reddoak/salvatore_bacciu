import threading
import unittest
from datetime import date

from django.db import connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from prenotazioni import servizi
from prenotazioni.models import Fascia, Gommone, Prenotazione


@unittest.skipUnless(connection.vendor == "postgresql", "Il lock FOR UPDATE si verifica solo su Postgres")
class ConcorrenzaTest(TransactionTestCase):
    """Molte prenotazioni nello stesso istante non devono mai superare la capienza."""

    def setUp(self):
        self.giorno = date(timezone.localdate().year + 1, 8, 10)
        self.fascia = Fascia.objects.create(codice="t", nome="Test", orario="9", durata_ore=1, prezzo_persona=10)
        Gommone.objects.all().delete()
        Gommone.objects.create(nome="A", capienza=12, ordine=1)
        Gommone.objects.create(nome="B", capienza=12, ordine=2)

    def lancia(self, n_richieste, persone):
        via = threading.Barrier(n_richieste)
        esiti = []

        def richiesta(i):
            try:
                via.wait()
                servizi.crea_prenotazione(data=self.giorno, fascia=self.fascia, persone=persone, nome=f"c{i}")
                esiti.append(True)
            except servizi.PostiNonDisponibili:
                esiti.append(False)
            finally:
                connections.close_all()

        thread = [threading.Thread(target=richiesta, args=(i,)) for i in range(n_richieste)]
        for t in thread:
            t.start()
        for t in thread:
            t.join()
        return esiti

    def test_singoli_in_parallelo(self):
        esiti = self.lancia(40, 1)
        self.assertEqual(sum(esiti), 24)
        stato = servizi.stato_uscita(self.giorno, self.fascia)
        self.assertEqual([g.occupati for g in stato.gommoni], [12, 12])

    def test_gruppi_in_parallelo(self):
        # Gruppi da 5: ne entrano 2 per gommone (10/12), quindi 4 in tutto
        esiti = self.lancia(12, 5)
        self.assertEqual(sum(esiti), 4)
        stato = servizi.stato_uscita(self.giorno, self.fascia)
        self.assertTrue(all(g.occupati <= g.capienza for g in stato.gommoni))
        self.assertEqual(Prenotazione.objects.count(), 4)
