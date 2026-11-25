from django import forms
from django.contrib import admin
from django.db.models import Q

from .models import (
    ActionPlan,
    Activity,
    ActivityBlocker,
    ActivityEvidence,
    CriticalSuccessFactor,
    Indicator,
    IndicatorMeasurement,
    Organization,
    OrganizationalUnit,
    Plan,
    PlanArtifact,
    ReportCycle,
    Risk,
    RiskAcceptance,
    RiskAssessment,
    RiskMaterialization,
    RiskRemediationSubmission,
    RiskTreatment,
    SectorReport,
    StrategicAction,
    StrategicTarget,
    UserProfile,
)


class StrategicActionAdminForm(forms.ModelForm):
    class Meta:
        model = StrategicAction
        fields = "__all__"
        labels = {
            "artifact": "Item principal do plano",
            "related_objectives": "Objetivos e referências vinculados",
            "coordinating_unit": "Unidade coordenadora",
            "code": "Código da ação estratégica",
            "title": "Título da ação estratégica",
            "description": "Descrição",
            "due_date": "Prazo estratégico",
            "status": "Situação",
            "progress": "Percentual de execução",
            "funding_sources": "Fontes de recurso",
            "participating_units": "Unidades participantes",
        }

    def clean(self):
        data = super().clean()
        artifact = data.get("artifact")
        if not artifact:
            return data
        plan = artifact.plan
        eligible = OrganizationalUnit.objects.filter(exclusive_plan=plan)
        if plan.plan_type != Plan.PlanType.PESP:
            eligible = OrganizationalUnit.objects.filter(Q(exclusive_plan=plan) | Q(exclusive_plan__isnull=True))
        coordinator = data.get("coordinating_unit")
        if coordinator and not eligible.filter(pk=coordinator.pk).exists():
            self.add_error("coordinating_unit", "Escolha uma unidade que pertença ao plano da ação.")
        participants = data.get("participating_units")
        if participants is not None and participants.exclude(pk__in=eligible).exists():
            self.add_error("participating_units", "Escolha unidades que pertençam ao plano da ação.")
        objectives = data.get("related_objectives")
        if objectives is not None and objectives.exclude(plan=plan, artifact_type__in=[PlanArtifact.ArtifactType.OBJECTIVE, PlanArtifact.ArtifactType.REFERENCE]).exists():
            self.add_error("related_objectives", "Escolha objetivos que pertençam ao plano da ação.")
        return data


@admin.register(StrategicAction)
class StrategicActionAdmin(admin.ModelAdmin):
    form = StrategicActionAdminForm
    list_display = ("code", "title", "coordinating_unit", "status", "progress", "due_date")
    list_filter = ("status", "coordinating_unit", "artifact__plan")
    search_fields = ("code", "title", "description")
    fieldsets = (
        ("Identificação", {"fields": ("artifact", "related_objectives", "code", "title", "description")}),
        ("Responsabilidade e execução", {"fields": ("coordinating_unit", "participating_units", "status", "progress", "due_date")}),
        ("Recursos", {"fields": ("funding_sources",)}),
    )


admin.site.site_header = "Administração do GEPEI"
admin.site.site_title = "GEPEI"
admin.site.index_title = "Cadastros e configurações"

admin.site.register(Organization)
admin.site.register(OrganizationalUnit)
admin.site.register(UserProfile)
admin.site.register(Plan)
admin.site.register(PlanArtifact)
admin.site.register(ActionPlan)
admin.site.register(Activity)
admin.site.register(ActivityEvidence)
admin.site.register(ActivityBlocker)
admin.site.register(Risk)
admin.site.register(RiskAssessment)
admin.site.register(RiskTreatment)
admin.site.register(RiskMaterialization)
admin.site.register(RiskAcceptance)
admin.site.register(RiskRemediationSubmission)
admin.site.register(StrategicTarget)
admin.site.register(Indicator)
admin.site.register(IndicatorMeasurement)
admin.site.register(CriticalSuccessFactor)
admin.site.register(ReportCycle)
admin.site.register(SectorReport)
