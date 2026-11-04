"""Rebuild quarterly PEI reports after checking each sector's current links."""

from copy import deepcopy

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import QuarterlySectorReport
from core.quarterly_reports import _snapshot


class Command(BaseCommand):
    help = "Confere todos os relatórios trimestrais com os vínculos atuais. Use --apply para atualizar os defasados."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        reports = QuarterlySectorReport.objects.select_related("plan", "unit").order_by("unit__acronym", "year", "quarter", "pk")
        if options["apply"]:
            reports = reports.select_for_update()
        for report in reports:
            current = _snapshot(report.plan, report.unit, report.year, report.quarter)
            sections = ("objectives", "targets", "indicators", "actions")
            before = {section: len(report.snapshot.get(section, [])) for section in sections}
            after = {section: len(current[section]) for section in sections}
            old_ids = {section: {item.get("id") for item in report.snapshot.get(section, [])} for section in sections}
            new_ids = {section: {item.get("id") for item in current[section]} for section in sections}
            changed = old_ids != new_ids
            label = f"{report.unit.acronym} · {report.quarter}º trimestre de {report.year} · {report.plan.acronym}"
            if changed and options["apply"]:
                previous = deepcopy(report.snapshot)
                history = previous.pop("previous_versions", [])
                history.append({"snapshot": previous, "reason": "Revisão dos vínculos por setor", "replaced_at": timezone.now().isoformat()})
                current["previous_versions"] = history
                current["last_edited_at"] = timezone.now().isoformat()
                current["last_edited_by"] = "revisão dos vínculos por setor"
                report.snapshot = current
                report.save(update_fields=["snapshot"])
            state = "atualizado" if changed and options["apply"] else "defasado" if changed else "correto"
            self.stdout.write(f"{label}: {state}; antes={before}; esperado={after}")
