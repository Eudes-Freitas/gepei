import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Group, Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

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
    UserProfile,
)


class LoadPeiIndicatorsTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="SESED", acronym="SESED")
        self.unit = OrganizationalUnit.objects.create(
            organization=organization, name="Coordenadoria de Programas para a Cidadania", acronym="CPCID",
            unit_type=OrganizationalUnit.UnitType.UNIT,
        )
        plan = Plan.objects.create(
            name="Plano Estratégico Institucional", acronym="PEI", plan_type=Plan.PlanType.PEI,
            start_date=date(2025, 1, 1), end_date=date(2034, 12, 31),
        )
        self.objectives = {}
        for number in ("12", "13"):
            objective = PlanArtifact.objects.create(
                plan=plan, artifact_type=PlanArtifact.ArtifactType.OBJECTIVE, code=f"OE {number}", title=f"Objetivo {number}"
            )
            project = PlanArtifact.objects.create(
                plan=plan, parent=objective, artifact_type=PlanArtifact.ArtifactType.PROJECT, title=f"Projeto {number}"
            )
            StrategicAction.objects.create(
                artifact=project, code=f"AE {number}.1", title="Ação", coordinating_unit=self.unit
            )
            self.objectives[number] = objective

    def test_indicators_and_targets_are_linked_by_number_to_objective(self):
        call_command("load_pei_indicators", stdout=StringIO())

        objective = self.objectives["13"]
        indicators = Indicator.objects.filter(artifacts=objective).order_by("code")
        self.assertEqual([i.code for i in indicators], [f"IE 13.{n}" for n in range(1, 6)])
        self.assertEqual(StrategicTarget.objects.filter(artifact=objective).count(), 5)
        indicator = Indicator.objects.get(code="IE 13.3")
        self.assertEqual(indicator.indicator_type, Indicator.IndicatorType.RESULT)
        self.assertEqual([t.code for t in indicator.targets.all()], ["Mt 13.3"])
        self.assertEqual(indicator.targets.get().artifact, objective)
        self.assertEqual(indicator.responsible_unit, self.unit)
        self.assertIn("participantes engajados", indicator.formula)
        self.assertEqual(Indicator.objects.get(code="IE 12.2").direction, Indicator.Direction.LOWER_IS_BETTER)
        self.assertEqual(Indicator.objects.count(), 10)

    def test_load_is_idempotent_and_renames_legacy_result_code(self):
        legacy = Indicator.objects.create(code="IR 13.3", name="Antigo")
        legacy.artifacts.add(self.objectives["13"])

        call_command("load_pei_indicators", stdout=StringIO())
        call_command("load_pei_indicators", stdout=StringIO())

        self.assertEqual(Indicator.objects.count(), 10)
        legacy.refresh_from_db()
        self.assertEqual(legacy.code, "IE 13.3")
        self.assertEqual(StrategicTarget.objects.count(), 10)


class UserAndGroupManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", password="senha-segura")
        self.organization = Organization.objects.create(name="SESED", acronym="SESED")
        self.unit = OrganizationalUnit.objects.create(
            organization=self.organization,
            name="Coordenadoria de Planejamento Institucional",
            acronym="COPIN",
            unit_type=OrganizationalUnit.UnitType.SECTOR,
        )
        self.group = Group.objects.create(name="Gestores")

    def test_pages_require_permission(self):
        User.objects.create_user(username="comum", password="senha-segura")
        self.client.login(username="comum", password="senha-segura")
        self.assertEqual(self.client.get("/usuarios/novo/").status_code, 403)
        self.assertEqual(self.client.get("/usuarios/grupos/novo/").status_code, 403)

    def test_user_menu_links_to_users_and_groups_lists(self):
        self.client.login(username="admin", password="senha-segura")
        response = self.client.get("/")
        self.assertContains(response, 'href="/usuarios/"', html=False)
        self.assertContains(response, 'href="/usuarios/grupos/"', html=False)
        self.assertNotContains(response, "Cadastrar perfil")

    def test_user_list_shows_registered_users_with_group_and_unit(self):
        member = User.objects.create_user(username="ana@exemplo.gov.br", email="ana@exemplo.gov.br", first_name="Ana", last_name="Lima")
        member.groups.add(self.group)
        UserProfile.objects.create(user=member, unit=self.unit)
        self.client.login(username="admin", password="senha-segura")
        response = self.client.get("/usuarios/")
        self.assertContains(response, "Ana Lima")
        self.assertContains(response, "Gestores")
        self.assertContains(response, "COPIN")
        self.assertContains(response, "Cadastrar usuário")
        self.assertContains(response, f'href="/usuarios/{member.id}/editar/"', html=False)

    def test_edit_user_changes_group_unit_and_keeps_password_when_blank(self):
        member = User.objects.create_user(username="ana@exemplo.gov.br", email="ana@exemplo.gov.br", password="antiga-123", first_name="Ana")
        other_group = Group.objects.create(name="Consulta")
        self.client.login(username="admin", password="senha-segura")
        response = self.client.post(
            f"/usuarios/{member.id}/editar/",
            {"name": "Ana Lima", "email": "ana.lima@exemplo.gov.br", "password": "", "group": other_group.id, "unit_name": "Setor Novo", "is_active": "0"},
        )
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.get_full_name(), "Ana Lima")
        self.assertEqual(member.username, "ana.lima@exemplo.gov.br")
        self.assertTrue(member.check_password("antiga-123"))
        self.assertFalse(member.is_active)
        self.assertEqual(list(member.groups.all()), [other_group])
        self.assertEqual(member.profile.unit.name, "Setor Novo")

    def test_delete_user_and_protect_users_with_records(self):
        removable = User.objects.create_user(username="sem-registro")
        busy = User.objects.create_user(username="com-registro")
        self.client.login(username="admin", password="senha-segura")
        self.assertContains(self.client.get(f"/usuarios/{removable.id}/excluir/"), "Excluir usuário")
        self.assertEqual(self.client.post(f"/usuarios/{removable.id}/excluir/").status_code, 302)
        self.assertFalse(User.objects.filter(pk=removable.pk).exists())

        plan = Plan.objects.create(name="Plano", acronym="PEI", plan_type=Plan.PlanType.PEI, start_date=date(2025, 1, 1), end_date=date(2034, 12, 31))
        artifact = PlanArtifact.objects.create(plan=plan, artifact_type=PlanArtifact.ArtifactType.PROJECT, title="Projeto")
        action = StrategicAction.objects.create(artifact=artifact, code="AE 1.1", title="Ação", coordinating_unit=self.unit)
        ActionPlan.objects.create(action=action, manager=busy)
        self.client.post(f"/usuarios/{busy.id}/excluir/")
        self.assertTrue(User.objects.filter(pk=busy.pk).exists())

        self.client.post(f"/usuarios/{self.admin.id}/excluir/")
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_group_list_edit_and_delete(self):
        view_perm = Permission.objects.get(codename="view_risk")
        self.group.permissions.add(view_perm)
        self.client.login(username="admin", password="senha-segura")
        response = self.client.get("/usuarios/grupos/")
        self.assertContains(response, "Gestores")
        self.assertContains(response, "Cadastrar perfil")

        response = self.client.get(f"/usuarios/grupos/{self.group.id}/editar/")
        self.assertContains(response, "Editar perfil")
        self.assertContains(response, f'value="{view_perm.id}" checked', html=False)

        new_perm = Permission.objects.get(codename="add_risk")
        response = self.client.post(f"/usuarios/grupos/{self.group.id}/editar/", {"name": "Gestores RH", "permissions": [new_perm.id]})
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, "Gestores RH")
        self.assertEqual(list(self.group.permissions.all()), [new_perm])

        self.assertEqual(self.client.post(f"/usuarios/grupos/{self.group.id}/excluir/").status_code, 302)
        self.assertFalse(Group.objects.filter(pk=self.group.pk).exists())

    def test_unit_suggestions_return_close_matches(self):
        self.client.login(username="admin", password="senha-segura")
        names = [item["name"] for item in self.client.get("/usuarios/setores/?q=copin").json()["results"]]
        self.assertEqual(names, [self.unit.name])
        names = [item["name"] for item in self.client.get("/usuarios/setores/?q=Coordenadora de Planejamento").json()["results"]]
        self.assertIn(self.unit.name, names)

    def test_create_user_with_existing_unit(self):
        self.client.login(username="admin", password="senha-segura")
        response = self.client.post(
            "/usuarios/novo/",
            {"name": "Maria da Silva", "email": "Maria@exemplo.gov.br", "password": "senha-forte-1", "group": self.group.id, "unit_name": "copin"},
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="maria@exemplo.gov.br")
        self.assertEqual(user.get_full_name(), "Maria da Silva")
        self.assertEqual(user.profile.unit, self.unit)
        self.assertEqual(list(user.groups.all()), [self.group])
        self.assertEqual(OrganizationalUnit.objects.count(), 1)

    def test_create_user_registers_new_unit_when_not_found(self):
        self.client.login(username="admin", password="senha-segura")
        self.client.post(
            "/usuarios/novo/",
            {"name": "João", "email": "joao@exemplo.gov.br", "password": "senha-forte-1", "group": self.group.id, "unit_name": "Gerência de Dados"},
        )
        user = User.objects.get(username="joao@exemplo.gov.br")
        self.assertEqual(user.profile.unit.name, "Gerência de Dados")
        self.assertEqual(user.profile.unit.unit_type, OrganizationalUnit.UnitType.SECTOR)
        self.assertEqual(user.profile.unit.organization, self.organization)

    def test_create_user_rejects_duplicate_email(self):
        self.client.login(username="admin", password="senha-segura")
        response = self.client.post(
            "/usuarios/novo/",
            {"name": "Admin 2", "email": "ADMIN", "password": "x", "group": self.group.id, "unit_name": "COPIN"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_group_page_lists_permissions_by_module_and_saves_selection(self):
        self.client.login(username="admin", password="senha-segura")
        response = self.client.get("/usuarios/grupos/novo/")
        self.assertContains(response, "Planejamento estratégico")
        self.assertContains(response, "Visualizar")
        self.assertContains(response, "Filtrar permissões...")

        chosen = Permission.objects.get(codename="view_risk")
        response = self.client.post("/usuarios/grupos/novo/", {"name": "Analistas", "permissions": [chosen.id, "999999"]})
        self.assertEqual(response.status_code, 302)
        group = Group.objects.get(name="Analistas")
        self.assertEqual(list(group.permissions.all()), [chosen])


class LoginAndProfileTests(TestCase):
    def setUp(self):
        self.person = User.objects.create_user(
            username="ana@exemplo.gov.br", email="ana@exemplo.gov.br", password="senha-segura", first_name="Ana", last_name="Lima"
        )

    def test_login_accepts_email_or_full_name(self):
        for typed in ["ana@exemplo.gov.br", "ANA@exemplo.gov.br", "Ana Lima", "ana lima"]:
            self.client.logout()
            response = self.client.post("/login/", {"username": typed, "password": "senha-segura"})
            self.assertEqual(response.status_code, 302, typed)
        self.client.logout()
        response = self.client.post("/login/", {"username": "Ana Lima", "password": "errada"})
        self.assertEqual(response.status_code, 200)

    def test_login_by_name_is_refused_when_name_is_ambiguous(self):
        User.objects.create_user(username="ana2@exemplo.gov.br", password="senha-segura", first_name="Ana", last_name="Lima")
        response = self.client.post("/login/", {"username": "Ana Lima", "password": "senha-segura"})
        self.assertEqual(response.status_code, 200)

    def test_user_edits_only_own_name_email_and_password(self):
        self.client.login(username="ana@exemplo.gov.br", password="senha-segura")
        response = self.client.get("/minha-conta/")
        self.assertEqual(list(response.context["form"].fields), ["name", "email", "password"])
        response = self.client.post(
            "/minha-conta/", {"name": "Ana Maria Lima", "email": "ana.maria@exemplo.gov.br", "password": "nova-senha-123"}
        )
        self.assertRedirects(response, "/minha-conta/")
        self.person.refresh_from_db()
        self.assertEqual(self.person.get_full_name(), "Ana Maria Lima")
        self.assertEqual(self.person.username, "ana.maria@exemplo.gov.br")
        self.assertTrue(self.person.check_password("nova-senha-123"))
        self.assertEqual(self.client.get("/").status_code, 200)  # sessão preservada após trocar a senha


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
        UserProfile.objects.create(user=self.user, unit=unit)

    def test_non_administrator_only_sees_own_sector(self):
        other_unit = OrganizationalUnit.objects.create(
            organization=self.unit.organization, name="Outro Setor", acronym="OUTRO", unit_type=OrganizationalUnit.UnitType.SECTOR
        )
        other_action = StrategicAction.objects.create(
            artifact=self.artifact, coordinating_unit=other_unit, code="AE 09.09", title="Ação de outro setor"
        )
        self.client.login(username="copin", password="senha-segura")
        response = self.client.get("/planos-de-acao/")
        self.assertContains(response, "AE 01.01")
        self.assertNotContains(response, "AE 09.09")
        self.assertEqual(self.client.get(f"/planos-de-acao/{other_action.id}/").status_code, 404)

        admin_group = Group.objects.create(name="Administrador")
        self.user.groups.add(admin_group)
        response = self.client.get("/planos-de-acao/")
        self.assertContains(response, "AE 09.09")
        self.assertEqual(self.client.get(f"/planos-de-acao/{other_action.id}/").status_code, 200)

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

        response = self.client.get("/metas/")
        self.assertContains(response, "<h1>Metas</h1>", html=False)
        self.assertContains(response, "Mt 01.1")
        self.assertContains(response, f'href="/indicadores/{indicator.id}/"', html=False)

        response = self.client.get("/indicadores/")
        self.assertContains(response, "<h1>Indicadores</h1>", html=False)
        self.assertContains(response, "IE 01.1")
        self.assertContains(response, "Registrar aferição")

        response = self.client.post(
            f"/indicadores/{indicator.id}/",
            {
                "measured_by": self.user.id,
                "baseline_value": "40",
                "baseline_date": "2025-12-31",
                "period_start": "2026-01-01",
                "period_end": "2026-06-30",
                "measured_value": "63",
                "expected_value": "999",
                "source_reference": "[DEMONSTRAÇÃO] Planilha fictícia",
                "note": "[DEMONSTRAÇÃO] Valor criado para testar o semáforo.",
            },
        )
        self.assertEqual(response.status_code, 302)
        measurement = IndicatorMeasurement.objects.get(indicator=indicator)
        self.assertEqual(measurement.recorded_by, self.user)
        # 40 -> 70 entre 31/12/2025 e 31/12/2034 (3287 dias); 181 dias decorridos: 40 + 30 * 181 / 3287.
        self.assertEqual(measurement.expected_value, Decimal("41.65"))
        self.assertEqual(measurement.reference_period, "01/01/2026 a 30/06/2026")
        self.assertEqual(str(measurement.baseline_date), "2025-12-31")
        self.assertEqual(measurement.measured_by, self.user)
        self.assertEqual(measurement.measured_unit, self.unit)
        self.assertEqual(measurement.baseline_value, "40")

        response = self.client.get(f"/indicadores/{indicator.id}/")
        self.assertContains(response, "Setor responsável")
        self.assertContains(response, "indicator-chart-data", html=False)
        self.assertContains(response, "vendor/highcharts.js", html=False)
        self.assertContains(response, "data-view-measurement", html=False)
        self.assertContains(response, 'type="date"', html=False)
        self.assertContains(response, "Conforme")
        self.assertContains(response, "[DEMONSTRAÇÃO] Planilha fictícia")
        self.assertContains(response, "Anexar evidência da aferição")
        self.assertContains(response, 'enctype="multipart/form-data"', html=False)

    def test_indicator_definition_can_be_edited_by_authorized_user(self):
        indicator = Indicator.objects.create(code="IE 02.1", name="Taxa de crescimento", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        self.client.login(username="copin", password="senha-segura")
        response = self.client.get(f"/indicadores/{indicator.id}/")
        self.assertNotContains(response, "data-open-definition-form>Editar")
        response = self.client.post(
            f"/indicadores/{indicator.id}/", {"operation": "edit_definition", "formula": "x", "direction": "MAIOR_MELHOR"}
        )
        self.assertEqual(response.status_code, 403)

        self.user.user_permissions.add(Permission.objects.get(codename="change_indicator"))
        response = self.client.get(f"/indicadores/{indicator.id}/")
        self.assertContains(response, "data-open-definition-form>Editar")
        response = self.client.post(
            f"/indicadores/{indicator.id}/",
            {
                "operation": "edit_definition",
                "indicator_type": "RESULTADO",
                "formula": "(A / B) x 100",
                "unit_of_measure": "%",
                "data_source": "Folha de pagamento",
                "baseline": "37%",
                "direction": "MAIOR_MELHOR",
            },
        )
        self.assertEqual(response.status_code, 302)
        indicator.refresh_from_db()
        self.assertEqual((indicator.formula, indicator.unit_of_measure, indicator.baseline), ("(A / B) x 100", "%", "37%"))

    def test_indicator_page_renders_legacy_measurement_without_responsible(self):
        indicator = Indicator.objects.create(code="IE 03.1", name="Indicador antigo", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        IndicatorMeasurement.objects.create(
            indicator=indicator, reference_period="2025", measured_value="5", recorded_by=self.user
        )
        self.client.login(username="copin", password="senha-segura")
        response = self.client.get(f"/indicadores/{indicator.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "copin")
        self.assertContains(response, "Setor responsável")

    def test_measurement_can_be_edited_by_authorized_user(self):
        indicator = Indicator.objects.create(code="IE 04.1", name="Indicador editável", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        measurement = IndicatorMeasurement.objects.create(
            indicator=indicator, reference_period="2026", measured_value="5", recorded_by=self.user
        )
        self.client.login(username="copin", password="senha-segura")
        self.assertNotContains(self.client.get(f"/indicadores/{indicator.id}/?editar={measurement.id}"), 'name="measurement_id"')

        self.user.user_permissions.add(Permission.objects.get(codename="change_indicatormeasurement"))
        response = self.client.get(f"/indicadores/{indicator.id}/?editar={measurement.id}")
        self.assertContains(response, f'name="measurement_id" value="{measurement.id}"', html=False)
        response = self.client.post(
            f"/indicadores/{indicator.id}/",
            {
                "measurement_id": measurement.id,
                "measured_by": self.user.id,
                "baseline_value": "2",
                "baseline_date": "2025-12-31",
                "period_start": "2026-01-01",
                "period_end": "2026-12-31",
                "measured_value": "9",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(IndicatorMeasurement.objects.filter(indicator=indicator).count(), 1)
        measurement.refresh_from_db()
        self.assertEqual((measurement.measured_value, measurement.baseline_value), ("9", "2"))
        self.assertEqual(measurement.reference_period, "01/01/2026 a 31/12/2026")

    def test_report_cycle_submission_validation_and_closure(self):
        validator = User.objects.create_user(username="validador", password="senha-segura")
        UserProfile.objects.create(user=validator, unit=self.unit)
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

    def test_activity_can_only_be_completed_with_an_evidence_attachment(self):
        self.client.login(username="copin", password="senha-segura")
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(
            action_plan=action_plan,
            executor=self.user,
            title="Entregar relatório",
            weight=100,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 6, 30),
        )
        edit_url = f"/planos-de-acao/{self.action.id}/atividades/{activity.id}/editar/"
        data = {
            "title": "Entregar relatório",
            "description": "",
            "executor": self.user.id,
            "weight": "100",
            "start_date": "2026-05-01",
            "end_date": "2026-06-30",
            "progress": "100",
            "status": StrategicAction.Status.COMPLETED,
            "expected_delivery": "",
            "requires_financial_resource": "NAO",
        }

        response = self.client.post(edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "registre ao menos uma evidência com anexo")
        activity.refresh_from_db()
        self.assertNotEqual(activity.status, StrategicAction.Status.COMPLETED)

        ActivityEvidence.objects.create(
            activity=activity,
            created_by=self.user,
            title="Relatório final",
            evidence_type=ActivityEvidence.EvidenceType.ATTACHMENT,
            attachment="activity_evidences/relatorio.pdf",
        )
        response = self.client.post(edit_url, data)
        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertEqual(activity.status, StrategicAction.Status.COMPLETED)

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

        evidence_data = {
            "operation": "add_evidence",
            "evidence-title": "Ata da reunião",
            "evidence-evidence_type": ActivityEvidence.EvidenceType.SEI,
            "evidence-description": "Validação realizada com as unidades.",
            "evidence-reference": "SEI 0001/2026",
            "evidence-url": "",
        }
        response = self.client.post(follow_up_url, evidence_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ActivityEvidence.objects.filter(activity=activity).count(), 0)

        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                follow_up_url,
                {**evidence_data, "evidence-attachment": SimpleUploadedFile("ata.pdf", b"%PDF-1.4 ata")},
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
