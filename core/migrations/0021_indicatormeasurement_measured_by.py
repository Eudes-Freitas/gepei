import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0020_indicatormeasurement_dates"),
    ]

    operations = [
        migrations.AddField(
            model_name="indicatormeasurement",
            name="measured_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="performed_measurements",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="indicatormeasurement",
            name="measured_unit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="performed_measurements",
                to="core.organizationalunit",
            ),
        ),
    ]
