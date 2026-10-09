from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_indicator_indicator_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="indicatormeasurement",
            name="baseline_value",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
