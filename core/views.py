from decimal import Decimal, InvalidOperation, ROUND_DOWN

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, F, Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    ActivityBlockerForm,
    ActivityEvidenceForm,
    ActivityForm,
    ActivityRiskForm,
    IndicatorMeasurementForm,
    ReportCycleForm,
    ReportValidationForm,
    RiskAcceptanceForm,
    RiskAssessmentForm,
    RiskIdentityForm,
    RiskIdentificationForm,
    RiskMaterializationForm,
    RiskRemediationSubmissionForm,
    RiskTimingForm,
    RiskTreatmentForm,
    SectorReportForm,
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


def _indicator_signal(indicator):
    measurements = list(indicator.measurements.all())
    latest = measurements[0] if measurements else None
    if not latest:
        return {"code": "gray", "label": "Sem aferição", "achievement": None, "measurement": None}
    measured = _decimal_from_measurement(latest.measured_value)
    expected = latest.expected_value
    if measured is None or expected is None:
        return {"code": "gray", "label": "Dado insuficiente", "achievement": None, "measurement": latest}
    if indicator.direction == Indicator.Direction.RANGE:
        return {"code": "gray", "label": "Faixa a configurar", "achievement": None, "measurement": latest}
    if indicator.direction == Indicator.Direction.LOWER_IS_BETTER:
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
        "code": code,
        "label": label,
        "achievement": round(float(achievement), 1),
        "measurement": latest,
    }


@login_required
def dashboard(request):
    plans = Plan.objects.filter(active=True).order_by("acronym")
    units = OrganizationalUnit.objects.select_related("organization").order_by("name")
    actions = StrategicAction.objects.select_related("artifact", "artifact__plan", "coordinating_unit")

    selected_plan = request.GET.get("plan", "")
    selected_unit = request.GET.get("unit", "")
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
    if unit_filter:
        objective_query = objective_query.filter(
            Q(actions__in=actions)
            | Q(planartifact__actions__in=actions)
            | Q(planartifact__planartifact__actions__in=actions)
        ).distinct()

    # Riscos prioritários: apenas altos e críticos do recorte (setor selecionado ou todos os setores).
    risk_alerts = sorted(
        [risk for risk in risks if risk.level >= 10],
        key=lambda risk: (-risk.level, risk.title),
    )[:5]
    context = {
        "plans": plans,
        "units": units,
        "selected_plan": selected_plan,
        "selected_unit": selected_unit,
        "selected_status": selected_status,
        "actions_status_choices": StrategicAction.Status.choices,
        "action_count": action_count,
        "objective_count": objective_query.count(),
        "delayed_count": deadline_alert.count(),
        "blocked_count": actions.filter(status=StrategicAction.Status.BLOCKED).count(),
        "critical_risk_count": sum(1 for risk in risks if risk.level >= 15),
        "progress_average": round(float(progress_average), 1),
        "status_summary": status_summary,
        "recent_actions": actions.annotate(activity_count=Count("action_plan__activities")).order_by(
            F("due_date").asc(nulls_last=True), "code"
        )[:6],
        "can_manage_actions": request.user.is_staff and request.user.has_perm("core.view_strategicaction"),
        "can_add_actions": request.user.is_staff and request.user.has_perm("core.add_strategicaction"),
        "risk_alerts": risk_alerts,
        "unit_filter": unit_filter,
        "today": today,
    }
    return render(request, "core/dashboard.html", context)


@login_required
def pei_overview(request):
    plans = Plan.objects.filter(active=True).order_by("start_date", "acronym")
    selected_plan = request.GET.get("plan", "")
    plan = plans.filter(pk=selected_plan).first() if selected_plan.isdigit() else plans.first()

    if not plan:
        return render(
            request,
            "core/pei_overview.html",
            {"plans": plans, "plan": None, "selected_plan": "", "dimension_groups": []},
        )

    artifacts = list(
        PlanArtifact.objects.filter(plan=plan)
        .select_related("parent", "parent__parent")
        .prefetch_related("targets", "indicators", "critical_success_factors")
        .order_by("id")
    )
    actions = list(
        StrategicAction.objects.filter(artifact__plan=plan)
        .select_related("artifact", "coordinating_unit")
        .prefetch_related("participating_units")
        .order_by("artifact__id", "code")
    )
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
        return {
            "artifact": objective,
            "projects": projects,
            "direct_actions": direct_actions,
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
def indicator_overview(request):
    plans = Plan.objects.filter(active=True).order_by("start_date", "acronym")
    units = OrganizationalUnit.objects.order_by("name")
    selected_plan = request.GET.get("plan", "")
    selected_unit = request.GET.get("unit", "")
    selected_objective = request.GET.get("objective", "")
    selected_status = request.GET.get("status", "")
    plan = plans.filter(pk=selected_plan).first() if selected_plan.isdigit() else plans.first()

    indicators = Indicator.objects.none()
    objectives = PlanArtifact.objects.none()
    if plan:
        objectives = PlanArtifact.objects.filter(
            plan=plan,
            artifact_type=PlanArtifact.ArtifactType.OBJECTIVE,
        ).order_by("code", "title")
        indicators = (
            Indicator.objects.filter(artifacts__plan=plan)
            .select_related("responsible_unit")
            .prefetch_related("artifacts", "artifacts__plan", "targets", "measurements")
            .distinct()
            .order_by("code", "name")
        )
        if selected_unit.isdigit():
            indicators = indicators.filter(responsible_unit_id=selected_unit)
        if selected_objective.isdigit():
            indicators = indicators.filter(artifacts__id=selected_objective)

    indicator_rows = []
    signal_counts = {"green": 0, "yellow": 0, "orange": 0, "red": 0, "gray": 0}
    for indicator in indicators:
        signal = _indicator_signal(indicator)
        signal_counts[signal["code"]] += 1
        indicator_rows.append({"indicator": indicator, "signal": signal})
    if selected_status in signal_counts:
        indicator_rows = [row for row in indicator_rows if row["signal"]["code"] == selected_status]

    return render(
        request,
        "core/indicator_overview.html",
        {
            "plans": plans,
            "units": units,
            "objectives": objectives,
            "plan": plan,
            "selected_plan": str(plan.id) if plan else "",
            "selected_unit": selected_unit,
            "selected_objective": selected_objective,
            "selected_status": selected_status,
            "indicator_rows": indicator_rows,
            "indicator_count": sum(signal_counts.values()),
            "updated_count": sum(value for key, value in signal_counts.items() if key != "gray"),
            "attention_count": signal_counts["yellow"] + signal_counts["orange"] + signal_counts["red"],
            "signal_counts": signal_counts,
        },
    )


@login_required
def indicator_detail(request, indicator_id):
    indicator = get_object_or_404(
        Indicator.objects.select_related("responsible_unit").prefetch_related(
            "artifacts",
            "artifacts__plan",
            "targets",
            "measurements",
            "measurements__recorded_by",
        ),
        pk=indicator_id,
    )
    if request.method == "POST":
        form = IndicatorMeasurementForm(request.POST, request.FILES)
        if form.is_valid():
            measurement = form.save(commit=False)
            measurement.indicator = indicator
            measurement.recorded_by = request.user
            measurement.save()
            messages.success(request, "Aferição registrada e semáforo atualizado.")
            return redirect("indicator_detail", indicator_id=indicator.id)
    else:
        form = IndicatorMeasurementForm()
    signal = _indicator_signal(indicator)
    return render(
        request,
        "core/indicator_detail.html",
        {"indicator": indicator, "signal": signal, "measurement_form": form},
    )


def _sector_report_content(report):
    actions = list(
        StrategicAction.objects.filter(artifact__plan=report.cycle.plan, coordinating_unit=report.unit)
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
        Indicator.objects.filter(artifacts__plan=report.cycle.plan, responsible_unit=report.unit)
        .prefetch_related("measurements")
        .distinct()
        .order_by("code")
    )
    indicator_rows = [{"indicator": item, "signal": _indicator_signal(item)} for item in indicators]
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
def report_cycle_overview(request):
    if request.method == "POST":
        form = ReportCycleForm(request.POST)
        if form.is_valid():
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
    cycle_rows = []
    for cycle in cycles:
        reports = list(cycle.sector_reports.all())
        cycle_rows.append(
            {
                "cycle": cycle,
                "report_count": len(reports),
                "submitted_count": sum(item.status != SectorReport.Status.DRAFT for item in reports),
                "approved_count": sum(item.status in [SectorReport.Status.APPROVED, SectorReport.Status.CONSOLIDATED] for item in reports),
            }
        )
    return render(request, "core/report_cycle_overview.html", {"cycle_rows": cycle_rows, "cycle_form": form})


@login_required
def report_cycle_detail(request, cycle_id):
    cycle = get_object_or_404(
        ReportCycle.objects.select_related("plan", "created_by").prefetch_related("sector_reports__unit", "sector_reports__validator"),
        pk=cycle_id,
    )
    reports = list(cycle.sector_reports.all())
    if request.method == "POST":
        operation = request.POST.get("operation")
        if operation == "consolidate":
            if reports and all(item.status == SectorReport.Status.APPROVED for item in reports):
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
            "cycle": cycle,
            "reports": reports,
            "approved_count": sum(item.status in [SectorReport.Status.APPROVED, SectorReport.Status.CONSOLIDATED] for item in reports),
            "submitted_count": sum(item.status != SectorReport.Status.DRAFT for item in reports),
            "returned_count": sum(item.status == SectorReport.Status.RETURNED for item in reports),
        },
    )


@login_required
def sector_report_detail(request, cycle_id, report_id):
    report = get_object_or_404(
        SectorReport.objects.select_related("cycle", "cycle__plan", "unit", "prepared_by", "validator"),
        pk=report_id,
        cycle_id=cycle_id,
    )
    content = _sector_report_content(report)
    report_form = SectorReportForm(instance=report, current_user=request.user)
    validation_form = ReportValidationForm()
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
    return render(
        request,
        "core/sector_report_detail.html",
        {"report": report, "content": content, "report_form": report_form, "validation_form": validation_form},
    )


@login_required
def action_plan_list(request):
    plans = Plan.objects.filter(active=True).order_by("acronym")
    units = OrganizationalUnit.objects.order_by("name")
    actions = StrategicAction.objects.select_related("artifact", "artifact__plan", "coordinating_unit").annotate(
        activity_count=Count("action_plan__activities"),
        allocated_weight=Sum("action_plan__activities__weight"),
        activity_progress=Avg("action_plan__activities__progress"),
    )
    selected_plan = request.GET.get("plan", "")
    selected_unit = request.GET.get("unit", "")
    selected_status = request.GET.get("status", "")
    if selected_plan.isdigit():
        actions = actions.filter(artifact__plan_id=selected_plan)
    if selected_unit.isdigit():
        actions = actions.filter(coordinating_unit_id=selected_unit)
    if selected_status in StrategicAction.Status.values:
        actions = actions.filter(status=selected_status)

    return render(
        request,
        "core/action_plan_list.html",
        {
            "actions": actions.order_by("artifact__code", "code"),
            "plans": plans,
            "units": units,
            "actions_status_choices": StrategicAction.Status.choices,
            "selected_plan": selected_plan,
            "selected_unit": selected_unit,
            "selected_status": selected_status,
        },
    )


@login_required
def risk_overview(request):
    plans = Plan.objects.filter(active=True).order_by("acronym")
    units = OrganizationalUnit.objects.order_by("name")
    risks = Risk.objects.select_related(
        "action",
        "action__artifact",
        "action__artifact__plan",
        "action__coordinating_unit",
        "activity",
        "owner",
    ).prefetch_related("treatments")

    selected_plan = request.GET.get("plan", "")
    selected_unit = request.GET.get("unit", "")
    selected_status = request.GET.get("status", "")
    if selected_plan.isdigit():
        risks = risks.filter(action__artifact__plan_id=selected_plan)
    if selected_unit.isdigit():
        risks = risks.filter(action__coordinating_unit_id=selected_unit)
    if selected_status in Risk.Status.values:
        risks = risks.filter(status=selected_status)

    risks = list(risks.order_by("action__artifact__code", "action__code", "title"))
    return render(
        request,
        "core/risk_overview.html",
        {
            "risks": risks,
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
        return
    total_progress = sum((activity.weight * activity.progress / 100 for activity in activities), 0)
    action.progress = total_progress
    total_weight = sum((activity.weight for activity in activities), 0)
    if total_weight == 100 and all(
        activity.status == StrategicAction.Status.COMPLETED and activity.progress == 100 for activity in activities
    ):
        action.status = StrategicAction.Status.COMPLETED
    elif action.status not in [StrategicAction.Status.BLOCKED, StrategicAction.Status.SUSPENDED]:
        action.status = StrategicAction.Status.IN_PROGRESS
    action.save(update_fields=["progress", "status"])


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


@login_required
def action_plan_detail(request, action_id):
    action = get_object_or_404(
        StrategicAction.objects.select_related("artifact", "artifact__plan", "coordinating_unit"),
        pk=action_id,
    )
    try:
        action_plan = action.action_plan
    except ActionPlan.DoesNotExist:
        action_plan = None

    if request.method == "POST" and request.POST.get("operation") == "start_plan":
        action_plan = ActionPlan.objects.create(action=action, manager=request.user)
        messages.success(request, "Plano de ação iniciado. Agora você pode cadastrar as atividades e tarefas.")
        return redirect("action_plan_detail", action_id=action.id)

    form = None
    if action_plan:
        if request.method == "POST" and request.POST.get("operation") == "add_activity":
            form = ActivityForm(request.POST, action_plan=action_plan)
            if form.is_valid():
                current_total = action_plan.activities.aggregate(total=Sum("weight"))["total"] or Decimal("0")
                if current_total + form.cleaned_data["weight"] > Decimal("100") and request.POST.get("confirm_rebalance") != "1":
                    form.add_error(
                        "weight",
                        "O total ultrapassaria 100%. Confirme a redistribuição dos pesos ou informe um peso menor.",
                    )
            if form.is_valid():
                with transaction.atomic():
                    activity = form.save(commit=False)
                    activity.action_plan = action_plan
                    activity.position = (action_plan.activities.aggregate(last_position=Max("position"))["last_position"] or 0) + 1
                    activity.save()
                    rebalanced = _rebalance_activity_weights(action_plan, activity)
                    _sync_action_progress(action, action_plan)
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
        "allocated_weight": allocated_weight,
        "remaining_weight": 100 - allocated_weight,
        "today": timezone.localdate(),
        **_action_indicators_summary(action),
    }
    return render(request, "core/action_plan_detail.html", context)


def _action_indicators_summary(action):
    objective = action.artifact
    while objective and objective.artifact_type != PlanArtifact.ArtifactType.OBJECTIVE:
        objective = objective.parent
    url = f"{reverse('indicator_overview')}?plan={action.artifact.plan_id}"
    if objective:
        url += f"&objective={objective.id}"
    return {
        "indicators_url": url,
        "objective_target_count": objective.targets.count() if objective else 0,
        "objective_indicator_count": objective.indicators.count() if objective else 0,
    }


def _get_activity_for_action(action_id, activity_id):
    return get_object_or_404(
        Activity.objects.select_related("action_plan", "action_plan__action"),
        pk=activity_id,
        action_plan__action_id=action_id,
    )


@login_required
def activity_edit(request, action_id, activity_id):
    activity = _get_activity_for_action(action_id, activity_id)
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
def activity_follow_up(request, action_id, activity_id):
    activity = _get_activity_for_action(action_id, activity_id)
    action = activity.action_plan.action
    operation = request.POST.get("operation") if request.method == "POST" else ""

    evidence_form = ActivityEvidenceForm(prefix="evidence")
    blocker_form = ActivityBlockerForm(prefix="blocker")
    risk_form = ActivityRiskForm(prefix="risk")

    if operation == "add_evidence":
        evidence_form = ActivityEvidenceForm(request.POST, request.FILES, prefix="evidence")
        if evidence_form.is_valid():
            evidence = evidence_form.save(commit=False)
            evidence.activity = activity
            evidence.created_by = request.user
            evidence.save()
            messages.success(request, "Evidência registrada na atividade.")
            return redirect("activity_follow_up", action_id=action.id, activity_id=activity.id)
    elif operation == "add_blocker":
        blocker_form = ActivityBlockerForm(request.POST, prefix="blocker")
        if blocker_form.is_valid():
            blocker = blocker_form.save(commit=False)
            blocker.activity = activity
            blocker.created_by = request.user
            blocker.save()
            messages.success(request, "Impedimento registrado na atividade.")
            return redirect("activity_follow_up", action_id=action.id, activity_id=activity.id)
    elif operation == "add_risk":
        risk_form = ActivityRiskForm(request.POST, prefix="risk")
        if risk_form.is_valid():
            risk = risk_form.save(commit=False)
            risk.action = action
            risk.activity = activity
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
                    responsible=risk.owner,
                    preventive_measure=risk.preventive_measure,
                    contingency_measure=risk.contingency_measure,
                    created_by=request.user,
                )
            messages.success(request, "Risco registrado na atividade.")
            return redirect("activity_follow_up", action_id=action.id, activity_id=activity.id)

    return render(
        request,
        "core/activity_follow_up.html",
        {
            "action": action,
            "activity": activity,
            "evidences": activity.evidences.select_related("created_by"),
            "blockers": activity.blockers.select_related("resolution_owner", "created_by"),
            "risks": activity.risks.select_related("owner"),
            "evidence_form": evidence_form,
            "blocker_form": blocker_form,
            "risk_form": risk_form,
        },
    )


@login_required
def risk_map(request, action_id):
    action = get_object_or_404(
        StrategicAction.objects.select_related("artifact", "artifact__plan", "coordinating_unit"),
        pk=action_id,
    )
    action_plan = get_object_or_404(ActionPlan, action=action)
    if request.method == "POST":
        form = RiskIdentificationForm(request.POST, action_plan=action_plan)
        if form.is_valid():
            with transaction.atomic():
                risk = form.save(commit=False)
                risk.action = action
                risk.status = Risk.Status.IDENTIFIED
                decision = form.cleaned_data["treatment_decision"]
                risk.treatment = decision
                risk.save()
                RiskAssessment.objects.create(
                    risk=risk,
                    assessment_type=RiskAssessment.AssessmentType.CURRENT,
                    probability=risk.probability,
                    impact=risk.impact,
                    author=request.user,
                )
                if decision:
                    RiskTreatment.objects.create(
                        risk=risk,
                        decision=decision,
                        responsible=risk.owner,
                        due_date=form.cleaned_data["treatment_due_date"],
                        preventive_measure=risk.preventive_measure,
                        contingency_measure=risk.contingency_measure,
                        created_by=request.user,
                    )
                    risk.status = Risk.Status.IN_TREATMENT
                    risk.save(update_fields=["status"])
            messages.success(request, "Risco incluído no mapa do plano de ação.")
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)
    else:
        form = RiskIdentificationForm(action_plan=action_plan)

    risks = action.risks.select_related("activity", "owner").prefetch_related(
        "assessments", "treatments", "materializations", "acceptances"
    ).order_by("status", "title")
    return render(
        request,
        "core/risk_map.html",
        {"action": action, "action_plan": action_plan, "risks": risks, "form": form},
    )


def _get_risk_for_action(action_id, risk_id):
    return get_object_or_404(
        Risk.objects.select_related("action", "activity", "owner"),
        pk=risk_id,
        action_id=action_id,
    )


@login_required
def risk_detail(request, action_id, risk_id):
    risk = _get_risk_for_action(action_id, risk_id)
    action = risk.action
    action_plan = action.action_plan
    operation = request.POST.get("operation") if request.method == "POST" else ""
    identity_form = RiskIdentityForm(instance=risk, action_plan=action_plan, prefix="identity")
    assessment_form = RiskAssessmentForm(prefix="assessment")
    timing_form = RiskTimingForm(instance=risk, prefix="timing")
    treatment_form = RiskTreatmentForm(prefix="treatment")
    materialization_form = RiskMaterializationForm(prefix="materialization")
    acceptance_form = RiskAcceptanceForm(prefix="acceptance")
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
    elif operation == "add_assessment":
        assessment_form = RiskAssessmentForm(request.POST, prefix="assessment")
        if assessment_form.is_valid():
            assessment = assessment_form.save(commit=False)
            assessment.risk = risk
            assessment.author = request.user
            assessment.save()
            risk.probability = assessment.probability
            risk.impact = assessment.impact
            risk.save(update_fields=["probability", "impact"])
            messages.success(request, "Nova avaliação registrada.")
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)
    elif operation == "add_treatment":
        treatment_form = RiskTreatmentForm(request.POST, prefix="treatment")
        if treatment_form.is_valid():
            treatment = treatment_form.save(commit=False)
            treatment.risk = risk
            treatment.created_by = request.user
            treatment.save()
            risk.treatment = treatment.decision
            risk.preventive_measure = treatment.preventive_measure
            risk.contingency_measure = treatment.contingency_measure
            if risk.status not in [Risk.Status.MATERIALIZED, Risk.Status.CLOSED]:
                risk.status = Risk.Status.IN_TREATMENT
            risk.save(update_fields=["treatment", "preventive_measure", "contingency_measure", "status"])
            messages.success(request, "Tratamento registrado.")
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)
    elif operation == "materialize":
        materialization_form = RiskMaterializationForm(request.POST, prefix="materialization")
        if materialization_form.is_valid():
            materialization = materialization_form.save(commit=False)
            materialization.risk = risk
            materialization.recorded_by = request.user
            materialization.save()
            risk.status = Risk.Status.MATERIALIZED
            risk.save(update_fields=["status"])
            messages.success(request, "Materialização do risco registrada.")
            return redirect("risk_detail", action_id=action.id, risk_id=risk.id)
    elif operation == "accept":
        acceptance_form = RiskAcceptanceForm(request.POST, prefix="acceptance")
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
            "assessments": risk.assessments.select_related("author"),
            "treatments": risk.treatments.select_related("responsible", "created_by"),
            "materializations": risk.materializations.select_related("recorded_by"),
            "acceptances": acceptances,
            "pending_acceptance": pending_acceptance,
            "identity_form": identity_form,
            "assessment_form": assessment_form,
            "timing_form": timing_form,
            "treatment_form": treatment_form,
            "materialization_form": materialization_form,
            "acceptance_form": acceptance_form,
            "remediation_form": remediation_form,
        },
    )


@login_required
def activity_delete(request, action_id, activity_id):
    activity = _get_activity_for_action(action_id, activity_id)
    action = activity.action_plan.action
    if request.method == "POST":
        activity.delete()
        _sync_action_progress(action, action.action_plan)
        messages.success(request, "Atividade excluída do plano de ação.")
        return redirect("action_plan_detail", action_id=action.id)
    return render(request, "core/activity_confirm_delete.html", {"activity": activity, "action": action})


@login_required
def activity_move(request, action_id, activity_id, direction):
    if request.method != "POST" or direction not in {"acima", "abaixo"}:
        return redirect("action_plan_detail", action_id=action_id)
    activity = _get_activity_for_action(action_id, activity_id)
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
