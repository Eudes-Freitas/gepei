from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0040_merge_20261110_1311")]

    operations = [
        migrations.RemoveConstraint(
            model_name="quarterlysectorreport",
            name="unique_quarterly_sector_report",
        ),
    ]
