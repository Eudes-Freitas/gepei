from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Organization, OrganizationalUnit, Plan, PlanArtifact, StrategicAction
from core.pesp_alinea_data import ALINEAS, ORGAN_ALINEAS
from core.pesp_data import ACTIONS, OBJECTIVES


ORGANS = {
    "SESED": "Secretaria de Estado da Segurança Pública e da Defesa Social",
    "SEAP": "Secretaria de Estado da Administração Penitenciária",
    "PMRN": "Polícia Militar",
    "PCRN": "Polícia Civil",
    "PPRN": "Polícia Penal",
    "CBMRN": "Corpo de Bombeiros Militar",
    "PCIRN": "Polícia Científica",
    "SEMJIDH": "SEMJIDH",
    "COPDEC": "Coordenadoria Estadual de Proteção e Defesa Civil",
}


class Command(BaseCommand):
    help = "Cadastra ações, alíneas e órgãos das matrizes do PESP/RN 2022–2031."

    @transaction.atomic
    def handle(self, *args, **options):
        plan, _ = Plan.objects.get_or_create(
            acronym="PESP", plan_type=Plan.PlanType.PESP,
            defaults={
                "name": "Plano Estadual de Segurança Pública e Defesa Social do RN",
                "start_date": date(2022, 1, 1),
                "end_date": date(2031, 12, 31),
            },
        )
        government, _ = Organization.objects.get_or_create(
            acronym="GOV-RN", defaults={"name": "Governo do Estado do Rio Grande do Norte"},
        )
        units = {}
        for code, name in ORGANS.items():
            units[code], _ = OrganizationalUnit.objects.get_or_create(
                exclusive_plan=plan, acronym=code,
                defaults={"organization": government, "name": name, "unit_type": OrganizationalUnit.UnitType.SECTOR},
            )
        references = {}
        for code, description in OBJECTIVES.items():
            description = description[0].upper() + description[1:]
            title = description if len(description) <= 255 else description[:252].rsplit(" ", 1)[0] + "…"
            reference, _ = PlanArtifact.objects.get_or_create(
                plan=plan, code=f"OE {code}",
                defaults={"artifact_type": PlanArtifact.ArtifactType.REFERENCE, "title": title, "description": description},
            )
            if reference.artifact_type == PlanArtifact.ArtifactType.OBJECTIVE:
                reference.artifact_type = PlanArtifact.ArtifactType.REFERENCE
                reference.save(update_fields=["artifact_type"])
            references[code] = reference

        for number, title, organs, reference_codes, _ in ACTIONS:
            code = f"AE {number:02d}"
            item, _ = PlanArtifact.objects.get_or_create(
                plan=plan, code=code, artifact_type=PlanArtifact.ArtifactType.ACTION,
                defaults={"title": title},
            )
            # Mantém os registros agregados de cargas anteriores para seus vínculos históricos.
            StrategicAction.objects.filter(artifact__plan=plan, code=code).update(is_execution_item=False)
            for letter, description in ALINEAS[number].items():
                assigned = [units[org] for org, letters in ORGAN_ALINEAS[number].items() if letter in letters]
                action, _ = StrategicAction.objects.get_or_create(
                    artifact__plan=plan, code=f"{code}.{letter}",
                    defaults={
                        "artifact": item,
                        "title": description if len(description) <= 255 else description[:252].rsplit(" ", 1)[0] + "…",
                        "description": description,
                        "coordinating_unit": assigned[0],
                    },
                )
                action.participating_units.add(*(org for org in assigned if org.pk != action.coordinating_unit_id))
                action.related_objectives.add(*(references[ref] for ref in reference_codes))
        self.stdout.write(self.style.SUCCESS(
            f"PESP cadastrado com {len(units)} órgãos, {len(ACTIONS)} ações e {sum(map(len, ALINEAS.values()))} alíneas."
        ))
