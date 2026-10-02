"""Dados fictícios, identificados como demonstração, para apresentar o GEPEI."""

from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.models import (
    ActionPlan,
    Activity,
    ActivityBlocker,
    ActivityEvidence,
    Risk,
    RiskAcceptance,
    RiskAssessment,
    RiskMaterialization,
    RiskTreatment,
    StrategicAction,
)


class Command(BaseCommand):
    help = "Inclui dados fictícios de execução para demonstração do piloto."

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username="eudessax@gmail.com").first()
        if not user:
            raise CommandError("Usuário de demonstração não encontrado.")

        self.add_activities(
            "AE 01.2",
            user,
            [
                ("[DEMONSTRAÇÃO] Levantar necessidades de capacitação", 30, 100, "CONCLUIDA", date(2026, 1, 10), date(2026, 3, 31), "Matriz de necessidades de capacitação", "0", "0", ""),
                ("[DEMONSTRAÇÃO] Selecionar cursos prioritários", 35, 60, "EM_ANDAMENTO", date(2026, 4, 1), date(2026, 9, 30), "Plano de cursos priorizados", "15000", "9000", "FAF"),
                ("[DEMONSTRAÇÃO] Executar ciclo de capacitações", 35, 25, "EM_ANDAMENTO", date(2026, 7, 1), date(2026, 12, 15), "Relatório de execução do ciclo", "42000", "8000", "FAF"),
            ],
        )
        self.add_activities(
            "AE 03.1",
            user,
            [
                ("[DEMONSTRAÇÃO] Elaborar minuta do programa QVST", 40, 100, "CONCLUIDA", date(2026, 1, 5), date(2026, 2, 28), "Minuta do Programa de QVST", "0", "0", ""),
                ("[DEMONSTRAÇÃO] Validar proposta com unidades", 30, 50, "EM_ANDAMENTO", date(2026, 3, 1), date(2026, 8, 30), "Ata de validação", "0", "0", ""),
                ("[DEMONSTRAÇÃO] Publicar programa aprovado", 30, 0, "NAO_INICIADA", date(2026, 9, 1), date(2026, 10, 31), "Portaria publicada", "0", "0", ""),
            ],
        )
        monitored_activity = Activity.objects.get(
            action_plan__action__code="AE 01.2",
            title="[DEMONSTRAÇÃO] Selecionar cursos prioritários",
        )
        ActivityEvidence.objects.update_or_create(
            activity=monitored_activity,
            title="[DEMONSTRAÇÃO] Ata de validação das necessidades",
            defaults={
                "created_by": user,
                "evidence_type": ActivityEvidence.EvidenceType.SEI,
                "description": "Registro fictício da validação do levantamento pelas unidades participantes.",
                "reference": "Processo SEI 00000.000000/2026-00",
            },
        )
        ActivityBlocker.objects.update_or_create(
            activity=monitored_activity,
            description="[DEMONSTRAÇÃO] Duas unidades ainda não enviaram suas prioridades de capacitação.",
            defaults={
                "created_by": user,
                "resolution_owner": user,
                "expected_resolution_date": date(2026, 9, 15),
                "status": ActivityBlocker.Status.IN_TREATMENT,
                "resolution_note": "Cobrança encaminhada às chefias das unidades pendentes.",
            },
        )
        action = monitored_activity.action_plan.action
        self.add_risk_scenario(
            action, user, "[DEMONSTRAÇÃO] Baixa adesão das unidades ao levantamento",
            "Conflito de agenda e atraso na indicação dos participantes.", 3, 4,
            Risk.Status.IN_TREATMENT, RiskTreatment.Decision.MITIGATE,
            activity=monitored_activity,
            preventive="Acompanhar semanalmente as respostas e comunicar as chefias.",
            contingency="Prorrogar apenas o prazo das unidades justificadamente pendentes.",
            occurrence_timing=Risk.OccurrenceTiming.ANY_TIME,
        )
        self.add_risk_scenario(
            action, user, "[DEMONSTRAÇÃO] Pequeno ajuste no cronograma de entrevistas",
            "Possível remarcação de uma reunião setorial.", 1, 2,
            Risk.Status.IDENTIFIED, None,
            occurrence_timing=Risk.OccurrenceTiming.DATE_OR_MILESTONE,
            expected_occurrence_date=date(2026, 9, 10),
            trigger="Reunião de validação com as unidades participantes.",
        )
        self.add_risk_scenario(
            action, user, "[DEMONSTRAÇÃO] Atraso no envio das informações setoriais",
            "Unidades participantes não enviaram os dados no prazo acordado.", 4, 4,
            Risk.Status.MATERIALIZED, RiskTreatment.Decision.MITIGATE,
            activity=monitored_activity,
            preventive="Enviar lembretes e acompanhar o recebimento semanalmente.",
            contingency="Consolidar os dados recebidos e escalonar pendências às chefias.",
            materialized=True,
            occurrence_timing=Risk.OccurrenceTiming.EXPOSURE_WINDOW,
            exposure_start_date=date(2026, 8, 15),
            exposure_end_date=date(2026, 9, 1),
        )
        self.add_risk_scenario(
            action, user, "[DEMONSTRAÇÃO] Indisponibilidade temporária do formulário",
            "Manutenção programada do serviço de formulários.", 2, 3,
            Risk.Status.CLOSED, RiskTreatment.Decision.ACCEPT,
            preventive="Divulgar previamente a janela de manutenção.",
            contingency="Receber respostas por processo SEI durante a indisponibilidade.",
            accepted=True,
            occurrence_timing=Risk.OccurrenceTiming.DATE_OR_MILESTONE,
            trigger="Janela de manutenção programada do serviço.",
        )
        risk_action = StrategicAction.objects.get(code="AE 08.1")
        risk, _ = Risk.objects.get_or_create(
            action=risk_action,
            title="[DEMONSTRAÇÃO] Informações setoriais incompletas",
            defaults={
                "owner": user,
                "cause": "Atualizações setoriais não enviadas no período de monitoramento.",
                "probability": 4,
                "impact": 4,
                "status": Risk.Status.IN_TREATMENT,
                "treatment": "Mitigar",
                "preventive_measure": "Realizar acompanhamento semanal e comunicação às chefias.",
                "contingency_measure": "Escalonar a pendência à COPIN e ao gestor responsável.",
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Dados fictícios inseridos. Risco de demonstração: nível {risk.level}."))

    def add_risk_scenario(
        self, action, user, title, cause, probability, impact, status, decision,
        activity=None, preventive="", contingency="", materialized=False, accepted=False,
        occurrence_timing=Risk.OccurrenceTiming.UNKNOWN, exposure_start_date=None,
        exposure_end_date=None, expected_occurrence_date=None, trigger="",
    ):
        risk, created = Risk.objects.get_or_create(
            action=action,
            activity=activity,
            title=title,
            defaults={
                "owner": user,
                "cause": cause,
                "probability": probability,
                "impact": impact,
                "status": status,
                "treatment": decision or "",
                "preventive_measure": preventive,
                "contingency_measure": contingency,
                "occurrence_timing": occurrence_timing,
                "exposure_start_date": exposure_start_date,
                "exposure_end_date": exposure_end_date,
                "expected_occurrence_date": expected_occurrence_date,
                "trigger_description": trigger,
            },
        )
        if not created and risk.occurrence_timing == Risk.OccurrenceTiming.UNKNOWN:
            risk.occurrence_timing = occurrence_timing
            risk.exposure_start_date = exposure_start_date
            risk.exposure_end_date = exposure_end_date
            risk.expected_occurrence_date = expected_occurrence_date
            risk.trigger_description = trigger
            risk.save(update_fields=[
                "occurrence_timing",
                "exposure_start_date",
                "exposure_end_date",
                "expected_occurrence_date",
                "trigger_description",
            ])
        RiskAssessment.objects.update_or_create(
            risk=risk,
            assessment_type=RiskAssessment.AssessmentType.CURRENT,
            notes="Avaliação fictícia para demonstração da matriz 5×5.",
            defaults={
                "probability": probability,
                "impact": impact,
                "author": user,
            },
        )
        latest_assessment = risk.assessments.first()
        if latest_assessment:
            risk.probability = latest_assessment.probability
            risk.impact = latest_assessment.impact
            risk.save(update_fields=["probability", "impact"])
        if decision:
            RiskTreatment.objects.update_or_create(
                risk=risk,
                decision=decision,
                justification="Decisão fictícia registrada para teste do fluxo.",
                defaults={
                    "responsible": user,
                    "due_date": date(2026, 9, 30),
                    "preventive_measure": preventive,
                    "contingency_measure": contingency,
                    "created_by": user,
                },
            )
        if materialized:
            RiskMaterialization.objects.update_or_create(
                risk=risk,
                occurred_on=date(2026, 9, 3),
                description="O prazo terminou sem o recebimento de todas as informações.",
                defaults={
                    "actual_impact": "A consolidação foi adiada em cinco dias úteis.",
                    "actions_taken": "As chefias foram comunicadas e foi definido novo prazo.",
                    "evidence_reference": "Processo SEI 00000.000001/2026-00",
                    "recorded_by": user,
                },
            )
        if accepted:
            RiskAcceptance.objects.update_or_create(
                risk=risk,
                authority=user,
                justification="Impacto limitado e contingência suficiente para manter a atividade.",
                defaults={
                    "decision": RiskAcceptance.Decision.ACCEPTED,
                    "recorded_by": user,
                },
            )
        return risk

    def add_activities(self, action_code, user, rows):
        action = StrategicAction.objects.get(code=action_code)
        action_plan, _ = ActionPlan.objects.get_or_create(action=action, defaults={"manager": user})
        for position, (title, weight, progress, status, start_date, end_date, expected_delivery, planned_cost, disbursed_cost, funding_source) in enumerate(rows, start=1):
            Activity.objects.update_or_create(
                action_plan=action_plan,
                title=title,
                defaults={
                    "executor": user,
                    "description": "Registro fictício criado exclusivamente para demonstração da plataforma.",
                    "weight": Decimal(str(weight)),
                    "progress": Decimal(str(progress)),
                    "status": status,
                    "position": position,
                    "start_date": start_date,
                    "end_date": end_date,
                    "expected_delivery": expected_delivery,
                    "requires_financial_resource": bool(Decimal(planned_cost) or Decimal(disbursed_cost) or funding_source),
                    "planned_cost": Decimal(planned_cost),
                    "disbursed_cost": Decimal(disbursed_cost),
                    "funding_source": funding_source,
                },
            )
        activities = list(action_plan.activities.all())
        action.progress = sum((item.weight * item.progress / 100 for item in activities), Decimal("0"))
        action.status = StrategicAction.Status.IN_PROGRESS
        action.save(update_fields=["progress", "status"])
