from decimal import Decimal

from django.db import migrations


def correct_checks(apps, schema_editor):
    Activity = apps.get_model("core", "Activity")
    StrategicAction = apps.get_model("core", "StrategicAction")
    affected_plans = set()

    for activity in Activity.objects.filter(progress__gte=100).iterator():
        blocker_confirmed = activity.blockers.exists()
        risk_confirmed = activity.risk_non_occurrences.exists() or activity.risks.filter(materializations__isnull=False).exists()
        changes = {"blocker_checked": blocker_confirmed, "risk_checked": risk_confirmed}
        if not (blocker_confirmed and risk_confirmed):
            changes.update(progress=Decimal("99"), status="EM_ANDAMENTO")
            affected_plans.add(activity.action_plan_id)
        Activity.objects.filter(pk=activity.pk).update(**changes)

    for plan_id in affected_plans:
        activities = list(Activity.objects.filter(action_plan_id=plan_id))
        action = StrategicAction.objects.get(action_plan__id=plan_id)
        progress = sum((item.weight * item.progress / 100 for item in activities), Decimal("0"))
        changes = {"progress": progress}
        if action.status not in ("BLOQUEADA", "SUSPENSA"):
            changes["status"] = "EM_ANDAMENTO" if any(item.progress > 0 for item in activities) else "NAO_INICIADA"
        StrategicAction.objects.filter(pk=action.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [("core", "0043_alter_activityevidence_evidence_type")]

    operations = [migrations.RunPython(correct_checks, migrations.RunPython.noop)]
