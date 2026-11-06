from django.db import migrations, models
import django.db.models.deletion
from datetime import date


def link_existing_risks(apps, schema_editor):
    Risk = apps.get_model('core', 'Risk')
    ActionPlan = apps.get_model('core', 'ActionPlan')
    Activity = apps.get_model('core', 'Activity')
    alias = schema_editor.connection.alias
    for risk in Risk.objects.using(alias).filter(activity__isnull=True).select_related('action'):
        plan, _ = ActionPlan.objects.using(alias).get_or_create(
            action_id=risk.action_id, defaults={'manager_id': risk.owner_id}
        )
        activity = Activity.objects.using(alias).create(
            action_plan_id=plan.pk,
            executor_id=risk.owner_id,
            title=f'Atividade vinculada ao risco: {risk.title}'[:255],
            description='Atividade criada para vincular um risco anteriormente sem atividade. Revisar o planejamento.',
            weight=0,
            end_date=risk.action.due_date or date(2026, 12, 31),
        )
        risk.activity_id = activity.pk
        risk.save(using=alias, update_fields=['activity'])


class Migration(migrations.Migration):
    dependencies = [('core', '0026_quarterlysectorreport')]
    operations = [
        migrations.RunPython(link_existing_risks, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='risk', name='activity',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='risks', to='core.activity'),
        ),
    ]
