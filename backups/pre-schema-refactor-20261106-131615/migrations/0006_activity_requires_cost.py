from django.db import migrations, models


def mark_existing_financial_activities(apps, schema_editor):
    Activity = apps.get_model("core", "Activity")
    Activity.objects.exclude(planned_cost__isnull=True).exclude(planned_cost=0).update(requires_financial_resource=True)
    Activity.objects.exclude(disbursed_cost__isnull=True).exclude(disbursed_cost=0).update(requires_financial_resource=True)
    Activity.objects.exclude(funding_source="").update(requires_financial_resource=True)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_activity_operational_dates_order_and_financial_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="requires_financial_resource",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing_financial_activities, migrations.RunPython.noop),
    ]
