from django.contrib import admin
from django.templatetags.static import static
from django.http import HttpResponse
from django.urls import include, path
from django.views.generic import RedirectView

from prenotazioni.api import stripe_webhook
from sito import views as sito_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("prenotazioni.urls")),
    path("stripe/webhook/", stripe_webhook, name="stripe_webhook"),
    # Healthcheck per Railway
    path("favicon.ico", RedirectView.as_view(url=static("sito/favicon.svg"))),
    path("salute/", lambda request: HttpResponse("ok", content_type="text/plain")),
    path("", sito_views.home, name="home"),
]

admin.site.site_header = "Cala Brandinchi"
admin.site.site_title = "Cala Brandinchi Escursioni"
admin.site.index_title = "Prenotazioni"
