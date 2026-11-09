from django.db import migrations


DIMENSIONS = (
    ("Gestão de Pessoas e Infraestrutura", ("Eixo 01", "Eixo 02", "Eixo 03", "Eixo 04")),
    ("Processos Internos", ("Eixo 05", "Eixo 06")),
    ("Resultados Institucionais", ("Eixo 07", "Eixo 08")),
    ("Impacto para a Sociedade", ("Eixo 09",)),
)


def repair_pei_dimensions(apps, schema_editor):
    Plan = apps.get_model("core", "Plan")
    PlanArtifact = apps.get_model("core", "PlanArtifact")
    for plan in Plan.objects.filter(plan_type="PEI"):
        for title, axis_codes in DIMENSIONS:
            dimension = PlanArtifact.objects.filter(
                plan=plan,
                parent__isnull=True,
                artifact_type="DIMENSAO",
                title=title,
            ).first()
            if not dimension:
                dimension = PlanArtifact.objects.create(
                    plan=plan,
                    parent=None,
                    artifact_type="DIMENSAO",
                    code="",
                    title=title,
                )
            PlanArtifact.objects.filter(
                plan=plan,
                artifact_type="EIXO",
                code__in=axis_codes,
            ).update(parent=dimension)


class Migration(migrations.Migration):
    dependencies = [("core", "0012_risk_monitoring_status")]

    operations = [migrations.RunPython(repair_pei_dimensions, migrations.RunPython.noop)]
