from django import forms
from django.contrib import admin

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
)


class StrategicActionAdminForm(forms.ModelForm):
    class Meta:
        model = StrategicAction
        fields = "__all__"
        labels = {
            "artifact": "Projeto estratégico vinculado",
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


@admin.register(StrategicAction)
class StrategicActionAdmin(admin.ModelAdmin):
    form = StrategicActionAdminForm
    list_display = ("code", "title", "coordinating_unit", "status", "progress", "due_date")
    list_filter = ("status", "coordinating_unit", "artifact__plan")
    search_fields = ("code", "title", "description")
    fieldsets = (
        ("Identificação", {"fields": ("artifact", "code", "title", "description")}),
        ("Responsabilidade e execução", {"fields": ("coordinating_unit", "participating_units", "status", "progress", "due_date")}),
        ("Recursos", {"fields": ("funding_sources",)}),
    )


admin.site.site_header = "Administração do GEPEI"
admin.site.site_title = "GEPEI"
admin.site.index_title = "Cadastros e configurações"

admin.site.register(Organization)
admin.site.register(OrganizationalUnit)
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
