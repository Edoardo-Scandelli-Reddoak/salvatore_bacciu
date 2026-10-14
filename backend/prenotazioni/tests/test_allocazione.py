from prenotazioni import servizi
from prenotazioni.models import Chiusura, Prenotazione

from .base import BaseTest


class AssegnazioneTest(BaseTest):
    def test_riempie_prima_il_primo_gommone(self):
        for n in (4, 3, 2):
            self.assertEqual(self.prenota(n).gommone, self.g1)
        self.assertEqual(self.occupati(self.g1), 9)
        self.assertEqual(self.occupati(self.g2), 0)

    def test_gruppo_che_non_entra_passa_al_secondo(self):
        # Caso del cliente: 10/12 sul primo, arriva un gruppo da 3
        self.prenota(10)
        p = self.prenota(3)
        self.assertEqual(p.gommone, self.g2)
        self.assertEqual(self.occupati(self.g1), 10)
        self.assertEqual(self.occupati(self.g2), 3)

    def test_chi_entra_ancora_nel_primo_lo_riempie(self):
        self.prenota(10)
        self.prenota(3)  # va sul secondo
        p = self.prenota(2)  # entra nei 2 posti rimasti sul primo
        self.assertEqual(p.gommone, self.g1)
        self.assertEqual(self.occupati(self.g1), 12)

    def test_best_fit_sceglie_il_gommone_piu_pieno(self):
        # Primo con 6 liberi, secondo con 3 liberi: un gruppo da 3 va sul secondo
        # e lascia intatti i 6 posti del primo per un gruppo più grande
        self.prenota(6)
        self.prenota(9)  # non entra nel primo (6 liberi) → secondo
        p = self.prenota(3)
        self.assertEqual(p.gommone, self.g2)
        self.assertEqual(self.stato().max_persone, 6)

    def test_gruppo_mai_diviso(self):
        self.prenota(10)
        self.prenota(10)
        # 4 posti liberi in totale ma 2+2: un gruppo da 3 non entra
        stato = self.stato()
        self.assertEqual(stato.posti_liberi, 4)
        self.assertEqual(stato.max_persone, 2)
        with self.assertRaises(servizi.PostiNonDisponibili) as ctx:
            self.prenota(3)
        self.assertEqual(ctx.exception.max_persone, 2)

    def test_uscita_piena_rifiuta(self):
        self.prenota(12)
        self.prenota(12)
        self.assertEqual(self.stato().posti_liberi, 0)
        with self.assertRaises(servizi.PostiNonDisponibili):
            self.prenota(1)
        self.assertEqual(Prenotazione.objects.count(), 2)

    def test_gruppo_piu_grande_di_un_gommone(self):
        with self.assertRaises(servizi.PostiNonDisponibili):
            self.prenota(13)

    def test_mattino_e_pomeriggio_indipendenti(self):
        self.prenota(12)
        self.prenota(12)
        p = self.prenota(12, fascia=self.pomeriggio)
        self.assertEqual(p.gommone, self.g1)

    def test_eliminata_libera_i_posti(self):
        p = self.prenota(12)
        self.prenota(12)
        p.delete()
        self.assertEqual(self.prenota(5).gommone, self.g1)

    def test_esclusiva_occupa_tutto_il_gommone(self):
        p = self.prenota(4, esclusiva=True)
        self.assertEqual(p.gommone, self.g1)
        self.assertEqual(self.occupati(self.g1), 12)
        # Il resto va sul secondo, anche un gruppo piccolo
        self.assertEqual(self.prenota(2).gommone, self.g2)

    def test_esclusiva_richiede_un_gommone_vuoto(self):
        self.prenota(2)
        self.prenota(2, esclusiva=True)  # secondo gommone, vuoto
        with self.assertRaises(servizi.PostiNonDisponibili):
            self.prenota(2, esclusiva=True)

    def test_importo_calcolato(self):
        self.assertEqual(self.prenota(3).importo, 240)  # 3 × 80 €
        self.assertEqual(self.prenota(2, fascia=self.pomeriggio).importo, 140)
        self.assertIsNone(self.prenota(4, esclusiva=True).importo)

    def test_gommone_scelto_a_mano(self):
        p = Prenotazione(data=self.giorno, fascia=self.mattino, persone=2, nome="x")
        servizi.assegna_gommone(p, preferito=self.g2)
        self.assertEqual(p.gommone, self.g2)
        self.prenota(11)  # va sul primo
        p = Prenotazione(data=self.giorno, fascia=self.mattino, persone=2, nome="y")
        with self.assertRaises(servizi.PostiNonDisponibili):
            servizi.assegna_gommone(p, preferito=self.g1)


class ChiusureTest(BaseTest):
    def test_chiusura_giornata(self):
        Chiusura.objects.create(data=self.giorno, motivo="Maestrale")
        stato = self.stato()
        self.assertTrue(stato.chiusa)
        self.assertEqual(stato.posti_liberi, 0)
        with self.assertRaises(servizi.PostiNonDisponibili):
            self.prenota(2)

    def test_chiusura_solo_pomeriggio(self):
        Chiusura.objects.create(data=self.giorno, fascia=self.pomeriggio)
        self.assertFalse(self.stato(self.mattino).chiusa)
        self.assertTrue(self.stato(self.pomeriggio).chiusa)

    def test_gommone_fermo(self):
        Chiusura.objects.create(data=self.giorno, gommone=self.g1, motivo="Manutenzione")
        self.assertEqual(self.stato().posti_liberi, 12)
        self.assertEqual(self.prenota(4).gommone, self.g2)

    def test_gommone_disattivato(self):
        self.g2.attivo = False
        self.g2.save()
        self.prenota(12)
        with self.assertRaises(servizi.PostiNonDisponibili):
            self.prenota(1)

    def test_periodo_coerente_con_singola_uscita(self):
        self.prenota(10)
        self.prenota(3)
        Chiusura.objects.create(data=self.giorno, fascia=self.pomeriggio)
        (_, uscite), = servizi.stati_periodo(self.giorno, self.giorno)
        for u in uscite:
            singola = servizi.stato_uscita(self.giorno, u.fascia)
            self.assertEqual((u.posti_liberi, u.max_persone, u.chiusa), (singola.posti_liberi, singola.max_persone, singola.chiusa))
