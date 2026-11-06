from django.db import migrations, models


def move_accepted_risks_to_monitoring(apps, schema_editor):
    Risk = apps.get_model("core", "Risk")
    for risk in Risk.objects.exclude(status="MATERIALIZADO"):
        latest_acceptance = risk.acceptances.order_by("-recorded_at", "-id").first()
        if latest_acceptance and latest_acceptance.decision == "ACEITO":
            risk.status = "EM_MONITORAMENTO"
            risk.save(update_fields=["status"])


class Migration(migrations.Migration):
    dependencies = [("core", "0011_risk_remediation_submission")]

    operations = [
        migrations.AlterField(
            model_name="risk",
            name="status",
            field=models.CharField(
                choices=[
                    ("IDENTIFICADO", "Identificado"),
                    ("EM_TRATAMENTO", "Em tratamento"),
                    ("EM_MONITORAMENTO", "Em monitoramento"),
                    ("MATERIALIZADO", "Materializado"),
                    ("ENCERRADO", "Encerrado"),
                ],
                default="IDENTIFICADO",
                max_length=16,
            ),
        ),
        migrations.RunPython(move_accepted_risks_to_monitoring, migrations.RunPython.noop),
    ]
