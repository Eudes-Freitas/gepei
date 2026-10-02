from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0013_repair_pei_dimension_hierarchy")]

    operations = [
        migrations.AddField(
            model_name="indicatormeasurement",
            name="expected_value",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Meta prevista especificamente para o período desta aferição.",
                max_digits=14,
                null=True,
            ),
        )
    ]
