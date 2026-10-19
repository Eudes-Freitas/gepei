import calendar
from datetime import date

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


def _snapshot_indicator_chart(indicator):
    """Monta a série apenas com as aferições preservadas no relatório."""
    from .views import _decimal_from_measurement

    points = []
    for measurement in reversed(indicator.get("measurements", [])):
        result = _decimal_from_measurement(measurement.get("result"))
        if result is None:
            continue
        expected = _decimal_from_measurement(measurement.get("expected"))
        points.append((measurement.get("period") or "Período não informado", float(result), float(expected) if expected is not None else None))
    if not points:
        return None
    return {
        "categories": [period for period, _, _ in points],
        "result": [{"y": value} for _, value, _ in points],
        "expected": [expected for _, _, expected in points],
        "has_expected": any(expected is not None for _, _, expected in points),
    }


def _snapshot(plan, unit, year, quarter):
    from .views import _final_progress, _indicator_signal
    start, end = _period(year, quarter)
    actions = list(StrategicAction.objects.filter(artifact__plan=plan, coordinating_unit=unit).select_related("artifact"))
    activities = list(Activity.objects.filter(action_plan__action__in=actions).select_related("action_plan__action", "executor"))
    targets = list(StrategicTarget.objects.filter(artifact__plan=plan).filter(Q(action__coordinating_unit=unit) | Q(action__isnull=True, indicators__responsible_unit=unit)).distinct().select_related("artifact"))
    indicators = list(Indicator.objects.filter(artifacts__plan=plan, responsible_unit=unit).distinct().prefetch_related("measurements", "artifacts"))
    artifacts = {a.id: a for a in PlanArtifact.objects.filter(plan=plan)}
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
    indicator_by_id = {indicator.pk: indicator for indicator in indicators}
    for indicator in indicators:
        measurements = [m for m in indicator.measurements.all() if (m.period_end or timezone.localtime(m.recorded_at).date()) <= end]
        measurements.sort(key=lambda m: (m.period_end or timezone.localtime(m.recorded_at).date(), m.recorded_at, m.pk), reverse=True)
        indicator._prefetched_objects_cache["measurements"] = measurements
        signal = _indicator_signal(indicator)
        latest = signal["measurement"]
        indicator_rows.append({"id": indicator.id, "code": indicator.code, "name": indicator.name, "formula": indicator.formula, "unit": indicator.unit_of_measure, "source": indicator.data_source, "status": signal["label"], "achievement": signal["achievement"], "latest_result": latest.measured_value if latest else None, "latest_period": latest.reference_period if latest else "", "measurements": [{"period": m.reference_period, "result": m.measured_value, "expected": str(m.expected_value) if m.expected_value is not None else None, "baseline": m.baseline_value, "source": m.source_reference} for m in measurements if (m.period_end or timezone.localtime(m.recorded_at).date()) >= start]})
    target_rows = []
    for target in targets:
        progress = []
        for indicator_id in target.indicators.values_list("pk", flat=True):
            indicator = indicator_by_id.get(indicator_id)
            if indicator is None:
                continue
            signal = _indicator_signal(indicator, target=target)
            value = _final_progress(indicator, signal["measurement"], target=target)
            if value is not None:
                progress.append(value)
        target_rows.append({
            "code": target.code, "description": target.description, "value": target.target_value,
            "unit": target.unit_of_measure, "period": target.reference_period,
            "objective": target.artifact.code,
            "progress": round(sum(progress) / len(progress), 1) if progress else None,
        })
    risks = Risk.objects.filter(action__in=actions).select_related("action", "activity")
    evidences = ActivityEvidence.objects.filter(activity__in=activities, created_at__date__range=(start, end)).select_related("activity")
    blockers = ActivityBlocker.objects.filter(activity__in=activities)
    return {
        "unit": unit.name, "unit_acronym": unit.acronym, "plan": plan.name, "plan_acronym": plan.acronym,
        "year": year, "quarter": quarter, "period_start": start.isoformat(), "period_end": end.isoformat(), "period_label": f"{start:%d/%m/%Y} a {end:%d/%m/%Y}",
        "objectives": [{"code": artifacts[pk].code, "title": artifacts[pk].title} for pk in sorted(objective_ids)],
        "targets": target_rows,
        "indicators": indicator_rows,
        "actions": [{"code": a.code, "title": a.title, "status": a.get_status_display(), "progress": str(a.progress), "due_date": a.due_date.isoformat() if a.due_date else ""} for a in actions],
        "activities": [{"action": a.action_plan.action.code, "title": a.title, "status": a.get_status_display(), "progress": str(a.progress), "executor": a.executor.get_full_name() or a.executor.username} for a in activities],
        "risks": [{"title": r.title, "action": r.action.code, "status": r.get_status_display(), "level": r.level, "cause": r.cause, "control": r.preventive_measure} for r in risks],
        "blockers": [{"description": b.description, "status": b.get_status_display()} for b in blockers],
        "evidences": [{"title": e.title, "activity": e.activity.title, "reference": e.reference, "url": e.url, "file": e.attachment.name} for e in evidences],
        "planned_cost": str(sum(a.planned_cost or 0 for a in activities)), "disbursed_cost": str(sum(a.disbursed_cost or 0 for a in activities)),
    }


@login_required
def overview(request):
    if not _can_view(request.user):
        raise PermissionDenied
    today = timezone.localdate()
    selected_unit = selected_unit_for_request(request)
    selected_plan = request.GET.get("plan", "")
    selected_year = request.GET.get("year", "")
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
    years = sorted(set(reports.values_list("year", flat=True)) | {today.year}, reverse=True)
    if selected_unit.isdigit():
        reports = reports.filter(unit_id=selected_unit)
    if selected_plan.isdigit():
        reports = reports.filter(plan_id=selected_plan)
    if selected_year.isdigit():
        reports = reports.filter(year=int(selected_year))
    units = view_units.filter(pk=selected_unit) if selected_unit.isdigit() else view_units
    sector_rows = [{"unit": unit, "reports": [r for r in reports if r.unit_id == unit.pk], "can_consolidate": can_consolidate and write_units.filter(pk=unit.pk).exists()} for unit in units]
    return render(request, "core/quarterly_report_overview.html", {"units": view_units, "selected_unit": selected_unit, "plans": Plan.objects.filter(active=True), "selected_plan": selected_plan, "years": years, "selected_year": selected_year, "sector_rows": sector_rows, "consolidation_form": form, "can_consolidate": can_consolidate})


@login_required
def detail(request, report_id):
    if not _can_view(request.user):
        raise PermissionDenied
    report = get_object_or_404(QuarterlySectorReport.objects.filter(unit__in=view_scope_units(OrganizationalUnit.objects.all(), request.user)).select_related("unit", "plan", "consolidated_by"), pk=report_id)
    ids = user_unit_ids(request.user)
    request.read_only_other_unit = ids is not None and report.unit_id not in ids
    can_delete = request.user.has_perm("core.consolidate_quarterlysectorreport") and scope_units(
        OrganizationalUnit.objects.filter(pk=report.unit_id), request.user
    ).exists()
    data = report.snapshot
    indicator_rows = []
    for index, indicator in enumerate(data.get("indicators", [])):
        indicator_rows.append({
            "item": indicator,
            "chart": _snapshot_indicator_chart(indicator),
            "chart_data_id": f"quarterly-report-chart-{index}",
        })
    return render(request, "core/quarterly_report_detail.html", {
        "report": report,
        "data": data,
        "can_delete": can_delete,
        "indicator_rows": indicator_rows,
        "has_indicator_charts": any(row["chart"] for row in indicator_rows),
    })


@login_required
@require_POST
def delete(request, report_id):
    if not request.user.has_perm("core.consolidate_quarterlysectorreport"):
        raise PermissionDenied
    report = get_object_or_404(
        QuarterlySectorReport.objects.filter(unit__in=scope_units(OrganizationalUnit.objects.all(), request.user)),
        pk=report_id,
    )
    report.delete()
    messages.success(request, "Relatório trimestral excluído.")
    return redirect("report_cycle_overview")
