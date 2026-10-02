import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_activity_follow_up"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RiskAssessment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("assessment_type", models.CharField(choices=[("ATUAL", "Avaliação atual"), ("INERENTE", "Risco inerente"), ("RESIDUAL", "Risco residual")], default="ATUAL", max_length=10)),
                ("probability", models.PositiveSmallIntegerField()),
                ("impact", models.PositiveSmallIntegerField()),
                ("notes", models.TextField(blank=True)),
                ("assessed_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("risk", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assessments", to="core.risk")),
            ],
            options={"ordering": ["-assessed_at", "-id"]},
        ),
        migrations.CreateModel(
            name="RiskTreatment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("decision", models.CharField(choices=[("ACEITAR", "Aceitar"), ("MITIGAR", "Mitigar"), ("EVITAR", "Evitar"), ("TRANSFERIR", "Transferir")], max_length=12)),
                ("justification", models.TextField(blank=True)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("preventive_measure", models.TextField(blank=True)),
                ("contingency_measure", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_risk_treatments", to=settings.AUTH_USER_MODEL)),
                ("responsible", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="risk_treatments", to=settings.AUTH_USER_MODEL)),
                ("risk", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="treatments", to="core.risk")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="RiskMaterialization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("occurred_on", models.DateField()),
                ("description", models.TextField()),
                ("actual_impact", models.TextField()),
                ("actions_taken", models.TextField()),
                ("evidence_reference", models.CharField(blank=True, max_length=255)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("recorded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("risk", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="materializations", to="core.risk")),
            ],
            options={"ordering": ["-occurred_on", "-id"]},
        ),
        migrations.CreateModel(
            name="RiskAcceptance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("decision", models.CharField(choices=[("ACEITO", "Aceito"), ("NAO_ACEITO", "Não aceito")], max_length=10)),
                ("justification", models.TextField()),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("authority", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="risk_acceptances", to=settings.AUTH_USER_MODEL)),
                ("recorded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recorded_risk_acceptances", to=settings.AUTH_USER_MODEL)),
                ("risk", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="acceptances", to="core.risk")),
            ],
            options={"ordering": ["-recorded_at", "-id"]},
        ),
    ]
