"""
Disponibilità e assegnazione dei gommoni.

Regole:
- ogni uscita (data + fascia) ha i gommoni attivi non chiusi, ciascuno con la sua capienza;
- un gruppo non si divide mai su due gommoni;
- tra i gommoni in cui il gruppo entra si sceglie quello con MENO posti liberi
  (a parità, quello con `ordine` più basso): così si riempie un gommone prima di
  aprire il successivo, e chi non entra nel primo passa direttamente al secondo;
- una prenotazione in esclusiva richiede un gommone vuoto e lo occupa tutto.

Le scritture passano da `assegna_gommone` dentro una transazione: la riga della
fascia viene bloccata (SELECT … FOR UPDATE) così due prenotazioni simultanee per
la stessa uscita non possono superare la capienza.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Chiusura, Fascia, Gommone, Prenotazione


class PostiNonDisponibili(Exception):
    """Il gruppo non entra in nessun gommone di quell'uscita."""

    def __init__(self, messaggio, max_persone=0):
        super().__init__(messaggio)
        self.messaggio = messaggio
        self.max_persone = max_persone


@dataclass
class StatoGommone:
    gommone: Gommone
    occupati: int = 0
    prenotazioni: list = field(default_factory=list)
    chiuso: bool = False

    @property
    def capienza(self):
        return self.gommone.capienza

    @property
    def liberi(self):
        if self.chiuso or not self.gommone.attivo:
            return 0
        return max(self.capienza - self.occupati, 0)

    @property
    def da_incassare(self):
        return sum((p.da_incassare() or 0) for p in self.prenotazioni if not p.in_attesa)

    @property
    def esclusiva(self):
        return any(p.esclusiva for p in self.prenotazioni)

    @property
    def percentuale(self):
        return min(round(self.occupati * 100 / self.capienza), 100) if self.capienza else 0

    @property
    def sovraccarico(self):
        return self.occupati > self.capienza


@dataclass
class StatoUscita:
    data: date
    fascia: Fascia
    gommoni: list
    chiusa: bool = False
    motivo_chiusura: str = ""

    @property
    def posti_liberi(self):
        return 0 if self.chiusa else sum(g.liberi for g in self.gommoni)

    @property
    def max_persone(self):
        """Gruppo più grande che si può ancora prenotare (i gruppi non si dividono)."""
        return 0 if self.chiusa else max((g.liberi for g in self.gommoni), default=0)

    @property
    def occupati(self):
        return sum(g.occupati for g in self.gommoni)

    @property
    def capienza(self):
        return sum(g.capienza for g in self.gommoni if g.gommone.attivo and not g.chiuso)

    @property
    def n_prenotazioni(self):
        return sum(len(g.prenotazioni) for g in self.gommoni)

    @property
    def livello(self):
        """Per i colori del pannello: chiusa, piena, quasi, libera."""
        if self.chiusa:
            return "chiusa"
        if self.max_persone == 0:
            return "piena"
        if self.capienza and self.posti_liberi * 4 <= self.capienza:
            return "quasi"
        return "libera"


def motivo_non_prenotabile_online(giorno, fascia=None, adesso=None):
    """
    Perché il sito non accetta prenotazioni per quel giorno (e uscita), oppure None.
    Il pannello non passa di qui: il proprietario può sempre inserire a mano.
    """
    adesso = adesso or timezone.localtime()
    oggi = adesso.date()
    if giorno < oggi:
        return "La data è già passata."
    if not in_stagione(giorno):
        return "Le uscite sono dal 1° maggio al 30 settembre."
    if fascia is not None and giorno == oggi and fascia.prenotabile_fino_alle and adesso.time() > fascia.prenotabile_fino_alle:
        return f"Per oggi le prenotazioni online del {fascia.nome.lower()} sono chiuse: chiamaci o scrivici su WhatsApp."
    return None


def in_stagione(giorno):
    inizio = date(giorno.year, *settings.STAGIONE_INIZIO)
    fine = date(giorno.year, *settings.STAGIONE_FINE)
    return inizio <= giorno <= fine


def _costruisci_stato(giorno, fascia, gommoni, prenotazioni, chiusure):
    """Monta lo StatoUscita da dati già caricati (una sola uscita)."""
    chiusa_tutta = next((c for c in chiusure if c.gommone_id is None), None)
    gommoni_chiusi = {c.gommone_id for c in chiusure if c.gommone_id}

    per_gommone = {g.pk: StatoGommone(gommone=g, chiuso=g.pk in gommoni_chiusi) for g in gommoni}
    for p in prenotazioni:
        stato = per_gommone.get(p.gommone_id)
        if stato is None:
            continue
        stato.prenotazioni.append(p)
        stato.occupati += p.posti_occupati(stato.gommone)

    # Anche i gommoni spenti compaiono se hanno ancora prenotazioni: vanno gestite
    elenco = [s for s in per_gommone.values() if s.gommone.attivo or s.prenotazioni]
    if chiusa_tutta:
        motivo = chiusa_tutta.motivo
    elif not fascia.attiva:
        motivo = "Uscita disattivata"
    else:
        motivo = ""
    return StatoUscita(
        data=giorno,
        fascia=fascia,
        gommoni=elenco,
        chiusa=bool(chiusa_tutta) or not fascia.attiva,
        motivo_chiusura=motivo,
    )


def prenotazioni_valide():
    """Prenotazioni che occupano posti: confermate, oppure con il pagamento in corso e non scaduto."""
    return Prenotazione.objects.filter(Q(scade_il__isnull=True) | Q(scade_il__gt=timezone.now()))


def _prenotazioni_attive(dal, al):
    return (
        prenotazioni_valide().filter(data__range=(dal, al))
        .select_related("gommone", "fascia")
        .prefetch_related("pagamenti")
        .order_by("creata_il")
    )


def stato_uscita(giorno, fascia, escludi=None):
    """Fotografia di un'uscita. `escludi` = id di una prenotazione da non contare (modifica)."""
    prenotazioni = _prenotazioni_attive(giorno, giorno).filter(fascia=fascia)
    if escludi:
        prenotazioni = prenotazioni.exclude(pk=escludi)
    chiusure = Chiusura.objects.filter(data=giorno).filter(Q(fascia__isnull=True) | Q(fascia=fascia))
    return _costruisci_stato(giorno, fascia, list(Gommone.objects.all()), list(prenotazioni), list(chiusure))


def scegli_gommone(stato, persone, esclusiva=False, preferito=None):
    """
    Restituisce il gommone in cui mettere il gruppo, o solleva PostiNonDisponibili.
    `preferito` = gommone scelto a mano dal pannello: si usa se il gruppo ci entra.
    """
    if stato.chiusa:
        raise PostiNonDisponibili(
            f"L'uscita del {stato.data:%d/%m/%Y} ({stato.fascia.nome.lower()}) è chiusa"
            + (f": {stato.motivo_chiusura}" if stato.motivo_chiusura else "."),
        )

    def entra(s):
        if s.chiuso or not s.gommone.attivo:
            return False
        if esclusiva:
            return s.occupati == 0 and persone <= s.capienza
        return s.liberi >= persone

    if preferito is not None:
        s = next((s for s in stato.gommoni if s.gommone.pk == preferito.pk), None)
        if s and entra(s):
            return s.gommone
        if s is None or s.chiuso or not s.gommone.attivo:
            motivo = f"{preferito.nome} non è disponibile per questa uscita."
        elif esclusiva:
            motivo = f"{preferito.nome} non è vuoto ({s.occupati}/{s.capienza}): l'esclusiva richiede un gommone libero."
        else:
            motivo = f"Su {preferito.nome} restano {s.liberi} posti, il gruppo è di {persone}."
        raise PostiNonDisponibili(motivo, stato.max_persone)

    candidati = [s for s in stato.gommoni if entra(s)]
    if not candidati:
        if esclusiva:
            motivo = "Nessun gommone è completamente libero per un'esclusiva in questa uscita."
        elif stato.max_persone:
            motivo = (
                f"Non c'è posto per {persone} persone insieme: al massimo {stato.max_persone} "
                f"sullo stesso gommone ({stato.posti_liberi} posti liberi in totale)."
            )
        else:
            motivo = "Uscita al completo."
        raise PostiNonDisponibili(motivo, stato.max_persone)

    # Best fit: il gommone più pieno in cui il gruppo entra; a parità, l'ordine
    migliore = min(candidati, key=lambda s: (s.liberi, s.gommone.ordine, s.gommone.pk))
    return migliore.gommone


@transaction.atomic
def assegna_gommone(prenotazione, preferito=None):
    """
    Blocca l'uscita, verifica i posti e imposta `prenotazione.gommone` (non salva).
    Va chiamata dentro la stessa transazione in cui poi si salva la prenotazione.
    """
    Fascia.objects.select_for_update().get(pk=prenotazione.fascia_id)
    stato = stato_uscita(prenotazione.data, prenotazione.fascia, escludi=prenotazione.pk)
    prenotazione.gommone = scegli_gommone(
        stato, prenotazione.persone, esclusiva=prenotazione.esclusiva, preferito=preferito
    )
    return prenotazione.gommone


def verifica_posti(prenotazione, scelto=None, originale=None, blocca=True):
    """
    Regole del pannello per inserire o modificare una prenotazione. Imposta
    `prenotazione.gommone` e restituisce True se il gruppo è stato spostato d'ufficio.
    Solleva PostiNonDisponibili con un messaggio da mostrare.

    - gommone lasciato vuoto → assegnazione automatica;
    - gommone scelto a mano (diverso da quello di prima) → si usa solo se il gruppo ci entra;
    - modifica senza toccare il gommone → resta lì se ci sta, altrimenti si cerca posto altrove.

    Con `blocca=False` non prende il lock: serve al controllo dal vivo mentre si compila il form.
    """
    assegna = assegna_gommone if blocca else _assegna_senza_lock
    if scelto is not None and originale is not None and scelto == originale:
        try:
            assegna(prenotazione, preferito=scelto)
            return False
        except PostiNonDisponibili:
            assegna(prenotazione)
            return True
    assegna(prenotazione, preferito=scelto)
    return False


def _assegna_senza_lock(prenotazione, preferito=None):
    stato = stato_uscita(prenotazione.data, prenotazione.fascia, escludi=prenotazione.pk)
    prenotazione.gommone = scegli_gommone(
        stato, prenotazione.persone, esclusiva=prenotazione.esclusiva, preferito=preferito
    )
    return prenotazione.gommone


def completa_importo(prenotazione):
    if prenotazione.importo is None and not prenotazione.esclusiva:
        prenotazione.importo = prenotazione.importo_calcolato()


@transaction.atomic
def crea_prenotazione(**dati):
    """Usata dal sito: assegna il gommone, calcola l'importo e salva in un'unica transazione."""
    prenotazione = Prenotazione(**dati)
    prenotazione.full_clean(exclude=["gommone"])
    assegna_gommone(prenotazione)
    completa_importo(prenotazione)
    prenotazione.confermata_il = timezone.now()
    prenotazione.save()
    return prenotazione


def stati_periodo(dal, al, fasce=None):
    """Stato di tutte le uscite tra due date (incluse), con 4 query in tutto."""
    fasce = list(fasce if fasce is not None else Fascia.objects.all())
    gommoni = list(Gommone.objects.all())

    prenotazioni = defaultdict(list)
    for p in _prenotazioni_attive(dal, al):
        prenotazioni[(p.data, p.fascia_id)].append(p)
    chiusure = defaultdict(list)
    for c in Chiusura.objects.filter(data__range=(dal, al)):
        chiusure[c.data].append(c)

    giorni = []
    giorno = dal
    while giorno <= al:
        uscite = []
        for f in fasce:
            del_giorno = [c for c in chiusure[giorno] if c.fascia_id in (None, f.pk)]
            uscite.append(_costruisci_stato(giorno, f, gommoni, prenotazioni[(giorno, f.pk)], del_giorno))
        giorni.append((giorno, uscite))
        giorno += timedelta(days=1)
    return giorni
