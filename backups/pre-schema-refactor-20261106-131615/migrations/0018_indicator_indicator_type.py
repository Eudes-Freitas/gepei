from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_userprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="indicator",
            name="indicator_type",
            field=models.CharField(
                blank=True,
                choices=[("ESFORCO", "Esforço"), ("RESULTADO", "Resultado")],
                max_length=10,
            ),
        ),
    ]
