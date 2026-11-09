from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0014_indicatormeasurement_expected_value"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="ReportCycle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=180)),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                ("due_date", models.DateField()),
                ("status", models.CharField(choices=[("ABERTO", "Aberto para preenchimento"), ("EM_CONSOLIDACAO", "Em consolidação"), ("ENCERRADO", "Encerrado")], default="ABERTO", max_length=18)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_report_cycles", to=settings.AUTH_USER_MODEL)),
                ("participating_units", models.ManyToManyField(related_name="report_cycles", to="core.organizationalunit")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="report_cycles", to="core.plan")),
            ],
            options={"ordering": ["-period_end", "-id"]},
        ),
        migrations.CreateModel(
            name="SectorReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("RASCUNHO", "Rascunho"), ("ENVIADO", "Enviado para validação"), ("DEVOLVIDO", "Devolvido para correção"), ("APROVADO", "Aprovado"), ("CONSOLIDADO", "Consolidado")], default="RASCUNHO", max_length=14)),
                ("executive_summary", models.TextField(blank=True)),
                ("complements", models.TextField(blank=True)),
                ("next_steps", models.TextField(blank=True)),
                ("management_decision_needed", models.TextField(blank=True)),
                ("validator_comment", models.TextField(blank=True)),
                ("resubmission_due_date", models.DateField(blank=True, null=True)),
                ("snapshot", models.JSONField(blank=True, default=dict)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("validated_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cycle", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sector_reports", to="core.reportcycle")),
                ("prepared_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="prepared_sector_reports", to=settings.AUTH_USER_MODEL)),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sector_reports", to="core.organizationalunit")),
                ("validator", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="assigned_sector_reports", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["unit__name"]},
        ),
        migrations.AddConstraint(model_name="sectorreport", constraint=models.UniqueConstraint(fields=("cycle", "unit"), name="unique_report_per_cycle_unit")),
    ]
