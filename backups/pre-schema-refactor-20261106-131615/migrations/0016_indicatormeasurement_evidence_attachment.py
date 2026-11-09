from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0015_report_cycles_and_sector_reports")]

    operations = [
        migrations.AddField(
            model_name="indicatormeasurement",
            name="evidence_attachment",
            field=models.FileField(blank=True, upload_to="indicator_measurements/%Y/%m/"),
        )
    ]
