# Generated manually for the activity-plan evolution.

from django.db import migrations, models
import django.db.models.deletion


def define_activity_positions(apps, schema_editor):
    Activity = apps.get_model("core", "Activity")
    action_plan_ids = Activity.objects.order_by().values_list("action_plan_id", flat=True).distinct()
    for action_plan_id in action_plan_ids:
        activities = Activity.objects.filter(action_plan_id=action_plan_id).order_by("end_date", "id")
        for position, activity in enumerate(activities, start=1):
            Activity.objects.filter(pk=activity.pk).update(position=position)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_criticalsuccessfactor_artifact_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="activity",
            old_name="due_date",
            new_name="end_date",
        ),
        migrations.AddField(
            model_name="activity",
            name="start_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="position",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="activity",
            name="planned_cost",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="disbursed_cost",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="funding_source",
            field=models.CharField(blank=True, choices=[("FAF", "Fundo a Fundo (FaF)"), ("0500", "Fonte 0500"), ("CONVENIO", "Convênio"), ("OUTRA", "Outra")], max_length=12),
        ),
        migrations.AddField(
            model_name="activity",
            name="funding_source_other",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="activity",
            name="financial_reference",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="activity",
            name="financial_responsible_unit",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="financially_monitored_activities", to="core.organizationalunit"),
        ),
        migrations.RunPython(define_activity_positions, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="activity",
            options={"ordering": ["position", "start_date", "end_date", "id"]},
        ),
    ]
