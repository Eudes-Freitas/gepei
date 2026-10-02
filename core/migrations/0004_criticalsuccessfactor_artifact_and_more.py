# Generated manually for the controlled PEI import.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_alter_strategicaction_due_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="criticalsuccessfactor",
            name="artifact",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="critical_success_factors",
                to="core.planartifact",
            ),
        ),
        migrations.AlterField(
            model_name="criticalsuccessfactor",
            name="action",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="critical_success_factors",
                to="core.strategicaction",
            ),
        ),
    ]
