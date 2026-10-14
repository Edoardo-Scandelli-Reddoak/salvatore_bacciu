from django.urls import path

from . import api

app_name = "api"

urlpatterns = [
    path("disponibilita/", api.disponibilita, name="disponibilita"),
    path("calendario/", api.calendario_mese, name="calendario"),
    path("prenotazioni/", api.crea_prenotazione, name="crea_prenotazione"),
    path("pagamento/verifica/", api.pagamento_verifica, name="pagamento_verifica"),
    path("pagamento/esito/", api.pagamento_esito, name="pagamento_esito"),
    path("pagamento/annulla/", api.pagamento_annulla, name="pagamento_annulla"),
    path("pagamento/simula/", api.pagamento_simula, name="pagamento_simula"),
]
