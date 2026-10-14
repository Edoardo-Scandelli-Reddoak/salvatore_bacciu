from django.conf import settings
from django.db.models import Max, Min
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

from prenotazioni.models import Fascia, Gommone


class HomeView(TemplateView):
    template_name = "sito/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        fasce = list(Fascia.objects.filter(attiva=True))
        capienza = Gommone.objects.filter(attivo=True).aggregate(m=Max("capienza"))["m"] or 12
        ctx.update(
            {
                "fasce": fasce,
                "uscite": {f.codice: f for f in fasce},
                "prezzo_minimo": Fascia.objects.filter(attiva=True).aggregate(m=Min("prezzo_persona"))["m"] or 0,
                "acconto_persona": Fascia.objects.filter(attiva=True).aggregate(m=Min("acconto_persona"))["m"] or 0,
                # Il gruppo più grande prenotabile è la capienza del gommone più grande
                "persone_opzioni": range(1, capienza + 1),
                "stagione_inizio": "%02d-%02d" % settings.STAGIONE_INIZIO,
                "stagione_fine": "%02d-%02d" % settings.STAGIONE_FINE,
            }
        )
        return ctx


# Il cookie CSRF serve alla POST di prenotazione
home = ensure_csrf_cookie(HomeView.as_view())
