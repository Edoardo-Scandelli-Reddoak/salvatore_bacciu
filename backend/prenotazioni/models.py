import secrets
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Fascia(models.Model):
    """Una delle uscite giornaliere: oggi mattino e pomeriggio."""

    nome = models.CharField(max_length=50)
    codice = models.SlugField(
        unique=True, help_text="Identificativo usato dal sito, es. «mattino». Meglio non cambiarlo."
    )
    orario = models.CharField(max_length=30, help_text="Orario di partenza come appare al cliente, es. «8:30».")
    durata_ore = models.PositiveSmallIntegerField("durata (ore)")
    prezzo_persona = models.DecimalField("prezzo a persona (€)", max_digits=7, decimal_places=2)
    acconto_persona = models.DecimalField(
        "acconto online a persona (€)",
        max_digits=7,
        decimal_places=2,
        default=Decimal("20"),
        help_text="Quota che il cliente paga sul sito per prenotare. Il resto si salda all'imbarco.",
    )
    prenotabile_fino_alle = models.TimeField(
        "prenotabile online fino alle",
        null=True,
        blank=True,
        help_text="Per il giorno stesso: dopo quest'ora il sito non accetta più prenotazioni per questa uscita. Vuoto = nessun limite.",
    )
    ordine = models.PositiveSmallIntegerField(default=0, help_text="Ordine di visualizzazione.")
    attiva = models.BooleanField(default=True, help_text="Se spenta, non si prenota più questa uscita.")

    class Meta:
        verbose_name = "uscita"
        verbose_name_plural = "uscite"
        ordering = ["ordine", "pk"]

    def __str__(self):
        return f"{self.nome} ({self.orario})"


class Gommone(models.Model):
    nome = models.CharField(max_length=50, unique=True)
    capienza = models.PositiveSmallIntegerField(
        default=12,
        validators=[MinValueValidator(1)],
        help_text="Posti per i clienti, skipper escluso.",
    )
    ordine = models.PositiveSmallIntegerField(
        default=0, help_text="A parità di posti liberi si riempie prima il gommone con ordine più basso."
    )
    attivo = models.BooleanField(default=True, help_text="Se spento, non riceve nuove prenotazioni.")

    class Meta:
        verbose_name = "gommone"
        verbose_name_plural = "gommoni"
        ordering = ["ordine", "pk"]

    def __str__(self):
        return self.nome


class Chiusura(models.Model):
    """Giornata, uscita o gommone non disponibili (meteo, manutenzione, ferie…)."""

    data = models.DateField()
    fascia = models.ForeignKey(
        Fascia,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="uscita",
        help_text="Vuoto = tutta la giornata.",
    )
    gommone = models.ForeignKey(
        Gommone,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Vuoto = tutti i gommoni.",
    )
    motivo = models.CharField(max_length=200, blank=True)
    creata_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "chiusura"
        verbose_name_plural = "chiusure"
        ordering = ["-data"]

    def __str__(self):
        cosa = self.gommone.nome if self.gommone else "tutti i gommoni"
        quando = self.fascia.nome.lower() if self.fascia else "tutto il giorno"
        return f"{self.data:%d/%m/%Y} · {quando} · {cosa}"


def nuovo_codice():
    # Niente caratteri ambigui (0/O, 1/I/L): il codice si detta anche al telefono
    alfabeto = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(6))


class Prenotazione(models.Model):
    class Canale(models.TextChoices):
        SITO = "sito", "Sito"
        TELEFONO = "telefono", "Telefono"
        WHATSAPP = "whatsapp", "WhatsApp"
        DI_PERSONA = "di_persona", "Di persona"
        ALTRO = "altro", "Altro"

    codice = models.CharField(max_length=6, unique=True, default=nuovo_codice, editable=False)
    data = models.DateField()
    fascia = models.ForeignKey(Fascia, on_delete=models.PROTECT, verbose_name="uscita")
    gommone = models.ForeignKey(
        Gommone,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Lascia vuoto per l'assegnazione automatica: si riempie prima il gommone più pieno in cui il gruppo entra.",
    )
    persone = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    esclusiva = models.BooleanField(
        "gommone in esclusiva",
        default=False,
        help_text="Il gruppo occupa l'intero gommone, a prescindere dal numero di persone.",
    )

    nome = models.CharField("nome e cognome", max_length=120)
    telefono = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    note = models.TextField(blank=True)

    importo = models.DecimalField(
        "importo (€)",
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Vuoto = persone × prezzo dell'uscita. Per le esclusive va inserito a mano.",
    )
    canale = models.CharField(max_length=20, choices=Canale.choices, default=Canale.TELEFONO)

    # Prenotazioni dal sito: finché il cliente paga i posti restano bloccati fino a `scade_il`.
    # Vuoto = prenotazione confermata (pagata, oppure inserita dal pannello).
    scade_il = models.DateTimeField("pagamento in corso fino al", null=True, blank=True, editable=False)
    confermata_il = models.DateTimeField("confermata il", null=True, blank=True, editable=False)
    acconto_dovuto = models.DecimalField("acconto online (€)", max_digits=8, decimal_places=2, null=True, blank=True, editable=False)
    stripe_sessione = models.CharField("sessione Stripe", max_length=255, blank=True, editable=False)

    creata_il = models.DateTimeField("creata il", auto_now_add=True)
    aggiornata_il = models.DateTimeField("aggiornata il", auto_now=True)

    class Meta:
        verbose_name = "prenotazione"
        verbose_name_plural = "prenotazioni"
        ordering = ["data", "fascia__ordine", "gommone__ordine", "creata_il"]
        indexes = [models.Index(fields=["data", "fascia"])]

    def __str__(self):
        return f"{self.codice} · {self.nome} · {self.persone} pers."

    @property
    def in_attesa(self):
        return self.scade_il is not None

    @property
    def scaduta(self):
        return self.scade_il is not None and self.scade_il <= timezone.now()

    def totale_pagato(self):
        """Acconti e saldi meno i rimborsi (usa i pagamenti già caricati se ci sono)."""
        totale = Decimal("0")
        for p in self.pagamenti.all():
            totale += -p.importo if p.tipo == Pagamento.Tipo.RIMBORSO else p.importo
        return totale

    def da_incassare(self):
        importo = self.importo_calcolato()
        if importo is None:
            return None
        return max(importo - self.totale_pagato(), Decimal("0"))

    def posti_occupati(self, gommone=None):
        """Posti tolti al gommone: tutta la capienza se in esclusiva."""
        gommone = gommone or self.gommone
        if self.esclusiva and gommone is not None:
            return max(gommone.capienza, self.persone)
        return self.persone

    def importo_calcolato(self):
        if self.importo is not None:
            return self.importo
        if self.esclusiva or self.fascia_id is None:
            return None
        return self.fascia.prezzo_persona * Decimal(self.persone)


class Pagamento(models.Model):
    """Un movimento di denaro: acconto online, saldo all'imbarco, rimborso."""

    class Tipo(models.TextChoices):
        ACCONTO = "acconto", "Acconto"
        SALDO = "saldo", "Saldo"
        RIMBORSO = "rimborso", "Rimborso"

    class Metodo(models.TextChoices):
        STRIPE = "stripe", "Stripe (online)"
        CONTANTI = "contanti", "Contanti"
        POS = "pos", "POS / carta"
        BONIFICO = "bonifico", "Bonifico"
        ALTRO = "altro", "Altro"

    # SET_NULL: se una prenotazione viene eliminata, i movimenti restano per la contabilità
    prenotazione = models.ForeignKey(
        Prenotazione, on_delete=models.SET_NULL, null=True, blank=True, related_name="pagamenti"
    )
    riferimento = models.CharField(
        max_length=200, blank=True, help_text="Codice e nome della prenotazione, conservati anche se viene eliminata."
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    metodo = models.CharField(max_length=20, choices=Metodo.choices)
    importo = models.DecimalField("importo (€)", max_digits=8, decimal_places=2, help_text="Sempre positivo, anche per i rimborsi.")
    eseguito_il = models.DateTimeField("eseguito il", default=timezone.now)
    note = models.CharField(max_length=300, blank=True)
    stripe_sessione = models.CharField("sessione Stripe", max_length=255, blank=True)
    stripe_pagamento = models.CharField("PaymentIntent Stripe", max_length=255, blank=True)
    stripe_rimborso = models.CharField("rimborso Stripe", max_length=255, blank=True)
    registrato_da = models.CharField(max_length=150, blank=True, help_text="Utente del pannello, oppure «Stripe».")

    class Meta:
        verbose_name = "pagamento"
        verbose_name_plural = "pagamenti"
        ordering = ["-eseguito_il"]
        constraints = [
            # Stripe può mandare la stessa notifica più volte: un acconto per sessione, un movimento per rimborso
            models.UniqueConstraint(
                fields=["stripe_sessione"], condition=~models.Q(stripe_sessione=""), name="pagamento_sessione_unica"
            ),
            models.UniqueConstraint(
                fields=["stripe_rimborso"], condition=~models.Q(stripe_rimborso=""), name="pagamento_rimborso_unico"
            ),
            models.CheckConstraint(condition=models.Q(importo__gt=0), name="pagamento_importo_positivo"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.importo} € · {self.riferimento}"

    def save(self, *args, **kwargs):
        if self.prenotazione_id and not self.riferimento:
            self.riferimento = f"{self.prenotazione.codice} · {self.prenotazione.nome}"
        super().save(*args, **kwargs)
