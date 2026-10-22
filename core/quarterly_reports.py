import calendar
import re
from datetime import date

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.urls import reverse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import QuarterlyReportForm
from .models import Activity, ActivityBlocker, ActivityEvidence, Indicator, OrganizationalUnit, Plan, PlanArtifact, QuarterlySectorReport, Risk, StrategicAction, StrategicTarget
from .permissions import scope_units, selected_unit_for_request, user_unit_ids, view_scope_units


def _can_view(user):
    return any(user.has_perm(p) for p in ("core.view_quarterlysectorreport", "core.view_sectorreport", "core.view_reportcycle", "core.consolidate_quarterlysectorreport"))


def _period(year, quarter):
    month = (quarter - 1) * 3 + 1
    return date(year, month, 1), date(year, month + 2, calendar.monthrange(year, month + 2)[1])


def _snapshot(plan, unit, year, quarter):
    from .views import _indicator_signal
    start, end = _period(year, quarter)
    actions = list(StrategicAction.objects.filter(artifact__plan=plan).filter(Q(coordinating_unit=unit) | Q(participating_units=unit)).distinct().select_related("artifact"))
    activities = list(Activity.objects.filter(action_plan__action__in=actions).select_related("action_plan__action", "executor"))
    artifacts = {a.id: a for a in PlanArtifact.objects.filter(plan=plan)}
    action_artifact_ids = set()
    for action in actions:
        node = artifacts.get(action.artifact_id)
        visited = set()
        while node and node.pk not in visited:
            visited.add(node.pk)
            action_artifact_ids.add(node.pk)
            node = artifacts.get(node.parent_id)
    targets = list(StrategicTarget.objects.filter(artifact__plan=plan).filter(Q(action__in=actions) | Q(action__isnull=True, indicators__responsible_unit=unit) | Q(action__isnull=True, indicators__responsible_units=unit) | Q(action__isnull=True, artifact_id__in=action_artifact_ids)).distinct().select_related("artifact"))
    indicators = list(Indicator.objects.filter(((Q(responsible_unit=unit) | Q(responsible_units=unit)) & (Q(artifacts__plan=plan) | Q(targets__artifact__plan=plan))) | Q(targets__in=targets)).distinct().prefetch_related("measurements", "artifacts", "responsible_units", "targets__artifact__plan"))
    objective_ids = set()
    artifact_ids = {a.artifact_id for a in actions} | {t.artifact_id for t in targets} | {a.id for i in indicators for a in i.artifacts.all() if a.plan_id == plan.id}
    for pk in artifact_ids:
        node = artifacts.get(pk)
        visited = set()
        while node and node.id not in visited:
            visited.add(node.id)
            if node.artifact_type == PlanArtifact.ArtifactType.OBJECTIVE:
                objective_ids.add(node.id)
            node = artifacts.get(node.parent_id)
    indicator_rows = []
    for indicator in indicators:
        measurements = [m for m in indicator.measurements.all() if (m.period_end or timezone.localtime(m.recorded_at).date()) <= end]
        measurements.sort(key=lambda m: (m.period_end or timezone.localtime(m.recorded_at).date(), m.recorded_at, m.pk), reverse=True)
        indicator._prefetched_objects_cache["measurements"] = measurements
        signal = _indicator_signal(indicator, evaluation_date=end)
        latest = signal["measurement"]
        indicator_rows.append({"id": indicator.id, "code": indicator.code, "name": indicator.name, "formula": indicator.formula, "unit": indicator.measurement_unit, "reference_parameters": indicator.reference_parameters, "source": indicator.data_source, "target_ids": [t.pk for t in indicator.targets.all()], "history": [{"period": m.reference_period, "result": m.measured_value, "expected": str(m.expected_value) if m.expected_value is not None else None} for m in measurements], "responsible_units": indicator.responsible_units_label, "status": signal["label"], "achievement": signal["achievement"], "latest_result": latest.measured_value if latest else None, "latest_period": latest.reference_period if latest else "", "measurements": [{"period": m.reference_period, "result": m.measured_value, "expected": str(m.expected_value) if m.expected_value is not None else None, "baseline": m.baseline_value, "source": m.source_reference, "id": m.pk, "file": m.evidence_attachment.name, "period_end": m.period_end.isoformat() if m.period_end else ""} for m in measurements if (m.period_end or timezone.localtime(m.recorded_at).date()) >= start]})
    risks = Risk.objects.filter(action__in=actions).select_related("action", "activity")
    evidences = ActivityEvidence.objects.filter(activity__in=activities, created_at__date__range=(start, end)).select_related("activity")
    blockers = ActivityBlocker.objects.filter(activity__in=activities)
    return {
        "unit": unit.name, "unit_acronym": unit.acronym, "plan": plan.name, "plan_acronym": plan.acronym,
        "year": year, "quarter": quarter, "period_start": start.isoformat(), "period_end": end.isoformat(), "period_label": f"{start:%d/%m/%Y} a {end:%d/%m/%Y}",
        "scope_version": 2,
        "contains_test_data": any("[TESTE]" in m["period"] for row in indicator_rows for m in row["measurements"]) or any("[TESTE]" in a.title for a in activities),
        "objectives": [{"id": pk, "code": artifacts[pk].code, "title": artifacts[pk].title} for pk in sorted(objective_ids)],
        "targets": [{"id": t.pk, "code": t.code, "description": t.description, "value": t.target_value, "unit": t.unit_of_measure, "period": t.reference_period, "objective": t.artifact.code} for t in targets],
        "indicators": indicator_rows,
        "actions": [{"id": a.pk, "code": a.code, "title": a.title, "status": a.get_status_display(), "progress": str(a.progress), "due_date": a.due_date.isoformat() if a.due_date else ""} for a in actions],
        "activities": [{"id": a.pk, "action_id": a.action_plan.action_id, "action": a.action_plan.action.code, "title": a.title, "status": a.get_status_display(), "progress": str(a.progress), "executor": a.executor.get_full_name() or a.executor.username} for a in activities],
        "risks": [{"id": r.pk, "title": r.title, "action": r.action.code, "status": r.get_status_display(), "level": r.level, "cause": r.cause, "control": r.preventive_measure} for r in risks],
        "blockers": [{"id": b.pk, "description": b.description, "status": b.get_status_display()} for b in blockers],
        "evidences": [{"id": e.pk, "activity_id": e.activity_id, "title": e.title, "activity": e.activity.title, "reference": e.reference, "url": e.url, "file": e.attachment.name} for e in evidences],
        "planned_cost": str(sum(a.planned_cost or 0 for a in activities)), "disbursed_cost": str(sum(a.disbursed_cost or 0 for a in activities)),
    }


@login_required
def overview(request):
    if not _can_view(request.user):
        raise PermissionDenied
    today = timezone.localdate()
    selected_unit = selected_unit_for_request(request)
    selected_plan = request.GET.get("plan", "")
    view_units = view_scope_units(OrganizationalUnit.objects.order_by("name"), request.user)
    write_units = scope_units(OrganizationalUnit.objects.order_by("name"), request.user)
    can_consolidate = request.user.has_perm("core.consolidate_quarterlysectorreport")
    initial = {"unit": selected_unit, "plan": selected_plan or Plan.objects.filter(active=True).values_list("pk", flat=True).first(), "year": today.year, "quarter": (today.month - 1) // 3 + 1}
    form = QuarterlyReportForm(request.POST if request.method == "POST" else None, units=write_units, initial=initial)
    if request.method == "POST":
        if not can_consolidate:
            raise PermissionDenied
        if form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                # Serialize consolidation requests for the same sector.
                unit = OrganizationalUnit.objects.select_for_update().get(pk=data["unit"].pk)
                report, created = QuarterlySectorReport.objects.get_or_create(plan=data["plan"], unit=unit, year=data["year"], quarter=data["quarter"], defaults={"consolidated_by": request.user, "snapshot": _snapshot(data["plan"], unit, data["year"], data["quarter"])})
            messages.success(request, "Relatório trimestral consolidado." if created else "Este setor já tem relatório consolidado para o plano e trimestre escolhidos.")
            return redirect("quarterly_report_detail", report_id=report.id)
    reports = QuarterlySectorReport.objects.filter(unit__in=view_units).select_related("unit", "plan", "consolidated_by")
    if selected_unit.isdigit():
        reports = reports.filter(unit_id=selected_unit)
    if selected_plan.isdigit():
        reports = reports.filter(plan_id=selected_plan)
    available_periods = [{"value": f"{year}-{quarter}", "label": f"{quarter}º trimestre de {year}"} for year, quarter in reports.order_by("-year", "-quarter").values_list("year", "quarter").distinct()]
    selected_period = request.GET.get("period", "")
    match = re.fullmatch(r"([2-9]\d{3})-([1-4])", selected_period)
    available_years = list(reports.order_by("-year").values_list("year", flat=True).distinct())
    selected_year = request.GET.get("year", "")
    selected_quarter = request.GET.get("quarter", "")
    if match:
        selected_year, selected_quarter = match.groups()
        if not any(item["value"] == selected_period for item in available_periods):
            available_periods.insert(0, {"value": selected_period, "label": f"{selected_quarter}º trimestre de {selected_year}"})
    else:
        selected_period = ""
    if selected_year.isascii() and selected_year.isdigit() and len(selected_year) == 4:
        reports = reports.filter(year=int(selected_year))
    else:
        selected_year = ""
    if selected_quarter in ("1", "2", "3", "4"):
        reports = reports.filter(quarter=int(selected_quarter))
    else:
        selected_quarter = ""
    if not selected_period and selected_year and selected_quarter:
        selected_period = f"{selected_year}-{selected_quarter}"
    units = view_units.filter(pk=selected_unit) if selected_unit.isdigit() else view_units
    if selected_period:
        units = units.filter(pk__in=reports.values("unit_id"))
    sector_rows = [{"unit": unit, "reports": [r for r in reports if r.unit_id == unit.pk], "can_consolidate": can_consolidate and write_units.filter(pk=unit.pk).exists()} for unit in units]
    return render(request, "core/quarterly_report_overview.html", {"units": view_units, "selected_unit": selected_unit, "plans": Plan.objects.filter(active=True), "selected_plan": selected_plan, "sector_rows": sector_rows, "consolidation_form": form, "can_consolidate": can_consolidate, "available_years": available_years, "selected_year": selected_year, "selected_quarter": selected_quarter, "quarters": range(1, 5), "available_periods": available_periods, "selected_period": selected_period})


def repair_report_scope(report):
    """Complementa a abrangência antiga, preservando os valores já consolidados."""
    from copy import deepcopy
    if report.snapshot.get("scope_version", 1) >= 2:
        return False
    corrected = _snapshot(report.plan, report.unit, report.year, report.quarter)
    snapshot = deepcopy(report.snapshot)
    def key(section, item):
        if section == "indicators":
            return item.get("id") or item.get("code") or item.get("name")
        if section in ("objectives", "targets", "actions"):
            return item.get("code") or item.get("description") or item.get("title")
        if section in ("activities", "risks"):
            return (item.get("action"), item.get("title"))
        if section == "blockers":
            return item.get("description")
        return (item.get("activity"), item.get("title"), item.get("file"))
    for section in ("objectives", "targets", "indicators", "actions", "activities", "risks", "blockers", "evidences"):
        rows = snapshot.setdefault(section, [])
        existing = {key(section, item): item for item in rows}
        for item in corrected[section]:
            previous = existing.get(key(section, item))
            if previous is None:
                rows.append(item)
                existing[key(section, item)] = item
            else:
                for field in ("id", "activity_id", "action_id"):
                    if field in item:
                        previous.setdefault(field, item[field])
                if section == "indicators":
                    for measurement in previous.get("measurements", []):
                        match = next((m for m in item["measurements"] if m.get("period") == measurement.get("period") and m.get("result") == measurement.get("result")), None)
                        if match:
                            for field in ("id", "file", "period_end"):
                                measurement.setdefault(field, match.get(field, ""))
    # Financial totals follow the preserved rows, including added participation.
    from decimal import Decimal
    for field in ("planned_cost", "disbursed_cost"):
        old_keys = {key("activities", item) for item in report.snapshot.get("activities", [])}
        added_ids = [item["id"] for item in corrected["activities"] if key("activities", item) not in old_keys]
        additional = sum((getattr(item, field) or Decimal("0") for item in Activity.objects.filter(pk__in=added_ids)), Decimal("0"))
        snapshot[field] = str(Decimal(snapshot.get(field, "0")) + additional)
    snapshot["scope_version"] = 2
    snapshot["scope_revised_at"] = timezone.now().isoformat()
    report.snapshot = snapshot
    report.save(update_fields=["snapshot"])
    return True


def _report_display_data(snapshot, report=None):
    """Adiciona classes visuais sem alterar os dados consolidados."""
    data = dict(snapshot)
    signal_classes = {"Conforme": "green", "Atenção": "yellow", "Alerta": "orange", "Crítico": "red"}
    data["indicators"] = [{**item, "signal_class": signal_classes.get(item.get("status"), "gray")} for item in snapshot.get("indicators", [])]
    action_classes = {label: value.lower() for value, label in [*StrategicAction.Status.choices, (Activity.PAUSED, "Pausada")]}
    risk_classes = {label: value.lower() for value, label in Risk.Status.choices}
    blocker_classes = {"Resolvido": "concluida", "Em tratamento": "em_andamento", "Aberto": "atrasada"}
    for key, classes in (("actions", action_classes), ("activities", action_classes), ("risks", risk_classes), ("blockers", blocker_classes)):
        data[key] = [{**item, "status_class": classes.get(item.get("status"), "neutral")} for item in snapshot.get(key, [])]
    # Group the preserved activity rows by their action, without querying live data.
    actions_by_id = {}
    actions_by_code = {}
    for action in data["actions"]:
        action["activities"] = []
        if action.get("id") is not None:
            actions_by_id[action["id"]] = action
        if action.get("code"):
            actions_by_code.setdefault(action["code"], []).append(action)
        try:
            action["due_date_display"] = date.fromisoformat(action.get("due_date") or "").strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            action["due_date_display"] = action.get("due_date") or "A definir"
    data["unassigned_activities"] = []
    for activity in data["activities"]:
        action = actions_by_id.get(activity.get("action_id"))
        if activity.get("action_id") is None:
            matches = actions_by_code.get(activity.get("action"), [])
            action = matches[0] if len(matches) == 1 else None
        if action is None:
            data["unassigned_activities"].append(activity)
        else:
            action["activities"].append(activity)
    from .views import _decimal_from_measurement
    linked_target_ids = set()
    for indicator_index, item in enumerate(data["indicators"]):
        ids = set(item.get("target_ids", []))
        item["targets"] = [dict(target) for target in snapshot.get("targets", []) if target.get("id") in ids]
        linked_target_ids.update(ids)
        item["measurements"] = [dict(m) for m in item.get("measurements", [])]
        chart_rows = []
        for measurement_index, measurement in enumerate(item["measurements"]):
            value = _decimal_from_measurement(measurement.get("result"))
            expected = _decimal_from_measurement(measurement.get("expected"))
            if value is not None:
                chart_rows.append({"period": measurement.get("period", ""), "result": float(value), "expected": float(expected) if expected is not None else None})
            if report and measurement.get("file"):
                measurement["download_url"] = reverse("quarterly_measurement_file", args=[report.pk, indicator_index, measurement_index])
        if item.get("history"):
            chart_rows = []
            for measurement in item["history"]:
                value = _decimal_from_measurement(measurement.get("result"))
                expected = _decimal_from_measurement(measurement.get("expected"))
                if value is not None:
                    chart_rows.append({"period": measurement.get("period", ""), "result": float(value), "expected": float(expected) if expected is not None else None})
        if not chart_rows:
            latest = _decimal_from_measurement(item.get("latest_result"))
            if latest is not None:
                chart_rows.append({"period": item.get("latest_period", "Último resultado"), "result": float(latest), "expected": None})
        chart_rows.reverse()
        parameters = item.get("reference_parameters", {})
        if chart_rows and parameters.get("baseline_value") is not None:
            baseline = _decimal_from_measurement(parameters["baseline_value"])
            if baseline is not None:
                chart_rows.insert(0, {"period": "Base 2024", "result": float(baseline), "expected": float(baseline)})
        item["chart"] = {"categories": [m["period"] for m in chart_rows], "result": [m["result"] for m in chart_rows], "expected": [m["expected"] for m in chart_rows]} if chart_rows else None
        item["chart_id"] = f"report-indicator-chart-{indicator_index}"
        item["chart_data_id"] = f"report-indicator-data-{indicator_index}"
    data["unlinked_targets"] = [dict(target) for target in snapshot.get("targets", []) if target.get("id") not in linked_target_ids]
    data["evidences"] = [dict(item) for item in snapshot.get("evidences", [])]
    for index, item in enumerate(data["evidences"]):
        if report and item.get("file"):
            item["download_url"] = reverse("quarterly_evidence_file", args=[report.pk, index])
    return data


def _get_visible_report(request, report_id):
    if not _can_view(request.user):
        raise PermissionDenied
    return get_object_or_404(QuarterlySectorReport.objects.filter(unit__in=view_scope_units(OrganizationalUnit.objects.all(), request.user)).select_related("unit", "plan", "consolidated_by"), pk=report_id)


def _snapshot_file(filename):
    if not filename:
        raise Http404("Este registro não tem anexo.")
    try:
        file = default_storage.open(filename, "rb")
    except FileNotFoundError:
        raise Http404("O arquivo não está disponível no servidor.")
    return FileResponse(file, filename=filename.rsplit("/", 1)[-1])


@login_required
def evidence_file(request, report_id, evidence_index):
    report = _get_visible_report(request, report_id)
    if not request.user.has_perm("core.view_activityevidence"):
        raise PermissionDenied
    try:
        evidence = report.snapshot.get("evidences", [])[evidence_index]
    except IndexError:
        raise Http404
    return _snapshot_file(evidence.get("file"))


@login_required
def measurement_file(request, report_id, indicator_index, measurement_index):
    report = _get_visible_report(request, report_id)
    if not request.user.has_perm("core.view_indicatormeasurement"):
        raise PermissionDenied
    try:
        measurement = report.snapshot.get("indicators", [])[indicator_index].get("measurements", [])[measurement_index]
    except IndexError:
        raise Http404
    return _snapshot_file(measurement.get("file"))


def _get_editable_report(request, report_id):
    if not request.user.has_perm("core.consolidate_quarterlysectorreport"):
        raise PermissionDenied
    return get_object_or_404(QuarterlySectorReport.objects.filter(unit__in=scope_units(OrganizationalUnit.objects.all(), request.user)).select_related("unit", "plan"), pk=report_id)


@login_required
def edit(request, report_id):
    report = _get_editable_report(request, report_id)
    form = QuarterlyReportForm(
        request.POST if request.method == "POST" else None,
        units=scope_units(OrganizationalUnit.objects.order_by("name"), request.user),
        initial={"plan": report.plan_id, "unit": report.unit_id, "year": report.year, "quarter": report.quarter},
    )
    if request.method == "POST" and form.is_valid():
        from copy import deepcopy
        with transaction.atomic():
            data = form.cleaned_data
            list(OrganizationalUnit.objects.select_for_update().filter(pk__in=[report.unit_id, data["unit"].pk]).order_by("pk"))
            report = QuarterlySectorReport.objects.select_for_update().get(pk=report.pk)
            duplicate = QuarterlySectorReport.objects.filter(plan=data["plan"], unit=data["unit"], year=data["year"], quarter=data["quarter"]).exclude(pk=report.pk).exists()
            if duplicate:
                form.add_error(None, "Já existe um relatório para este plano, setor, ano e trimestre. Selecione o relatório existente na lista.")
            else:
                previous = deepcopy(report.snapshot)
                history = previous.pop("previous_versions", [])
                history.append({"snapshot": previous, "plan_id": report.plan_id, "unit_id": report.unit_id, "year": report.year, "quarter": report.quarter, "replaced_at": timezone.now().isoformat(), "replaced_by": request.user.pk})
                snapshot = _snapshot(data["plan"], data["unit"], data["year"], data["quarter"])
                snapshot["previous_versions"] = history
                snapshot["last_edited_at"] = timezone.now().isoformat()
                snapshot["last_edited_by"] = request.user.get_full_name() or request.user.username
                report.plan, report.unit = data["plan"], data["unit"]
                report.year, report.quarter = data["year"], data["quarter"]
                report.snapshot = snapshot
                report.save(update_fields=["plan", "unit", "year", "quarter", "snapshot"])
                messages.success(request, "Relatório atualizado. A versão anterior foi preservada no histórico.")
                return redirect("quarterly_report_detail", report_id=report.pk)
    return render(request, "core/quarterly_report_form.html", {"report": report, "form": form})


@login_required
@require_POST
def delete(request, report_id):
    report = _get_editable_report(request, report_id)
    unit_id = report.unit_id
    report.delete()
    messages.success(request, "Relatório consolidado excluído. Os cadastros do plano e suas evidências foram mantidos.")
    return redirect(reverse("report_cycle_overview") + f"?unit={unit_id}")


@login_required
def detail(request, report_id):
    if not _can_view(request.user):
        raise PermissionDenied
    report = get_object_or_404(QuarterlySectorReport.objects.filter(unit__in=view_scope_units(OrganizationalUnit.objects.all(), request.user)).select_related("unit", "plan", "consolidated_by"), pk=report_id)
    ids = user_unit_ids(request.user)
    request.read_only_other_unit = ids is not None and report.unit_id not in ids
    return render(request, "core/quarterly_report_detail.html", {"report": report, "data": _report_display_data(report.snapshot, report), "can_manage_report": request.user.has_perm("core.consolidate_quarterlysectorreport") and scope_units(OrganizationalUnit.objects.all(), request.user).filter(pk=report.unit_id).exists()})
