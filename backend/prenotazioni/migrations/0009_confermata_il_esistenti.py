"""Le prenotazioni già presenti erano confermate fin dalla creazione."""

from django.db import migrations
from django.db.models import F


def imposta(apps, schema_editor):
    apps.get_model("prenotazioni", "Prenotazione").objects.filter(confermata_il__isnull=True, scade_il__isnull=True).update(
        confermata_il=F("creata_il")
    )


class Migration(migrations.Migration):
    dependencies = [("prenotazioni", "0008_pagamenti")]
    operations = [migrations.RunPython(imposta, migrations.RunPython.noop)]
