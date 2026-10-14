"""Le prenotazioni non hanno più uno stato: sono sempre confermate.
Le vecchie annullate vanno eliminate prima di togliere il campo, altrimenti tornerebbero attive."""

from django.db import migrations


def elimina(apps, schema_editor):
    apps.get_model("prenotazioni", "Prenotazione").objects.filter(stato="annullata").delete()


class Migration(migrations.Migration):
    dependencies = [("prenotazioni", "0004_limiti_iniziali")]
    operations = [migrations.RunPython(elimina, migrations.RunPython.noop)]
