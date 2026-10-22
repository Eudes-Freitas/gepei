from django.db import migrations
from django.db.models import Q


def reclassify_risks(apps, schema_editor):
    Risk = apps.get_model("core", "Risk")
    alias = schema_editor.connection.alias
    risks = Risk.objects.using(alias).filter(status="MATERIALIZADO").filter(
        Q(action__action_plan__isnull=True) | Q(action__status="NAO_INICIADA")
    )
    for risk in risks.iterator():
        risk.status = "EM_TRATAMENTO" if risk.treatment or risk.treatments.using(alias).exists() else "IDENTIFICADO"
        risk.save(using=alias, update_fields=["status"])


class Migration(migrations.Migration):
    dependencies = [("core", "0027_risk_required_activity")]
    operations = [migrations.RunPython(reclassify_risks, migrations.RunPython.noop)]
