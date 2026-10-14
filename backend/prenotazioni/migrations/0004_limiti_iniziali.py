"""Prenotazioni online del giorno stesso chiuse 30 minuti prima della prima partenza."""

from datetime import time

from django.db import migrations


def imposta(apps, schema_editor):
    Fascia = apps.get_model("prenotazioni", "Fascia")
    Fascia.objects.filter(codice="mattino", prenotabile_fino_alle__isnull=True).update(prenotabile_fino_alle=time(8, 0))
    Fascia.objects.filter(codice="pomeriggio", prenotabile_fino_alle__isnull=True).update(prenotabile_fino_alle=time(13, 30))


class Migration(migrations.Migration):
    dependencies = [("prenotazioni", "0003_limite_prenotazione_online")]
    operations = [migrations.RunPython(imposta, migrations.RunPython.noop)]
