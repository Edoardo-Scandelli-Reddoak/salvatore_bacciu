from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Prefetch, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import action, display
from unfold.forms import AdminPasswordChangeForm, BaseDialogForm, UserChangeForm, UserCreationForm

from . import pagamenti, servizi
from .admin_views import DisponibilitaView, UscitaView
from .models import Chiusura, Fascia, Gommone, Pagamento, Prenotazione

# --------------------------------------------------------------------------
# Utenti e gruppi con la grafica di Unfold
# --------------------------------------------------------------------------

admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


# --------------------------------------------------------------------------
# Prenotazioni
# --------------------------------------------------------------------------


class PrenotazioneForm(forms.ModelForm):
    class Meta:
        model = Prenotazione
        fields = "__all__"

    def clean(self):
        dati = super().clean()
        self.spostata_su = None
        if self.errors:
            return dati
        prova = Prenotazione(
            pk=self.instance.pk,
            data=dati["data"],
            fascia=dati["fascia"],
            persone=dati["persone"],
            esclusiva=dati.get("esclusiva", False),
        )
        scelto = dati.get("gommone")
        originale = self.instance.gommone if self.instance.pk else None
        # L'admin gira già dentro una transazione: il lock preso qui resta attivo fino
        # al salvataggio, quindi nessuna prenotazione dal sito si infila in mezzo.
        try:
            if servizi.verifica_posti(prova, scelto=scelto, originale=originale):
                self.spostata_su = prova.gommone
        except servizi.PostiNonDisponibili as errore:
            self.add_error("persone", errore.messaggio)
            return dati
        dati["gommone"] = prova.gommone
        return dati


def euro(valore):
    if valore is None:
        return "—"
    testo = f"{valore:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{testo.removesuffix(',00')} €"


class IncassoForm(BaseDialogForm):
    prefix = "incasso"  # il modulo della prenotazione sotto ha già un campo «importo»
    tipo = forms.ChoiceField(
        choices=[(Pagamento.Tipo.SALDO, "Saldo"), (Pagamento.Tipo.ACCONTO, "Acconto")], initial=Pagamento.Tipo.SALDO
    )
    metodo = forms.ChoiceField(
        choices=[c for c in Pagamento.Metodo.choices if c[0] != Pagamento.Metodo.STRIPE], initial=Pagamento.Metodo.CONTANTI
    )
    importo = forms.DecimalField(label="Importo (€)", min_value=0.01, max_digits=8, decimal_places=2)
    note = forms.CharField(required=False, max_length=300)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        p = Prenotazione.objects.filter(pk=self.object_id).first()
        if p and not self.is_bound:
            self.fields["importo"].initial = p.da_incassare() or None
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "border border-base-200 rounded-default px-3 py-2 w-full bg-white dark:bg-base-900 dark:border-base-700")


class RimborsoForm(BaseDialogForm):
    prefix = "rimborso"
    importo = forms.DecimalField(label="Importo da rimborsare (€)", min_value=0.01, max_digits=8, decimal_places=2)
    motivo = forms.CharField(required=False, max_length=300, initial="Annullata per meteo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        p = Prenotazione.objects.filter(pk=self.object_id).first()
        if p and not self.is_bound:
            self.fields["importo"].initial = pagamenti.rimborsabile_stripe(p)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "border border-base-200 rounded-default px-3 py-2 w-full bg-white dark:bg-base-900 dark:border-base-700")


def chiudi_dialogo(request, url):
    """Le finestre di Unfold girano con htmx: per ricaricare la pagina serve HX-Redirect."""
    if request.headers.get("HX-Request"):
        return HttpResponse(status=200, headers={"HX-Redirect": url})
    return redirect(url)


class PagamentiFilter(admin.SimpleListFilter):
    title = "pagamenti"
    parameter_name = "pagamenti"

    def lookups(self, request, model_admin):
        return [
            ("da_incassare", "Con saldo da incassare"),
            ("saldate", "Saldate"),
            ("in_attesa", "Pagamento online in corso"),
            ("abbandonate", "Pagamento online abbandonato"),
        ]

    def queryset(self, request, queryset):
        ora = timezone.now()
        valore = self.value()
        if valore == "abbandonate":
            return queryset.filter(scade_il__lte=ora)
        # Di norma i tentativi di pagamento abbandonati non si mostrano: non occupano posti
        queryset = queryset.exclude(scade_il__lte=ora)
        if valore == "in_attesa":
            return queryset.filter(scade_il__gt=ora)
        if valore in ("da_incassare", "saldate"):
            confermate = list(queryset.filter(scade_il__isnull=True).prefetch_related("pagamenti").select_related("fascia"))
            ids = [p.pk for p in confermate if (p.da_incassare() or 0) > 0]
            if valore == "saldate":
                ids = [p.pk for p in confermate if p.pk not in set(ids)]
            return queryset.filter(pk__in=ids)
        return queryset


class PagamentoInline(TabularInline):
    model = Pagamento
    extra = 0
    can_delete = False
    fields = ["eseguito_il", "tipo", "metodo", "importo", "note", "registrato_da"]
    readonly_fields = fields
    verbose_name_plural = "Movimenti di denaro"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Prenotazione)
class PrenotazioneAdmin(ModelAdmin):
    form = PrenotazioneForm
    list_display = [
        "codice",
        "data_uscita",
        "uscita",
        "gommone",
        "nome",
        "persone_display",
        "telefono",
        "canale_display",
        "pagato_display",
        "da_incassare_display",
        "prenotata_il",
    ]
    list_display_links = ["codice", "nome"]
    list_filter = [
        PagamentiFilter,
        ("data", RangeDateFilter),
        "fascia",
        "gommone",
        "canale",
        "esclusiva",
    ]
    list_filter_submit = True
    search_fields = ["codice", "nome", "telefono", "email"]
    date_hierarchy = "data"
    ordering = ["-data", "fascia__ordine", "gommone__ordine", "creata_il"]
    list_select_related = ["fascia", "gommone"]
    list_per_page = 50
    readonly_fields = ["codice", "creata_il", "aggiornata_il", "confermata_il", "riepilogo_pagamenti"]
    inlines = [PagamentoInline]
    actions_detail = ["registra_incasso", "rimborsa_stripe"]
    fieldsets = [
        ("Uscita", {"fields": ["data", "fascia", "persone", "esclusiva", "gommone"]}),
        ("Cliente", {"fields": ["nome", "telefono", "email"]}),
        ("Dettagli", {"fields": ["canale", "importo", "note"]}),
        ("Pagamenti", {"fields": ["riepilogo_pagamenti"]}),
        ("Registro", {"fields": ["codice", "creata_il", "confermata_il", "aggiornata_il"], "classes": ["collapse"]}),
    ]
    warn_unsaved_form = True

    class Media:
        # Controllo dei posti mentre si compila (vedi verifica_view)
        js = ["admin_extra/prenotazione_form.js"]

    def get_urls(self):
        vista = self.admin_site.admin_view
        return [
            path(
                "disponibilita/",
                vista(DisponibilitaView.as_view(model_admin=self)),
                name="prenotazioni_disponibilita",
            ),
            path(
                "verifica/",
                vista(self.verifica_view),
                name="prenotazioni_verifica",
            ),
            path(
                "uscita/<str:giorno>/<int:fascia_id>/",
                vista(UscitaView.as_view(model_admin=self)),
                name="prenotazioni_uscita",
            ),
        ] + super().get_urls()

    def verifica_view(self, request):
        """Dice al form, mentre lo si compila, se il gruppo entra e su quale gommone andrebbe."""
        q = request.GET
        try:
            giorno = forms.DateField().clean(q.get("data"))
            fascia = Fascia.objects.get(pk=q.get("fascia"))
            persone = int(q.get("persone"))
            if persone < 1:
                raise ValueError
        except (forms.ValidationError, Fascia.DoesNotExist, TypeError, ValueError):
            return JsonResponse({"completo": False})
        esistente = Prenotazione.objects.filter(pk=q.get("pk") or None).select_related("gommone").first()
        scelto = Gommone.objects.filter(pk=q.get("gommone") or None).first()
        prova = Prenotazione(
            pk=esistente.pk if esistente else None,
            data=giorno,
            fascia=fascia,
            persone=persone,
            esclusiva=q.get("esclusiva") in ("1", "true", "on"),
        )
        stato = servizi.stato_uscita(giorno, fascia, escludi=prova.pk)
        risposta = {
            "completo": True,
            "uscita": f"{fascia.nome} · {giorno:%d/%m/%Y}",
            "chiusa": stato.chiusa,
            "motivo_chiusura": stato.motivo_chiusura,
            "max_persone": stato.max_persone,
            "posti_liberi": stato.posti_liberi,
            "gommoni": [
                {"nome": g.gommone.nome, "occupati": g.occupati, "capienza": g.capienza, "chiuso": g.chiuso or not g.gommone.attivo}
                for g in stato.gommoni
            ],
        }
        try:
            spostata = servizi.verifica_posti(
                prova, scelto=scelto, originale=esistente.gommone if esistente else None, blocca=False
            )
            risposta.update(ok=True, gommone=prova.gommone.nome, spostata=spostata)
        except servizi.PostiNonDisponibili as errore:
            risposta.update(ok=False, errore=errore.messaggio)
        return JsonResponse(risposta)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            Prefetch("pagamenti", queryset=Pagamento.objects.order_by("eseguito_il"))
        )

    def get_fieldsets(self, request, obj=None):
        # In inserimento pagamenti e registro sono vuoti: non serve mostrarli
        if obj is None:
            return self.fieldsets[:-2]
        return self.fieldsets

    def get_inlines(self, request, obj):
        return self.inlines if obj else []

    @display(description="Riepilogo")
    def riepilogo_pagamenti(self, obj):
        if obj.in_attesa:
            return format_html(
                "Pagamento online in corso: i posti sono bloccati fino alle {}.",
                timezone.localtime(obj.scade_il).strftime("%H:%M del %d/%m"),
            )
        return format_html(
            "Totale <b>{}</b> · pagato <b>{}</b> · da incassare all'imbarco <b>{}</b>",
            euro(obj.importo_calcolato()),
            euro(obj.totale_pagato()),
            euro(obj.da_incassare()),
        )

    @display(description="Pagato", label={"in corso": "warning", "scaduto": "danger"})
    def pagato_display(self, obj):
        if obj.in_attesa:
            return "scaduto" if obj.scaduta else "in corso"
        pagato = obj.totale_pagato()
        return euro(pagato) if pagato else "—"

    @display(description="Da incassare")
    def da_incassare_display(self, obj):
        if obj.in_attesa:
            return "—"
        resto = obj.da_incassare()
        if resto is None:
            return "—"
        return euro(resto) if resto else "saldata"

    @action(
        description="Registra incasso",
        icon="payments",
        url_path="registra-incasso",
        dialog={
            "title": "Registra un incasso",
            "description": "Saldo all'imbarco o acconto ricevuto fuori dal sito (contanti, POS, bonifico).",
            "form_class": IncassoForm,
            "form_submit_text": "Registra",
        },
    )
    def registra_incasso(self, request, form, object_id):
        p = Prenotazione.objects.get(pk=object_id)
        pagamenti.registra_movimento(
            p, form.cleaned_data["tipo"], form.cleaned_data["metodo"], form.cleaned_data["importo"],
            request.user.get_username(), form.cleaned_data["note"],
        )
        messages.success(request, f"Registrati {euro(form.cleaned_data['importo'])} per {p.nome}.")
        return chiudi_dialogo(request, reverse("admin:prenotazioni_prenotazione_change", args=[object_id]))

    @action(
        description="Rimborsa con Stripe",
        icon="currency_exchange",
        url_path="rimborsa",
        dialog={
            "title": "Rimborsa il pagamento online",
            "description": "Restituisce al cliente, tramite Stripe, quanto ha pagato sul sito. Non si può annullare.",
            "form_class": RimborsoForm,
            "form_submit_text": "Rimborsa",
        },
    )
    def rimborsa_stripe(self, request, form, object_id):
        p = Prenotazione.objects.get(pk=object_id)
        url = reverse("admin:prenotazioni_prenotazione_change", args=[object_id])
        try:
            pagamenti.rimborsa(p, form.cleaned_data["importo"], request.user.get_username(), form.cleaned_data["motivo"])
        except pagamenti.ErrorePagamento as e:
            messages.error(request, e.messaggio)
            return chiudi_dialogo(request, url)
        messages.success(
            request,
            f"Rimborsati {euro(form.cleaned_data['importo'])} a {p.nome}. "
            "Se la prenotazione è annullata, ora puoi eliminarla: il movimento resta nei Pagamenti.",
        )
        return chiudi_dialogo(request, url)

    def save_model(self, request, obj, form, change):
        servizi.completa_importo(obj)
        if not change:
            obj.confermata_il = timezone.now()  # dal pannello la prenotazione nasce confermata
        super().save_model(request, obj, form, change)
        if getattr(form, "spostata_su", None):
            messages.warning(
                request,
                f"Il gruppo non entrava più nel gommone di prima: spostato su {form.spostata_su.nome}.",
            )
        if obj.gommone:
            messages.info(request, f"{obj.nome} ({obj.persone} pers.) è sul {obj.gommone.nome}.")

    @display(description="Data uscita", ordering="data")
    def data_uscita(self, obj):
        url = reverse("admin:prenotazioni_uscita", args=[obj.data.isoformat(), obj.fascia_id])
        return format_html('<a href="{}" title="Vedi l\'uscita">{}</a>', url, obj.data.strftime("%d/%m/%Y"))

    @display(description="Uscita", ordering="fascia__ordine")
    def uscita(self, obj):
        return obj.fascia.nome

    @display(description="Persone", ordering="persone")
    def persone_display(self, obj):
        return f"{obj.persone} · esclusiva" if obj.esclusiva else obj.persone

    @display(
        description="Canale",
        ordering="canale",
        label={
            Prenotazione.Canale.SITO.label: "primary",
            Prenotazione.Canale.TELEFONO.label: "info",
            Prenotazione.Canale.WHATSAPP.label: "success",
        },
    )
    def canale_display(self, obj):
        return obj.get_canale_display()

    @display(description="Prenotata il", ordering="creata_il")
    def prenotata_il(self, obj):
        return timezone.localtime(obj.creata_il).strftime("%d/%m/%Y %H:%M")


@admin.register(Pagamento)
class PagamentoAdmin(ModelAdmin):
    """Tutti i movimenti, anche di prenotazioni poi eliminate. Si creano dal dettaglio prenotazione."""

    list_display = ["eseguito_il_display", "riferimento_link", "tipo_display", "metodo", "importo_display", "registrato_da", "note"]
    list_filter = [("eseguito_il", RangeDateFilter), "tipo", "metodo"]
    list_filter_submit = True
    search_fields = ["riferimento", "prenotazione__codice", "prenotazione__nome", "stripe_pagamento", "stripe_sessione"]
    date_hierarchy = "eseguito_il"
    list_select_related = ["prenotazione"]
    readonly_fields = [
        "prenotazione", "riferimento", "tipo", "metodo", "importo", "eseguito_il", "registrato_da",
        "stripe_sessione", "stripe_pagamento", "stripe_rimborso",
    ]
    fields = readonly_fields + ["note"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # La contabilità non si cancella: solo un amministratore, per correggere errori
        return request.user.is_superuser

    @display(description="Data", ordering="eseguito_il")
    def eseguito_il_display(self, obj):
        return timezone.localtime(obj.eseguito_il).strftime("%d/%m/%Y %H:%M")

    @display(description="Prenotazione", ordering="riferimento")
    def riferimento_link(self, obj):
        if obj.prenotazione_id:
            url = reverse("admin:prenotazioni_prenotazione_change", args=[obj.prenotazione_id])
            return format_html('<a href="{}">{}</a>', url, obj.riferimento)
        return obj.riferimento

    @display(
        description="Tipo",
        ordering="tipo",
        label={
            Pagamento.Tipo.ACCONTO.label: "info",
            Pagamento.Tipo.SALDO.label: "success",
            Pagamento.Tipo.RIMBORSO.label: "danger",
        },
    )
    def tipo_display(self, obj):
        return obj.get_tipo_display()

    @display(description="Importo", ordering="importo")
    def importo_display(self, obj):
        return f"− {euro(obj.importo)}" if obj.tipo == Pagamento.Tipo.RIMBORSO else euro(obj.importo)


# --------------------------------------------------------------------------
# Configurazione
# --------------------------------------------------------------------------


@admin.register(Chiusura)
class ChiusuraAdmin(ModelAdmin):
    list_display = ["data", "fascia_display", "gommone_display", "motivo"]
    list_filter = [("data", RangeDateFilter), "fascia", "gommone"]
    list_filter_submit = True
    date_hierarchy = "data"

    @display(description="Uscita", ordering="fascia")
    def fascia_display(self, obj):
        return obj.fascia.nome if obj.fascia else "Tutto il giorno"

    @display(description="Gommone", ordering="gommone")
    def gommone_display(self, obj):
        return obj.gommone.nome if obj.gommone else "Tutti"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Avvisa se ci sono clienti già prenotati da contattare
        coinvolte = Prenotazione.objects.filter(data=obj.data)
        if obj.fascia_id:
            coinvolte = coinvolte.filter(fascia=obj.fascia_id)
        if obj.gommone_id:
            coinvolte = coinvolte.filter(gommone=obj.gommone_id)
        n = coinvolte.count()
        if n:
            url = reverse("admin:prenotazioni_prenotazione_changelist")
            filtro = f"?data__range__gte={obj.data:%d/%m/%Y}&data__range__lte={obj.data:%d/%m/%Y}"
            messages.warning(
                request,
                format_html(
                    'Attenzione: {} prenotazioni rientrano in questa chiusura e vanno gestite '
                    '(spostale o eliminale). <a class="underline" href="{}{}">Vedi le prenotazioni</a>',
                    n,
                    url,
                    filtro,
                ),
            )


@admin.register(Gommone)
class GommoneAdmin(ModelAdmin):
    list_display = ["nome", "capienza", "ordine", "attivo"]
    list_editable = ["ordine", "attivo"]


@admin.register(Fascia)
class FasciaAdmin(ModelAdmin):
    list_display = ["nome", "orario", "durata_ore", "prezzo_persona", "acconto_persona", "prenotabile_fino_alle", "attiva"]
    prepopulated_fields = {"codice": ["nome"]}
