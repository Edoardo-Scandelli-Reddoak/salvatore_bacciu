"""Uscite e gommoni comunicati dal cliente (07/10/2026). Si modificano poi dal pannello."""

from decimal import Decimal

from django.db import migrations


def crea(apps, schema_editor):
    Fascia = apps.get_model("prenotazioni", "Fascia")
    Gommone = apps.get_model("prenotazioni", "Gommone")
    Fascia.objects.get_or_create(
        codice="mattino",
        defaults={"nome": "Mattino", "orario": "8:30", "durata_ore": 5, "prezzo_persona": Decimal("80"), "ordine": 1},
    )
    Fascia.objects.get_or_create(
        codice="pomeriggio",
        defaults={"nome": "Pomeriggio", "orario": "14:00", "durata_ore": 4, "prezzo_persona": Decimal("70"), "ordine": 2},
    )
    for i in (1, 2):
        Gommone.objects.get_or_create(nome=f"Gommone {i}", defaults={"capienza": 12, "ordine": i})


class Migration(migrations.Migration):
    dependencies = [("prenotazioni", "0001_initial")]
    operations = [migrations.RunPython(crea, migrations.RunPython.noop)]
