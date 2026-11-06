import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_activity_requires_cost"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ActivityEvidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("evidence_type", models.CharField(choices=[("ANEXO", "Documento ou arquivo"), ("LINK", "Link"), ("FOTO", "Foto"), ("SEI", "Referência ao SEI"), ("OUTRA", "Outra")], max_length=10)),
                ("description", models.TextField(blank=True)),
                ("reference", models.CharField(blank=True, max_length=255)),
                ("url", models.URLField(blank=True)),
                ("attachment", models.FileField(blank=True, upload_to="activity_evidences/%Y/%m/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("activity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evidences", to="core.activity")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="ActivityBlocker",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.TextField()),
                ("expected_resolution_date", models.DateField(blank=True, null=True)),
                ("status", models.CharField(choices=[("ABERTO", "Aberto"), ("EM_TRATAMENTO", "Em tratamento"), ("RESOLVIDO", "Resolvido")], default="ABERTO", max_length=16)),
                ("resolution_note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("activity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="blockers", to="core.activity")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reported_activity_blockers", to=settings.AUTH_USER_MODEL)),
                ("resolution_owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assigned_activity_blockers", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["status", "expected_resolution_date", "-created_at"]},
        ),
    ]
