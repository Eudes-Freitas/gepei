from django.db import migrations


def normalize_statuses(apps, schema_editor):
    Risk = apps.get_model("core", "Risk")
    Risk.objects.filter(status="EM_MONITORAMENTO").update(status="EM_TRATAMENTO")


class Migration(migrations.Migration):
    dependencies = [("core", "0036_riskmaterialization_provision_responsible")]
    operations = [migrations.RunPython(normalize_statuses, migrations.RunPython.noop)]
