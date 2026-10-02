from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from .models import (
    ActionPlan,
    Activity,
    ActivityBlocker,
    ActivityEvidence,
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


class DashboardAndRiskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="copin", password="senha-segura")
        organization = Organization.objects.create(name="SESED", acronym="SESED")
        unit = OrganizationalUnit.objects.create(
            organization=organization,
            name="Coordenadoria de Planejamento Institucional",
            acronym="COPIN",
            unit_type=OrganizationalUnit.UnitType.SECTOR,
        )
        plan = Plan.objects.create(
            name="Plano Estratégico Institucional",
            acronym="PEI",
            plan_type=Plan.PlanType.PEI,
            start_date=date(2025, 1, 1),
            end_date=date(2034, 12, 31),
        )
        artifact = PlanArtifact.objects.create(
            plan=plan,
            artifact_type=PlanArtifact.ArtifactType.OBJECTIVE,
            code="OE 01",
            title="Capacitação continuada",
        )
        self.action = StrategicAction.objects.create(
            artifact=artifact,
            coordinating_unit=unit,
            code="AE 01.01",
            title="Implementar programa de capacitação",
            due_date=date(2026, 12, 31),
        )
        self.unit = unit
        self.artifact = artifact

    def test_dashboard_requires_login_and_loads_for_authorized_user(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.client.login(username="copin", password="senha-segura")
        response = self.client.get("/")
        self.assertContains(response, "<h1>Painel</h1>", html=False)
        self.assertContains(response, "AE 01.01")
        self.assertContains(response, ">Planos</summary>", html=False)
        self.assertContains(response, f'href="/pei/?plan={self.artifact.plan_id}"', html=False)
        self.assertContains(response, ">Execução<", html=False)
        self.assertContains(response, 'href="/riscos/"', html=False)

    def test_pei_overview_connects_strategy_to_action_plan(self):
        self.client.login(username="copin", password="senha-segura")
        response = self.client.get("/pei/")
        self.assertContains(response, "Exploração dos planos")
        self.assertContains(response, "Capacitação continuada")
        self.assertContains(response, "AE 01.01")
        self.assertContains(response, "Abrir plano de ação")
        self.assertContains(response, "Ver metas e indicadores deste objetivo")
        self.assertContains(response, f'href="/planos-de-acao/{self.action.id}/"', html=False)

    def test_plans_menu_lists_registered_active_plans(self):
        other_plan = Plan.objects.create(
            name="Plano Plurianual", acronym="PPA", plan_type=Plan.PlanType.PPA,
            start_date=date(2026, 1, 1), end_date=date(2029, 12, 31),
        )
        inactive_plan = Plan.objects.create(
            name="Plano anterior", acronym="ANT", plan_type=Plan.PlanType.OTHER,
            start_date=date(2020, 1, 1), end_date=date(2024, 12, 31), active=False,
        )
        self.client.login(username="copin", password="senha-segura")
        response = self.client.get(f"/pei/?plan={other_plan.id}")
        self.assertContains(response, f'href="/pei/?plan={self.artifact.plan_id}"', html=False)
        self.assertContains(response, f'href="/pei/?plan={other_plan.id}" aria-current="page"', html=False)
        self.assertContains(response, "PPA · Plano Plurianual")
        self.assertContains(response, "ANT · Plano anterior")
        self.assertNotContains(response, f'href="/pei/?plan={inactive_plan.id}"', html=False)

    def test_indicator_measurement_updates_period_signal_and_history(self):
        target = StrategicTarget.objects.create(
            artifact=self.artifact,
            code="Mt 01.1",
            description="Capacitar 70% dos servidores no período.",
            target_value="70%",
            reference_period="2026",
        )
        indicator = Indicator.objects.create(
            code="IE 01.1",
            name="Percentual de servidores capacitados",
            frequency=Indicator.Frequency.ANNUAL,
            direction=Indicator.Direction.HIGHER_IS_BETTER,
            responsible_unit=self.unit,
        )
        indicator.artifacts.add(self.artifact)
        indicator.targets.add(target)
        self.client.login(username="copin", password="senha-segura")

        response = self.client.get("/indicadores/")
        self.assertContains(response, "Metas e indicadores")
        self.assertContains(response, "IE 01.1")
        self.assertContains(response, "Registrar aferição")

        response = self.client.post(
            f"/indicadores/{indicator.id}/",
            {
                "reference_period": "[DEMONSTRAÇÃO] Exercício 2026",
                "measured_value": "63",
                "expected_value": "70",
                "source_reference": "[DEMONSTRAÇÃO] Planilha fictícia",
                "note": "[DEMONSTRAÇÃO] Valor criado para testar o semáforo.",
            },
        )
        self.assertEqual(response.status_code, 302)
        measurement = IndicatorMeasurement.objects.get(indicator=indicator)
        self.assertEqual(measurement.recorded_by, self.user)
        self.assertEqual(measurement.expected_value, 70)

        response = self.client.get(f"/indicadores/{indicator.id}/")
        self.assertContains(response, "Atenção")
        self.assertContains(response, "90%")
        self.assertContains(response, "[DEMONSTRAÇÃO] Planilha fictícia")
        self.assertContains(response, "Anexar evidência da aferição")
        self.assertContains(response, 'enctype="multipart/form-data"', html=False)

    def test_report_cycle_submission_validation_and_closure(self):
        validator = User.objects.create_user(username="validador", password="senha-segura")
        self.client.login(username="copin", password="senha-segura")
        response = self.client.post(
            "/relatorios/",
            {
                "name": "[DEMONSTRAÇÃO] Relatório anual 2026",
                "plan": self.artifact.plan_id,
                "period_start": "2026-01-01",
                "period_end": "2026-12-31",
                "due_date": "2027-01-20",
                "participating_units": [self.unit.id],
            },
        )
        self.assertEqual(response.status_code, 302)
        cycle = ReportCycle.objects.get()
        report = SectorReport.objects.get(cycle=cycle, unit=self.unit)

        response = self.client.post(
            f"/relatorios/{cycle.id}/setores/{report.id}/",
            {
                "operation": "submit",
                "executive_summary": "[DEMONSTRAÇÃO] Resultados fictícios do período.",
                "complements": "[DEMONSTRAÇÃO] Sem complementos.",
                "next_steps": "[DEMONSTRAÇÃO] Prosseguir com as atividades.",
                "management_decision_needed": "",
                "validator": validator.id,
            },
        )
        self.assertEqual(response.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.status, SectorReport.Status.SUBMITTED)
        self.assertEqual(report.snapshot["action_count"], 1)

        self.client.login(username="validador", password="senha-segura")
        response = self.client.post(
            f"/relatorios/{cycle.id}/setores/{report.id}/",
            {"operation": "validate", "decision": "APPROVE", "comment": "[DEMONSTRAÇÃO] Aprovado."},
        )
        self.assertEqual(response.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.status, SectorReport.Status.APPROVED)

        self.client.login(username="copin", password="senha-segura")
        self.client.post(f"/relatorios/{cycle.id}/", {"operation": "consolidate"})
        cycle.refresh_from_db()
        report.refresh_from_db()
        self.assertEqual(cycle.status, ReportCycle.Status.CONSOLIDATING)
        self.assertEqual(report.status, SectorReport.Status.CONSOLIDATED)
        self.client.post(f"/relatorios/{cycle.id}/", {"operation": "close"})
        cycle.refresh_from_db()
        self.assertEqual(cycle.status, ReportCycle.Status.CLOSED)

    def test_risk_level_uses_probability_times_impact(self):
        risk = Risk.objects.create(
            action=self.action,
            owner=self.user,
            title="Contingenciamento orçamentário",
            cause="Restrição de recursos",
            probability=4,
            impact=5,
        )
        self.assertEqual(risk.level, 20)

    def test_user_can_start_an_action_plan_and_add_an_activity(self):
        self.client.login(username="copin", password="senha-segura")
        detail_url = f"/planos-de-acao/{self.action.id}/"

        response = self.client.post(detail_url, {"operation": "start_plan"})
        self.assertEqual(response.status_code, 302)
        action_plan = ActionPlan.objects.get(action=self.action)
        self.assertEqual(action_plan.manager, self.user)

        response = self.client.get(detail_url)
        self.assertContains(response, "Esta atividade demandará recurso financeiro?")
        self.assertContains(response, "Peso distribuído")
        self.assertContains(response, "Peso distribuído</span><strong>0%</strong>", html=False)
        self.assertContains(response, "A Ação Estratégica deve ser desdobrada em atividades ou tarefas")
        self.assertContains(response, "Peso na Ação Estratégica")
        self.assertContains(response, 'value="NAO"')
        self.assertContains(response, 'value="SIM"')

        response = self.client.post(
            detail_url,
            {
                "operation": "add_activity",
                "title": "Elaborar diagnóstico de capacitação",
                "description": "Mapear competências prioritárias.",
                "executor": self.user.id,
                "weight": "40",
                "start_date": "2026-05-01",
                "end_date": "2026-06-30",
                "progress": "25",
                "status": StrategicAction.Status.IN_PROGRESS,
                "expected_delivery": "Relatório técnico",
                "requires_financial_resource": "SIM",
                "planned_cost": "1200.00",
                "disbursed_cost": "450.00",
                "funding_source": "FAF",
                "financial_responsible_unit": self.action.coordinating_unit_id,
                "financial_reference": "Processo de demonstração",
            },
        )
        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(action_plan=action_plan)
        self.assertEqual(activity.weight, 40)
        self.assertEqual(activity.start_date, date(2026, 5, 1))
        self.assertEqual(activity.end_date, date(2026, 6, 30))
        self.assertEqual(activity.funding_source, "FAF")
        self.action.refresh_from_db()
        self.assertEqual(self.action.progress, 10)

        response = self.client.get(detail_url)
        self.assertContains(response, "R$ 1.200,00")
        self.assertContains(response, "Peso distribuído</span><strong>40%</strong>", html=False)
        self.assertContains(response, "25%</td>", html=False)
        self.assertNotContains(response, "40,00%")
        self.assertNotContains(response, "25,00%")

    def test_adding_activity_rebalances_weights_and_rejects_more_than_100(self):
        self.client.login(username="copin", password="senha-segura")
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        first = Activity.objects.create(
            action_plan=action_plan, executor=self.user, title="Primeira",
            weight=Decimal("60"), progress=Decimal("50"),
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 10), position=1,
        )
        second = Activity.objects.create(
            action_plan=action_plan, executor=self.user, title="Segunda",
            weight=Decimal("40"), progress=Decimal("25"),
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 10), position=2,
        )
        detail_url = f"/planos-de-acao/{self.action.id}/"
        payload = {
            "operation": "add_activity", "title": "Terceira", "executor": self.user.id,
            "weight": "25", "start_date": "2026-01-01", "end_date": "2026-01-10",
            "progress": "20", "status": StrategicAction.Status.IN_PROGRESS,
            "requires_financial_resource": "NAO",
        }
        response = self.client.post(detail_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirme a redistribuição dos pesos")
        self.assertEqual(action_plan.activities.count(), 2)

        response = self.client.post(detail_url, {**payload, "confirm_rebalance": "1"})
        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        second.refresh_from_db()
        self.action.refresh_from_db()
        self.assertEqual(first.weight, Decimal("45"))
        self.assertEqual(second.weight, Decimal("30"))
        self.assertEqual(self.action.progress, Decimal("35"))
        self.assertContains(self.client.get(detail_url), "Peso distribuído</span><strong>100%</strong>", html=False)

        response = self.client.post(detail_url, {**payload, "weight": "101"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(action_plan.activities.count(), 3)

    def test_user_can_edit_move_and_delete_an_activity(self):
        self.client.login(username="copin", password="senha-segura")
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        first = Activity.objects.create(
            action_plan=action_plan,
            executor=self.user,
            title="Primeira",
            weight=40,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 10),
            position=1,
        )
        second = Activity.objects.create(
            action_plan=action_plan,
            executor=self.user,
            title="Segunda",
            weight=20,
            start_date=date(2026, 1, 11),
            end_date=date(2026, 1, 20),
            position=2,
        )
        detail_url = f"/planos-de-acao/{self.action.id}/"
        response = self.client.get(f"{detail_url}atividades/{first.id}/editar/")
        self.assertContains(response, 'value="2026-01-01"')
        self.assertContains(response, 'value="2026-01-10"')

        self.client.post(f"{detail_url}atividades/{second.id}/mover/acima/")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(second.position, 1)
        self.assertEqual(first.position, 2)

        response = self.client.post(
            f"{detail_url}atividades/{first.id}/editar/",
            {
                "title": "Primeira revisada",
                "description": "Texto atualizado",
                "executor": self.user.id,
                "weight": "40",
                "start_date": "2026-01-01",
                "end_date": "2026-01-15",
                "progress": "30",
                "status": StrategicAction.Status.IN_PROGRESS,
                "expected_delivery": "Nota técnica",
                "requires_financial_resource": "SIM",
                "planned_cost": "100",
                "disbursed_cost": "25",
                "funding_source": "0500",
                "funding_source_other": "",
                "financial_responsible_unit": self.action.coordinating_unit_id,
                "financial_reference": "Referência",
            },
        )
        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        self.assertEqual(first.title, "Primeira revisada")
        self.assertEqual(first.disbursed_cost, 25)

        response = self.client.post(f"{detail_url}atividades/{first.id}/excluir/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Activity.objects.filter(pk=first.id).exists())

    def test_user_can_follow_up_activity_with_evidence_blocker_and_risk(self):
        self.client.login(username="copin", password="senha-segura")
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(
            action_plan=action_plan,
            executor=self.user,
            title="Consolidar diagnóstico",
            weight=100,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 6, 30),
        )
        follow_up_url = f"/planos-de-acao/{self.action.id}/atividades/{activity.id}/acompanhar/"

        response = self.client.post(
            follow_up_url,
            {
                "operation": "add_evidence",
                "evidence-title": "Ata da reunião",
                "evidence-evidence_type": ActivityEvidence.EvidenceType.SEI,
                "evidence-description": "Validação realizada com as unidades.",
                "evidence-reference": "SEI 0001/2026",
                "evidence-url": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ActivityEvidence.objects.filter(activity=activity).count(), 1)

        response = self.client.post(
            follow_up_url,
            {
                "operation": "add_blocker",
                "blocker-description": "Unidade não enviou os dados.",
                "blocker-resolution_owner": self.user.id,
                "blocker-expected_resolution_date": "2026-06-10",
                "blocker-status": ActivityBlocker.Status.IN_TREATMENT,
                "blocker-resolution_note": "Cobrança encaminhada.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ActivityBlocker.objects.filter(activity=activity).count(), 1)

        response = self.client.post(
            follow_up_url,
            {
                "operation": "add_risk",
                "risk-title": "Atraso na consolidação",
                "risk-cause": "Dados incompletos",
                "risk-owner": self.user.id,
                "risk-probability": 3,
                "risk-impact": 4,
                "risk-status": Risk.Status.IN_TREATMENT,
                "risk-treatment": "Mitigar",
                "risk-preventive_measure": "Monitoramento semanal",
                "risk-contingency_measure": "Escalonar à chefia",
            },
        )
        self.assertEqual(response.status_code, 302)
        risk = Risk.objects.get(activity=activity)
        self.assertEqual(risk.action, self.action)
        self.assertEqual(risk.level, 12)

        response = self.client.get(follow_up_url)
        self.assertContains(response, "Ata da reunião")
        self.assertContains(response, "Unidade não enviou os dados")
        self.assertContains(response, "Atraso na consolidação")

    def test_risk_map_covers_identification_treatment_materialization_and_acceptance(self):
        self.client.login(username="copin", password="senha-segura")
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(
            action_plan=action_plan,
            executor=self.user,
            title="Aplicar questionário",
            weight=100,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 6, 30),
        )
        map_url = f"/planos-de-acao/{self.action.id}/riscos/"
        response = self.client.post(
            map_url,
            {
                "activity": activity.id,
                "title": "Baixa adesão",
                "cause": "Conflito de agenda",
                "owner": self.user.id,
                "probability": 3,
                "impact": 4,
                "occurrence_timing": Risk.OccurrenceTiming.ANY_TIME,
                "trigger_description": "Atraso no retorno das unidades.",
                "treatment_decision": RiskTreatment.Decision.MITIGATE,
                "treatment_due_date": "2026-06-15",
                "preventive_measure": "Acompanhar respostas",
                "contingency_measure": "Escalonar à chefia",
            },
        )
        self.assertEqual(response.status_code, 302)
        risk = Risk.objects.get(title="Baixa adesão")
        self.assertEqual(risk.status, Risk.Status.IN_TREATMENT)
        self.assertEqual(risk.occurrence_timing_summary, "Pode ocorrer a qualquer momento")
        self.assertEqual(RiskAssessment.objects.get(risk=risk).level, 12)
        self.assertEqual(RiskTreatment.objects.get(risk=risk).decision, RiskTreatment.Decision.MITIGATE)

        detail_url = f"{map_url}{risk.id}/"
        response = self.client.get(detail_url)
        self.assertContains(response, "O que você deseja alterar?")
        self.assertContains(response, "Editar identificação e responsabilidade")
        self.assertContains(response, "Reavaliar classificação")

        response = self.client.post(
            detail_url,
            {
                "operation": "update_identity",
                "identity-title": "Baixa adesão revisada",
                "identity-cause": "Conflito de agenda e comunicação insuficiente",
                "identity-activity": activity.id,
                "identity-owner": self.user.id,
            },
        )
        self.assertEqual(response.status_code, 302)
        risk.refresh_from_db()
        self.assertEqual(risk.title, "Baixa adesão revisada")
        self.assertEqual(risk.cause, "Conflito de agenda e comunicação insuficiente")

        response = self.client.post(
            detail_url,
            {
                "operation": "update_timing",
                "timing-occurrence_timing": Risk.OccurrenceTiming.EXPOSURE_WINDOW,
                "timing-exposure_start_date": "2026-05-15",
                "timing-exposure_end_date": "2026-06-30",
                "timing-expected_occurrence_date": "",
                "timing-trigger_description": "Enquanto as unidades respondem ao levantamento.",
            },
        )
        self.assertEqual(response.status_code, 302)
        risk.refresh_from_db()
        self.assertEqual(risk.occurrence_timing, Risk.OccurrenceTiming.EXPOSURE_WINDOW)
        self.assertEqual(risk.occurrence_timing_summary, "De 15/05/2026 a 30/06/2026")

        response = self.client.post(
            detail_url,
            {
                "operation": "materialize",
                "materialization-occurred_on": "2026-06-20",
                "materialization-description": "O prazo terminou sem todas as respostas.",
                "materialization-actual_impact": "Consolidação adiada.",
                "materialization-actions_taken": "Chefias comunicadas.",
                "materialization-evidence_reference": "SEI 0002/2026",
            },
        )
        self.assertEqual(response.status_code, 302)
        risk.refresh_from_db()
        self.assertEqual(risk.status, Risk.Status.MATERIALIZED)
        self.assertEqual(RiskMaterialization.objects.filter(risk=risk).count(), 1)

        response = self.client.post(
            detail_url,
            {
                "operation": "accept",
                "acceptance-authority": self.user.id,
                "acceptance-decision": RiskAcceptance.Decision.ACCEPTED,
                "acceptance-justification": "Impacto dentro da alçada definida.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RiskAcceptance.objects.filter(risk=risk).count(), 1)

        response = self.client.post(
            detail_url,
            {
                "operation": "accept",
                "acceptance-authority": self.user.id,
                "acceptance-decision": RiskAcceptance.Decision.ACCEPTED_WITH_RESERVATIONS,
                "acceptance-justification": "Aceite condicionado à complementação das evidências.",
                "acceptance-remedial_actions": "Anexar a manifestação das unidades pendentes.",
                "acceptance-remediation_responsible": self.user.id,
                "acceptance-reevaluation_due_date": "2026-07-10",
            },
        )
        self.assertEqual(response.status_code, 302)
        conditional_acceptance = RiskAcceptance.objects.filter(
            risk=risk,
            decision=RiskAcceptance.Decision.ACCEPTED_WITH_RESERVATIONS,
        ).get()
        self.assertEqual(
            conditional_acceptance.remedial_actions,
            "Anexar a manifestação das unidades pendentes.",
        )
        self.assertEqual(conditional_acceptance.remediation_responsible, self.user)
        risk.refresh_from_db()
        self.assertEqual(risk.status, Risk.Status.IN_TREATMENT)

        response = self.client.post(
            detail_url,
            {
                "operation": "submit_remediation",
                "acceptance_id": conditional_acceptance.id,
                "remediation-completion_summary": "As manifestações pendentes foram juntadas ao processo.",
                "remediation-evidence_reference": "SEI 0003/2026",
            },
        )
        self.assertEqual(response.status_code, 302)
        submission = RiskRemediationSubmission.objects.get(acceptance=conditional_acceptance)
        self.assertEqual(submission.submitted_by, self.user)
        self.assertEqual(submission.evidence_reference, "SEI 0003/2026")

        response = self.client.post(
            detail_url,
            {
                "operation": "accept",
                "acceptance-authority": self.user.id,
                "acceptance-decision": RiskAcceptance.Decision.ACCEPTED,
                "acceptance-justification": "Risco residual aceito após o cumprimento das diligências.",
            },
        )
        self.assertEqual(response.status_code, 302)
        risk.refresh_from_db()
        self.assertEqual(risk.status, Risk.Status.MONITORING)

        response = self.client.get(detail_url)
        self.assertContains(response, "Diligências reapresentadas")
        self.assertContains(response, "SEI 0003/2026")

        response = self.client.get(map_url)
        self.assertContains(response, "Mapa de riscos")
        self.assertContains(response, "Baixa adesão")
        self.assertContains(response, "Decidir aceite")
        self.assertContains(response, "Prazo para concluir o tratamento (opcional)")

        response = self.client.get("/riscos/")
        self.assertContains(response, "Riscos consolidados")
        self.assertContains(response, "Baixa adesão revisada")
        self.assertContains(response, "Em monitoramento")
