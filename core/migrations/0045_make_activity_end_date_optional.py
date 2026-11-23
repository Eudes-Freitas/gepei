from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0044_correct_activity_completion_checks")]

    operations = [
        migrations.AlterField(
            model_name="activity",
            name="end_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
