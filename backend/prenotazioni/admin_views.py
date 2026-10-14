"""Pagine del pannello che non sono semplici liste: calendario, uscita, dashboard."""

import calendar
from datetime import date, timedelta

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.generic import TemplateView
from unfold.views import UnfoldModelAdminViewMixin

from . import servizi
from .models import Fascia

MESI = [
    "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def url_nuova_prenotazione(giorno, fascia):
    # L'admin di Django usa i parametri GET come valori iniziali del form
    return reverse("admin:prenotazioni_prenotazione_add") + "?" + urlencode(
        {"data": giorno.strftime("%d/%m/%Y"), "fascia": fascia.pk}
    )


def righe_calendario(giorni):
    """Prepara le righe per il template: giorno, etichette, uscite con i link."""
    oggi = timezone.localdate()
    righe = []
    for giorno, uscite in giorni:
        righe.append(
            {
                "giorno": giorno,
                "giorno_sett": GIORNI[giorno.weekday()],
                "oggi": giorno == oggi,
                "passato": giorno < oggi,
                "weekend": giorno.weekday() >= 5,
                "fuori_stagione": not servizi.in_stagione(giorno),
                "uscite": [
                    {
                        "stato": u,
                        "url": reverse("admin:prenotazioni_uscita", args=[giorno.isoformat(), u.fascia.pk]),
                        "url_nuova": url_nuova_prenotazione(giorno, u.fascia),
                    }
                    for u in uscite
                ],
            }
        )
    return righe


def primo_mese_utile(oggi):
    """Mese da mostrare di default: quello corrente in stagione, altrimenti l'inizio della prossima."""
    if servizi.in_stagione(oggi):
        return date(oggi.year, oggi.month, 1)
    mese_inizio, _ = settings.STAGIONE_INIZIO
    anno = oggi.year if oggi < date(oggi.year, *settings.STAGIONE_INIZIO) else oggi.year + 1
    return date(anno, mese_inizio, 1)


class DisponibilitaView(UnfoldModelAdminViewMixin, TemplateView):
    title = "Calendario disponibilità"
    permission_required = ("prenotazioni.view_prenotazione",)
    template_name = "admin/prenotazioni/disponibilita.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            anno, mese = map(int, self.request.GET["mese"].split("-"))
            inizio = date(anno, mese, 1)
        except (KeyError, ValueError):
            inizio = primo_mese_utile(timezone.localdate())
        fine = date(inizio.year, inizio.month, calendar.monthrange(inizio.year, inizio.month)[1])
        prec = inizio - timedelta(days=1)
        succ = fine + timedelta(days=1)

        fasce = list(Fascia.objects.all())
        ctx.update(
            {
                "fasce": fasce,
                "righe": righe_calendario(servizi.stati_periodo(inizio, fine, fasce)),
                "titolo_mese": f"{MESI[inizio.month].capitalize()} {inizio.year}",
                "mese_prec": f"{prec.year}-{prec.month:02d}",
                "mese_succ": f"{succ.year}-{succ.month:02d}",
                "mese_oggi": primo_mese_utile(timezone.localdate()).strftime("%Y-%m"),
            }
        )
        return ctx


class UscitaView(UnfoldModelAdminViewMixin, TemplateView):
    """Una singola uscita: occupazione e lista d'imbarco per gommone."""

    title = "Uscita"
    permission_required = ("prenotazioni.view_prenotazione",)
    template_name = "admin/prenotazioni/uscita.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            giorno = date.fromisoformat(kwargs["giorno"])
        except ValueError as errore:
            raise Http404("Data non valida") from errore
        fascia = get_object_or_404(Fascia, pk=kwargs["fascia_id"])
        stato = servizi.stato_uscita(giorno, fascia)
        altre = [
            {
                "fascia": f,
                "url": reverse("admin:prenotazioni_uscita", args=[giorno.isoformat(), f.pk]),
            }
            for f in Fascia.objects.exclude(pk=fascia.pk)
        ]
        ctx.update(
            {
                "title": f"{fascia.nome} · {GIORNI[giorno.weekday()]} {giorno:%d/%m/%Y}",
                "uscita": stato,
                "giorno": giorno,
                "fascia": fascia,
                "altre_uscite": altre,
                "url_nuova": url_nuova_prenotazione(giorno, fascia),
                "url_giorno_prec": reverse(
                    "admin:prenotazioni_uscita", args=[(giorno - timedelta(days=1)).isoformat(), fascia.pk]
                ),
                "url_giorno_succ": reverse(
                    "admin:prenotazioni_uscita", args=[(giorno + timedelta(days=1)).isoformat(), fascia.pk]
                ),
                "url_calendario": reverse("admin:prenotazioni_disponibilita") + f"?mese={giorno:%Y-%m}",
                "persone_totali": sum(p.persone for g in stato.gommoni for p in g.prenotazioni),
                "da_incassare": sum(g.da_incassare for g in stato.gommoni),
            }
        )
        return ctx


def dashboard_callback(request, context):
    """Home del pannello: le uscite di oggi in evidenza e i prossimi 14 giorni."""
    oggi = timezone.localdate()
    fasce = list(Fascia.objects.all())
    in_stagione = servizi.in_stagione(oggi)
    # Fuori stagione i prossimi giorni sarebbero tutti vuoti: si mostra l'inizio della prossima
    inizio = oggi if in_stagione else primo_mese_utile(oggi)
    giorni = servizi.stati_periodo(inizio, inizio + timedelta(days=13), fasce)
    uscite_oggi = [servizi.stato_uscita(oggi, f) for f in fasce] if in_stagione else []
    context.update(
        {
            "oggi": oggi,
            "oggi_label": f"{GIORNI[oggi.weekday()]} {oggi.day} {MESI[oggi.month]}",
            "uscite_oggi": [
                {
                    "stato": u,
                    "url": reverse("admin:prenotazioni_uscita", args=[oggi.isoformat(), u.fascia.pk]),
                    "persone": sum(p.persone for g in u.gommoni for p in g.prenotazioni),
                    "da_incassare": sum(g.da_incassare for g in u.gommoni),
                }
                for u in uscite_oggi
            ],
            "righe": righe_calendario(giorni),
            "fasce": fasce,
            "url_calendario": reverse("admin:prenotazioni_disponibilita"),
            "url_nuova": reverse("admin:prenotazioni_prenotazione_add"),
            "in_stagione": in_stagione,
            "titolo_periodo": "Prossimi 14 giorni" if in_stagione else f"Inizio stagione: dal {inizio.day} {MESI[inizio.month]} {inizio.year}",
        }
    )
    return context
