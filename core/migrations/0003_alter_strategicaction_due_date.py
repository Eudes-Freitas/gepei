# Generated manually for the controlled PEI import.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_activity_description_strategicaction_description_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="strategicaction",
            name="due_date",
            field=models.DateField(
                blank=True,
                help_text="Preenchido no cronograma operacional; não é inferido da vigência do PEI.",
                null=True,
            ),
        ),
    ]
