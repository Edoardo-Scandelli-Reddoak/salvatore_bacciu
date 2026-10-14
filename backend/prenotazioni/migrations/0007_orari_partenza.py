"""Orari di partenza: il mattino parte alle 8:30, il pomeriggio alle 14:00 (non più una fascia 8:30/9:00)."""

from django.db import migrations

NUOVI = {"8:30/9:00": "8:30", "14:00/14:30": "14:00"}


def aggiorna(apps, schema_editor):
    Fascia = apps.get_model("prenotazioni", "Fascia")
    for vecchio, nuovo in NUOVI.items():
        Fascia.objects.filter(orario=vecchio).update(orario=nuovo)


class Migration(migrations.Migration):
    dependencies = [("prenotazioni", "0006_senza_stato")]
    operations = [migrations.RunPython(aggiorna, migrations.RunPython.noop)]
