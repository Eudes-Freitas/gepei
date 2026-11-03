"""Sincroniza apenas as linhas de base de 2024 da tabela de METAS.pdf."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Indicator
from core.pei_baseline_data import REFERENCE_PARAMETERS


class Command(BaseCommand):
    help = "Confere as 37 linhas de base de 2024 do PEI; use --apply para corrigir indicadores e aferições."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        items = []
        for number, reference in REFERENCE_PARAMETERS.items():
            matches = Indicator.objects.filter(
                code__in=(f"IE {number}", f"IR {number}"), artifacts__plan__acronym="PEI"
            ).distinct()
            if matches.count() != 1:
                raise CommandError(f"Indicador ausente ou ambíguo: {number}")
            items.append((matches.get(), reference["baseline_text"]))

        changed_indicators = changed_measurements = 0
        for indicator, baseline in items:
            if indicator.baseline != baseline:
                self.stdout.write(f"{indicator.code}: {indicator.baseline!r} → {baseline!r}")
                changed_indicators += 1
                if options["apply"]:
                    indicator.baseline = baseline
                    indicator.save(update_fields=["baseline"])
            for measurement in indicator.measurements.all():
                baseline_date = date(2024, 12, 31) if baseline != "Não há" else None
                if measurement.baseline_value != baseline or measurement.baseline_date != baseline_date:
                    changed_measurements += 1
                    if options["apply"]:
                        measurement.baseline_value = baseline
                        measurement.baseline_date = baseline_date
                        measurement.save(update_fields=["baseline_value", "baseline_date"])

        self.stdout.write(self.style.SUCCESS(
            f"Conferidos {len(items)} indicadores. Linhas de base a corrigir: {changed_indicators}; "
            f"aferições a corrigir: {changed_measurements}. Aplicado: {options['apply']}."
        ))
