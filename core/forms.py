from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from .models import (
    Activity,
    ActivityBlocker,
    ActivityEvidence,
    Indicator,
    IndicatorMeasurement,
    Organization,
    OrganizationalUnit,
    ReportCycle,
    Risk,
    RiskAcceptance,
    RiskAssessment,
    RiskMaterialization,
    RiskRemediationSubmission,
    RiskTreatment,
    SectorReport,
    StrategicAction,
    UserProfile,
)


class IndicatorDefinitionForm(forms.ModelForm):
    """Edição da ficha (definição) do indicador."""

    class Meta:
        model = Indicator
        fields = ["indicator_type", "formula", "unit_of_measure", "data_source", "baseline", "direction"]
        labels = {
            "indicator_type": "Tipo",
            "formula": "Fórmula",
            "unit_of_measure": "Unidade de medida",
            "data_source": "Fonte de dados",
            "baseline": "Linha de base",
            "direction": "Sentido esperado",
        }
        widgets = {"formula": forms.Textarea(attrs={"rows": 3})}


class IndicatorMeasurementForm(forms.ModelForm):
    class Meta:
        model = IndicatorMeasurement
        fields = [
            "measured_by",
            "baseline_value",
            "baseline_date",
            "measured_value",
            "period_start",
            "period_end",
            "source_reference",
            "evidence_attachment",
            "note",
        ]
        labels = {
            "measured_by": "Responsável pela aferição",
            "baseline_value": "Valor basal",
            "baseline_date": "Data do valor basal",
            "measured_value": "Resultado aferido",
            "period_start": "Período de aferição — início",
            "period_end": "Período de aferição — fim",
            "source_reference": "Referência da fonte",
            "evidence_attachment": "Anexar evidência da aferição",
            "note": "Observações",
        }
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
            "baseline_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "period_start": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "period_end": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ["measured_by", "baseline_value", "baseline_date", "period_start", "period_end"]:
            self.fields[name].required = True
        measured_by = self.fields["measured_by"]
        measured_by.queryset = get_user_model().objects.filter(is_active=True).order_by("first_name", "last_name", "username")
        measured_by.label_from_instance = lambda user: user.get_full_name() or user.username
        measured_by.empty_label = "Selecione quem realizou a aferição"
        measured_by.help_text = "O setor da pessoa selecionada será registrado como setor responsável pela aferição."
        self.fields["baseline_value"].help_text = "Valor de partida (linha de base) usado como comparação para este resultado."
        self.fields["baseline_date"].help_text = "Data em que o valor basal foi apurado."
        self.fields["measured_value"].help_text = "Informe o valor apurado. Use apenas o número para calcular o semáforo."
        self.fields["period_start"].help_text = "Primeiro dia do período a que o resultado se refere."
        self.fields["period_end"].help_text = "Último dia do período a que o resultado se refere."
        self.fields["source_reference"].help_text = "Informe planilha, processo SEI, sistema ou documento que comprove o resultado."
        self.fields["evidence_attachment"].help_text = "Anexe a planilha, relatório, PDF, imagem ou outro arquivo comprobatório, quando houver."

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("period_start"), cleaned.get("period_end")
        if start and end:
            if end < start:
                self.add_error("period_end", "O fim do período não pode ser anterior ao início.")
            else:
                # O texto do período continua sendo guardado para exibição e para as aferições antigas.
                self.instance.reference_period = f"{start:%d/%m/%Y} a {end:%d/%m/%Y}"
        return cleaned

class ReportCycleForm(forms.ModelForm):
    class Meta:
        model = ReportCycle
        fields = ["name", "plan", "period_start", "period_end", "due_date", "participating_units"]
        labels = {
            "name": "Nome do ciclo",
            "plan": "Plano",
            "period_start": "Início do período",
            "period_end": "Fim do período",
            "due_date": "Prazo para envio",
            "participating_units": "Unidades participantes",
        }
        widgets = {
            "period_start": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "period_end": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "due_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "participating_units": forms.SelectMultiple(attrs={"size": 7}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("period_start")
        end = cleaned_data.get("period_end")
        due = cleaned_data.get("due_date")
        if start and end and start > end:
            self.add_error("period_end", "O fim do período não pode ser anterior ao início.")
        if end and due and due < end:
            self.add_error("due_date", "O prazo para envio não pode ser anterior ao fim do período.")
        return cleaned_data


class SectorReportForm(forms.ModelForm):
    class Meta:
        model = SectorReport
        fields = ["executive_summary", "complements", "next_steps", "management_decision_needed", "validator"]
        labels = {
            "executive_summary": "Síntese dos resultados alcançados",
            "complements": "Complementos, dificuldades e providências",
            "next_steps": "Próximos passos",
            "management_decision_needed": "Necessidade de decisão da gestão",
            "validator": "Pessoa responsável pela validação",
        }
        widgets = {
            "executive_summary": forms.Textarea(attrs={"rows": 4}),
            "complements": forms.Textarea(attrs={"rows": 4}),
            "next_steps": forms.Textarea(attrs={"rows": 3}),
            "management_decision_needed": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        validators = get_user_model().objects.filter(is_active=True).order_by("username")
        if current_user:
            validators = validators.exclude(pk=current_user.pk)
        self.fields["validator"].queryset = validators
        self.fields["validator"].help_text = "Deve ser uma pessoa diferente de quem prepara e envia o relatório."


class ReportValidationForm(forms.Form):
    decision = forms.ChoiceField(
        label="Decisão",
        choices=(("APPROVE", "Aprovar relatório"), ("RETURN", "Devolver para correção")),
    )
    comment = forms.CharField(label="Manifestação do validador", widget=forms.Textarea(attrs={"rows": 4}))
    resubmission_due_date = forms.DateField(
        label="Novo prazo para reapresentação",
        required=False,
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("decision") == "RETURN" and not cleaned_data.get("resubmission_due_date"):
            self.add_error("resubmission_due_date", "Informe o novo prazo para a correção.")
        return cleaned_data


class ActivityForm(forms.ModelForm):
    """Cadastro de atividade operacional dentro de um plano de ação."""

    requires_financial_resource = forms.TypedChoiceField(
        choices=(("NAO", "Não"), ("SIM", "Sim")),
        coerce=lambda value: value == "SIM",
        empty_value=False,
        label="Esta atividade demandará recurso financeiro?",
        widget=forms.RadioSelect(attrs={"data-financial-toggle": "true"}),
    )

    class Meta:
        model = Activity
        fields = [
            "title",
            "description",
            "executor",
            "weight",
            "start_date",
            "end_date",
            "progress",
            "status",
            "expected_delivery",
            "requires_financial_resource",
            "planned_cost",
            "disbursed_cost",
            "funding_source",
            "funding_source_other",
            "financial_responsible_unit",
            "financial_reference",
        ]
        labels = {
            "title": "Atividade ou tarefa",
            "description": "Descrição",
            "executor": "Responsável pela execução",
            "weight": "Peso na Ação Estratégica",
            "start_date": "Data de início",
            "end_date": "Data de conclusão",
            "progress": "Percentual executado (%)",
            "status": "Situação",
            "expected_delivery": "Entrega ou produto previsto",
            "planned_cost": "Recurso financeiro previsto (R$)",
            "disbursed_cost": "Valor desembolsado (R$)",
            "funding_source": "Fonte de financiamento",
            "funding_source_other": "Outra fonte — especificar",
            "financial_responsible_unit": "Unidade que acompanha a execução financeira",
            "financial_reference": "Referência financeira (processo, convênio ou observação)",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "start_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "end_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "weight": forms.NumberInput(attrs={"min": "0.01", "max": "100", "step": "0.01"}),
            "progress": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "0.01"}),
            "planned_cost": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "disbursed_cost": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        }

    def __init__(self, *args, action_plan, **kwargs):
        super().__init__(*args, **kwargs)
        self.action_plan = action_plan
        self.fields["executor"].queryset = get_user_model().objects.filter(is_active=True).order_by("username")
        self.fields["financial_responsible_unit"].queryset = OrganizationalUnit.objects.order_by("name")
        self.fields["start_date"].required = True
        self.fields["end_date"].required = True
        self.fields["weight"].help_text = "Informe um peso entre 0,01% e 100%. Se o total passar de 100%, os pesos das atividades existentes serão reduzidos proporcionalmente."
        has_financial_resource = self.instance.pk and any(
            [
                self.instance.planned_cost,
                self.instance.disbursed_cost,
                self.instance.funding_source,
                self.instance.financial_responsible_unit_id,
                self.instance.financial_reference,
            ]
        )
        self.initial["requires_financial_resource"] = "SIM" if has_financial_resource else "NAO"

    def clean_weight(self):
        weight = self.cleaned_data["weight"]
        if weight < Decimal("0.01") or weight > Decimal("100"):
            raise forms.ValidationError("Informe um peso entre 0,01% e 100%.")
        current_total = sum(
            (
                activity.weight
                for activity in self.action_plan.activities.exclude(pk=self.instance.pk)
            ),
            Decimal("0"),
        )
        if self.instance.pk and current_total + weight > Decimal("100"):
            remaining = (Decimal("100") - current_total).quantize(Decimal("0.01"))
            remaining_text = f"{remaining:f}".rstrip("0").rstrip(".").replace(".", ",") or "0"
            raise forms.ValidationError(
                f"O peso excede 100%. Restam {remaining_text}% para distribuir nesta ação."
            )
        return weight

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and start_date > end_date:
            self.add_error("end_date", "A data de conclusão não pode ser anterior à data de início.")

        if cleaned_data.get("status") == StrategicAction.Status.COMPLETED:
            has_evidence = self.instance.pk and self.instance.evidences.exclude(attachment="").exists()
            if not has_evidence:
                self.add_error(
                    "status",
                    "Para concluir a atividade, registre ao menos uma evidência com anexo (ícone de documento na lista de atividades).",
                )

        requires_financial_resource = cleaned_data.get("requires_financial_resource")
        planned_cost = cleaned_data.get("planned_cost")
        disbursed_cost = cleaned_data.get("disbursed_cost")
        funding_source = cleaned_data.get("funding_source")
        funding_source_other = cleaned_data.get("funding_source_other")
        if requires_financial_resource and (planned_cost or disbursed_cost) and not funding_source:
            self.add_error("funding_source", "Informe a fonte de financiamento quando houver recurso financeiro ou desembolso.")
        if requires_financial_resource and funding_source == Activity.FundingSource.OTHER and not funding_source_other:
            self.add_error("funding_source_other", "Especifique a outra fonte de financiamento.")
        if not requires_financial_resource:
            cleaned_data["planned_cost"] = None
            cleaned_data["disbursed_cost"] = None
            cleaned_data["funding_source"] = ""
            cleaned_data["funding_source_other"] = ""
            cleaned_data["financial_responsible_unit"] = None
            cleaned_data["financial_reference"] = ""
        return cleaned_data


class ActivityEvidenceForm(forms.ModelForm):
    class Meta:
        model = ActivityEvidence
        fields = ["title", "evidence_type", "description", "reference", "url", "attachment"]
        labels = {
            "title": "Título da evidência",
            "evidence_type": "Tipo",
            "description": "Descrição",
            "reference": "Referência ou número do processo SEI",
            "url": "Link",
            "attachment": "Anexo (arquivo ou foto)",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attachment"].required = True
        self.fields["attachment"].help_text = "Obrigatório. Anexe o documento, relatório ou foto que comprova a entrega."


class ActivityBlockerForm(forms.ModelForm):
    class Meta:
        model = ActivityBlocker
        fields = ["description", "resolution_owner", "expected_resolution_date", "status", "resolution_note"]
        labels = {
            "description": "Impedimento identificado",
            "resolution_owner": "Responsável pela solução",
            "expected_resolution_date": "Previsão de desbloqueio",
            "status": "Situação",
            "resolution_note": "Providência ou solução adotada",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "resolution_note": forms.Textarea(attrs={"rows": 2}),
            "expected_resolution_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["resolution_owner"].queryset = get_user_model().objects.filter(is_active=True).order_by("username")


class ActivityRiskForm(forms.ModelForm):
    treatment = forms.ChoiceField(
        choices=(("", "---------"), ("Evitar", "Evitar"), ("Mitigar", "Mitigar"), ("Transferir", "Transferir"), ("Aceitar", "Aceitar")),
        required=False,
        label="Resposta ao risco",
    )

    class Meta:
        model = Risk
        fields = [
            "title",
            "cause",
            "owner",
            "probability",
            "impact",
            "status",
            "treatment",
            "preventive_measure",
            "contingency_measure",
        ]
        labels = {
            "title": "Risco identificado",
            "cause": "Causa",
            "owner": "Responsável pelo risco",
            "probability": "Probabilidade (1 a 5)",
            "impact": "Impacto (1 a 5)",
            "status": "Situação",
            "preventive_measure": "Medida preventiva ou controle",
            "contingency_measure": "Medida de contingência",
        }
        widgets = {
            "cause": forms.Textarea(attrs={"rows": 2}),
            "preventive_measure": forms.Textarea(attrs={"rows": 2}),
            "contingency_measure": forms.Textarea(attrs={"rows": 2}),
            "probability": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "impact": forms.NumberInput(attrs={"min": 1, "max": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = get_user_model().objects.filter(is_active=True).order_by("username")

    def clean_probability(self):
        value = self.cleaned_data["probability"]
        if not 1 <= value <= 5:
            raise forms.ValidationError("Informe um valor entre 1 e 5.")
        return value

    def clean_impact(self):
        value = self.cleaned_data["impact"]
        if not 1 <= value <= 5:
            raise forms.ValidationError("Informe um valor entre 1 e 5.")
        return value


class RiskIdentificationForm(forms.ModelForm):
    treatment_decision = forms.ChoiceField(
        choices=(("", "Definir posteriormente"), *RiskTreatment.Decision.choices),
        required=False,
        label="Resposta inicial ao risco",
    )
    treatment_due_date = forms.DateField(
        required=False,
        label="Prazo para concluir o tratamento (opcional)",
        help_text="Este prazo se refere à medida de tratamento, não à data em que o risco poderá ocorrer.",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )

    class Meta:
        model = Risk
        fields = [
            "activity",
            "title",
            "cause",
            "owner",
            "probability",
            "impact",
            "occurrence_timing",
            "exposure_start_date",
            "exposure_end_date",
            "expected_occurrence_date",
            "trigger_description",
            "treatment_decision",
            "treatment_due_date",
            "preventive_measure",
            "contingency_measure",
        ]
        labels = {
            "activity": "Atividade afetada (opcional)",
            "title": "Risco identificado",
            "cause": "Causa",
            "owner": "Responsável pelo risco",
            "probability": "Probabilidade (1 a 5)",
            "impact": "Impacto (1 a 5)",
            "occurrence_timing": "Quando o risco pode ocorrer?",
            "exposure_start_date": "Início do período de exposição",
            "exposure_end_date": "Fim do período de exposição",
            "expected_occurrence_date": "Data provável (opcional)",
            "trigger_description": "Marco, sinal ou condição de ocorrência (opcional)",
            "preventive_measure": "Medida preventiva ou controle",
            "contingency_measure": "Medida de contingência",
        }
        widgets = {
            "cause": forms.Textarea(attrs={"rows": 2}),
            "preventive_measure": forms.Textarea(attrs={"rows": 2}),
            "contingency_measure": forms.Textarea(attrs={"rows": 2}),
            "probability": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "impact": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "occurrence_timing": forms.Select(attrs={"data-occurrence-timing": "true"}),
            "exposure_start_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "exposure_end_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "expected_occurrence_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "trigger_description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, action_plan, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activity"].queryset = action_plan.activities.order_by("position", "title")
        self.fields["owner"].queryset = get_user_model().objects.filter(is_active=True).order_by("username")

    def clean_probability(self):
        value = self.cleaned_data["probability"]
        if not 1 <= value <= 5:
            raise forms.ValidationError("Informe um valor entre 1 e 5.")
        return value

    def clean_impact(self):
        value = self.cleaned_data["impact"]
        if not 1 <= value <= 5:
            raise forms.ValidationError("Informe um valor entre 1 e 5.")
        return value

    def clean(self):
        cleaned_data = super().clean()
        timing = cleaned_data.get("occurrence_timing")
        exposure_start = cleaned_data.get("exposure_start_date")
        exposure_end = cleaned_data.get("exposure_end_date")
        expected_date = cleaned_data.get("expected_occurrence_date")
        trigger = cleaned_data.get("trigger_description")
        if timing == Risk.OccurrenceTiming.EXPOSURE_WINDOW:
            if not exposure_start and not exposure_end:
                self.add_error("exposure_start_date", "Informe ao menos o início ou o fim do período provável.")
            elif exposure_start and exposure_end and exposure_start > exposure_end:
                self.add_error("exposure_end_date", "O fim do período não pode ser anterior ao início.")
        else:
            cleaned_data["exposure_start_date"] = None
            cleaned_data["exposure_end_date"] = None
        if timing == Risk.OccurrenceTiming.DATE_OR_MILESTONE:
            if not expected_date and not trigger:
                self.add_error("trigger_description", "Informe uma data provável ou descreva o marco ou condição.")
        else:
            cleaned_data["expected_occurrence_date"] = None
        return cleaned_data


class RiskTimingForm(forms.ModelForm):
    class Meta:
        model = Risk
        fields = [
            "occurrence_timing",
            "exposure_start_date",
            "exposure_end_date",
            "expected_occurrence_date",
            "trigger_description",
        ]
        labels = {
            "occurrence_timing": "Quando o risco pode ocorrer?",
            "exposure_start_date": "Início do período de exposição",
            "exposure_end_date": "Fim do período de exposição",
            "expected_occurrence_date": "Data provável (opcional)",
            "trigger_description": "Marco, sinal ou condição de ocorrência (opcional)",
        }
        widgets = {
            "occurrence_timing": forms.Select(attrs={"data-occurrence-timing": "true"}),
            "exposure_start_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "exposure_end_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "expected_occurrence_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "trigger_description": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        timing = cleaned_data.get("occurrence_timing")
        exposure_start = cleaned_data.get("exposure_start_date")
        exposure_end = cleaned_data.get("exposure_end_date")
        expected_date = cleaned_data.get("expected_occurrence_date")
        trigger = cleaned_data.get("trigger_description")
        if timing == Risk.OccurrenceTiming.EXPOSURE_WINDOW:
            if not exposure_start and not exposure_end:
                self.add_error("exposure_start_date", "Informe ao menos o início ou o fim do período provável.")
            elif exposure_start and exposure_end and exposure_start > exposure_end:
                self.add_error("exposure_end_date", "O fim do período não pode ser anterior ao início.")
        else:
            cleaned_data["exposure_start_date"] = None
            cleaned_data["exposure_end_date"] = None
        if timing == Risk.OccurrenceTiming.DATE_OR_MILESTONE:
            if not expected_date and not trigger:
                self.add_error("trigger_description", "Informe uma data provável ou descreva o marco ou condição.")
        else:
            cleaned_data["expected_occurrence_date"] = None
        return cleaned_data


class RiskIdentityForm(forms.ModelForm):
    class Meta:
        model = Risk
        fields = ["title", "cause", "activity", "owner"]
        labels = {
            "title": "Risco identificado",
            "cause": "Causa",
            "activity": "Atividade afetada (opcional)",
            "owner": "Responsável pelo risco",
        }
        widgets = {"cause": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, action_plan=None, **kwargs):
        super().__init__(*args, **kwargs)
        if action_plan is not None:
            self.fields["activity"].queryset = action_plan.activities.all()
        self.fields["owner"].queryset = get_user_model().objects.filter(is_active=True).order_by("username")


class RiskAssessmentForm(forms.ModelForm):
    class Meta:
        model = RiskAssessment
        fields = ["assessment_type", "probability", "impact", "notes"]
        labels = {
            "assessment_type": "Tipo de avaliação",
            "probability": "Probabilidade (1 a 5)",
            "impact": "Impacto (1 a 5)",
            "notes": "Justificativa da avaliação",
        }
        widgets = {
            "probability": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "impact": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        for field in ["probability", "impact"]:
            value = cleaned_data.get(field)
            if value is not None and not 1 <= value <= 5:
                self.add_error(field, "Informe um valor entre 1 e 5.")
        return cleaned_data


class RiskTreatmentForm(forms.ModelForm):
    class Meta:
        model = RiskTreatment
        fields = ["decision", "justification", "responsible", "due_date", "preventive_measure", "contingency_measure"]
        labels = {
            "decision": "Resposta ao risco",
            "justification": "Justificativa",
            "responsible": "Responsável pelo tratamento",
            "due_date": "Prazo para concluir o tratamento (opcional)",
            "preventive_measure": "Medida preventiva ou controle",
            "contingency_measure": "Medida de contingência",
        }
        widgets = {
            "justification": forms.Textarea(attrs={"rows": 2}),
            "due_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "preventive_measure": forms.Textarea(attrs={"rows": 2}),
            "contingency_measure": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].queryset = get_user_model().objects.filter(is_active=True).order_by("username")
        self.fields["due_date"].help_text = "Não é uma previsão de quando o risco ocorrerá; é o prazo da ação de tratamento."


class RiskMaterializationForm(forms.ModelForm):
    class Meta:
        model = RiskMaterialization
        fields = ["occurred_on", "description", "actual_impact", "actions_taken", "evidence_reference"]
        labels = {
            "occurred_on": "Data em que ocorreu (registro posterior)",
            "description": "O que ocorreu",
            "actual_impact": "Impacto ocorrido",
            "actions_taken": "Providências adotadas",
            "evidence_reference": "Referência da evidência",
        }
        widgets = {
            "occurred_on": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
            "actual_impact": forms.Textarea(attrs={"rows": 2}),
            "actions_taken": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["occurred_on"].help_text = "Preencha somente depois que o risco tiver se materializado."


class RiskAcceptanceForm(forms.ModelForm):
    class Meta:
        model = RiskAcceptance
        fields = [
            "authority",
            "decision",
            "justification",
            "remedial_actions",
            "remediation_responsible",
            "reevaluation_due_date",
        ]
        labels = {
            "authority": "Autoridade que decidiu sobre o aceite",
            "decision": "Decisão da autoridade",
            "justification": "Fundamentação da decisão",
            "remedial_actions": "Diligências saneadoras exigidas",
            "remediation_responsible": "Responsável pelas diligências",
            "reevaluation_due_date": "Prazo para reapresentação e nova avaliação",
        }
        widgets = {
            "justification": forms.Textarea(attrs={"rows": 2}),
            "remedial_actions": forms.Textarea(attrs={"rows": 3}),
            "reevaluation_due_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_users = get_user_model().objects.filter(is_active=True).order_by("username")
        self.fields["authority"].queryset = active_users
        self.fields["remediation_responsible"].queryset = active_users
        self.fields["authority"].help_text = "Pessoa com alçada que tomou a decisão formal sobre o risco."
        self.fields["remedial_actions"].help_text = "Informe o que deve ser corrigido, complementado ou comprovado antes da nova avaliação."
        self.fields["remediation_responsible"].help_text = "Pessoa encarregada de cumprir e comprovar as diligências."
        self.fields["reevaluation_due_date"].help_text = "Data-limite para reapresentar o caso; deixe em branco quando ainda não houver prazo definido."

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("decision") == RiskAcceptance.Decision.ACCEPTED_WITH_RESERVATIONS:
            if not cleaned_data.get("remedial_actions"):
                self.add_error("remedial_actions", "Informe as diligências saneadoras exigidas.")
            if not cleaned_data.get("remediation_responsible"):
                self.add_error("remediation_responsible", "Informe quem ficará responsável pelas diligências.")
        else:
            cleaned_data["remedial_actions"] = ""
            cleaned_data["remediation_responsible"] = None
            cleaned_data["reevaluation_due_date"] = None
        return cleaned_data


class RiskRemediationSubmissionForm(forms.ModelForm):
    class Meta:
        model = RiskRemediationSubmission
        fields = ["completion_summary", "evidence_reference"]
        labels = {
            "completion_summary": "Como as diligências foram cumpridas",
            "evidence_reference": "Evidência ou referência SEI",
        }
        widgets = {"completion_summary": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["completion_summary"].help_text = "Descreva o resultado e o que foi corrigido ou complementado."
        self.fields["evidence_reference"].help_text = "Informe processo, documento, link ou outra comprovação, quando houver."


class UserCreateForm(forms.Form):
    name = forms.CharField(label="Nome", max_length=150)
    email = forms.EmailField(label="E-mail", max_length=150)
    password = forms.CharField(label="Senha inicial", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    group = forms.ModelChoiceField(label="Perfil", queryset=Group.objects.order_by("name"), empty_label="Selecione o perfil")
    unit_name = forms.CharField(label="Setor", max_length=180)

    is_active = forms.TypedChoiceField(
        label="Situação",
        choices=[("1", "Ativo"), ("0", "Inativo")],
        coerce=lambda value: value == "1",
        initial="1",
    )

    def __init__(self, *args, user=None, **kwargs):
        """Sem `user` cadastra um usuário novo; com `user` edita o existente."""
        self.edited_user = user
        if user is not None:
            profile = getattr(user, "profile", None)
            kwargs.setdefault(
                "initial",
                {
                    "name": user.get_full_name(),
                    "email": user.email or user.username,
                    "group": user.groups.first(),
                    "unit_name": profile.unit.name if profile and profile.unit else "",
                    "is_active": "1" if user.is_active else "0",
                },
            )
        super().__init__(*args, **kwargs)
        self.fields["email"].help_text = "O e-mail também será o login do usuário."
        self.fields["unit_name"].help_text = "Digite para buscar. Se o setor não existir, ele será cadastrado com o que você digitar."
        self.fields["unit_name"].widget.attrs.update({"autocomplete": "off", "data-unit-input": ""})
        self.unit = None
        if user is None:
            del self.fields["is_active"]
        else:
            self.fields["password"].required = False
            self.fields["password"].label = "Nova senha"
            self.fields["password"].help_text = "Deixe em branco para manter a senha atual."

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        others = get_user_model().objects.all()
        if self.edited_user is not None:
            others = others.exclude(pk=self.edited_user.pk)
        if others.filter(username__iexact=email).exists() or others.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe um usuário com este e-mail.")
        return email

    def clean_unit_name(self):
        name = " ".join(self.cleaned_data["unit_name"].split())
        self.unit = (
            OrganizationalUnit.objects.filter(name__iexact=name).first()
            or OrganizationalUnit.objects.filter(acronym__iexact=name).first()
        )
        if not self.unit and not Organization.objects.filter(active=True).exists():
            raise forms.ValidationError("Cadastre um órgão ativo antes de criar setores.")
        return name

    @transaction.atomic
    def save(self):
        data = self.cleaned_data
        unit = self.unit
        if not unit:
            organization = Organization.objects.filter(active=True).order_by("id").first()
            organ = OrganizationalUnit.objects.filter(
                organization=organization, unit_type=OrganizationalUnit.UnitType.ORGAN
            ).order_by("id").first()
            unit = OrganizationalUnit.objects.create(
                organization=organization,
                parent=organ,
                name=data["unit_name"],
                unit_type=OrganizationalUnit.UnitType.SECTOR,
            )
        first_name, _, last_name = data["name"].partition(" ")
        if self.edited_user is None:
            user = get_user_model().objects.create_user(
                username=data["email"],
                email=data["email"],
                password=data["password"],
                first_name=first_name,
                last_name=last_name,
            )
        else:
            user = self.edited_user
            user.username = user.email = data["email"]
            user.first_name, user.last_name = first_name, last_name
            user.is_active = data["is_active"]
            if data["password"]:
                user.set_password(data["password"])
            user.save()
        user.groups.set([data["group"]])
        UserProfile.objects.update_or_create(user=user, defaults={"unit": unit})
        return user


class ProfileForm(forms.Form):
    """Autoedição: o próprio usuário altera apenas nome, e-mail e senha."""

    name = forms.CharField(label="Nome", max_length=150)
    email = forms.EmailField(label="E-mail", max_length=150)
    password = forms.CharField(
        label="Nova senha",
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Deixe em branco para manter a senha atual.",
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        kwargs.setdefault("initial", {"name": user.get_full_name(), "email": user.email or user.username})
        super().__init__(*args, **kwargs)
        self.fields["email"].help_text = "O e-mail também é o seu login."

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        others = get_user_model().objects.exclude(pk=self.user.pk)
        if others.filter(username__iexact=email).exists() or others.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe um usuário com este e-mail.")
        return email

    def save(self):
        data = self.cleaned_data
        user = self.user
        user.username = user.email = data["email"]
        user.first_name, _, user.last_name = data["name"].partition(" ")
        if data["password"]:
            user.set_password(data["password"])
        user.save()
        return user


class GroupForm(forms.Form):
    name = forms.CharField(label="Nome do perfil", max_length=150)

    def __init__(self, *args, group=None, **kwargs):
        self.group = group
        if group is not None:
            kwargs.setdefault("initial", {"name": group.name})
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        others = Group.objects.all()
        if self.group is not None:
            others = others.exclude(pk=self.group.pk)
        if others.filter(name__iexact=name).exists():
            raise forms.ValidationError("Já existe um perfil com este nome.")
        return name
