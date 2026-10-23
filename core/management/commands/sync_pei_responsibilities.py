"""Confere e aplica os responsáveis do Apêndice B, sem apagar execução ou aferições."""
import json
from copy import deepcopy
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Indicator, OrganizationalUnit, Plan, PlanArtifact, QuarterlySectorReport, SectorReport, StrategicAction, StrategicTarget
from core.pei_indicator_data import INDICATOR_ROWS
from core.pei_responsibility_data import ACTION_COUNTS, OBJECTIVE_RESPONSIBILITIES, SOURCE_PAGES


class Command(BaseCommand):
    help = "Audita os vínculos do PEI conforme OBJETIVOS E AÇÕES.pdf. Sem --apply, apenas confere."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--rebuild-reports", action="store_true")
        parser.add_argument("--audit-file")

    @transaction.atomic
    def handle(self, *args, **options):
        from core.quarterly_reports import _snapshot
        plan = Plan.objects.get(acronym="PEI")
        organization_ids = set(StrategicAction.objects.filter(artifact__plan=plan).values_list("coordinating_unit__organization_id", flat=True))
        if len(organization_ids) != 1:
            raise CommandError("O plano precisa ter uma organização identificável para conferir as siglas dos setores.")
        units = {unit.acronym: unit for unit in OrganizationalUnit.objects.filter(organization_id=next(iter(organization_ids)))}
        missing = sorted({unit for group in OBJECTIVE_RESPONSIBILITIES.values() for unit in group} - units.keys())
        if missing:
            raise CommandError("Setores não encontrados: " + ", ".join(missing))
        objectives = {item.code: item for item in PlanArtifact.objects.filter(plan=plan, artifact_type=PlanArtifact.ArtifactType.OBJECTIVE)}
        # Validate the entire expected inventory before making any change.
        actions = {}
        items = {}
        for objective, count in ACTION_COUNTS.items():
            if f"OE {objective}" not in objectives:
                raise CommandError(f"Objetivo ausente: OE {objective}")
            for number in range(1, count + 1):
                code = f"AE {objective}.{number}"
                try:
                    actions[code] = StrategicAction.objects.get(artifact__plan=plan, code=code)
                except StrategicAction.DoesNotExist:
                    raise CommandError("Ação ausente: " + code)
        for row in INDICATOR_ROWS:
            number = row[0]
            try:
                target = StrategicTarget.objects.get(artifact__plan=plan, code=f"Mt {number}")
                indicator = Indicator.objects.filter(artifacts__plan=plan, code__in=[f"IE {number}", f"IR {number}"]).distinct().get()
            except (StrategicTarget.DoesNotExist, Indicator.DoesNotExist):
                raise CommandError("Meta ou indicador ausente: " + number)
            items[number] = target, indicator
        audit = {"source": "OBJETIVOS E AÇÕES.pdf, Apêndice B, páginas 51–60", "applied": options["apply"], "actions": [], "indicators_and_targets": [], "rebuilt_reports": []}
        for code, action in actions.items():
            objective = code.split()[1].split(".")[0]
            expected = set(OBJECTIVE_RESPONSIBILITIES[objective])
            previous = {action.coordinating_unit.acronym, *action.participating_units.values_list("acronym", flat=True)}
            audit["actions"].append({"code": code, "before": sorted(previous), "expected": sorted(expected), "changed": previous != expected, "pages": SOURCE_PAGES[objective]})
            if options["apply"]:
                if action.coordinating_unit.acronym not in expected:
                    action.coordinating_unit = units[OBJECTIVE_RESPONSIBILITIES[objective][0]]
                    action.save(update_fields=["coordinating_unit"])
                action.participating_units.set([units[name] for name in expected if units[name].pk != action.coordinating_unit_id])
        for number, (target, indicator) in items.items():
            objective = number.split(".")[0]
            expected = set(OBJECTIVE_RESPONSIBILITIES[objective])
            previous = {unit.acronym for unit in indicator.responsible_units.all()}
            if indicator.responsible_unit_id:
                previous.add(indicator.responsible_unit.acronym)
            correct_objective = objectives[f"OE {objective}"]
            linkage_correct = target.artifact_id == correct_objective.pk and set(indicator.targets.values_list("pk", flat=True)) == {target.pk} and set(indicator.artifacts.values_list("pk", flat=True)) == {correct_objective.pk}
            audit["indicators_and_targets"].append({"indicator": indicator.code, "target": target.code, "before": sorted(previous), "expected": sorted(expected), "changed": previous != expected or not linkage_correct, "pages": SOURCE_PAGES[objective]})
            if options["apply"]:
                if not indicator.responsible_unit_id or indicator.responsible_unit.acronym not in expected:
                    indicator.responsible_unit = units[OBJECTIVE_RESPONSIBILITIES[objective][0]]
                    indicator.save(update_fields=["responsible_unit"])
                indicator.responsible_units.set([units[name] for name in expected])
                target.artifact = correct_objective
                if target.action_id:
                    node = target.action.artifact
                    while node and node.artifact_type != PlanArtifact.ArtifactType.OBJECTIVE:
                        node = node.parent
                    if not node or node.pk != correct_objective.pk:
                        target.action = None
                target.save(update_fields=["artifact", "action"])
                indicator.artifacts.set([correct_objective])
                indicator.targets.set([target])
        if options["apply"] and options["rebuild_reports"]:
            for report in QuarterlySectorReport.objects.select_for_update().filter(plan=plan).select_related("unit", "plan"):
                previous = deepcopy(report.snapshot)
                history = previous.pop("previous_versions", [])
                history.append({"snapshot": previous, "reason": "Revisão dos vínculos conforme OBJETIVOS E AÇÕES.pdf", "replaced_at": timezone.now().isoformat()})
                snapshot = _snapshot(plan, report.unit, report.year, report.quarter)
                snapshot.update(previous_versions=history, last_edited_at=timezone.now().isoformat(), last_edited_by="revisão documental dos setores responsáveis", responsibility_source=audit["source"])
                report.snapshot = snapshot
                report.save(update_fields=["snapshot"])
                audit["rebuilt_reports"].append({"id": report.pk, "unit": report.unit.acronym, "year": report.year, "quarter": report.quarter, "counts": {key: len(snapshot[key]) for key in ("objectives", "targets", "indicators", "actions")}})
        if options["apply"] and options["rebuild_reports"]:
            from core.views import _sector_report_content, _sector_report_snapshot
            for report in SectorReport.objects.select_for_update().filter(cycle__plan=plan).select_related("cycle", "unit"):
                if not report.snapshot and report.status != SectorReport.Status.CONSOLIDATED:
                    continue
                previous = deepcopy(report.snapshot)
                history = previous.pop("previous_versions", [])
                history.append({"snapshot": previous, "reason": "Revisão dos vínculos conforme OBJETIVOS E AÇÕES.pdf", "replaced_at": timezone.now().isoformat()})
                snapshot = _sector_report_snapshot(_sector_report_content(report))
                snapshot["previous_versions"] = history
                snapshot["responsibility_source"] = audit["source"]
                report.snapshot = snapshot
                report.save(update_fields=["snapshot"])
                audit["rebuilt_reports"].append({"kind": "sector_cycle", "id": report.pk, "unit": report.unit.acronym, "cycle": report.cycle_id, "counts": {key: snapshot[key] for key in ("action_count", "indicator_count")}})
        if options["audit_file"]:
            Path(options["audit_file"]).write_text(json.dumps(audit, ensure_ascii=False, indent=2))
        changed_actions = sum(item["changed"] for item in audit["actions"])
        changed_indicators = sum(item["changed"] for item in audit["indicators_and_targets"])
        self.stdout.write(f"39 ações conferidas: {changed_actions} divergências. 37 pares meta/indicador conferidos: {changed_indicators} divergências. Relatórios refeitos: {len(audit['rebuilt_reports'])}. Aplicado: {options['apply']}.")
