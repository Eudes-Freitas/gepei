from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("core", "0008_risk_lifecycle")]

    operations = [
        migrations.AddField(
            model_name="risk",
            name="occurrence_timing",
            field=models.CharField(
                choices=[
                    ("QUALQUER_MOMENTO", "Pode ocorrer a qualquer momento"),
                    ("PERIODO", "Durante um período de exposição"),
                    ("DATA_MARCO", "Em uma data ou marco provável"),
                    ("INDETERMINADO", "Não é possível estimar o momento"),
                ],
                default="INDETERMINADO",
                max_length=20,
            ),
        ),
        migrations.AddField(model_name="risk", name="exposure_start_date", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="risk", name="exposure_end_date", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="risk", name="expected_occurrence_date", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="risk", name="trigger_description", field=models.TextField(blank=True)),
    ]
