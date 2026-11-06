from django.db import migrations, models


def normalize_risk_statuses(apps, schema_editor):
    Risk = apps.get_model("core", "Risk")
    Risk.objects.exclude(status="MATERIALIZADO").update(status="NAO_MATERIALIZADO")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0033_merge_20261023_1649"),
    ]

    operations = [
        migrations.AlterField(
            model_name="risk",
            name="status",
            field=models.CharField(
                choices=[
                    ("NAO_MATERIALIZADO", "Não materializado"),
                    ("MATERIALIZADO", "Materializado"),
                ],
                default="NAO_MATERIALIZADO",
                max_length=18,
            ),
        ),
        migrations.RunPython(normalize_risk_statuses, migrations.RunPython.noop),
    ]
