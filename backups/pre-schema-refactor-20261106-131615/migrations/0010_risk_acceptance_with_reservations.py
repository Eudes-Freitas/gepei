from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_risk_occurrence_timing"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="riskacceptance",
            name="decision",
            field=models.CharField(
                choices=[
                    ("ACEITO", "Aceito"),
                    ("ACEITO_RESSALVAS", "Aceito com ressalvas"),
                    ("NAO_ACEITO", "Não aceito"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="riskacceptance",
            name="remedial_actions",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="riskacceptance",
            name="remediation_responsible",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assigned_risk_remediations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="riskacceptance",
            name="reevaluation_due_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
