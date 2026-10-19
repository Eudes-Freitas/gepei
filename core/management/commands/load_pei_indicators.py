"""Carrega metas e indicadores do Quadro de Indicadores do PEI (Apêndice A), idempotente."""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Indicator, OrganizationalUnit, PlanArtifact, StrategicAction, StrategicTarget
from core.pei_indicator_data import (
    INDICATOR_ACTION_CODES,
    INDICATOR_RESPONSIBLE_UNITS,
    INDICATOR_ROWS,
    INDICATOR_UNITS_SOURCES,
)


class Command(BaseCommand):
    help = "Carrega as metas (Mt NN.N) e os indicadores (IE NN.N) do PEI e os vincula ao objetivo OE NN correspondente."

    @transaction.atomic
    def handle(self, *args, **options):
        objectives = {}
        missing = set()
        created_indicators = created_targets = 0

        for number, name, kind, periodicity, polarity, purpose, formula, target_text, target_value in INDICATOR_ROWS:
            objective_code = f"OE {number.split('.')[0]}"
            if objective_code not in objectives:
                candidates = PlanArtifact.objects.filter(
                    artifact_type=PlanArtifact.ArtifactType.OBJECTIVE, code=objective_code
                )
                objectives[objective_code] = candidates.filter(plan__acronym="PEI").first() or candidates.first()
            objective = objectives[objective_code]
            if not objective:
                missing.add(objective_code)
                continue

            action = StrategicAction.objects.filter(
                artifact__parent=objective,
                code=INDICATOR_ACTION_CODES[number],
            ).first()

            target_defaults = {
                "description": target_text,
                "target_value": target_value,
                "reference_period": periodicity.rstrip("."),
            }
            if action:
                target_defaults["action"] = action
            target, target_created = StrategicTarget.objects.update_or_create(
                artifact=objective,
                code=f"Mt {number}",
                defaults=target_defaults,
            )
            created_targets += target_created

            indicator = (
                Indicator.objects.filter(code=f"IE {number}", artifacts=objective).first()
                or Indicator.objects.filter(code=f"IR {number}", artifacts=objective).first()
                or Indicator.objects.filter(code__in=[f"IE {number}", f"IR {number}"]).first()
            )
            indicator_created = indicator is None
            if indicator_created:
                indicator = Indicator()
            indicator.code = f"IE {number}"
            indicator.name = name
            indicator.indicator_type = kind
            indicator.description = purpose
            indicator.formula = formula
            indicator.frequency = Indicator.Frequency.BIENNIAL if periodicity.startswith("Bienal") else Indicator.Frequency.ANNUAL
            indicator.direction = (
                Indicator.Direction.LOWER_IS_BETTER if polarity == "Negativa" else Indicator.Direction.HIGHER_IS_BETTER
            )
            unit, source = INDICATOR_UNITS_SOURCES.get(number, ("", ""))
            indicator.unit_of_measure = indicator.unit_of_measure or unit
            indicator.data_source = indicator.data_source or source
            if not indicator.responsible_unit_id:
                fallback_action = action or StrategicAction.objects.filter(artifact__parent=objective).order_by("code").first()
                indicator.responsible_unit = OrganizationalUnit.objects.filter(
                    organization=fallback_action.coordinating_unit.organization,
                    acronym=INDICATOR_RESPONSIBLE_UNITS[number.split(".")[0]],
                ).first() if fallback_action else None
                if not indicator.responsible_unit:
                    indicator.responsible_unit = fallback_action.coordinating_unit if fallback_action else None
            indicator.save()
            indicator.artifacts.set([objective])
            indicator.targets.set([target])
            created_indicators += indicator_created

        total = len(INDICATOR_ROWS) - sum(1 for row in INDICATOR_ROWS if f"OE {row[0].split('.')[0]}" in missing)
        self.stdout.write(
            self.style.SUCCESS(
                f"{total} metas e indicadores carregados ({created_targets} metas e {created_indicators} indicadores novos)."
            )
        )
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    "Objetivos não encontrados (carregue o plano antes): " + ", ".join(sorted(missing))
                )
            )
