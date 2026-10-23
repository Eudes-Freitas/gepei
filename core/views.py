import unicodedata
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from difflib import SequenceMatcher

from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, F, Max, ProtectedError, Q, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

from .forms import (
    ActivityPlanningRiskFormSet,
    ActionPlanExecutionForm,
    ActionPlanManagerForm,
    ActivityBlockerForm,
    ActivityEvidenceForm,
    ActivityForm,
    ActivityProgressForm,
    ActivityRiskForm,
    InitialActivityRiskForm,
    ActivityRiskReportForm,
    UnforeseenActivityRiskForm,
    GroupForm,
    IndicatorDefinitionForm,
    IndicatorMeasurementForm,
    ProfileForm,
    ReportCycleForm,
    ReportValidationForm,
    StrategicTargetForm,
    RiskAcceptanceForm,
    RiskAssessmentForm,
    RiskCreateForm,
    RiskIdentityForm,
    RiskIdentificationForm,
    RiskMaterializationForm,
    RiskRemediationSubmissionForm,
    RiskTimingForm,
    RiskTreatmentForm,
    SectorReportForm,
    UserCreateForm,
)
from .permissions import (
    permission_modules,
    scope_actions,
    view_scope_actions,
    scope_by_unit,
    view_scope_by_unit,
    scope_units,
    view_scope_units,
    selected_unit_for_request,
    user_unit_ids,
)
from .models import (
    ActionPlan,
    Activity,
    ActivityBlocker,
    ActivityEvidence,
    Indicator,
    OrganizationalUnit,
    Plan,
    PlanArtifact,
    ReportCycle,
    Risk,
    RiskAcceptance,
    RiskAssessment,
    RiskMaterialization,
    RiskTreatment,
    SectorReport,
    StrategicAction,
    StrategicTarget,
)


def _decimal_from_measurement(value):
    if value is None or value == "":
        return None
    text = str(value).strip().replace("%", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _final_target_value(indicator):
    for target in indicator.targets.all():
        value = _decimal_from_measurement(target.target_value)
        if value is not None:
            return value
    return None


def _plan_end_date(indicator):
    ends = [artifact.plan.end_date for artifact in indicator.artifacts.all() if artifact.plan_id]
    return max(ends) if ends else None


def _period_target(indicator, baseline_value, baseline_date, period_end, target=None):
    """Meta do período: evolução linear da linha de base (na data da linha de base) até a meta final no fim do plano."""
    if indicator.reference_parameters and period_end and baseline_date == date(2024, 12, 31):
        from .indicator_reference import expected_at
        expected = expected_at(indicator.reference_parameters, period_end)
        return expected.quantize(Decimal(".01")) if expected is not None else None
    final = _decimal_from_measurement(target.target_value) if target else _final_target_value(indicator)
    plan_end = target.artifact.plan.end_date if target else _plan_end_date(indicator)
    basal = _decimal_from_measurement(baseline_value)
    if final is None or plan_end is None or basal is None or not baseline_date or not period_end:
        return None
    total_days = (plan_end - baseline_date).days
    if total_days <= 0:
        return None
    elapsed = min(max((period_end - baseline_date).days, 0), total_days)
    expected = basal + (final - basal) * Decimal(elapsed) / Decimal(total_days)
    return expected.quantize(Decimal("0.01"))


def _final_progress(indicator, measurement, target=None):
    """Percentual do caminho já percorrido da linha de base até a meta final do plano."""
    if measurement is None:
        return None
    final = _decimal_from_measurement(target.target_value) if target else _final_target_value(indicator)
    if indicator.reference_parameters and measurement.baseline_date == date(2024, 12, 31):
        signal = _indicator_signal(indicator, target=target)
        return signal.get("achievement")
    basal = _decimal_from_measurement(measurement.baseline_value)
    measured = _decimal_from_measurement(measurement.measured_value)
    if final is None or basal is None or measured is None or final == basal:
        return None
    return round(float((measured - basal) / (final - basal) * 100), 1)


def _selected_results_year(request):
    value = request.GET.get("year", "")
    return value if value.isascii() and value.isdigit() and len(value) == 4 and int(value) > 0 else ""


def _results_measurements(indicator, year=""):
    measurements = list(indicator.measurements.all())
    if not year:
        return measurements
    selected = int(year)
    def matches(measurement):
        period_date = measurement.period_end or measurement.period_start
        if period_date:
            return period_date.year == selected
        return str(selected) in re.findall(r"(?<!\d)\d{4}(?!\d)", measurement.reference_period)
    return [measurement for measurement in measurements if matches(measurement)]


def _indicator_pace(indicator, measurement, measured, target=None, year=""):
    """Compara o avanço realizado com a trajetória linear esperada até a data de avaliação."""
    baseline = _decimal_from_measurement(measurement.baseline_value)
    final = _decimal_from_measurement(target.target_value) if target else _final_target_value(indicator)
    end = target.artifact.plan.end_date if target else _plan_end_date(indicator)
    start = measurement.baseline_date
    if baseline is None or final is None or not start or not end or start >= end or final == baseline:
        return None
    if (indicator.direction == Indicator.Direction.HIGHER_IS_BETTER and final < baseline) or (
        indicator.direction == Indicator.Direction.LOWER_IS_BETTER and final > baseline
    ):
        return {"code": "gray", "label": "Meta incompatível com o sentido do indicador", "achievement": None}
    evaluation_date = min(end, date(int(year), 12, 31)) if year else end
    if evaluation_date <= start:
        return {"code": "gray", "label": "Período não iniciado", "achievement": None, "evaluation_date": evaluation_date}
    elapsed = Decimal((evaluation_date - start).days) / Decimal((end - start).days)
    realized = (measured - baseline) / (final - baseline)
    return {
        "achievement": max(Decimal("0"), realized / elapsed * 100),
        "calculation_mode": "pace",
        "evaluation_date": evaluation_date,
        "expected_value": baseline + (final - baseline) * elapsed,
        "expected_progress": round(float(elapsed * 100), 1),
        "realized_progress": round(float(realized * 100), 1),
    }


def _indicator_signal(indicator, target=None, year="", evaluation_date=None):
    measurements = _results_measurements(indicator, year)
    latest = measurements[0] if measurements else None
    if not latest:
        return {"code": "gray", "label": "Sem aferição", "achievement": None, "measurement": None}
    measured = _decimal_from_measurement(latest.measured_value)
    expected = latest.expected_value
    if target is not None:
        target_expected = _period_target(indicator, latest.baseline_value, latest.baseline_date, latest.period_end, target=target)
        if target_expected is not None or len(indicator.targets.all()) > 1:
            expected = target_expected
    if indicator.reference_parameters and latest.baseline_date == date(2024, 12, 31) and measured is not None:
        from .indicator_reference import document_pace
        when = evaluation_date or date(int(year) if year else max(map(int, indicator.reference_parameters["projections"])), 12, 31)
        pace = document_pace(indicator, latest, measurements, when, aggregate=not year and evaluation_date is None)
    else:
        pace = _indicator_pace(indicator, latest, measured, target=target, year=year) if measured is not None and indicator.direction != Indicator.Direction.RANGE else None
    if pace is not None and pace.get("code") == "gray":
        return {**pace, "measurement": latest}
    if measured is None or (expected is None and pace is None):
        return {"code": "gray", "label": "Dado insuficiente", "achievement": None, "measurement": latest}
    if indicator.direction == Indicator.Direction.RANGE:
        return {"code": "gray", "label": "Faixa a configurar", "achievement": None, "measurement": latest}
    if pace is not None:
        achievement = pace["achievement"]
    elif indicator.direction == Indicator.Direction.LOWER_IS_BETTER:
        if measured <= expected or measured == 0:
            achievement = Decimal("100")
        else:
            achievement = expected / measured * 100
    else:
        if expected == 0:
            achievement = Decimal("100") if measured >= expected else Decimal("0")
        else:
            achievement = measured / expected * 100
    if achievement >= 100:
        code, label = "green", "Conforme"
    elif achievement >= 90:
        code, label = "yellow", "Atenção"
    elif achievement >= 70:
        code, label = "orange", "Alerta"
    else:
        code, label = "red", "Crítico"
    return {
        **(pace or {"calculation_mode": "period", "expected_value": expected}),
        "code": code,
        "label": label,
        "achievement": round(float(achievement), 1),
        "measurement": latest,
    }


SIGNAL_STYLE = {
    "green": ("Conforme", "#16834a"),
    "yellow": ("Atenção", "#e5a11b"),
    "orange": ("Alerta", "#e07b1a"),
    "red": ("Crítico", "#d84a4a"),
    "gray": ("Sem aferição", "#aebbc8"),
}
SIGNAL_SEVERITY = {"green": 1, "yellow": 2, "orange": 3, "red": 4}


def _percent(part, whole):
    return round(part / whole * 100) if whole else 0


def _signal_matches(code, selected):
    if selected == "measured":
        return code not in ("gray", "none")
    if selected == "attention":
        return code in ("yellow", "orange", "red")
    if selected == "unmeasured":
        return code in ("gray", "none")
    return code == selected


def _selected_result_status(request, kind):
    selected = request.GET.get(f"{kind}_status")
    if selected is not None:
        return selected
    legacy_page = "target_overview" if kind == "target" else "indicator_overview"
    return request.GET.get("status", "") if request.resolver_match.url_name == legacy_page else ""


def _target_signal(target, signals):
    codes = [signals[item.id] for item in target.indicators.all() if item.id in signals]
    measured = [code for code in codes if code != "gray"]
    return max(measured, key=SIGNAL_SEVERITY.get) if measured else ("gray" if codes else "none")


def _can_write_target(user, target):
    ids = user_unit_ids(user)
    if ids is None:
        return True
    if target.action_id:
        return scope_actions(StrategicAction.objects.all(), user).filter(pk=target.action_id).exists()
    indicators = list(target.indicators.all())
    return bool(indicators) and all(indicator.responsible_unit_ids & ids for indicator in indicators)


def _scoped_targets(user, plans, unit_id=""):
    targets = StrategicTarget.objects.filter(artifact__plan__in=plans).filter(
        Q(action__isnull=True) | Q(action__in=view_scope_actions(StrategicAction.objects.all(), user))
    )
    visible_ids = user_unit_ids(user, for_view=True)
    if visible_ids is not None:
        targets = targets.filter(Q(action__in=view_scope_actions(StrategicAction.objects.all(), user)) | Q(action__isnull=True, indicators__responsible_unit_id__in=visible_ids) | Q(action__isnull=True, indicators__responsible_units__id__in=visible_ids))
    if unit_id.isdigit():
        targets = targets.filter(Q(action__coordinating_unit_id=unit_id) | Q(action__participating_units__id=unit_id) | Q(action__isnull=True, indicators__responsible_unit_id=unit_id) | Q(action__isnull=True, indicators__responsible_units__id=unit_id))
    return targets.select_related("artifact", "artifact__plan", "action").prefetch_related(
        "indicators", "indicators__responsible_units", "indicators__measurements", "indicators__targets", "indicators__artifacts__plan"
    ).distinct()


def _target_execution(target, user=None, unit_id="", year=""):
    """Execução da meta: situação, atingimento e progresso até a meta final a partir dos seus indicadores."""
    indicators = []
    visible_ids = user_unit_ids(user, for_view=True) if user else None
    for indicator in target.indicators.all():
        if visible_ids is not None and not indicator.responsible_unit_ids.intersection(visible_ids):
            continue
        if unit_id.isdigit() and int(unit_id) not in indicator.responsible_unit_ids:
            continue
        signal = _indicator_signal(indicator, target=target, year=year)
        indicators.append(
            {"indicator": indicator, "signal": signal, "progress": _final_progress(indicator, signal["measurement"], target=target)}
        )
    code = _target_signal(target, {item["indicator"].id: item["signal"]["code"] for item in indicators})
    achievements = [item["signal"]["achievement"] for item in indicators if item["signal"]["achievement"] is not None]
    progress = [item["progress"] for item in indicators if item["progress"] is not None]
    measurements = [item["signal"]["measurement"] for item in indicators if item["signal"]["measurement"]]
    return {
        "target": target,
        "indicators": indicators,
        "code": code,
        "label": "Sem indicador" if code == "none" else SIGNAL_STYLE[code][0],
        "achievement": min(achievements) if achievements else None,
        "progress": round(sum(progress) / len(progress), 1) if progress else None,
        "measured_count": len(measurements),
        "last_measurement": max(measurements, key=lambda item: item.recorded_at) if measurements else None,
    }


def _target_achievement_chart(execution):
    """Equal weight average of normalized percentages; missing values stay unknown."""
    points = []
    values = []
    for item in execution["indicators"]:
        raw = item["signal"]["achievement"]
        value = max(0, min(raw, 100)) if raw is not None else None
        if value is not None:
            values.append(value)
        points.append({
            "name": item["indicator"].code or item["indicator"].name,
            "indicator_id": item["indicator"].id,
            "y": value,
            "raw": raw,
            "color": SIGNAL_STYLE[item["signal"]["code"]][1],
        })
    total = round(sum(values) / len(values), 1) if values else None
    palette = ["#1769aa", "#16834a", "#7357c9", "#e5a11b", "#0b8994", "#c55783"]
    pie_points = [
        {**point, "y": point["y"] / len(values), "achievement": point["raw"], "color": palette[index % len(palette)]}
        for index, point in enumerate(points) if point["y"] is not None
    ] if values else []
    if values:
        remaining = max(0, 100 - sum(point["y"] for point in pie_points))
        if remaining > 0:
            pie_points.append({"name": "Falta atingir", "y": remaining, "achievement": None, "indicator_id": None, "color": "#e1e7ef"})
    else:
        pie_points = [{"name": "Sem aferição suficiente", "y": 100, "achievement": None, "indicator_id": None, "color": "#e1e7ef"}]
    return {
        "pie_points": pie_points,
        "total": total,
        "measured_count": len(values),
        "indicator_count": len(points),
        "partial": len(values) != len(points),
        "points": [{"name": "Total da meta", "y": total, "raw": total, "color": "#1769aa", "indicator_id": None}] + points,
    }


def _objective_artifact_ids(objective_id):
    ids = {int(objective_id)}
    pending = ids
    while pending:
        pending = set(PlanArtifact.objects.filter(parent_id__in=pending).values_list("id", flat=True)) - ids
        ids.update(pending)
    return ids


def _performance_summary(user, dash_plans, base_filters, unit_id):
    """Indicadores (aferição e situação frente à meta) e metas (situação derivada dos indicadores) do painel."""

    def indicator_link(**extra):
        return f"{reverse('indicator_overview')}?{urlencode({**base_filters, **extra})}"

    indicator_qs = view_scope_by_unit(
        Indicator.objects.filter(artifacts__plan__in=dash_plans),
        user,
        "responsible_unit_id",
        include_unassigned=True,
    ).prefetch_related("measurements", "artifacts").distinct()
    if unit_id:
        indicator_qs = indicator_qs.filter(Q(responsible_unit_id=unit_id) | Q(responsible_units__id=unit_id)).distinct()

    signal_counts = {code: 0 for code in SIGNAL_STYLE}
    indicator_signal = {}
    by_objective = {}
    for indicator in indicator_qs:
        signal = _indicator_signal(indicator)
        indicator_signal[indicator.id] = signal["code"]
        signal_counts[signal["code"]] += 1
        if signal["achievement"] is not None:
            for artifact in indicator.artifacts.all():
                if artifact.artifact_type == PlanArtifact.ArtifactType.OBJECTIVE:
                    by_objective.setdefault(artifact.id, (artifact, []))[1].append(min(signal["achievement"], 100))
    indicator_total = sum(signal_counts.values())
    measured = indicator_total - signal_counts["gray"]

    objective_bars = sorted(
        (
            {
                "name": artifact.code,
                "full": f"{artifact.code} · {artifact.title}",
                "y": round(sum(values) / len(values), 1),
                "url": indicator_link(objective=artifact.id, plan=artifact.plan_id),
            }
            for artifact, values in by_objective.values()
        ),
        key=lambda item: item["name"],
    )

    targets = list(
        _scoped_targets(user, dash_plans, unit_id)
    )
    target_counts = {"green": 0, "yellow": 0, "orange": 0, "red": 0, "gray": 0, "none": 0}
    attention = []
    for target in targets:
        key = _target_signal(target, indicator_signal)
        target_counts[key] += 1
        if key in ("yellow", "orange", "red"):
            attention.append((SIGNAL_SEVERITY[key], target, key))
    attention.sort(key=lambda item: (-item[0], item[1].code))

    def target_link(target=None, **extra):
        filters = {**base_filters, **extra}
        if target:
            filters.update(plan=target.artifact.plan_id, target=target.id)
        return f"{reverse('target_overview')}?{urlencode(filters)}"

    target_measured = len(targets) - target_counts["gray"] - target_counts["none"]
    charts = {
        "measured": [
            {"name": "Aferidos", "y": measured, "color": "#1769aa", "url": indicator_link(status="measured")},
            {"name": "Sem aferição", "y": signal_counts["gray"], "color": "#aebbc8", "url": indicator_link(status="gray")},
        ],
        "signal": [
            {"name": SIGNAL_STYLE[code][0], "y": signal_counts[code], "color": SIGNAL_STYLE[code][1], "url": indicator_link(status=code)}
            for code in ("green", "yellow", "orange", "red")
        ],
        "objectives": objective_bars,
        "targets": [
            {"name": "Conforme", "y": target_counts["green"], "color": "#16834a", "url": target_link(status="green")},
            {"name": "Atenção", "y": target_counts["yellow"], "color": "#e5a11b", "url": target_link(status="yellow")},
            {"name": "Alerta", "y": target_counts["orange"], "color": "#e07b1a", "url": target_link(status="orange")},
            {"name": "Crítico", "y": target_counts["red"], "color": "#d84a4a", "url": target_link(status="red")},
            {"name": "Sem aferição", "y": target_counts["gray"], "color": "#aebbc8", "url": target_link(status="gray")},
            {"name": "Sem indicador", "y": target_counts["none"], "color": "#d0d7de", "url": target_link(status="none")},
        ],
    }
    return {
        "indicator_query": urlencode(base_filters),
        "signal_counts": signal_counts,
        "indicator_total": indicator_total,
        "indicator_measured": measured,
        "indicator_measured_pct": _percent(measured, indicator_total),
        "indicator_green_pct": _percent(signal_counts["green"], measured),
        "indicator_attention": signal_counts["yellow"] + signal_counts["orange"] + signal_counts["red"],
        "target_query": urlencode(base_filters),
        "target_attention_count": sum(target_counts[code] for code in ("yellow", "orange", "red")),
        "target_total": len(targets),
        "target_counts": target_counts,
        "target_measured": target_measured,
        "target_green_pct": _percent(target_counts["green"], target_measured),
        "target_attention": [
            {
                "code": target.code or "Meta",
                "description": target.description,
                "label": SIGNAL_STYLE[key][0],
                "color": SIGNAL_STYLE[key][1],
                "url": target_link(target),
            }
            for _, target, key in attention[:5]
        ],
        "performance_charts": charts,
    }


@login_required
def dashboard(request):
    plans = Plan.objects.filter(active=True).order_by("acronym")
    units = view_scope_units(OrganizationalUnit.objects.select_related("organization").order_by("name"), request.user)
    actions = view_scope_actions(
        StrategicAction.objects.select_related("artifact", "artifact__plan", "coordinating_unit"), request.user
    )

    selected_plan = request.GET.get("plan", "")
    selected_unit = selected_unit_for_request(request)
    selected_status = request.GET.get("status", "")
    if selected_plan.isdigit():
        actions = actions.filter(artifact__plan_id=selected_plan)
    # Selecting the organ itself (e.g. SESED) covers every unit, so no unit filter applies.
    unit_filter = (
        selected_unit.isdigit()
        and units.filter(pk=selected_unit).exclude(unit_type=OrganizationalUnit.UnitType.ORGAN).exists()
    )
    if unit_filter:
        actions = actions.filter(coordinating_unit_id=selected_unit)
    if selected_status in StrategicAction.Status.values:
        actions = actions.filter(status=selected_status)

    today = timezone.localdate()
    actions = actions.order_by("due_date")
    action_count = actions.count()
    sector_actions = actions.exclude(coordinating_unit__unit_type=OrganizationalUnit.UnitType.ORGAN)
    sector_action_count = sector_actions.count()
    action_page = Paginator(
        sector_actions.annotate(activity_count=Count("action_plan__activities")).order_by(
            F("due_date").asc(nulls_last=True), "code"
        ),
        10,
    ).get_page(request.GET.get("page"))
    page_query = urlencode(
        {key: value for key, value in (("plan", selected_plan), ("unit", selected_unit), ("status", selected_status)) if value}
    )
    deadline_alert = actions.filter(due_date__lt=today).exclude(
        status__in=[StrategicAction.Status.COMPLETED, StrategicAction.Status.SUSPENDED]
    )
    risks = list(
        Risk.objects.filter(action__in=actions).select_related("action", "action__coordinating_unit", "activity")
    )
    status_summary = [
        {
            "code": code,
            "label": label,
            "total": actions.filter(status=code).count(),
        }
        for code, label in StrategicAction.Status.choices
    ]
    progress_average = actions.aggregate(average=Avg("progress"))["average"] or 0
    objective_query = PlanArtifact.objects.filter(artifact_type=PlanArtifact.ArtifactType.OBJECTIVE)
    if selected_plan.isdigit():
        objective_query = objective_query.filter(plan_id=selected_plan)
    if unit_filter or user_unit_ids(request.user, for_view=True) is not None:
        objective_query = objective_query.filter(
            Q(actions__in=actions)
            | Q(planartifact__actions__in=actions)
            | Q(planartifact__planartifact__actions__in=actions)
        ).distinct()

    # Riscos prioritários: apenas altos e críticos do recorte (setor selecionado ou todos os setores).
    risk_alerts = sorted(
        [risk for risk in risks if risk.level >= 15],
        key=lambda risk: (-risk.level, risk.title),
    )[:5]
    can_view_risks = request.user.has_perm("core.view_risk")

    # Donut e legenda clicável: cada situação leva à lista de execução já filtrada.
    status_colors = {
        "NAO_INICIADA": "#aebbc8",
        "EM_ANDAMENTO": "#1769aa",
        "CONCLUIDA": "#20a46b",
        "ATRASADA": "#e5a11b",
        "BLOQUEADA": "#d84a4a",
        "SUSPENSA": "#7357c9",
    }
    base_filters = {key: value for key, value in (("plan", selected_plan), ("unit", selected_unit if unit_filter else "")) if value}
    stops, cursor = [], 0.0
    for item in status_summary:
        item["color"] = status_colors.get(item["code"], "#aebbc8")
        item["query"] = urlencode({**base_filters, "status": item["code"]})
        if action_count and item["total"]:
            end = cursor + item["total"] / action_count * 100
            stops.append(f"{item['color']} {cursor:.2f}% {end:.2f}%")
            cursor = end
    donut_gradient = f"conic-gradient({', '.join(stops)})" if stops else "conic-gradient(#e9eff4 0 100%)"

    # Progresso médio por objetivo estratégico (as ações podem estar em projetos abaixo do objetivo).
    dash_plans = plans.filter(pk=selected_plan) if selected_plan.isdigit() else plans
    artifacts = {item.id: item for item in PlanArtifact.objects.filter(plan__in=dash_plans)}
    progress_by_objective = {}
    for artifact_id, progress in actions.values_list("artifact_id", "progress"):
        node = artifacts.get(artifact_id)
        while node is not None and node.artifact_type != PlanArtifact.ArtifactType.OBJECTIVE:
            node = artifacts.get(node.parent_id)
        if node is not None:
            progress_by_objective.setdefault(node.id, []).append(float(progress or 0))
    objective_progress = [
        {
            "id": objective_id,
            "code": artifacts[objective_id].code,
            "title": artifacts[objective_id].title,
            "plan_id": artifacts[objective_id].plan_id,
            "query": urlencode({**base_filters, **({"status": selected_status} if selected_status else {}), "objective": objective_id, "plan": artifacts[objective_id].plan_id}),
            "average": round(sum(values) / len(values), 1),
            "actions": len(values),
        }
        for objective_id, values in progress_by_objective.items()
    ]
    objective_progress.sort(key=lambda item: item["code"])

    performance = _performance_summary(request.user, dash_plans, base_filters, selected_unit if unit_filter else "")

    context = {
        **performance,
        "plans": plans,
        "units": units,
        "selected_plan": selected_plan,
        "selected_unit": selected_unit,
        "selected_status": selected_status,
        "can_view_risks": can_view_risks,
        "can_plans": request.user.has_perm("core.view_plan"),
        "can_exec": request.user.has_perm("core.view_actionplan"),
        "can_indicators": request.user.has_perm("core.view_indicator"),
        "can_targets": request.user.has_perm("core.view_strategictarget"),
        "base_query": urlencode({**base_filters, **({"status": selected_status} if selected_status else {})}),
        "risk_query": urlencode({**base_filters, **({"action_status": selected_status} if selected_status else {}), "level": "priority"}),
        "delayed_query": urlencode({**base_filters, **({"status": selected_status} if selected_status else {}), "overdue": "1"}),
        "donut_gradient": donut_gradient,
        "objective_progress": objective_progress,
        "actions_status_choices": StrategicAction.Status.choices,
        "action_count": action_count,
        "objective_count": objective_query.count(),
        "objective_query": urlencode({**base_filters, **({"status": selected_status} if selected_status else {}), "objectives": ",".join(str(pk) for pk in objective_query.values_list("pk", flat=True)), "dashboard": "1"}),
        "action_chart": [{"name": item["label"], "y": item["total"], "color": item["color"], "url": f"{reverse('action_plan_list')}?{item['query']}"} for item in status_summary],
        "delayed_count": deadline_alert.count(),
        "blocked_count": actions.filter(status=StrategicAction.Status.BLOCKED).count(),
        "critical_risk_count": sum(1 for risk in risks if risk.level >= 15),
        "progress_average": round(float(progress_average), 1),
        "status_summary": status_summary,
        "recent_actions": action_page.object_list,
        "action_page": action_page,
        "action_page_range": action_page.paginator.get_elided_page_range(action_page.number, on_each_side=2, on_ends=1),
        "page_query": page_query,
        "sector_action_count": sector_action_count,
        "can_add_actions": request.user.is_staff and request.user.has_perm("core.add_strategicaction"),
        "risk_alerts": risk_alerts,
        "unit_filter": unit_filter,
        "today": today,
    }
    return render(request, "core/dashboard.html", context)


@login_required
@permission_required("core.view_plan", raise_exception=True)
def pei_overview(request):
    plans = Plan.objects.filter(active=True).order_by("start_date", "acronym")
    units = view_scope_units(OrganizationalUnit.objects.order_by("name"), request.user)
    selected_unit = selected_unit_for_request(request)
    selected_plan = request.GET.get("plan", "")
    plan = plans.filter(pk=selected_plan).first() if selected_plan.isdigit() else plans.first()

    if not plan:
        return render(
            request,
            "core/pei_overview.html",
            {"plans": plans, "units": units, "selected_unit": selected_unit, "plan": None, "selected_plan": "", "dimension_groups": []},
        )

    artifacts = list(
        PlanArtifact.objects.filter(plan__in=plans.filter(pk=selected_plan) if selected_plan.isdigit() else plans)
        .select_related("parent", "parent__parent")
        .prefetch_related("targets", "indicators", "critical_success_factors")
        .order_by("id")
    )
    actions = list(
        view_scope_actions(StrategicAction.objects.filter(artifact__plan__in=plans.filter(pk=selected_plan) if selected_plan.isdigit() else plans), request.user)
        .select_related("artifact", "coordinating_unit")
        .prefetch_related("participating_units", "critical_success_factors")
        .order_by("artifact__id", "code")
    )
    focused_objective = request.GET.get("objective", "")
    focused_action = request.GET.get("action", "")
    if focused_action.isdigit():
        action = get_object_or_404(view_scope_actions(StrategicAction.objects.all(), request.user), pk=focused_action)
        focused_objective = str(action.artifact_id)
        by_id = {item.id: item for item in artifacts}
        node = by_id.get(action.artifact_id)
        while node and node.artifact_type != PlanArtifact.ArtifactType.OBJECTIVE:
            node = by_id.get(node.parent_id)
        focused_objective = str(node.id) if node else ""
    if focused_objective.isdigit():
        objective = get_object_or_404(PlanArtifact, pk=focused_objective, artifact_type=PlanArtifact.ArtifactType.OBJECTIVE, plan__in=plans)
        keep = _objective_artifact_ids(objective.id)
        node = objective
        while node.parent_id:
            keep.add(node.parent_id)
            node = node.parent
        artifacts = [item for item in artifacts if item.id in keep]
        actions = [item for item in actions if item.artifact_id in keep]
        if focused_action.isdigit():
            actions = [item for item in actions if item.id == int(focused_action)]
    unit = selected_unit_for_request(request)
    status = request.GET.get("status", "")
    if unit.isdigit():
        actions = [item for item in actions if item.coordinating_unit_id == int(unit)]
    if status in StrategicAction.Status.values:
        actions = [item for item in actions if item.status == status]
    if request.GET.get("dashboard") == "1":
        selected_ids = {int(value) for value in request.GET.get("objectives", "").split(",") if value.isdigit()}
        keep = set(selected_ids)
        by_id = {item.id: item for item in artifacts}
        for artifact_id in list(selected_ids):
            node = by_id.get(artifact_id)
            while node and node.parent_id:
                keep.add(node.parent_id)
                node = by_id.get(node.parent_id)
            keep.update(_objective_artifact_ids(artifact_id))
        artifacts = [item for item in artifacts if item.id in keep]
        actions = [item for item in actions if item.artifact_id in keep]
        unit = selected_unit_for_request(request)
        status = request.GET.get("status", "")
        if unit.isdigit():
            actions = [item for item in actions if item.coordinating_unit_id == int(unit)]
        if status in StrategicAction.Status.values:
            actions = [item for item in actions if item.status == status]
    if user_unit_ids(request.user, for_view=True) is not None or unit.isdigit():
        by_id = {item.id: item for item in artifacts}
        keep = set()
        for action in actions:
            node = by_id.get(action.artifact_id)
            while node and node.id not in keep:
                keep.add(node.id)
                node = by_id.get(node.parent_id)
        artifacts = [item for item in artifacts if item.id in keep]
    children = {}
    for artifact in artifacts:
        children.setdefault(artifact.parent_id, []).append(artifact)
    actions_by_artifact = {}
    for action in actions:
        actions_by_artifact.setdefault(action.artifact_id, []).append(action)

    def objective_node(objective):
        projects = [
            {
                "artifact": project,
                "actions": actions_by_artifact.get(project.id, []),
                "factor_count": len(project.critical_success_factors.all()),
            }
            for project in children.get(objective.id, [])
            if project.artifact_type == PlanArtifact.ArtifactType.PROJECT
        ]
        direct_actions = actions_by_artifact.get(objective.id, [])
        action_count = len(direct_actions) + sum(len(item["actions"]) for item in projects)
        # Fatores críticos de sucesso do PEI (Apêndice B): do próprio objetivo e dos seus projetos.
        factors = sorted(
            [*objective.critical_success_factors.all(), *(f for item in projects for f in item["artifact"].critical_success_factors.all())],
            key=lambda factor: factor.id,
        )
        return {
            "artifact": objective,
            "expanded": str(objective.id) == focused_objective or request.GET.get("dashboard") == "1",
            "projects": projects,
            "direct_actions": direct_actions,
            "factors": factors,
            "target_count": len(objective.targets.all()),
            "indicator_count": len(objective.indicators.all()),
            "action_count": action_count,
        }

    dimension_groups = []
    dimensions = [item for item in children.get(None, []) if item.artifact_type == PlanArtifact.ArtifactType.DIMENSION]
    dimensions.sort(key=lambda item: min((axis.code for axis in children.get(item.id, [])), default=item.title))
    for dimension in dimensions:
        axes = []
        for axis in children.get(dimension.id, []):
            objectives = [
                objective_node(item)
                for item in children.get(axis.id, [])
                if item.artifact_type == PlanArtifact.ArtifactType.OBJECTIVE
            ]
            axes.append({"artifact": axis, "objectives": objectives})
        dimension_groups.append({"artifact": dimension, "axes": axes})

    # Mantém visíveis cadastros antigos que ainda não têm dimensão/eixo associados.
    orphan_objectives = [
        objective_node(item)
        for item in artifacts
        if item.artifact_type == PlanArtifact.ArtifactType.OBJECTIVE
        and (not item.parent_id or item.parent.artifact_type != PlanArtifact.ArtifactType.AXIS)
    ]

    progress_average = sum(float(action.progress) for action in actions) / len(actions) if actions else 0
    context = {
        "plans": plans,
        "units": units,
        "selected_unit": selected_unit,
        "plan": plan,
        "selected_plan": str(plan.id),
        "dimension_groups": dimension_groups,
        "orphan_objectives": orphan_objectives,
        "objective_count": sum(item.artifact_type == PlanArtifact.ArtifactType.OBJECTIVE for item in artifacts),
        "project_count": sum(item.artifact_type == PlanArtifact.ArtifactType.PROJECT for item in artifacts),
        "action_count": len(actions),
        "progress_average": round(progress_average, 1),
    }
    return render(request, "core/pei_overview.html", context)


@login_required
@permission_required("core.view_indicator", raise_exception=True)
def indicator_overview(request):
    return _results_overview(request)


@login_required
@permission_required("core.view_strategictarget", raise_exception=True)
def target_overview(request):
    return _results_overview(request)


def _results_overview(request):
    context = {"units": view_scope_units(OrganizationalUnit.objects.order_by("name"), request.user)}
    if request.user.has_perm("core.view_strategictarget"):
        target_context = _target_overview_context(request)
        if not isinstance(target_context, dict):
            return target_context
        context.update(target_context)
    if request.user.has_perm("core.view_indicator"):
        context.update(_indicator_overview_context(request))
    selected_year = _selected_results_year(request)
    year_plans = Plan.objects.filter(active=True)
    if request.GET.get("plan", "").isdigit():
        year_plans = year_plans.filter(pk=request.GET["plan"])
    years = set()
    for available_plan in year_plans:
        years.update(range(available_plan.start_date.year, available_plan.end_date.year + 1))
    if selected_year:
        years.add(int(selected_year))
    context["selected_year"] = selected_year
    context["available_years"] = sorted(years, reverse=True)
    can_measure = request.user.has_perm("core.view_indicatormeasurement")
    context["can_view_measurements"] = can_measure
    context["can_add_measurement"] = request.user.has_perm("core.add_indicatormeasurement")
    visible_targets = {row["target"].id: row["target"] for row in context.get("target_rows", [])}
    for execution in context.get("target_rows", []):
        execution["target"].can_write = _can_write_target(request.user, execution["target"])
        execution["target"].achievement_summary = _target_achievement_chart(execution) if can_measure else None
    linked_ids = set()
    writable_indicators = set(scope_by_unit(Indicator.objects.all(), request.user, "responsible_unit_id", include_unassigned=True).values_list("pk", flat=True))
    for row in context.get("indicator_rows", []):
        row["indicator"].can_write = row["indicator"].id in writable_indicators
        row["targets"] = [visible_targets[item.id] for item in row["indicator"].targets.all() if item.id in visible_targets]
        linked_ids.update(item.id for item in row["targets"])
        row["measurements"] = _results_measurements(row["indicator"], selected_year) if can_measure else []
        row["chart"] = _measurement_chart(row["indicator"], year=selected_year) if can_measure else None
        row["chart_data_id"] = f"target-chart-data-{row['indicator'].id}"
        measurement = row["signal"]["measurement"]
        measured = _decimal_from_measurement(measurement.measured_value) if measurement and can_measure else None
        row["current_chart_data_id"] = f"current-result-data-{row['indicator'].id}"
        row["current_chart"] = {
            "result": float(measured) if measured is not None else None,
            "expected": float(row["signal"]["expected_value"]) if row["signal"].get("expected_value") is not None else None,
            "achievement": row["signal"]["achievement"],
            "unit": row["indicator"].measurement_unit,
            "period": measurement.reference_period if measurement else "",
        } if can_measure and measurement else None
    context["standalone_targets"] = [item for pk, item in visible_targets.items() if pk not in linked_ids]
    context["inline_charts"] = bool(context.get("indicator_rows")) and can_measure
    return render(request, "core/indicator_overview.html", context)


def _indicator_overview_context(request):
    plans = Plan.objects.filter(active=True).order_by("start_date", "acronym")
    units = view_scope_units(OrganizationalUnit.objects.order_by("name"), request.user)
    selected_plan = request.GET.get("plan", "")
    selected_unit = selected_unit_for_request(request)
    selected_objective = request.GET.get("objective", "")
    selected_status = _selected_result_status(request, "indicator")
    selected_year = _selected_results_year(request)
    plan = plans.filter(pk=selected_plan).first() if selected_plan.isdigit() else plans.first()

    indicators = Indicator.objects.none()
    objectives = PlanArtifact.objects.none()
    if plan:
        objectives = PlanArtifact.objects.filter(
            plan__in=plans.filter(pk=selected_plan) if selected_plan.isdigit() else plans,
            artifact_type=PlanArtifact.ArtifactType.OBJECTIVE,
        ).order_by("code", "title")
        indicators = (
            view_scope_by_unit(Indicator.objects.filter(artifacts__plan__in=plans.filter(pk=selected_plan) if selected_plan.isdigit() else plans), request.user, "responsible_unit_id", include_unassigned=True)
            .select_related("responsible_unit")
            .prefetch_related("responsible_units", "artifacts", "artifacts__plan", "targets", "targets__artifact__plan", "targets__action", "measurements", "measurements__recorded_by", "measurements__measured_by", "measurements__measured_unit")
            .distinct()
            .order_by("code", "name")
        )
        if selected_unit.isdigit():
            indicators = indicators.filter(Q(responsible_unit_id=selected_unit) | Q(responsible_units__id=selected_unit)).distinct()
        if selected_objective.isdigit():
            indicators = indicators.filter(artifacts__id=selected_objective)

    if request.GET.get("target", "").isdigit():
        indicators = indicators.filter(targets__id=request.GET["target"])
    indicator_rows = []
    signal_counts = {"green": 0, "yellow": 0, "orange": 0, "red": 0, "gray": 0}
    for indicator in indicators:
        signal = _indicator_signal(indicator, year=selected_year)
        signal_counts[signal["code"]] += 1
        indicator_rows.append({"indicator": indicator, "signal": signal})
    if selected_status == "none":
        indicator_rows = []
    if selected_status in (*SIGNAL_STYLE, "measured", "attention", "unmeasured"):
        indicator_rows = [row for row in indicator_rows if _signal_matches(row["signal"]["code"], selected_status)]

    signal_counts = {code: sum(row["signal"]["code"] == code for row in indicator_rows) for code in SIGNAL_STYLE}

    return {
            "plans": plans,
            "units": units,
            "objectives": objectives,
            "plan": plan,
            "selected_plan": selected_plan,
            "selected_unit": selected_unit,
            "selected_objective": selected_objective,
            "selected_indicator_status": selected_status,
            "indicator_rows": indicator_rows,
            "indicator_count": sum(signal_counts.values()),
            "updated_count": sum(value for key, value in signal_counts.items() if key != "gray"),
            "attention_count": signal_counts["yellow"] + signal_counts["orange"] + signal_counts["red"],
            "signal_counts": signal_counts,
    }


def _target_overview_context(request):
    plans = Plan.objects.filter(active=True).order_by("start_date", "acronym")
    selected_plan = request.GET.get("plan", "")
    selected_year = _selected_results_year(request)
    selected_objective = request.GET.get("objective", "")
    plan = plans.filter(pk=selected_plan).first() if selected_plan.isdigit() else plans.first()

    targets = StrategicTarget.objects.none()
    objectives = PlanArtifact.objects.none()
    if plan:
        objectives = PlanArtifact.objects.filter(
            plan__in=plans.filter(pk=selected_plan) if selected_plan.isdigit() else plans,
            artifact_type=PlanArtifact.ArtifactType.OBJECTIVE,
        ).order_by("code", "title")
        targets = _scoped_targets(request.user, plans.filter(pk=selected_plan) if selected_plan.isdigit() else plans, selected_unit_for_request(request)).order_by("code", "description")
        if selected_objective.isdigit():
            targets = targets.filter(artifact_id=selected_objective)

    editable_targets = targets.filter(pk__in=[target.pk for target in targets if _can_write_target(request.user, target)])
    if request.GET.get("target", "").isdigit():
        targets = targets.filter(pk=request.GET["target"])
    selected_status = _selected_result_status(request, "target")
    if selected_status in (*SIGNAL_STYLE, "none", "unmeasured", "attention", "measured"):
        indicators = view_scope_by_unit(Indicator.objects.filter(artifacts__plan__in=plans.filter(pk=selected_plan) if selected_plan.isdigit() else plans).distinct(), request.user, "responsible_unit_id", include_unassigned=True)
        if selected_unit_for_request(request).isdigit():
            indicators = indicators.filter(Q(responsible_unit_id=selected_unit_for_request(request)) | Q(responsible_units__id=selected_unit_for_request(request))).distinct()
        signals = {item.id: _indicator_signal(item, year=selected_year)["code"] for item in indicators.prefetch_related("measurements")}
        targets = [target for target in targets if _signal_matches(_target_signal(target, signals), selected_status)]

    target_rows = [_target_execution(target, request.user, selected_unit_for_request(request), year=selected_year) for target in targets]
    status_counts = {code: sum(1 for row in target_rows if row["code"] == code) for code in (*SIGNAL_STYLE, "none")}
    progress_rows = [row for row in target_rows if row["progress"] is not None]
    progress_chart = {
        "categories": [row["target"].code or "Meta" for row in progress_rows],
        "descriptions": [row["target"].description for row in progress_rows],
        "values": [max(min(row["progress"], 100), 0) for row in progress_rows],
        "raw": [row["progress"] for row in progress_rows],
        "colors": [SIGNAL_STYLE.get(row["code"], SIGNAL_STYLE["gray"])[1] for row in progress_rows],
        "labels": [row["label"] for row in progress_rows],
    } if progress_rows else None
    focused_charts = []
    if request.GET.get("target", "").isdigit() and len(target_rows) == 1:
        for item in target_rows[0]["indicators"]:
            chart = _measurement_chart(item["indicator"], year=selected_year) if request.user.has_perm("core.view_indicatormeasurement") else None
            focused_charts.append({"element_id": f"target-chart-data-{item['indicator'].id}", "chart": chart})

    write_ids = user_unit_ids(request.user)
    selected_unit = selected_unit_for_request(request)
    own_selection = write_ids is None or (selected_unit.isdigit() and int(selected_unit) in write_ids)
    can_add_target = own_selection and request.user.has_perm("core.add_strategictarget")
    can_edit_target = request.user.has_perm("core.change_strategictarget")
    target_form = None
    editing_target = None
    if request.method == "POST":
        _require_permission(
            request.user,
            "change_strategictarget" if request.POST.get("target_id", "").isdigit() else "add_strategictarget",
        )
    if plan and (can_add_target or can_edit_target):
        form_actions = scope_actions(StrategicAction.objects.all(), request.user)
        form_indicators = scope_by_unit(Indicator.objects.all(), request.user, "responsible_unit_id")
        unit_id = selected_unit_for_request(request)
        if unit_id.isdigit():
            form_indicators = form_indicators.filter(Q(responsible_unit_id=unit_id) | Q(responsible_units__id=unit_id)).distinct()
            form_actions = form_actions.filter(coordinating_unit_id=unit_id)
        if request.method == "POST":
            target_id = request.POST.get("target_id", "")
            if target_id.isdigit():
                _require_permission(request.user, "change_strategictarget")
                editing_target = get_object_or_404(editable_targets, pk=target_id)
            else:
                _require_permission(request.user, "add_strategictarget")
            target_form = StrategicTargetForm(request.POST, instance=editing_target, plan=plan, actions=form_actions, visible_indicators=form_indicators)
            if target_form.is_valid():
                candidate = target_form.instance
                if write_ids is not None:
                    action = target_form.cleaned_data.get("action")
                    indicators = target_form.cleaned_data.get("indicators")
                    if action is None and not indicators:
                        raise PermissionDenied
                    if action and not scope_actions(StrategicAction.objects.all(), request.user).filter(pk=action.pk).exists():
                        raise PermissionDenied
                    if any(not item.responsible_unit_ids.intersection(write_ids) for item in indicators):
                        raise PermissionDenied
                target = target_form.save()
                messages.success(request, "Meta atualizada." if editing_target else "Meta cadastrada.")
                return redirect(f"{reverse('target_overview')}?{urlencode({'plan': plan.id, **({'year': selected_year} if selected_year else {})})}#meta-{target.id}")
        elif request.GET.get("editar", "").isdigit() and can_edit_target:
            editing_target = get_object_or_404(editable_targets, pk=request.GET["editar"])
            target_form = StrategicTargetForm(instance=editing_target, plan=plan, actions=form_actions, visible_indicators=form_indicators)
        elif can_add_target:
            initial = {"artifact": selected_objective} if selected_objective.isdigit() else {}
            target_form = StrategicTargetForm(initial=initial, plan=plan, actions=form_actions, visible_indicators=form_indicators)

    return {
            "can_add_target": can_add_target,
            "can_edit_target": can_edit_target,
            "target_form": target_form,
            "editing_target": editing_target,
            "plans": plans,
            "objectives": objectives,
            "plan": plan,
            "selected_plan": selected_plan,
            "selected_objective": selected_objective,
            "targets": targets,
            "target_rows": target_rows,
            "status_counts": status_counts,
            "target_attention_count": status_counts["yellow"] + status_counts["orange"] + status_counts["red"],
            "progress_chart": progress_chart,
            "focused_charts": focused_charts,
            "selected_target_status": selected_status,
            "selected_unit": selected_unit_for_request(request),
            "selected_target": request.GET.get("target", ""),
    }


def _measurement_chart(indicator, year=""):
    """Geometria (SVG) do gráfico de linha.

    Parte da linha de base (na data da linha de base) e liga cada resultado aferido ao fim do seu
    período de aferição, em ordem cronológica; a meta de cada período vai em linha à parte.
    """
    entries = []
    baseline = None
    for measurement in _results_measurements(indicator, year):
        basal = _decimal_from_measurement(measurement.baseline_value)
        if basal is not None and measurement.baseline_date and (
            baseline is None or measurement.baseline_date < baseline[0]
        ):
            baseline = (measurement.baseline_date, float(basal), measurement.baseline_value)
        value = _decimal_from_measurement(measurement.measured_value)
        if value is None:
            continue
        when = measurement.period_end
        if when is None:
            try:
                when = datetime.strptime(measurement.reference_period.strip()[-10:], "%d/%m/%Y").date()
            except ValueError:
                when = timezone.localtime(measurement.recorded_at).date()
        entries.append(
            {
                "when": when,
                "order": measurement.recorded_at,
                "value": float(value),
                "text": measurement.measured_value,
                "expected": measurement.expected_value,
                "label": when.strftime("%d/%m/%Y"),
                "tip": f"{measurement.reference_period}: {measurement.measured_value}",
                "kind": "measured",
            }
        )
    if baseline:
        entries.append(
            {
                "when": baseline[0],
                "order": None,
                "value": baseline[1],
                "text": baseline[2],
                "expected": None,
                "label": baseline[0].strftime("%d/%m/%Y"),
                "tip": f"Linha de base em {baseline[0]:%d/%m/%Y}: {baseline[2]}",
                "kind": "baseline",
            }
        )
    if not any(item["kind"] == "measured" for item in entries):
        return None
    entries.sort(key=lambda item: (item["when"], item["kind"] != "baseline", str(item["order"])))

    return {
        "categories": [item["label"] for item in entries],
        "result": [
            {"y": item["value"], "baseline": item["kind"] == "baseline", "tip": item["tip"]} for item in entries
        ],
        "expected": [float(item["expected"]) if item["expected"] is not None else None for item in entries],
        "has_baseline": baseline is not None,
        "has_expected": any(item["expected"] is not None for item in entries),
    }

@login_required
@permission_required("core.delete_indicatormeasurement", raise_exception=True)
def measurement_delete(request, indicator_id, measurement_id):
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])
    indicator = get_object_or_404(
        scope_by_unit(Indicator.objects.all(), request.user, "responsible_unit_id", include_unassigned=True), pk=indicator_id
    )
    measurement = get_object_or_404(indicator.measurements, pk=measurement_id)
    measurement.delete()
    messages.success(request, "Aferição removida. O gráfico e a situação foram atualizados.")
    return redirect(reverse("indicator_overview") + f"#indicador-{indicator.id}")


@login_required
@permission_required("core.view_indicator", raise_exception=True)
def indicator_detail(request, indicator_id):
    indicator = get_object_or_404(
        (view_scope_by_unit if request.method == "GET" else scope_by_unit)(Indicator.objects.all(), request.user, "responsible_unit_id", include_unassigned=True).select_related("responsible_unit").prefetch_related(
            "artifacts",
            "artifacts__plan",
            "targets",
            "targets__artifact__plan",
            "targets__action",
            "measurements",
            "measurements__recorded_by",
        ),
        pk=indicator_id,
    )
    writable = scope_by_unit(Indicator.objects.all(), request.user, "responsible_unit_id", include_unassigned=True).filter(pk=indicator.id).exists()
    request.read_only_other_unit = not writable
    indicator.can_write = writable
    can_edit_definition = writable and request.user.has_perm("core.change_indicator")
    can_edit_measurement = writable and request.user.has_perm("core.change_indicatormeasurement")
    editing_measurement = None
    definition_form = IndicatorDefinitionForm(instance=indicator) if can_edit_definition else None
    form = None
    if request.method == "POST" and request.POST.get("operation") == "edit_definition":
        if not can_edit_definition:
            raise PermissionDenied
        definition_form = IndicatorDefinitionForm(request.POST, instance=indicator)
        if definition_form.is_valid():
            definition_form.save()
            messages.success(request, "Ficha do indicador atualizada.")
            return redirect("indicator_detail", indicator_id=indicator.id)
    elif request.method == "POST":
        editing = None
        if request.POST.get("measurement_id", "").isdigit():
            if not can_edit_measurement:
                raise PermissionDenied
            editing = get_object_or_404(indicator.measurements.all(), pk=request.POST["measurement_id"])
        else:
            _require_permission(request.user, "add_indicatormeasurement")
        form = IndicatorMeasurementForm(request.POST, request.FILES, instance=editing)
        if form.is_valid():
            measurement = form.save(commit=False)
            measurement.indicator = indicator
            if editing is None:
                measurement.recorded_by = request.user
            profile = getattr(measurement.measured_by, "profile", None)
            measurement.measured_unit = profile.unit if profile else None
            measurement.expected_value = _period_target(
                indicator, measurement.baseline_value, measurement.baseline_date, measurement.period_end
            )
            measurement.save()
            if editing is None:
                messages.success(request, "Aferição registrada e semáforo atualizado.")
            else:
                messages.success(request, "Aferição atualizada e semáforo recalculado.")
            return redirect("indicator_detail", indicator_id=indicator.id)
        if editing is not None:
            editing_measurement = editing
    elif request.GET.get("editar", "").isdigit() and can_edit_measurement:
        editing_measurement = get_object_or_404(indicator.measurements.all(), pk=request.GET["editar"])
        form = IndicatorMeasurementForm(instance=editing_measurement)
    if form is None:
        form = IndicatorMeasurementForm(
            initial={"baseline_value": indicator.baseline, "baseline_date": indicator.reference_parameters.get("baseline_date"), "measured_by": request.user.pk}
        )
    signal = _indicator_signal(indicator)
    can_view_measurements = request.user.has_perm("core.view_indicatormeasurement")
    baseline = indicator.baseline
    if not baseline:
        dated = [item for item in indicator.measurements.all() if item.baseline_value]
        if dated:
            first = min(dated, key=lambda item: (item.baseline_date is None, item.baseline_date, item.recorded_at))
            baseline = first.baseline_value + (f" (em {first.baseline_date:%d/%m/%Y})" if first.baseline_date else "")
    return render(
        request,
        "core/indicator_detail.html",
        {
            "indicator": indicator,
            "baseline": baseline,
            "signal": signal,
            "measurement_form": form,
            "editing_measurement": editing_measurement,
            "can_edit_measurement": can_edit_measurement,
            "can_view_measurements": can_view_measurements,
            "can_add_measurement": writable and request.user.has_perm("core.add_indicatormeasurement"),
            "definition_form": definition_form,
            "final_target": _final_target_value(indicator),
            "final_progress": _final_progress(indicator, signal["measurement"]) if can_view_measurements else None,
            "chart": _measurement_chart(indicator) if can_view_measurements else None,
        },
    )


def _sector_report_content(report):
    actions = list(
        StrategicAction.objects.filter(artifact__plan=report.cycle.plan).filter(Q(coordinating_unit=report.unit) | Q(participating_units=report.unit)).distinct()
        .select_related("artifact")
        .order_by("code")
    )
    activities = list(
        Activity.objects.filter(action_plan__action__in=actions)
        .select_related("action_plan__action", "executor")
        .order_by("end_date", "title")
    )
    blockers = list(ActivityBlocker.objects.filter(activity__in=activities).exclude(status=ActivityBlocker.Status.RESOLVED))
    risks = list(Risk.objects.filter(action__in=actions).select_related("activity", "owner"))
    evidences = list(ActivityEvidence.objects.filter(activity__in=activities).select_related("activity"))
    indicators = list(
        Indicator.objects.filter(artifacts__plan=report.cycle.plan).filter(Q(responsible_unit=report.unit) | Q(responsible_units=report.unit)).distinct()
        .prefetch_related("measurements")
        .distinct()
        .order_by("code")
    )
    indicator_rows = [{"indicator": item, "signal": _indicator_signal(item)} for item in indicators]
    targets = list(
        StrategicTarget.objects.filter(artifact__plan=report.cycle.plan)
        .filter(Q(action__coordinating_unit=report.unit) | Q(action__isnull=True, indicators__responsible_unit=report.unit))
        .select_related("artifact", "artifact__plan")
        .prefetch_related("indicators", "indicators__measurements", "indicators__targets")
        .distinct()
        .order_by("code")
    )
    target_rows = [_target_execution(target, unit_id=str(report.unit_id)) for target in targets]
    artifacts = PlanArtifact.objects.filter(plan=report.cycle.plan).in_bulk()
    linked_artifact_ids = {action.artifact_id for action in actions} | {target.artifact_id for target in targets}
    for indicator in indicators:
        linked_artifact_ids.update(indicator.artifacts.filter(plan=report.cycle.plan).values_list("pk", flat=True))
    objective_ids = set()
    for artifact_id in linked_artifact_ids:
        artifact = artifacts.get(artifact_id)
        while artifact:
            if artifact.artifact_type == PlanArtifact.ArtifactType.OBJECTIVE:
                objective_ids.add(artifact.pk)
                break
            artifact = artifacts.get(artifact.parent_id)
    objectives = sorted((artifacts[pk] for pk in objective_ids), key=lambda item: item.code)
    financial = Activity.objects.filter(pk__in=[item.id for item in activities]).aggregate(
        planned=Sum("planned_cost"), disbursed=Sum("disbursed_cost")
    )
    return {
        "actions": actions,
        "activities": activities,
        "blockers": blockers,
        "risks": risks,
        "evidences": evidences,
        "indicator_rows": indicator_rows,
        "target_rows": target_rows,
        "objectives": objectives,
        "planned_cost": financial["planned"] or 0,
        "disbursed_cost": financial["disbursed"] or 0,
    }


def _sector_report_snapshot(content):
    return {
        "action_count": len(content["actions"]),
        "activity_count": len(content["activities"]),
        "open_blocker_count": len(content["blockers"]),
        "risk_count": len(content["risks"]),
        "materialized_risk_count": sum(item.status == Risk.Status.MATERIALIZED for item in content["risks"]),
        "evidence_count": len(content["evidences"]),
        "indicator_count": len(content["indicator_rows"]),
        "planned_cost": str(content["planned_cost"]),
        "disbursed_cost": str(content["disbursed_cost"]),
        "actions": [
            {"code": item.code, "title": item.title, "status": item.get_status_display(), "progress": str(item.progress)}
            for item in content["actions"]
        ],
        "risks": [{"title": item.title, "status": item.get_status_display(), "level": item.level} for item in content["risks"]],
    }


@login_required
@permission_required("core.view_reportcycle", raise_exception=True)
def report_cycle_overview(request):
    if request.method == "POST":
        _require_permission(request.user, "add_reportcycle")
        form = ReportCycleForm(request.POST)
        if form.is_valid():
            own_ids = user_unit_ids(request.user)
            if own_ids is not None and request.user.has_perm("core.view_other_units") and any(unit.pk not in own_ids for unit in form.cleaned_data["participating_units"]):
                raise PermissionDenied
            with transaction.atomic():
                cycle = form.save(commit=False)
                cycle.created_by = request.user
                cycle.save()
                form.save_m2m()
                for unit in cycle.participating_units.all():
                    SectorReport.objects.get_or_create(cycle=cycle, unit=unit)
            messages.success(request, "Ciclo aberto e relatórios setoriais preparados.")
            return redirect("report_cycle_detail", cycle_id=cycle.id)
    else:
        form = ReportCycleForm()
    cycles = ReportCycle.objects.select_related("plan", "created_by").prefetch_related("sector_reports", "participating_units")
    selected_unit = selected_unit_for_request(request)
    selected_year = request.GET.get("year", "")
    visible_units = {int(selected_unit)} if selected_unit.isdigit() else user_unit_ids(request.user, for_view=True)
    if visible_units is not None:
        cycles = cycles.filter(sector_reports__unit_id__in=visible_units).distinct()
    years = {timezone.localdate().year}
    for start, end in cycles.values_list("period_start", "period_end"):
        years.update(range(start.year, end.year + 1))
    if selected_year.isdigit() and 1 <= int(selected_year) <= 9999:
        year = int(selected_year)
        cycles = cycles.filter(period_start__lte=date(year, 12, 31), period_end__gte=date(year, 1, 1))
    cycle_rows = []
    for cycle in cycles:
        reports = [
            item for item in cycle.sector_reports.all() if visible_units is None or item.unit_id in visible_units
        ]
        cycle_rows.append(
            {
                "cycle": cycle,
                "report_count": len(reports),
                "submitted_count": sum(item.status != SectorReport.Status.DRAFT for item in reports),
                "approved_count": sum(item.status in [SectorReport.Status.APPROVED, SectorReport.Status.CONSOLIDATED] for item in reports),
            }
        )
    return render(
        request,
        "core/report_cycle_overview.html",
        {"units": view_scope_units(OrganizationalUnit.objects.order_by("name"), request.user), "selected_unit": selected_unit, "years": sorted(years, reverse=True), "selected_year": selected_year, "cycle_rows": cycle_rows, "cycle_form": form, "can_add_cycle": request.user.has_perm("core.add_reportcycle")},
    )


@login_required
@permission_required("core.view_reportcycle", raise_exception=True)
def report_cycle_detail(request, cycle_id):
    cycle = get_object_or_404(
        ReportCycle.objects.select_related("plan", "created_by").prefetch_related("sector_reports__unit", "sector_reports__validator"),
        pk=cycle_id,
    )
    all_reports = list(cycle.sector_reports.all())
    selected_unit = selected_unit_for_request(request)
    visible_units = {int(selected_unit)} if selected_unit.isdigit() else user_unit_ids(request.user, for_view=True)
    reports = [item for item in all_reports if visible_units is None or item.unit_id in visible_units]
    if visible_units is not None and not reports:
        raise Http404
    own_ids = user_unit_ids(request.user)
    readonly_cycle = own_ids is not None and request.user.has_perm("core.view_other_units") and any(item.unit_id not in own_ids for item in all_reports)
    request.read_only_other_unit = readonly_cycle
    if request.method == "POST" and readonly_cycle:
        raise PermissionDenied
    if request.method == "POST":
        _require_permission(request.user, "change_reportcycle")
        operation = request.POST.get("operation")
        if operation == "consolidate":
            if all_reports and all(item.status == SectorReport.Status.APPROVED for item in all_reports):
                cycle.status = ReportCycle.Status.CONSOLIDATING
                cycle.save(update_fields=["status"])
                cycle.sector_reports.update(status=SectorReport.Status.CONSOLIDATED)
                messages.success(request, "Relatórios aprovados reunidos na consolidação institucional.")
            else:
                messages.error(request, "Todos os relatórios setoriais precisam estar aprovados antes da consolidação.")
        elif operation == "close" and cycle.status == ReportCycle.Status.CONSOLIDATING:
            cycle.status = ReportCycle.Status.CLOSED
            cycle.closed_at = timezone.now()
            cycle.save(update_fields=["status", "closed_at"])
            messages.success(request, "Ciclo encerrado. A fotografia dos relatórios foi preservada.")
        return redirect("report_cycle_detail", cycle_id=cycle.id)
    return render(
        request,
        "core/report_cycle_detail.html",
        {
            "units": view_scope_units(OrganizationalUnit.objects.order_by("name"), request.user),
            "selected_unit": selected_unit,
            "cycle": cycle,
            "reports": reports,
            "approved_count": sum(item.status in [SectorReport.Status.APPROVED, SectorReport.Status.CONSOLIDATED] for item in reports),
            "submitted_count": sum(item.status != SectorReport.Status.DRAFT for item in reports),
            "returned_count": sum(item.status == SectorReport.Status.RETURNED for item in reports),
        },
    )


@login_required
@permission_required("core.view_sectorreport", raise_exception=True)
def sector_report_detail(request, cycle_id, report_id):
    report = get_object_or_404(
        (view_scope_by_unit if request.method == "GET" else scope_by_unit)(SectorReport.objects.all(), request.user, "unit_id").select_related(
            "cycle", "cycle__plan", "unit", "prepared_by", "validator"
        ),
        pk=report_id,
        cycle_id=cycle_id,
    )
    own_ids = user_unit_ids(request.user)
    request.read_only_other_unit = own_ids is not None and report.unit_id not in own_ids
    content = _sector_report_content(report)
    report_form = SectorReportForm(instance=report, current_user=request.user)
    validation_form = ReportValidationForm()
    if request.method == "POST":
        _require_permission(request.user, "change_sectorreport")
    if request.method == "POST" and report.cycle.status != ReportCycle.Status.CLOSED:
        operation = request.POST.get("operation")
        if operation in ["save", "submit"]:
            report_form = SectorReportForm(request.POST, instance=report, current_user=request.user)
            report_form.is_valid()
            if operation == "submit":
                if not request.POST.get("executive_summary", "").strip():
                    report_form.add_error("executive_summary", "Informe a síntese antes do envio.")
                if not request.POST.get("next_steps", "").strip():
                    report_form.add_error("next_steps", "Informe os próximos passos antes do envio.")
            if not report_form.errors:
                report = report_form.save(commit=False)
                report.prepared_by = request.user
                if operation == "submit":
                    report.status = SectorReport.Status.SUBMITTED
                    report.submitted_at = timezone.now()
                    report.snapshot = _sector_report_snapshot(content)
                elif report.status not in [SectorReport.Status.DRAFT, SectorReport.Status.RETURNED]:
                    report.status = SectorReport.Status.DRAFT
                report.save()
                messages.success(request, "Relatório enviado para validação." if operation == "submit" else "Rascunho salvo.")
                return redirect("sector_report_detail", cycle_id=report.cycle_id, report_id=report.id)
        elif operation == "validate" and report.status == SectorReport.Status.SUBMITTED:
            validation_form = ReportValidationForm(request.POST)
            if report.validator_id != request.user.id:
                validation_form.add_error(None, "Somente a pessoa designada pode validar este relatório.")
            if validation_form.is_valid():
                decision = validation_form.cleaned_data["decision"]
                report.validator_comment = validation_form.cleaned_data["comment"]
                report.validated_at = timezone.now()
                if decision == "APPROVE":
                    report.status = SectorReport.Status.APPROVED
                    report.resubmission_due_date = None
                    message = "Relatório aprovado."
                else:
                    report.status = SectorReport.Status.RETURNED
                    report.resubmission_due_date = validation_form.cleaned_data["resubmission_due_date"]
                    message = "Relatório devolvido para correção."
                report.save(update_fields=["status", "validator_comment", "validated_at", "resubmission_due_date", "updated_at"])
                messages.success(request, message)
                return redirect("sector_report_detail", cycle_id=report.cycle_id, report_id=report.id)
    if request.user.has_perm("core.view_indicatormeasurement"):
        for row in content["indicator_rows"]:
            row["chart"] = _measurement_chart(row["indicator"])
            row["chart_data_id"] = f"sector-report-chart-{row['indicator'].pk}"
    return render(
        request,
        "core/sector_report_detail.html",
        {"report": report, "content": content, "report_form": report_form, "validation_form": validation_form,
         "has_indicator_charts": any(row.get("chart") for row in content["indicator_rows"])},
    )


@login_required
@permission_required("core.view_actionplan", raise_exception=True)
def action_plan_list(request):
    plans = Plan.objects.filter(active=True).order_by("acronym")
    units = view_scope_units(OrganizationalUnit.objects.order_by("name"), request.user)
    actions = view_scope_actions(
        StrategicAction.objects.select_related("artifact", "artifact__plan", "coordinating_unit"), request.user
    ).annotate(
        activity_count=Count("action_plan__activities"),
        allocated_weight=Sum("action_plan__activities__weight"),
        activity_progress=Avg("action_plan__activities__progress"),
    )
    selected_plan = request.GET.get("plan", "")
    selected_unit = selected_unit_for_request(request)
    selected_status = request.GET.get("status", "")
    if selected_plan.isdigit():
        actions = actions.filter(artifact__plan_id=selected_plan)
    if selected_unit.isdigit():
        actions = actions.filter(coordinating_unit_id=selected_unit)
    if selected_status in StrategicAction.Status.values:
        actions = actions.filter(status=selected_status)

    if request.GET.get("objective", "").isdigit():
        actions = actions.filter(artifact_id__in=_objective_artifact_ids(request.GET["objective"]))
    if request.GET.get("overdue") == "1":
        actions = actions.filter(due_date__lt=timezone.localdate()).exclude(
            status__in=[StrategicAction.Status.COMPLETED, StrategicAction.Status.SUSPENDED]
        )

    display_mode = "list" if request.GET.get("view") == "list" else "columns"
    display_query = request.GET.copy()
    display_query["unit"] = selected_unit
    display_query["view"] = "columns"
    columns_url = "?" + display_query.urlencode()
    display_query["view"] = "list"
    list_url = "?" + display_query.urlencode()

    actions = list(actions.order_by("artifact__code", "code"))
    writable_ids = set(scope_actions(
        StrategicAction.objects.filter(pk__in=[action.pk for action in actions]), request.user
    ).values_list("pk", flat=True))
    can_manage_plans = any(request.user.has_perm(f"core.{codename}") for codename in (
        "add_actionplan", "add_activity", "change_activity", "delete_activity",
    ))
    for action in actions:
        action.can_write = action.pk in writable_ids and can_manage_plans

    return render(
        request,
        "core/action_plan_list.html",
        {
            "display_mode": display_mode,
            "columns_url": columns_url,
            "list_url": list_url,
            "actions": actions,
            "plans": plans,
            "units": units,
            "actions_status_choices": StrategicAction.Status.choices,
            "selected_plan": selected_plan,
            "selected_unit": selected_unit,
            "selected_status": selected_status,
        },
    )


# Operação do ciclo do risco → permissão exigida para executá-la.
RISK_OPERATION_PERMISSIONS = {
    "delete_risk": "delete_risk",
    "edit_materialization": "change_riskmaterialization",
    "delete_materialization": "delete_riskmaterialization",
    "update_identity": "change_risk",
    "update_timing": "change_risk",
    "add_assessment": "add_riskassessment",
    "delete_assessment": "delete_riskassessment",
    "edit_assessment": "change_riskassessment",
    "add_treatment": "add_risktreatment",
    "delete_treatment": "delete_risktreatment",
    "delete_acceptance": "delete_riskacceptance",
    "materialize": "add_riskmaterialization",
    "accept": "add_riskacceptance",
    "submit_remediation": "add_riskremediationsubmission",
}


def _require_permission(user, codename):
    if not user.has_perm(f"core.{codename}"):
        raise PermissionDenied


def _save_new_risk(user, form, action, activity=None):
    """Grava o risco com sua avaliação inicial e resposta obrigatória."""
    with transaction.atomic():
        risk = form.save(commit=False)
        risk.action = action
        if activity is not None:
            risk.activity = activity
        risk.owner = user
        risk.status = Risk.Status.IDENTIFIED
        decision = form.cleaned_data["treatment_decision"]
        risk.treatment = decision
        risk.save()
        RiskAssessment.objects.create(
            risk=risk,
            assessment_type=RiskAssessment.AssessmentType.CURRENT,
            probability=risk.probability,
            impact=risk.impact,
            author=user,
        )
        if decision:
            RiskTreatment.objects.create(
                risk=risk,
                decision=decision,
                responsible=form.cleaned_data["treatment_responsible"],
                due_date=form.cleaned_data["treatment_due_date"],
                preventive_measure=risk.preventive_measure,
                contingency_measure=risk.contingency_measure,
                created_by=user,
            )
            risk.status = Risk.Status.IN_TREATMENT
            risk.save(update_fields=["status"])
    return risk


def _registered_risks(request, actions):
    raw_ids = request.POST.get("registered_risks", "") if request.method == "POST" else request.GET.get("registered", "")
    ids = list(dict.fromkeys(int(value) for value in raw_ids.split(",") if value.isascii() and value.isdigit() and len(value) < 19))[-50:]
    records = {
        risk.pk: risk for risk in Risk.objects.filter(pk__in=ids, action__in=actions).select_related("activity", "action").prefetch_related("treatments__responsible")
    }
    return [records[pk] for pk in ids if pk in records]


def _next_risk_registration(request, registered_risks, risk):
    ids = [item.pk for item in registered_risks] + [risk.pk]
    return redirect(request.path + "?" + urlencode({"new": "1", "registered": ",".join(map(str, ids))}))


@login_required
def risk_overview(request):
    _require_permission(request.user, "view_risk")
    plans = Plan.objects.filter(active=True).order_by("acronym")
    units = view_scope_units(OrganizationalUnit.objects.order_by("name"), request.user)
    can_add_risk = request.user.has_perm("core.add_risk")
    creatable_actions = scope_actions(
        StrategicAction.objects.filter(action_plan__isnull=False).select_related("artifact"), request.user
    ).order_by("artifact__code", "code")
    registered_risks = _registered_risks(request, creatable_actions)
    if request.method == "POST":
        _require_permission(request.user, "add_risk")
        create_form = RiskCreateForm(request.POST, actions=creatable_actions)
        if create_form.is_valid():
            risk = _save_new_risk(request.user, create_form, create_form.cleaned_data["action"])
            messages.success(request, "Risco cadastrado e associado à AE selecionada.")
            if create_form.cleaned_data["register_another"]:
                return _next_risk_registration(request, registered_risks, risk)
            return redirect("risk_overview")
    else:
        initial = {"action": registered_risks[-1].action_id, "activity": registered_risks[-1].activity_id} if registered_risks else {}
        create_form = RiskCreateForm(actions=creatable_actions, initial=initial)
    activities_by_action = {}
    for activity in create_form.fields["activity"].queryset.select_related("action_plan"):
        activities_by_action.setdefault(activity.action_plan.action_id, []).append([activity.id, activity.title])
    risks = Risk.objects.filter(action__in=view_scope_actions(StrategicAction.objects.all(), request.user)).select_related(
        "action",
        "action__artifact",
        "action__artifact__plan",
        "action__coordinating_unit",
        "activity",
        "owner",
    ).prefetch_related("treatments")

    selected_plan = request.GET.get("plan", "")
    selected_unit = selected_unit_for_request(request)
    selected_status = request.GET.get("status", "")
    if selected_plan.isdigit():
        risks = risks.filter(action__artifact__plan_id=selected_plan)
    if selected_unit.isdigit():
        risks = risks.filter(action__coordinating_unit_id=selected_unit)
    if selected_status in Risk.Status.values:
        risks = risks.filter(status=selected_status)

    if request.GET.get("action_status") in StrategicAction.Status.values:
        risks = risks.filter(action__status=request.GET["action_status"])
    if request.GET.get("level") == "priority":
        risks = [risk for risk in risks if risk.level >= 15]
    else:
        risks = list(risks)

    risks.sort(key=lambda risk: (risk.action.artifact.code, risk.action.code, risk.title))
    return render(
        request,
        "core/risk_overview.html",
        {
            "risks": risks,
            "create_form": create_form,
            "registered_risks": registered_risks,
            "registered_risk_ids": ",".join(str(item.pk) for item in registered_risks),
            "activities_by_action": activities_by_action,
            "has_creatable_actions": can_add_risk and creatable_actions.exists(),
            "can_add_risk": can_add_risk,
            "plans": plans,
            "units": units,
            "risk_status_choices": Risk.Status.choices,
            "selected_plan": selected_plan,
            "selected_unit": selected_unit,
            "selected_status": selected_status,
            "critical_count": sum(risk.level >= 15 for risk in risks),
            "materialized_count": sum(risk.status == Risk.Status.MATERIALIZED for risk in risks),
            "monitoring_count": sum(risk.status == Risk.Status.MONITORING for risk in risks),
        },
    )


def _sync_action_progress(action, action_plan):
    activities = list(action_plan.activities.all())
    if not activities:
        action.progress = 0
        if action.status not in [StrategicAction.Status.BLOCKED, StrategicAction.Status.SUSPENDED]:
            action.status = StrategicAction.Status.NOT_STARTED
        action.save(update_fields=["progress", "status"])
        return
    total_progress = sum((activity.weight * activity.progress / 100 for activity in activities), 0)
    action.progress = total_progress
    total_weight = sum((activity.weight for activity in activities), 0)
    if total_weight == 100 and all(
        activity.status == StrategicAction.Status.COMPLETED and activity.progress == 100 for activity in activities
    ):
        action.status = StrategicAction.Status.COMPLETED
    elif action.status not in [StrategicAction.Status.BLOCKED, StrategicAction.Status.SUSPENDED]:
        action.status = StrategicAction.Status.IN_PROGRESS if any(activity.progress > 0 for activity in activities) else StrategicAction.Status.NOT_STARTED
    action.save(update_fields=["progress", "status"])


def _sync_activity_status(activity):
    if activity.progress == 100 and activity.evidences.exclude(attachment="").exists():
        status = StrategicAction.Status.COMPLETED
    elif activity.progress == 0:
        status = StrategicAction.Status.NOT_STARTED
    elif activity.end_date and activity.end_date < timezone.localdate():
        status = StrategicAction.Status.DELAYED
    elif activity.progress > 0:
        status = StrategicAction.Status.IN_PROGRESS
    else:
        status = StrategicAction.Status.NOT_STARTED
    if activity.status != status:
        activity.status = status
        activity.save(update_fields=["status"])


def _rebalance_activity_weights(action_plan, new_weight):
    activities = list(action_plan.activities.exclude(weight__isnull=True).order_by("position", "pk"))
    previous = [activity for activity in activities if activity.pk != new_weight.pk]
    previous_total = sum((activity.weight for activity in previous), Decimal("0"))
    if previous_total + new_weight.weight <= Decimal("100") or not previous_total:
        return False
    available = Decimal("100") - new_weight.weight
    assigned = Decimal("0")
    for index, activity in enumerate(previous):
        if index == len(previous) - 1:
            activity.weight = available - assigned
        else:
            activity.weight = (available * activity.weight / previous_total).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            assigned += activity.weight
        activity.save(update_fields=["weight"])
    return True


def _create_activity_risk(form, action, activity, user):
    risk = form.save(commit=False)
    risk.action = action
    risk.activity = activity
    risk.save()
    RiskAssessment.objects.create(
        risk=risk,
        assessment_type=RiskAssessment.AssessmentType.CURRENT,
        probability=risk.probability,
        impact=risk.impact,
        author=user,
    )
    if risk.treatment:
        treatment_codes = {
            "Aceitar": RiskTreatment.Decision.ACCEPT,
            "Mitigar": RiskTreatment.Decision.MITIGATE,
            "Evitar": RiskTreatment.Decision.AVOID,
            "Transferir": RiskTreatment.Decision.TRANSFER,
        }
        RiskTreatment.objects.create(
            risk=risk,
            decision=treatment_codes[risk.treatment],
            responsible=risk.owner,
            preventive_measure=risk.preventive_measure,
            contingency_measure=risk.contingency_measure,
            created_by=user,
        )
    return risk


@login_required
@permission_required("core.view_actionplan", raise_exception=True)
def action_plan_detail(request, action_id):
    action = get_object_or_404(
        (view_scope_actions if request.method == "GET" else scope_actions)(
            StrategicAction.objects.select_related("artifact", "artifact__plan", "coordinating_unit"), request.user
        ),
        pk=action_id,
    )
    request.read_only_other_unit = not scope_actions(StrategicAction.objects.all(), request.user).filter(pk=action.id).exists()
    try:
        action_plan = action.action_plan
    except ActionPlan.DoesNotExist:
        action_plan = None

    if request.method == "POST" and request.POST.get("operation") == "start_plan":
        _require_permission(request.user, "add_actionplan")
        action_plan = ActionPlan.objects.create(action=action, manager=request.user)
        messages.success(request, "Plano de ação iniciado. Agora você pode cadastrar as atividades e tarefas.")
        return redirect("action_plan_detail", action_id=action.id)

    form = None
    activity_risk_formset = ActivityPlanningRiskFormSet(prefix="activity-risks") if request.user.has_perm("core.add_risk") else None
    if action_plan:
        if request.method == "POST" and request.POST.get("operation") == "add_activity":
            _require_permission(request.user, "add_activity")
            has_risk_data = any(key.startswith("activity-risks-") for key in request.POST)
            risks_valid = True
            if has_risk_data:
                _require_permission(request.user, "add_risk")
                activity_risk_formset = ActivityPlanningRiskFormSet(request.POST, prefix="activity-risks")
                risks_valid = activity_risk_formset.is_valid()
            form = ActivityForm(request.POST, action_plan=action_plan)
            if form.is_valid():
                current_total = action_plan.activities.aggregate(total=Sum("weight"))["total"] or Decimal("0")
                if current_total + form.cleaned_data["weight"] > Decimal("100") and request.POST.get("confirm_rebalance") != "1":
                    form.add_error(
                        "weight",
                        "O total ultrapassaria 100%. Confirme a redistribuição dos pesos ou informe um peso menor.",
                    )
            if form.is_valid() and risks_valid:
                with transaction.atomic():
                    activity = form.save(commit=False)
                    activity.action_plan = action_plan
                    activity.position = (action_plan.activities.aggregate(last_position=Max("position"))["last_position"] or 0) + 1
                    activity.save()
                    rebalanced = _rebalance_activity_weights(action_plan, activity)
                    _sync_action_progress(action, action_plan)
                    if has_risk_data:
                        for risk_form in activity_risk_formset:
                            if risk_form.cleaned_data and not risk_form.cleaned_data.get("DELETE"):
                                _save_new_risk(request.user, risk_form, action, activity=activity)
                if rebalanced:
                    messages.success(request, "Atividade incluída. Os pesos anteriores foram redistribuídos para totalizar 100%.")
                else:
                    messages.success(request, "Atividade incluída no plano de ação.")
                return redirect("action_plan_detail", action_id=action.id)
        else:
            form = ActivityForm(action_plan=action_plan)

    activities = action_plan.activities.select_related("executor", "financial_responsible_unit").all() if action_plan else []
    allocated_weight = sum((activity.weight for activity in activities), 0)
    context = {
        "action": action,
        "action_plan": action_plan,
        "activities": activities,
        "form": form,
        "activity_risk_formset": activity_risk_formset,
        "allocated_weight": allocated_weight,
        "remaining_weight": 100 - allocated_weight,
        "can_edit_plan": bool(action_plan) and not request.read_only_other_unit and (request.user.has_perm("core.change_actionplan") or request.user.has_perm("core.change_strategicaction")),
        "today": timezone.localdate(),
        **_action_indicators_summary(action),
    }
    return render(request, "core/action_plan_detail.html", context)


@login_required
@permission_required("core.view_actionplan", raise_exception=True)
def action_plan_edit(request, action_id):
    action = get_object_or_404(
        scope_actions(StrategicAction.objects.select_related("artifact", "coordinating_unit"), request.user),
        pk=action_id,
    )
    action_plan = get_object_or_404(ActionPlan, action=action)
    can_edit_action = request.user.has_perm("core.change_strategicaction")
    can_edit_manager = request.user.has_perm("core.change_actionplan")
    if not can_edit_action and not can_edit_manager:
        raise PermissionDenied
    data = request.POST if request.method == "POST" else None
    action_form = ActionPlanExecutionForm(data, instance=action, prefix="action") if can_edit_action else None
    manager_form = ActionPlanManagerForm(data, instance=action_plan, prefix="plan") if can_edit_manager else None
    if request.method == "POST":
        action_valid = action_form.is_valid() if action_form is not None else True
        manager_valid = manager_form.is_valid() if manager_form is not None else True
        if action_valid and manager_valid:
            with transaction.atomic():
                if action_form is not None:
                    action_form.save()
                if manager_form is not None:
                    manager_form.save()
            messages.success(request, "Informações do plano de ação atualizadas.")
            return redirect("action_plan_detail", action_id=action.pk)
    return render(request, "core/action_plan_form.html", {
        "action": action, "action_plan": action_plan,
        "action_form": action_form, "manager_form": manager_form,
    })


def _action_indicators_summary(action):
    objective = action.artifact
    while objective and objective.artifact_type != PlanArtifact.ArtifactType.OBJECTIVE:
        objective = objective.parent
    query = f"?plan={action.artifact.plan_id}&unit={action.coordinating_unit_id}"
    if objective:
        query += f"&objective={objective.id}"
    return {
        "targets_url": f"{reverse('target_overview')}{query}",
        "indicators_url": f"{reverse('indicator_overview')}{query}",
        "objective_target_count": objective.targets.filter(Q(action__coordinating_unit_id=action.coordinating_unit_id) | Q(action__isnull=True, indicators__responsible_unit_id=action.coordinating_unit_id) | Q(action__isnull=True, indicators__responsible_units__id=action.coordinating_unit_id)).distinct().count() if objective else 0,
        "objective_indicator_count": objective.indicators.filter(Q(responsible_unit_id=action.coordinating_unit_id) | Q(responsible_units__id=action.coordinating_unit_id)).distinct().count() if objective else 0,
    }


def _normalize(text):
    return "".join(
        char for char in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(char) != "Mn"
    )


def _suggest_units(query, limit=8):
    """Setores cadastrados mais próximos do texto digitado (contém o texto ou grafia parecida)."""
    query = _normalize(query.strip())
    if not query:
        return []
    scored = []
    for unit in OrganizationalUnit.objects.order_by("name"):
        candidates = [_normalize(unit.name)] + ([_normalize(unit.acronym)] if unit.acronym else [])
        if any(candidate.startswith(query) for candidate in candidates):
            score = 2
        elif any(query in candidate for candidate in candidates):
            score = 1.5
        else:
            score = max(SequenceMatcher(None, query, candidate).ratio() for candidate in candidates)
            if score < 0.6:
                continue
        scored.append((score, unit))
    scored.sort(key=lambda item: -item[0])
    return [{"name": unit.name, "acronym": unit.acronym} for _, unit in scored[:limit]]


@login_required
@permission_required("auth.add_user", raise_exception=True)
def unit_suggestions(request):
    return JsonResponse({"results": _suggest_units(request.GET.get("q", ""))})


@login_required
@permission_required("auth.view_user", raise_exception=True)
def user_list(request):
    users = (
        get_user_model()
        .objects.select_related("profile__unit")
        .prefetch_related("groups")
        .order_by("first_name", "last_name", "username")
    )
    return render(request, "core/user_list.html", {"users": users})


@login_required
@permission_required("auth.add_user", raise_exception=True)
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"Usuário {user.get_full_name()} cadastrado.")
        return redirect("user_list")
    return render(request, "core/user_form.html", {"form": form, "has_groups": Group.objects.exists()})


@login_required
@permission_required("auth.change_user", raise_exception=True)
def user_edit(request, user_id):
    user = get_object_or_404(get_user_model(), pk=user_id)
    form = UserCreateForm(request.POST or None, user=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Usuário {user.get_full_name() or user.username} atualizado.")
        return redirect("user_list")
    return render(request, "core/user_form.html", {"form": form, "edited_user": user, "has_groups": Group.objects.exists()})


@login_required
def profile_edit(request):
    form = ProfileForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Seus dados foram atualizados.")
        return redirect("profile_edit")
    return render(request, "core/profile_form.html", {"form": form})


@login_required
@permission_required("auth.delete_user", raise_exception=True)
def user_delete(request, user_id):
    user = get_object_or_404(get_user_model(), pk=user_id)
    if user.pk == request.user.pk:
        messages.error(request, "Você não pode excluir o próprio usuário.")
        return redirect("user_list")
    if request.method == "POST":
        name = user.get_full_name() or user.username
        try:
            user.delete()
        except ProtectedError:
            messages.error(
                request,
                f"{name} possui atividades, riscos ou registros vinculados e não pode ser excluído. Desative o usuário na edição.",
            )
        else:
            messages.success(request, f"Usuário {name} excluído.")
        return redirect("user_list")
    return render(request, "core/user_confirm_delete.html", {"edited_user": user})


@login_required
@permission_required("auth.view_group", raise_exception=True)
def group_list(request):
    groups = Group.objects.annotate(user_total=Count("user", distinct=True), permission_total=Count("permissions", distinct=True)).order_by("name")
    return render(request, "core/group_list.html", {"groups": groups})


def _group_form(request, group=None):
    modules = permission_modules()
    allowed = {permission["id"] for module in modules for entity in module["entities"] for permission in entity["permissions"]}
    selected = set(group.permissions.values_list("id", flat=True)) & allowed if group else set()
    form = GroupForm(request.POST or None, group=group)
    if request.method == "POST":
        selected = {int(value) for value in request.POST.getlist("permissions") if value.isdigit()} & allowed
        if form.is_valid():
            if group is None:
                group = Group.objects.create(name=form.cleaned_data["name"])
                action = "cadastrado"
            else:
                group.name = form.cleaned_data["name"]
                group.save()
                action = "atualizado"
            group.permissions.set(selected)
            messages.success(request, f"Perfil {group.name} {action} com {len(selected)} permiss{'ão' if len(selected) == 1 else 'ões'}.")
            return redirect("group_list")
    return render(request, "core/group_form.html", {"form": form, "modules": modules, "selected": selected, "group": group})


@login_required
@permission_required("auth.add_group", raise_exception=True)
def group_create(request):
    return _group_form(request)


@login_required
@permission_required("auth.change_group", raise_exception=True)
def group_edit(request, group_id):
    return _group_form(request, get_object_or_404(Group, pk=group_id))


@login_required
@permission_required("auth.delete_group", raise_exception=True)
def group_delete(request, group_id):
    group = get_object_or_404(Group.objects.annotate(user_total=Count("user")), pk=group_id)
    if request.method == "POST":
        name = group.name
        group.delete()
        messages.success(request, f"Perfil {name} excluído.")
        return redirect("group_list")
    return render(request, "core/group_confirm_delete.html", {"group": group})


def _get_activity_for_action(user, action_id, activity_id, for_view=False):
    return get_object_or_404(
        Activity.objects.filter(
            action_plan__action__in=scope_actions(StrategicAction.objects.all(), user, for_view=for_view)
        ).select_related("action_plan", "action_plan__action"),
        pk=activity_id,
        action_plan__action_id=action_id,
    )


@login_required
@permission_required("core.change_activity", raise_exception=True)
def activity_edit(request, action_id, activity_id):
    activity = _get_activity_for_action(request.user, action_id, activity_id)
    action = activity.action_plan.action
    if request.method == "POST":
        form = ActivityForm(request.POST, instance=activity, action_plan=activity.action_plan)
        if form.is_valid():
            form.save()
            _sync_action_progress(action, activity.action_plan)
            messages.success(request, "Atividade atualizada.")
            return redirect("action_plan_detail", action_id=action.id)
    else:
        form = ActivityForm(instance=activity, action_plan=activity.action_plan)
    return render(request, "core/activity_form.html", {"activity": activity, "action": action, "form": form})


@login_required
@permission_required("core.view_activityevidence", raise_exception=True)
def evidence_file(request, action_id, activity_id, evidence_id):
    activity = _get_activity_for_action(request.user, action_id, activity_id, for_view=True)
    evidence = get_object_or_404(activity.evidences, pk=evidence_id)
    try:
        if not evidence.attachment:
            raise FileNotFoundError
        file = evidence.attachment.storage.open(evidence.attachment.name, "rb")
    except FileNotFoundError:
        messages.error(request, "O arquivo desta evidência não está disponível no servidor. Restaure o arquivo original ou anexe-o novamente.")
        return redirect(reverse("activity_follow_up", args=[action_id, activity_id]) + "#evidencias")
    return FileResponse(file, filename=evidence.attachment.name.rsplit("/", 1)[-1])


@login_required
@permission_required("core.view_activity", raise_exception=True)
@transaction.atomic
def activity_follow_up(request, action_id, activity_id):
    activity = _get_activity_for_action(request.user, action_id, activity_id, for_view=request.method == "GET")
    action = activity.action_plan.action
    registered_risks = [item for item in _registered_risks(request, StrategicAction.objects.filter(pk=action.pk)) if item.activity_id == activity.pk]
    request.read_only_other_unit = not scope_actions(StrategicAction.objects.all(), request.user).filter(pk=action.id).exists()
    operation = request.POST.get("operation") if request.method == "POST" else ""
    follow_up_permissions = {
        "update_progress": "change_activity",
        "add_evidence": "add_activityevidence",
        "add_blocker": "add_activityblocker",
        "add_risk": "add_risk",
    }
    if operation in follow_up_permissions:
        _require_permission(request.user, follow_up_permissions[operation])
    can_view = {
        "evidences": request.user.has_perm("core.view_activityevidence"),
        "blockers": request.user.has_perm("core.view_activityblocker"),
        "risks": request.user.has_perm("core.view_risk"),
    }

    progress_form = ActivityProgressForm(instance=activity, prefix="progress")
    editing_evidence = None
    editing_blocker = None
    edit_evidence_form = None
    edit_blocker_form = None
    evidence_id = request.POST.get("evidence_id") if operation == "edit_evidence" else request.GET.get("editar_evidencia")
    blocker_id = request.POST.get("blocker_id") if operation == "edit_blocker" else request.GET.get("editar_impedimento")
    if operation == "edit_evidence" or evidence_id:
        _require_permission(request.user, "view_activityevidence")
        _require_permission(request.user, "change_activityevidence")
        editing_evidence = get_object_or_404(activity.evidences, pk=evidence_id)
        edit_evidence_form = ActivityEvidenceForm(
            request.POST if operation == "edit_evidence" else None,
            request.FILES if operation == "edit_evidence" else None,
            instance=editing_evidence, prefix="evidence-edit",
        )
        if operation == "edit_evidence" and edit_evidence_form.is_valid():
            edit_evidence_form.save()
            activity.progress = Decimal("100")
            activity.status = StrategicAction.Status.COMPLETED
            activity.save(update_fields=["progress", "status"])
            _sync_action_progress(action, activity.action_plan)
            messages.success(request, "Evidência atualizada.")
            return redirect(reverse("activity_follow_up", args=[action.pk, activity.pk]) + "#evidencias")
    if operation == "edit_blocker" or blocker_id:
        _require_permission(request.user, "view_activityblocker")
        _require_permission(request.user, "change_activityblocker")
        editing_blocker = get_object_or_404(activity.blockers, pk=blocker_id)
        edit_blocker_form = ActivityBlockerForm(
            request.POST if operation == "edit_blocker" else None,
            instance=editing_blocker, prefix="blocker-edit",
        )
        if operation == "edit_blocker" and edit_blocker_form.is_valid():
            edit_blocker_form.save()
            _sync_action_progress(action, activity.action_plan)
            messages.success(request, "Impedimento atualizado.")
            return redirect(reverse("activity_follow_up", args=[action.pk, activity.pk]) + "#impedimentos")

    evidence_form = ActivityEvidenceForm(prefix="evidence", initial={"title": activity.expected_delivery})
    blocker_form = ActivityBlockerForm(prefix="blocker")
    risk_form = ActivityRiskForm(prefix="risk")
    selectable_risks = action.risks.filter(activity=activity).order_by("title") if can_view["risks"] else Risk.objects.none()
    risk_report_form = ActivityRiskReportForm(risks=selectable_risks, can_create=request.user.has_perm("core.add_risk"), prefix="risk-report")
    unforeseen_form = UnforeseenActivityRiskForm(prefix="unforeseen")
    occurrence_form = RiskMaterializationForm(action=action, prefix="occurrence")

    if operation == "report_risk":
        _require_permission(request.user, "view_risk")
        risk_report_form = ActivityRiskReportForm(request.POST, risks=selectable_risks, can_create=request.user.has_perm("core.add_risk"), prefix="risk-report")
        if risk_report_form.is_valid():
            selected_risk = risk_report_form.cleaned_data["risk"]
            materialized = risk_report_form.cleaned_data["materialized"] == "SIM"
            _require_permission(request.user, "change_risk" if selected_risk else "add_risk")
            valid = True
            current_occurrence = selected_risk.materializations.first() if selected_risk else None
            save_occurrence = materialized and (current_occurrence is None or risk_report_form.cleaned_data["edit_materialization"])
            if selected_risk is None:
                unforeseen_form = UnforeseenActivityRiskForm(request.POST, prefix="unforeseen")
                valid = unforeseen_form.is_valid()
            if save_occurrence:
                _require_permission(request.user, "change_riskmaterialization" if current_occurrence else "add_riskmaterialization")
                if current_occurrence:
                    _require_permission(request.user, "view_riskmaterialization")
                occurrence_form = RiskMaterializationForm(request.POST, request.FILES, instance=current_occurrence, action=action, prefix="occurrence")
                valid = occurrence_form.is_valid() and valid
                treatment = selected_risk.treatments.first() if selected_risk else None
                if valid and treatment and (treatment.preventive_measure or treatment.contingency_measure):
                    measure_source = occurrence_form.cleaned_data.get("measure_source")
                    if not measure_source:
                        occurrence_form.add_error("measure_source", "Informe se a providência prevista foi adotada ou se houve uma nova.")
                        valid = False
                    elif measure_source == RiskMaterialization.MeasureSource.NEW and not occurrence_form.cleaned_data.get("actions_taken", "").strip():
                        occurrence_form.add_error("actions_taken", "Descreva a nova providência adotada.")
                        valid = False
            if materialized and (selected_risk is None or selected_risk.status != Risk.Status.MATERIALIZED or action.status == StrategicAction.Status.NOT_STARTED) and not action.can_materialize_risks:
                risk_report_form.add_error("materialized", "Só é possível materializar um risco com plano de ação em andamento.")
                valid = False
            if valid:
                if selected_risk is None:
                    selected_risk = unforeseen_form.save(commit=False)
                    selected_risk.action = action
                    selected_risk.activity = activity
                    selected_risk.owner = request.user
                    selected_risk.is_unforeseen = True
                    selected_risk.save()
                    RiskAssessment.objects.create(risk=selected_risk, probability=selected_risk.probability, impact=selected_risk.impact, author=request.user)
                    if selected_risk.treatment:
                        decisions = {"Aceitar": "ACEITAR", "Mitigar": "MITIGAR", "Evitar": "EVITAR", "Transferir": "TRANSFERIR"}
                        RiskTreatment.objects.create(risk=selected_risk, decision=decisions[selected_risk.treatment], responsible=unforeseen_form.cleaned_data["treatment_responsible"], preventive_measure=selected_risk.preventive_measure, contingency_measure=selected_risk.contingency_measure, created_by=request.user)
                        selected_risk.status = Risk.Status.IN_TREATMENT
                else:
                    selected_risk = Risk.objects.select_for_update().get(pk=selected_risk.pk)
                    selected_risk.activity = activity
                if save_occurrence:
                    occurrence = occurrence_form.save(commit=False)
                    occurrence.risk = selected_risk
                    if not occurrence.pk:
                        occurrence.recorded_by = request.user
                    occurrence.save()
                if materialized:
                    selected_risk.status = Risk.Status.MATERIALIZED
                selected_risk.save()
                messages.success(request, "Risco registrado no acompanhamento da atividade.")
                if unforeseen_form.is_bound and unforeseen_form.cleaned_data.get("register_another"):
                    response = _next_risk_registration(request, registered_risks, selected_risk)
                    response["Location"] += "#riscos"
                    return response
                return redirect(reverse("activity_follow_up", args=[action.id, activity.id]) + "#riscos")


    if operation == "update_progress":
        progress_form = ActivityProgressForm(request.POST, instance=activity, prefix="progress")
        if progress_form.is_valid():
            progress_form.save()
            _sync_activity_status(activity)
            _sync_action_progress(action, activity.action_plan)
            messages.success(request, "Execução da atividade atualizada.")
            return redirect(reverse("activity_follow_up", args=[action.id, activity.id]) + "#inicio")
    elif operation == "add_evidence":
        evidence_form = ActivityEvidenceForm(request.POST, request.FILES, prefix="evidence")
        if evidence_form.is_valid():
            evidence = evidence_form.save(commit=False)
            evidence.activity = activity
            evidence.created_by = request.user
            evidence.save()
            activity.progress = Decimal("100")
            activity.status = StrategicAction.Status.COMPLETED
            activity.save(update_fields=["progress", "status"])
            _sync_action_progress(action, activity.action_plan)
            messages.success(request, "Evidência registrada. Atividade concluída com 100% de execução.")
            return redirect("activity_follow_up", action_id=action.id, activity_id=activity.id)
    elif operation == "add_blocker":
        blocker_form = ActivityBlockerForm(request.POST, prefix="blocker")
        if blocker_form.is_valid():
            blocker = blocker_form.save(commit=False)
            blocker.activity = activity
            blocker.created_by = request.user
            blocker.save()
            _sync_action_progress(action, activity.action_plan)
            messages.success(request, "Impedimento registrado na atividade.")
            return redirect("activity_follow_up", action_id=action.id, activity_id=activity.id)
    elif operation == "add_risk":
        risk_form = ActivityRiskForm(request.POST, prefix="risk")
        valid = risk_form.is_valid()
        if valid and risk_form.cleaned_data["status"] == Risk.Status.MATERIALIZED and not action.can_materialize_risks:
            risk_form.add_error("status", "Só é possível materializar um risco com plano de ação em andamento.")
            valid = False
        if valid:
            risk = risk_form.save(commit=False)
            risk.action = action
            risk.activity = activity
            risk.owner = request.user
            risk.save()
            RiskAssessment.objects.create(
                risk=risk,
                assessment_type=RiskAssessment.AssessmentType.CURRENT,
                probability=risk.probability,
                impact=risk.impact,
                author=request.user,
            )
            if risk.treatment:
                treatment_codes = {
                    "Aceitar": RiskTreatment.Decision.ACCEPT,
                    "Mitigar": RiskTreatment.Decision.MITIGATE,
                    "Evitar": RiskTreatment.Decision.AVOID,
                    "Transferir": RiskTreatment.Decision.TRANSFER,
                }
                RiskTreatment.objects.create(
                    risk=risk,
                    decision=treatment_codes[risk.treatment],
                    responsible=risk_form.cleaned_data["treatment_responsible"],
                    preventive_measure=risk.preventive_measure,
                    contingency_measure=risk.contingency_measure,
                    created_by=request.user,
                )
            messages.success(request, "Risco registrado na atividade.")
            return redirect("activity_follow_up", action_id=action.id, activity_id=activity.id)

    risk_prefill = {}
    can_view_occurrence = request.user.has_perm("core.view_riskmaterialization")
    can_edit_occurrence = can_view_occurrence and request.user.has_perm("core.change_riskmaterialization") and not request.read_only_other_unit
    for item in selectable_risks.prefetch_related("materializations", "treatments"):
        latest = next(iter(item.materializations.all()), None)
        treatment = next(iter(item.treatments.all()), None)
        risk_prefill[str(item.id)] = {
            "planned_measure": treatment.preventive_measure or treatment.contingency_measure if treatment else "",
            "materialized": "SIM" if latest or item.status == Risk.Status.MATERIALIZED else "NAO",
            "has_occurrence": latest is not None,
            "can_view": can_view_occurrence,
            "can_edit": can_edit_occurrence,
            "attachment_url": reverse("risk_materialization_file", args=[action.id, item.id, latest.id]) if latest and can_view_occurrence and latest.evidence_attachment else "",
            "occurrence": {
                "occurred_on": latest.occurred_on.isoformat(),
                "description": latest.description,
                "actual_impact": latest.actual_impact,
                "actions_taken": latest.actions_taken,
                "measure_source": latest.measure_source,
                "evidence_reference": latest.evidence_reference,
            } if latest and can_view_occurrence else {},
        }

    evidences = list(activity.evidences.select_related("created_by")) if can_view["evidences"] else []
    for evidence in evidences:
        evidence.attachment_available = bool(evidence.attachment and evidence.attachment.storage.exists(evidence.attachment.name))

    return render(
        request,
        "core/activity_follow_up.html",
        {
            "action": action,
            "activity": activity,
            "progress_form": progress_form,
            "can_view": can_view,
            "evidences": evidences,
            "blockers": activity.blockers.select_related("resolution_owner", "created_by") if can_view["blockers"] else [],
            "risks": activity.risks.select_related("owner").prefetch_related("treatments") if can_view["risks"] else [],
            "evidence_form": evidence_form,
            "editing_evidence": editing_evidence,
            "editing_blocker": editing_blocker,
            "edit_evidence_form": edit_evidence_form,
            "edit_blocker_form": edit_blocker_form,
            "blocker_form": blocker_form,
            "risk_form": risk_form,
            "risk_report_form": risk_report_form,
            "risk_prefill": risk_prefill,
            "unforeseen_form": unforeseen_form,
            "registered_risks": registered_risks,
            "registered_risk_ids": ",".join(str(item.pk) for item in registered_risks),
            "occurrence_form": occurrence_form,
        },
    )


@login_required
def risk_map(request, action_id):
    _require_permission(request.user, "view_risk")
    action = get_object_or_404(
        (view_scope_actions if request.method == "GET" else scope_actions)(
            StrategicAction.objects.select_related("artifact", "artifact__plan", "coordinating_unit"), request.user
        ),
        pk=action_id,
    )
    request.read_only_other_unit = not scope_actions(StrategicAction.objects.all(), request.user).filter(pk=action.id).exists()
    action_plan = get_object_or_404(ActionPlan, action=action)
    registered_risks = _registered_risks(request, StrategicAction.objects.filter(pk=action.pk))
    if request.method == "POST":
        _require_permission(request.user, "add_risk")
        form = RiskIdentificationForm(request.POST, action_plan=action_plan)
        if form.is_valid():
            risk = _save_new_risk(request.user, form, action)
            messages.success(request, "Risco incluído no mapa do plano de ação.")
            if form.cleaned_data["register_another"]:
                return _next_risk_registration(request, registered_risks, risk)
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)
    else:
        initial = {"activity": registered_risks[-1].activity_id} if registered_risks else {}
        form = RiskIdentificationForm(action_plan=action_plan, initial=initial)

    risks = action.risks.select_related("activity", "owner").prefetch_related(
        "assessments", "treatments", "materializations", "acceptances"
    ).order_by("status", "title")
    return render(
        request,
        "core/risk_map.html",
        {
            "action": action,
            "action_plan": action_plan,
            "risks": risks,
            "form": form,
            "registered_risks": registered_risks,
            "registered_risk_ids": ",".join(str(item.pk) for item in registered_risks),
            "can_add_risk": not request.read_only_other_unit and request.user.has_perm("core.add_risk"),
        },
    )


def _get_risk_for_action(user, action_id, risk_id, for_view=False):
    return get_object_or_404(
        Risk.objects.filter(action__in=scope_actions(StrategicAction.objects.all(), user, for_view=for_view)).select_related(
            "action", "activity", "owner"
        ),
        pk=risk_id,
        action_id=action_id,
    )


def _refresh_risk_status(risk):
    if risk.status in (Risk.Status.MATERIALIZED, Risk.Status.CLOSED):
        return
    acceptance = risk.acceptances.first()
    if acceptance:
        risk.status = (Risk.Status.MONITORING if acceptance.decision == RiskAcceptance.Decision.ACCEPTED
                       else Risk.Status.IN_TREATMENT)
    elif risk.treatments.exists():
        risk.status = Risk.Status.IN_TREATMENT
    else:
        risk.status = Risk.Status.IDENTIFIED


@login_required
@permission_required("core.view_riskmaterialization", raise_exception=True)
def risk_materialization_file(request, action_id, risk_id, materialization_id):
    _require_permission(request.user, "view_risk")
    risk = _get_risk_for_action(request.user, action_id, risk_id, for_view=True)
    occurrence = get_object_or_404(risk.materializations, pk=materialization_id)
    try:
        if not occurrence.evidence_attachment:
            raise FileNotFoundError
        file = occurrence.evidence_attachment.storage.open(occurrence.evidence_attachment.name, "rb")
    except FileNotFoundError:
        messages.error(request, "O anexo da evidência do risco não está disponível no servidor.")
        return redirect(reverse("risk_detail", args=[action_id, risk_id]) + "#ocorrencia")
    return FileResponse(file, filename=occurrence.evidence_attachment.name.rsplit("/", 1)[-1])


@login_required
@transaction.atomic
def risk_detail(request, action_id, risk_id):
    _require_permission(request.user, "view_risk")
    risk = _get_risk_for_action(request.user, action_id, risk_id, for_view=request.method == "GET")
    action = risk.action
    request.read_only_other_unit = not scope_actions(StrategicAction.objects.all(), request.user).filter(pk=action.id).exists()
    action_plan = ActionPlan.objects.filter(action=action).first()  # a AE pode ter risco sem plano de ação iniciado
    # Serialize changes to the single acceptance/response for this risk.
    Risk.objects.select_for_update().get(pk=risk.pk)
    current_treatment = risk.treatments.first()
    current_acceptance = risk.acceptances.first()
    operation = request.POST.get("operation") if request.method == "POST" else ""
    if operation in RISK_OPERATION_PERMISSIONS:
        permission = RISK_OPERATION_PERMISSIONS[operation]
        if operation == "add_treatment" and current_treatment:
            permission = "change_risktreatment"
        elif operation == "accept" and current_acceptance:
            permission = "change_riskacceptance"
        _require_permission(request.user, permission)
    if operation == "delete_risk":
        risk.delete()
        messages.success(request, "Risco e registros vinculados excluídos.")
        return redirect("risk_overview")
    if operation == "delete_materialization":
        materialization = get_object_or_404(risk.materializations, pk=request.POST.get("materialization_id"))
        materialization.delete()
        if risk.status == Risk.Status.MATERIALIZED and not risk.materializations.exists():
            risk.status = Risk.Status.IDENTIFIED
            _refresh_risk_status(risk)
            risk.save(update_fields=["status"])
        messages.success(request, "Materialização excluída.")
        return redirect(reverse("risk_detail", args=[action.id, risk.id]) + "#ocorrencia")
    if operation == "delete_assessment":
        assessment = get_object_or_404(risk.assessments, pk=request.POST.get("assessment_id"))
        is_latest = risk.assessments.first().pk == assessment.pk
        assessment.delete()
        remaining = risk.assessments.first()
        if is_latest and remaining:
            risk.probability = remaining.probability
            risk.impact = remaining.impact
            risk.save(update_fields=["probability", "impact"])
        messages.success(request, "Avaliação excluída." if remaining else
                         "Avaliação excluída. Sem histórico, a classificação atual foi mantida.")
        return redirect(reverse("risk_detail", args=[action.id, risk.id]) + "#analise")
    if operation in ("delete_treatment", "delete_acceptance"):
        if operation == "delete_treatment":
            if current_treatment:
                current_treatment.delete()
            risk.treatment = ""
            risk.preventive_measure = ""
            risk.contingency_measure = ""
        elif current_acceptance:
            current_acceptance.delete()
        _refresh_risk_status(risk)
        risk.save()
        messages.success(request, "Resposta excluída." if operation == "delete_treatment" else "Aceite excluído.")
        section = "tratamento" if operation == "delete_treatment" else "alcada"
        return redirect(reverse("risk_detail", args=[action.id, risk.id]) + "#" + section)
    identity_form = RiskIdentityForm(instance=risk, action_plan=action_plan, prefix="identity")
    editing_assessment = None
    assessment_id = request.POST.get("assessment_id") if operation == "edit_assessment" else request.GET.get("editar_avaliacao")
    if assessment_id:
        _require_permission(request.user, "change_riskassessment")
        editing_assessment = get_object_or_404(risk.assessments, pk=assessment_id)
    assessment_form = RiskAssessmentForm(instance=editing_assessment, prefix="assessment")
    timing_form = RiskTimingForm(instance=risk, prefix="timing")
    treatment_form = RiskTreatmentForm(instance=current_treatment, prefix="treatment")
    editing_materialization = None
    materialization_id = request.POST.get("materialization_id") if operation == "edit_materialization" else request.GET.get("editar_materializacao")
    if materialization_id:
        _require_permission(request.user, "change_riskmaterialization")
        editing_materialization = get_object_or_404(risk.materializations, pk=materialization_id)
    materialization_form = RiskMaterializationForm(instance=editing_materialization, action=action, prefix="materialization")
    acceptance_form = RiskAcceptanceForm(instance=current_acceptance, prefix="acceptance")
    remediation_form = RiskRemediationSubmissionForm(prefix="remediation")

    if operation == "update_identity":
        identity_form = RiskIdentityForm(
            request.POST,
            instance=risk,
            action_plan=action_plan,
            prefix="identity",
        )
        if identity_form.is_valid():
            identity_form.save()
            messages.success(request, "Identificação e responsabilidade do risco atualizadas.")
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)
    elif operation == "update_timing":
        timing_form = RiskTimingForm(request.POST, instance=risk, prefix="timing")
        if timing_form.is_valid():
            timing_form.save()
            messages.success(request, "Momento de possível ocorrência atualizado.")
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)
    elif operation in ("add_assessment", "edit_assessment"):
        if operation == "edit_assessment" and editing_assessment is None:
            raise Http404
        assessment_form = RiskAssessmentForm(request.POST, instance=editing_assessment, prefix="assessment")
        valid = assessment_form.is_valid()
        if operation == "add_assessment" and risk.assessments.exists():
            assessment_form.add_error(None, "Este risco já possui avaliação. Use o botão Editar avaliação.")
            valid = False
        if valid:
            assessment = assessment_form.save(commit=False)
            assessment.risk = risk
            assessment.author = request.user
            assessment.save()
            risk.probability = assessment.probability
            risk.impact = assessment.impact
            risk.save(update_fields=["probability", "impact"])
            messages.success(request, "Avaliação atualizada." if editing_assessment else "Avaliação registrada.")
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)
    elif operation == "add_treatment":
        treatment_form = RiskTreatmentForm(request.POST, instance=current_treatment, prefix="treatment")
        if treatment_form.is_valid():
            treatment = treatment_form.save(commit=False)
            treatment.risk = risk
            if not treatment.pk:
                treatment.created_by = request.user
            treatment.save()
            risk.treatment = treatment.decision
            risk.preventive_measure = treatment.preventive_measure
            risk.contingency_measure = treatment.contingency_measure
            _refresh_risk_status(risk)
            risk.save(update_fields=["treatment", "preventive_measure", "contingency_measure", "status"])
            messages.success(request, "Tratamento registrado.")
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)
    elif operation in ("materialize", "edit_materialization"):
        if operation == "edit_materialization" and editing_materialization is None:
            raise Http404
        materialization_form = RiskMaterializationForm(request.POST, request.FILES, instance=editing_materialization, action=action, prefix="materialization")
        if materialization_form.is_valid():
            materialization = materialization_form.save(commit=False)
            materialization.risk = risk
            if not materialization.pk:
                materialization.recorded_by = request.user
            materialization.save()
            risk.status = Risk.Status.MATERIALIZED
            risk.save(update_fields=["status"])
            messages.success(request, "Materialização do risco registrada.")
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)
    elif operation == "accept":
        acceptance_form = RiskAcceptanceForm(request.POST, instance=current_acceptance, prefix="acceptance")
        if acceptance_form.is_valid():
            acceptance = acceptance_form.save(commit=False)
            acceptance.risk = risk
            acceptance.recorded_by = request.user
            acceptance.save()
            if acceptance.decision == RiskAcceptance.Decision.ACCEPTED_WITH_RESERVATIONS:
                risk.status = Risk.Status.IN_TREATMENT
                risk.save(update_fields=["status"])
            elif acceptance.decision == RiskAcceptance.Decision.ACCEPTED:
                if risk.status != Risk.Status.MATERIALIZED:
                    risk.status = Risk.Status.MONITORING
                    risk.save(update_fields=["status"])
            elif risk.status != Risk.Status.MATERIALIZED:
                risk.status = Risk.Status.IN_TREATMENT
                risk.save(update_fields=["status"])
            messages.success(request, "Decisão de aceite registrada.")
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)
    elif operation == "submit_remediation":
        remediation_form = RiskRemediationSubmissionForm(request.POST, prefix="remediation")
        acceptance = get_object_or_404(
            RiskAcceptance,
            pk=request.POST.get("acceptance_id"),
            risk=risk,
            decision=RiskAcceptance.Decision.ACCEPTED_WITH_RESERVATIONS,
        )
        if acceptance.remediation_submissions.exists():
            remediation_form.add_error(None, "Estas diligências já foram reapresentadas para avaliação.")
        elif remediation_form.is_valid():
            submission = remediation_form.save(commit=False)
            submission.acceptance = acceptance
            submission.submitted_by = request.user
            submission.save()
            messages.success(request, "Cumprimento das diligências registrado. O risco está pronto para nova avaliação.")
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)

    # Cada seção só carrega dados quando o usuário pode visualizá-la; as demais ficam vazias.
    user = request.user
    can_view = {
        "assessments": user.has_perm("core.view_riskassessment"),
        "treatments": user.has_perm("core.view_risktreatment"),
        "materializations": user.has_perm("core.view_riskmaterialization"),
        "acceptances": user.has_perm("core.view_riskacceptance"),
    }
    acceptances = RiskAcceptance.objects.none()
    pending_acceptance = None
    if can_view["acceptances"]:
        acceptances = risk.acceptances.select_related(
            "authority", "recorded_by", "remediation_responsible"
        ).prefetch_related("remediation_submissions__submitted_by")
        pending_acceptance = acceptances.filter(
            decision=RiskAcceptance.Decision.ACCEPTED_WITH_RESERVATIONS,
            remediation_submissions__isnull=True,
        ).first()
    return render(
        request,
        "core/risk_detail.html",
        {
            "action": action,
            "risk": risk,
            "can_view": can_view,
            "can_view_remediation": user.has_perm("core.view_riskremediationsubmission"),
            "assessments": risk.assessments.select_related("author") if can_view["assessments"] else [],
            "treatments": risk.treatments.select_related("responsible", "created_by") if can_view["treatments"] else [],
            "current_treatment": current_treatment if can_view["treatments"] else None,
            "has_treatment": current_treatment is not None,
            "has_acceptance": current_acceptance is not None,
            "materializations": risk.materializations.select_related("recorded_by") if can_view["materializations"] else [],
            "acceptances": acceptances,
            "pending_acceptance": pending_acceptance,
            "identity_form": identity_form,
            "assessment_form": assessment_form,
            "editing_assessment": editing_assessment,
            "has_assessment": risk.assessments.exists(),
            "timing_form": timing_form,
            "treatment_form": treatment_form,
            "materialization_form": materialization_form,
            "can_materialize_risk": action.can_materialize_risks,
            "editing_materialization": editing_materialization,
            "acceptance_form": acceptance_form,
            "remediation_form": remediation_form,
        },
    )


@login_required
@permission_required("core.delete_activity", raise_exception=True)
@transaction.atomic
def activity_delete(request, action_id, activity_id):
    activity = _get_activity_for_action(request.user, action_id, activity_id)
    action = activity.action_plan.action
    if request.method == "POST":
        activity.risks.all().delete()
        activity.delete()
        _sync_action_progress(action, action.action_plan)
        messages.success(request, "Atividade excluída do plano de ação.")
        return redirect("action_plan_detail", action_id=action.id)
    return render(request, "core/activity_confirm_delete.html", {"activity": activity, "action": action, "risk_count": activity.risks.count()})


@login_required
@permission_required("core.change_activity", raise_exception=True)
def activity_move(request, action_id, activity_id, direction):
    if request.method != "POST" or direction not in {"acima", "abaixo"}:
        return redirect("action_plan_detail", action_id=action_id)
    activity = _get_activity_for_action(request.user, action_id, activity_id)
    action_plan = activity.action_plan
    activities = list(action_plan.activities.order_by("position", "start_date", "end_date", "id"))
    index = next(index for index, item in enumerate(activities) if item.pk == activity.pk)
    neighbour_index = index - 1 if direction == "acima" else index + 1
    if 0 <= neighbour_index < len(activities):
        neighbour = activities[neighbour_index]
        with transaction.atomic():
            activity.position, neighbour.position = neighbour.position, activity.position
            activity.save(update_fields=["position"])
            neighbour.save(update_fields=["position"])
        messages.success(request, "Ordem da atividade atualizada.")
    return redirect("action_plan_detail", action_id=action_id)
