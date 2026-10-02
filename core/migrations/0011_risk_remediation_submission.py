from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_risk_acceptance_with_reservations"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RiskRemediationSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("completion_summary", models.TextField()),
                ("evidence_reference", models.CharField(blank=True, max_length=255)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("acceptance", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="remediation_submissions", to="core.riskacceptance")),
                ("submitted_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="submitted_risk_remediations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-submitted_at", "-id"]},
        ),
    ]
