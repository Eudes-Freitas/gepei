from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0049_merge_20261125_1349"),
    ]

    operations = [
        migrations.AddField(
            model_name="indicatormeasurement",
            name="activities",
            field=models.ManyToManyField(
                blank=True,
                related_name="indicator_measurements",
                to="core.activity",
            ),
        ),
    ]
