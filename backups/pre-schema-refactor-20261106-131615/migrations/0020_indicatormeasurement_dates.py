from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_indicatormeasurement_baseline_value"),
    ]

    operations = [
        migrations.AddField(
            model_name="indicatormeasurement",
            name="baseline_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="indicatormeasurement",
            name="period_start",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="indicatormeasurement",
            name="period_end",
            field=models.DateField(blank=True, null=True),
        ),
    ]
