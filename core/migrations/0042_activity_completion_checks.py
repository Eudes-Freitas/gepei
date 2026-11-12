from django.db import migrations, models


def preserve_completed_activities(apps, schema_editor):
    Activity = apps.get_model("core", "Activity")
    Activity.objects.filter(progress__gte=100).update(blocker_checked=True, risk_checked=True)


class Migration(migrations.Migration):
    dependencies = [("core", "0041_allow_duplicate_quarterly_reports")]

    operations = [
        migrations.AddField(model_name="activity", name="blocker_checked", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="activity", name="risk_checked", field=models.BooleanField(default=False)),
        migrations.RunPython(preserve_completed_activities, migrations.RunPython.noop),
    ]
