import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Group, Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from .forms import RiskTreatmentForm
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
    QuarterlySectorReport,
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

    def test_quadro_has_action_mapping_for_every_indicator(self):
        from .pei_indicator_data import INDICATOR_ACTION_CODES, INDICATOR_ROWS

        self.assertEqual({row[0] for row in INDICATOR_ROWS}, set(INDICATOR_ACTION_CODES))
        project = PlanArtifact.objects.get(parent=self.objectives["13"])
        action = StrategicAction.objects.create(
            artifact=project, code="AE 13.2", title="Formar conselhos", coordinating_unit=self.unit
        )
        call_command("load_pei_indicators", stdout=StringIO())
        self.assertEqual(StrategicTarget.objects.get(code="Mt 13.4").action, action)
        self.assertEqual(StrategicTarget.objects.get(code="Mt 12.2").action.code, "AE 12.1")


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

    def test_report_access_denied_returns_to_reports(self):
        self.client.force_login(self.person)
        response = self.client.get("/relatorios/trimestrais/1/")
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Você não tem permissão para visualizar este relatório.", status_code=403)
        self.assertContains(response, 'href="/relatorios/">Voltar para relatórios</a>', status_code=403)

        response = self.client.get("/usuarios/novo/")
        self.assertContains(response, 'href="/">Voltar ao painel</a>', status_code=403)

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
        self.user.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="core").exclude(codename__in=["change_indicator", "change_indicatormeasurement", "view_other_units"])
        )

    def test_risk_treatment_requires_an_explicit_response_without_blank_option(self):
        form = RiskTreatmentForm()
        self.assertEqual(
            [value for value, _ in form.fields["decision"].choices],
            ["ACEITAR", "MITIGAR", "EVITAR", "TRANSFERIR"],
        )
        self.assertTrue(form.fields["decision"].required)
        self.assertIn("decision", RiskTreatmentForm({"decision": "", "responsible": self.user.pk}).errors)

    def test_risk_sections_require_their_own_permissions(self):
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        risk = Risk.objects.create(
            action=self.action, owner=self.user, title="Risco restrito", cause="Teste", probability=2, impact=2
        )
        RiskAssessment.objects.create(risk=risk, probability=2, impact=2, author=self.user, notes="Nota sigilosa")
        self.assertTrue(action_plan.pk)
        limited = User.objects.create_user(username="limitado", password="senha-segura")
        UserProfile.objects.create(user=limited, unit=self.unit)
        limited.user_permissions.add(Permission.objects.get(codename="view_risk"))
        self.client.login(username="limitado", password="senha-segura")

        response = self.client.get(f"/planos-de-acao/{self.action.id}/riscos/{risk.id}/")
        self.assertContains(response, "Você não tem permissão para visualizar as avaliações")
        self.assertNotContains(response, "Nota sigilosa")
        self.assertNotContains(response, "Reavaliar classificação")
        response = self.client.post(
            f"/planos-de-acao/{self.action.id}/riscos/{risk.id}/",
            {"operation": "add_assessment", "assessment-assessment_type": "ATUAL", "assessment-probability": 5, "assessment-impact": 5},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(RiskAssessment.objects.filter(risk=risk).count(), 1)

        limited.user_permissions.add(Permission.objects.get(codename="view_riskassessment"))
        response = self.client.get(f"/planos-de-acao/{self.action.id}/riscos/{risk.id}/")
        self.assertContains(response, "Nota sigilosa")
        self.assertNotContains(response, "Reavaliar classificação")

        nobody = User.objects.create_user(username="semriscos", password="senha-segura")
        self.client.login(username="semriscos", password="senha-segura")
        self.assertEqual(self.client.get("/riscos/").status_code, 403)

    def test_risk_detail_opens_when_action_has_no_action_plan(self):
        risk = Risk.objects.create(
            action=self.action, owner=self.user, title="Risco sem plano", cause="Teste", probability=2, impact=2
        )
        self.client.login(username="copin", password="senha-segura")
        response = self.client.get(f"/planos-de-acao/{self.action.id}/riscos/{risk.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Risco sem plano")

    def test_modules_without_permission_are_blocked_and_hidden_from_menu(self):
        ActionPlan.objects.create(action=self.action, manager=self.user)
        only_risks = User.objects.create_user(username="soriscos", password="senha-segura")
        UserProfile.objects.create(user=only_risks, unit=self.unit)
        only_risks.user_permissions.add(Permission.objects.get(codename="view_risk"))
        self.client.login(username="soriscos", password="senha-segura")

        home = self.client.get("/")
        self.assertContains(home, 'href="/riscos/"')
        for hidden in ["/planos-de-acao/", "/metas/", "/indicadores/", "/relatorios/", "/pei/"]:
            self.assertNotContains(home, f'<a href="{hidden}"')
        for blocked in [
            "/planos-de-acao/",
            f"/planos-de-acao/{self.action.id}/",
            "/metas/",
            "/indicadores/",
            "/relatorios/",
            "/pei/",
        ]:
            self.assertEqual(self.client.get(blocked).status_code, 403, blocked)
        self.assertEqual(self.client.post(f"/planos-de-acao/{self.action.id}/", {"operation": "start_plan"}).status_code, 403)

    def test_view_only_profile_cannot_change_execution_or_reports(self):
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(
            action_plan=action_plan, executor=self.user, title="Ativ", weight=100,
            start_date=date(2026, 5, 1), end_date=date(2026, 6, 30),
        )
        viewer = User.objects.create_user(username="leitor", password="senha-segura")
        UserProfile.objects.create(user=viewer, unit=self.unit)
        viewer.user_permissions.add(*Permission.objects.filter(codename__startswith="view_", content_type__app_label="core"))
        self.client.login(username="leitor", password="senha-segura")
        detail = self.client.get(f"/planos-de-acao/{self.action.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "Nova atividade")
        self.assertEqual(self.client.get(f"/planos-de-acao/{self.action.id}/atividades/{activity.id}/editar/").status_code, 403)
        self.assertEqual(self.client.post(f"/planos-de-acao/{self.action.id}/atividades/{activity.id}/excluir/").status_code, 403)
        self.assertTrue(Activity.objects.filter(pk=activity.pk).exists())
        self.assertEqual(self.client.post("/relatorios/", {"name": "x"}).status_code, 403)

    def test_target_can_be_created_and_edited_with_permissions(self):
        indicator = Indicator.objects.create(code="IE 01.1", name="Percentual capacitado")
        indicator.artifacts.add(self.artifact)
        self.client.login(username="copin", password="senha-segura")
        page = self.client.get("/metas/")
        self.assertContains(page, "Nova meta")

        payload = {
            "artifact": self.artifact.id,
            "code": "Mt 01.9",
            "description": "Capacitar 100% dos servidores até 2034.",
            "target_value": "100%",
            "unit_of_measure": "%",
            "reference_period": "Anual",
            "indicators": [indicator.id],
        }
        response = self.client.post("/metas/", payload)
        self.assertEqual(response.status_code, 302)
        target = StrategicTarget.objects.get(code="Mt 01.9")
        self.assertEqual(target.artifact, self.artifact)
        self.assertEqual(list(target.indicators.all()), [indicator])

        response = self.client.get(f"/metas/?editar={target.id}")
        self.assertContains(response, "Alterar Mt 01.9")
        response = self.client.post("/metas/", {**payload, "target_id": target.id, "target_value": "90%", "indicators": []})
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertEqual(target.target_value, "90%")
        self.assertEqual(target.indicators.count(), 0)

        viewer = User.objects.create_user(username="leitormetas", password="senha-segura")
        UserProfile.objects.create(user=viewer, unit=self.unit)
        viewer.user_permissions.add(Permission.objects.get(codename="view_strategictarget"))
        self.client.login(username="leitormetas", password="senha-segura")
        self.assertNotContains(self.client.get("/metas/"), "Nova meta")
        self.assertEqual(self.client.post("/metas/", payload).status_code, 403)
        self.assertEqual(self.client.post("/metas/", {**payload, "target_id": target.id}).status_code, 403)
    def test_dashboard_performance_charts_show_measured_and_on_target_percentages(self):
        good = Indicator.objects.create(code="IE 01.1", name="Capacitados")
        bad = Indicator.objects.create(code="IE 01.2", name="Satisfação")
        none = Indicator.objects.create(code="IE 01.3", name="Sem aferição")
        for indicator in (good, bad, none):
            indicator.artifacts.add(self.artifact)
        for indicator, measured in ((good, "100"), (bad, "50")):
            IndicatorMeasurement.objects.create(
                indicator=indicator, reference_period="2026", measured_value=measured,
                expected_value=Decimal("100"), recorded_by=self.user,
            )
        target = StrategicTarget.objects.create(artifact=self.artifact, code="Mt 01.1", description="Capacitar todos")
        target.indicators.set([good, bad])
        self.client.login(username="copin", password="senha-segura")
        response = self.client.get("/")
        self.assertEqual(response.context["indicator_total"], 3)
        self.assertEqual(response.context["indicator_measured_pct"], 67)
        self.assertEqual(response.context["indicator_green_pct"], 50)
        self.assertEqual(response.context["signal_counts"]["red"], 1)
        self.assertEqual(response.context["target_counts"]["red"], 1)  # a meta vale pelo pior indicador aferido
        self.assertEqual(response.context["target_attention"][0]["code"], "Mt 01.1")
        self.assertContains(response, 'id="chart-measured"')
        self.assertContains(response, 'id="chart-targets"')
        self.assertContains(response, "/indicadores/?status=red")
    def test_dashboard_clicks_filter_the_destination(self):
        self.client.force_login(self.user)
        for code, value in (("good", "100"), ("attention", "95"), ("critical", "50"), ("empty", None)):
            indicator = Indicator.objects.create(code=code, name=code, responsible_unit=self.unit)
            indicator.artifacts.add(self.artifact)
            target = StrategicTarget.objects.create(artifact=self.artifact, code=code, description=code)
            target.indicators.add(indicator)
            if value:
                IndicatorMeasurement.objects.create(indicator=indicator, reference_period="2026", measured_value=value,
                    expected_value=Decimal("100"), recorded_by=self.user)
        StrategicTarget.objects.create(artifact=self.artifact, code="unlinked", description="Sem indicador")
        response = self.client.get("/")
        charts = response.context["performance_charts"]
        for point in charts["targets"]:
            destination = self.client.get(point["url"])
            self.assertEqual(destination.status_code, 200)
            self.assertEqual(len(destination.context["targets"]), point["y"])
        for point in charts["measured"] + charts["signal"]:
            destination = self.client.get(point["url"])
            self.assertEqual(len(destination.context["indicator_rows"]), point["y"])
        destination = self.client.get("/indicadores/?status=attention")
        self.assertEqual({row["indicator"].code for row in destination.context["indicator_rows"]}, {"attention", "critical"})
        destination = self.client.get("/metas/?status=unmeasured")
        self.assertEqual({target.code for target in destination.context["targets"]}, {"empty", "unlinked"})
        target_url = response.context["target_attention"][0]["url"]
        self.assertEqual(len(self.client.get(target_url).context["targets"]), 1)

    def test_dashboard_overdue_priority_and_objective_links(self):
        self.client.force_login(self.user)
        self.action.due_date = date(2020, 1, 1)
        self.action.save()
        other = PlanArtifact.objects.create(plan=self.artifact.plan, artifact_type=PlanArtifact.ArtifactType.OBJECTIVE,
            code="OE 02", title="Outro objetivo")
        StrategicAction.objects.create(artifact=other, coordinating_unit=self.unit, code="AE 02", title="Outra ação")
        for score in (2, 4):
            Risk.objects.create(action=self.action, owner=self.user, title=f"Risco {score}", cause="Teste", probability=score, impact=score)
        response = self.client.get("/")
        destination = self.client.get("/planos-de-acao/?" + response.context["delayed_query"])
        self.assertEqual(list(destination.context["actions"]), [self.action])
        destination = self.client.get("/riscos/?" + response.context["risk_query"])
        self.assertEqual(len(destination.context["risks"]), response.context["critical_risk_count"])
        bar = next(item for item in response.context["objective_progress"] if item["code"] == self.artifact.code)
        destination = self.client.get("/planos-de-acao/?" + bar["query"])
        self.assertEqual(list(destination.context["actions"]), [self.action])

    def test_strategy_selection_expands_objective_and_filters_actions(self):
        self.client.force_login(self.user)
        project = PlanArtifact.objects.create(plan=self.artifact.plan, parent=self.artifact,
            artifact_type=PlanArtifact.ArtifactType.PROJECT, code="PR 01", title="Projeto selecionado")
        self.action.artifact = project
        self.action.save()
        other = PlanArtifact.objects.create(plan=self.artifact.plan,
            artifact_type=PlanArtifact.ArtifactType.OBJECTIVE, code="OE 99", title="Objetivo fora do recorte")
        StrategicAction.objects.create(artifact=other, coordinating_unit=self.unit, code="AE 99", title="Ação fora do recorte")
        for query in (f"objective={self.artifact.id}", f"action={self.action.id}"):
            response = self.client.get("/pei/?" + query)
            self.assertContains(response, f'id="objetivo-{self.artifact.id}" tabindex="-1" open')
            self.assertContains(response, f'id="acao-{self.action.id}"')
            self.assertNotContains(response, "Objetivo fora do recorte")
            self.assertNotContains(response, "Ação fora do recorte")
        response = self.client.get("/")
        self.assertContains(response, f'#objetivo-{self.artifact.id}')
        self.assertContains(response, f'data-href="/planos-de-acao/{self.action.id}/"')

    def test_risk_has_one_editable_response_and_acceptance(self):
        risk = Risk.objects.create(action=self.action, owner=self.user, title="Risco único", cause="Teste", probability=2, impact=2)
        url = f"/planos-de-acao/{self.action.id}/riscos/{risk.id}/"
        self.client.force_login(self.user)
        for operation, fields, Model in (
            ("add_treatment", {"treatment-decision": "MITIGAR", "treatment-responsible": self.user.id}, RiskTreatment),
            ("accept", {"acceptance-authority": self.user.id, "acceptance-decision": "ACEITO"}, RiskAcceptance),
        ):
            prefix = "treatment" if operation == "add_treatment" else "acceptance"
            for text in ("Primeiro registro", "Registro editado"):
                response = self.client.post(url, {"operation": operation, **fields, prefix + "-justification": text})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(Model.objects.filter(risk=risk).count(), 1)
                self.assertEqual(Model.objects.get(risk=risk).justification, text)
        response = self.client.get(url)
        self.assertNotContains(response, "Registrar decisão de aceite")
        self.assertContains(response, "data-edit-acceptance")
        for label in ("Editar aceite", "Excluir aceite", "Editar resposta e tratamento", "Excluir resposta"):
            self.assertContains(response, label)
        self.assertEqual(self.client.post(url, {"operation": "delete_acceptance"}).status_code, 302)
        self.assertFalse(RiskAcceptance.objects.filter(risk=risk).exists())
        risk.refresh_from_db()
        self.assertEqual(risk.status, Risk.Status.IN_TREATMENT)
        self.assertEqual(self.client.post(url, {"operation": "delete_treatment"}).status_code, 302)
        self.assertFalse(RiskTreatment.objects.filter(risk=risk).exists())
        risk.refresh_from_db()
        self.assertEqual(risk.treatment, "")
        self.assertEqual(risk.status, Risk.Status.IDENTIFIED)

    def test_database_rejects_duplicate_risk_response_and_acceptance(self):
        from django.db import IntegrityError, transaction
        risk = Risk.objects.create(action=self.action, owner=self.user, title="Risco sem duplicatas", cause="Teste", probability=2, impact=2)
        for Model, fields in (
            (RiskTreatment, dict(responsible=self.user, created_by=self.user, decision="MITIGAR")),
            (RiskAcceptance, dict(authority=self.user, recorded_by=self.user, decision="ACEITO", justification="Aceito")),
        ):
            Model.objects.create(risk=risk, **fields)
            with self.assertRaises(IntegrityError), transaction.atomic():
                Model.objects.create(risk=risk, **fields)

    def test_existing_risk_records_require_change_and_delete_permissions(self):
        risk = Risk.objects.create(action=self.action, owner=self.user, title="Risco protegido", cause="Teste", probability=2, impact=2)
        RiskAcceptance.objects.create(risk=risk, authority=self.user, recorded_by=self.user, decision="ACEITO", justification="Original")
        RiskTreatment.objects.create(risk=risk, responsible=self.user, created_by=self.user, decision="MITIGAR")
        self.user.user_permissions.remove(*Permission.objects.filter(codename__in=(
            "change_riskacceptance", "delete_riskacceptance", "change_risktreatment", "delete_risktreatment")))
        self.client.force_login(self.user)
        url = f"/planos-de-acao/{self.action.id}/riscos/{risk.id}/"
        for operation in ("accept", "add_treatment", "delete_acceptance", "delete_treatment"):
            self.assertEqual(self.client.post(url, {"operation": operation}).status_code, 403)
        self.assertEqual(risk.acceptances.count(), 1)
        self.assertEqual(risk.treatments.count(), 1)
        self.assertNotContains(self.client.get(url), "Excluir aceite")

    def test_delete_risk_assessment_updates_classification_and_checks_scope(self):
        risk = Risk.objects.create(action=self.action, owner=self.user, title="Excluir avaliação", cause="Teste", probability=5, impact=5)
        old = RiskAssessment.objects.create(risk=risk, author=self.user, probability=2, impact=3)
        latest = RiskAssessment.objects.create(risk=risk, author=self.user, probability=5, impact=5)
        url = f"/planos-de-acao/{self.action.id}/riscos/{risk.id}/"
        self.client.force_login(self.user)
        self.assertContains(self.client.get(url), "Excluir avaliação")
        response = self.client.post(url, {"operation": "delete_assessment", "assessment_id": latest.id})
        self.assertRedirects(response, url + "#analise")
        risk.refresh_from_db()
        self.assertEqual((risk.probability, risk.impact), (2, 3))
        other = Risk.objects.create(action=self.action, owner=self.user, title="Outro risco", cause="Teste", probability=1, impact=1)
        foreign = RiskAssessment.objects.create(risk=other, author=self.user, probability=1, impact=1)
        self.assertEqual(self.client.post(url, {"operation": "delete_assessment", "assessment_id": foreign.id}).status_code, 404)
        self.assertTrue(RiskAssessment.objects.filter(pk=foreign.id).exists())
        self.user.user_permissions.remove(Permission.objects.get(codename="delete_riskassessment"))
        self.assertEqual(self.client.post(url, {"operation": "delete_assessment", "assessment_id": old.id}).status_code, 403)
        self.assertTrue(RiskAssessment.objects.filter(pk=old.id).exists())
        self.user.user_permissions.add(Permission.objects.get(codename="delete_riskassessment"))
        self.assertEqual(self.client.post(url, {"operation": "delete_assessment", "assessment_id": old.id}).status_code, 302)
        self.assertFalse(risk.assessments.exists())
        risk.refresh_from_db()
        self.assertEqual((risk.probability, risk.impact), (2, 3))

    def test_edit_assessment_and_block_second_registration(self):
        self.client.force_login(self.user)
        risk = Risk.objects.create(action=self.action, owner=self.user, title="Uma avaliação", cause="Teste", probability=2, impact=2)
        url = f"/planos-de-acao/{self.action.id}/riscos/{risk.id}/"
        fields = {"assessment-assessment_type": "ATUAL", "assessment-probability": 3, "assessment-impact": 4}
        self.assertEqual(self.client.post(url, {"operation": "add_assessment", **fields}).status_code, 302)
        assessment = risk.assessments.get()
        response = self.client.get(url)
        self.assertContains(response, "Editar avaliação")
        self.assertNotContains(response, 'value="add_assessment"')
        self.client.post(url, {"operation": "add_assessment", **fields})
        self.assertEqual(risk.assessments.count(), 1)
        response = self.client.get(url, {"editar_avaliacao": assessment.id})
        self.assertContains(response, 'value="edit_assessment"')
        fields["assessment-impact"] = 5
        response = self.client.post(url, {"operation": "edit_assessment", "assessment_id": assessment.id, **fields})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(risk.assessments.count(), 1)
        risk.refresh_from_db()
        self.assertEqual((risk.probability, risk.impact), (3, 5))
        self.user.user_permissions.remove(Permission.objects.get(codename="change_riskassessment"))
        self.assertEqual(self.client.post(url, {"operation": "edit_assessment", "assessment_id": assessment.id, **fields}).status_code, 403)

    def test_indicator_detail_keeps_chart_definition_and_full_target_information(self):
        self.client.force_login(self.user)
        indicator = Indicator.objects.create(code="IE COMPLETO", name="Indicador completo", formula="A / B", data_source="Fonte institucional", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        target = StrategicTarget.objects.create(artifact=self.artifact, action=self.action, code="MT COMPLETA", description="Descrição completa da meta", target_value="100", unit_of_measure="servidores", reference_period="Até dezembro de 2034")
        target.indicators.add(indicator)
        IndicatorMeasurement.objects.create(indicator=indicator, reference_period="2026", measured_value="50", expected_value=Decimal("100"), recorded_by=self.user)
        response = self.client.get(f"/indicadores/{indicator.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["chart"])
        for text in ('id="indicator-chart"', "Ficha do indicador", "A / B", "Fonte institucional", "Aferições registradas", "Metas vinculadas ao indicador", "MT COMPLETA", "Descrição completa da meta", "servidores", "Até dezembro de 2034", self.action.title):
            self.assertContains(response, text)
        self.assertNotContains(response, 'id="indicator-definition-content" hidden')
        overview = self.client.get("/indicadores/")
        self.assertContains(overview, "Ver indicador e gráfico")
        self.assertContains(overview, "Valor esperado: 100 servidores")

    def test_results_page_unifies_targets_and_indicators_without_tabs(self):
        self.client.force_login(self.user)
        indicator = Indicator.objects.create(code="IE UNIFICADO", name="Indicador unificado")
        indicator.artifacts.add(self.artifact)
        target = StrategicTarget.objects.create(artifact=self.artifact, code="MT UNIFICADA", description="Meta unificada")
        target.indicators.add(indicator)
        for url in ("/indicadores/", "/metas/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "IE UNIFICADO")
            self.assertContains(response, "MT UNIFICADA")
            self.assertContains(response, "Indicadores do plano")
            self.assertContains(response, "Execução das metas")
            self.assertNotContains(response, 'class="results-tabs"')
        filtered = self.client.get("/metas/", {"target": target.pk})
        self.assertEqual(len(filtered.context["indicator_rows"]), 1)
        self.assertEqual(len(filtered.context["target_rows"]), 1)

    def test_sector_filter_applies_automatically_everywhere(self):
        other_unit = OrganizationalUnit.objects.create(organization=self.unit.organization, name="Outro setor automático", acronym="OUT", unit_type=OrganizationalUnit.UnitType.SECTOR)
        other_objective = PlanArtifact.objects.create(plan=self.artifact.plan, artifact_type=PlanArtifact.ArtifactType.OBJECTIVE, code="OE FORA", title="Objetivo externo automático")
        other_action = StrategicAction.objects.create(artifact=other_objective, coordinating_unit=other_unit, code="AE FORA", title="Ação externa automática")
        for unit, artifact, action, code in ((self.unit, self.artifact, self.action, "LOCAL"), (other_unit, other_objective, other_action, "FORA")):
            indicator = Indicator.objects.create(code=f"IE {code}", name=f"Indicador {code}", responsible_unit=unit)
            indicator.artifacts.add(artifact)
            target = StrategicTarget.objects.create(artifact=artifact, action=action, code=f"MT {code}", description=f"Meta {code}")
            target.indicators.add(indicator)
            Risk.objects.create(action=action, owner=self.user, title=f"Risco {code}", cause="Teste", probability=4, impact=4)
        StrategicTarget.objects.create(artifact=other_objective, code="MT SEM SETOR", description="Meta institucional sem vínculo")
        self.client.force_login(self.user)
        for query in ({}, {"unit": ""}, {"unit": str(other_unit.pk)}):
            dashboard = self.client.get("/", query)
            self.assertEqual(dashboard.context["selected_unit"], str(self.unit.pk))
            self.assertEqual(dashboard.context["action_count"], 1)
            self.assertEqual(dashboard.context["indicator_total"], 1)
            self.assertEqual(dashboard.context["target_total"], 1)
            self.assertEqual(dashboard.context["critical_risk_count"], 1)
            results = self.client.get("/indicadores/", query)
            self.assertEqual(results.context["selected_unit"], str(self.unit.pk))
            self.assertEqual(len(results.context["indicator_rows"]), 1)
            self.assertEqual(len(results.context["target_rows"]), 1)
            self.assertNotContains(results, "IE FORA")
            self.assertNotContains(results, "MT SEM SETOR")
            actions = self.client.get("/planos-de-acao/", query)
            self.assertEqual(list(actions.context["actions"]), [self.action])
            risks = self.client.get("/riscos/", query)
            self.assertEqual(len(risks.context["risks"]), 1)
        strategy = self.client.get("/pei/")
        self.assertContains(strategy, self.action.title)
        self.assertNotContains(strategy, other_objective.title)
        self.user.groups.add(Group.objects.create(name="Administrador"))
        dashboard = self.client.get("/")
        self.assertEqual(dashboard.context["selected_unit"], "")
        self.assertEqual(dashboard.context["action_count"], 2)
        self.assertEqual(dashboard.context["indicator_total"], 2)

    def test_results_show_indicator_chart_and_target_details_inline(self):
        self.client.force_login(self.user)
        indicator = Indicator.objects.create(code="IE MESMA TELA", name="Indicador na mesma tela", responsible_unit=self.unit, formula="A dividido por B", data_source="Fonte da mesma tela")
        indicator.artifacts.add(self.artifact)
        target = StrategicTarget.objects.create(artifact=self.artifact, action=self.action, code="MT MESMA TELA", description="Meta exibida junto ao gráfico", target_value="100", unit_of_measure="pessoas", reference_period="Até 2034")
        target.indicators.add(indicator)
        IndicatorMeasurement.objects.create(indicator=indicator, reference_period="2026", measured_value="50", expected_value=Decimal("100"), recorded_by=self.user)
        for url in ("/indicadores/", "/metas/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            for text in ("IE MESMA TELA", "MT MESMA TELA", "Meta exibida junto ao gráfico", "100 pessoas", "Até 2034", "Ficha do indicador", "A dividido por B", "Fonte da mesma tela", "Aferições registradas", f'id="target-indicator-chart-{indicator.pk}"', f'id="target-chart-data-{indicator.pk}"'):
                self.assertContains(response, text)
            self.assertNotContains(response, "Ver indicador e gráfico")
            self.assertNotContains(response, ">Ver meta<")
            self.assertNotContains(response, 'class="results-tabs"')

    def test_measurement_actions_delete_recalculates_signal_and_checks_scope(self):
        self.client.force_login(self.user)
        self.user.user_permissions.add(Permission.objects.get(codename="change_indicatormeasurement"))
        indicator = Indicator.objects.create(code="IE EDITAR", name="Editar aferições", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        old = IndicatorMeasurement.objects.create(indicator=indicator, reference_period="Anterior", measured_value="100", expected_value=Decimal("100"), recorded_by=self.user)
        latest = IndicatorMeasurement.objects.create(indicator=indicator, reference_period="Atual", measured_value="50", expected_value=Decimal("100"), recorded_by=self.user)
        page = self.client.get("/indicadores/")
        self.assertContains(page, "Editar aferição")
        self.assertContains(page, "Remover aferição")
        url = f"/indicadores/{indicator.id}/afericoes/{latest.id}/excluir/"
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertTrue(IndicatorMeasurement.objects.filter(pk=latest.id).exists())
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(IndicatorMeasurement.objects.filter(pk=latest.id).exists())
        page = self.client.get("/indicadores/")
        self.assertEqual(page.context["indicator_rows"][0]["signal"]["code"], "green")
        self.user.user_permissions.remove(Permission.objects.get(codename="delete_indicatormeasurement"))
        url = f"/indicadores/{indicator.id}/afericoes/{old.id}/excluir/"
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(IndicatorMeasurement.objects.filter(pk=old.id).exists())
        self.user.user_permissions.add(Permission.objects.get(codename="delete_indicatormeasurement"))
        other_unit = OrganizationalUnit.objects.create(organization=self.unit.organization, name="Setor protegido", unit_type=OrganizationalUnit.UnitType.SECTOR)
        foreign = Indicator.objects.create(name="Indicador protegido", responsible_unit=other_unit)
        foreign_measurement = IndicatorMeasurement.objects.create(indicator=foreign, reference_period="2026", measured_value="1", recorded_by=self.user)
        url = f"/indicadores/{foreign.id}/afericoes/{foreign_measurement.id}/excluir/"
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(IndicatorMeasurement.objects.filter(pk=foreign_measurement.id).exists())

    def test_target_achievement_chart_totals_multiple_indicators_per_target(self):
        self.client.force_login(self.user)
        first = StrategicTarget.objects.create(artifact=self.artifact, code="MT 100", description="Meta de cem", target_value="100")
        second = StrategicTarget.objects.create(artifact=self.artifact, code="MT 200", description="Meta de duzentos", target_value="200")
        for code, value in (("IE A", "50"), ("IE B", "150"), ("IE SEM DADO", None)):
            indicator = Indicator.objects.create(code=code, name=code, responsible_unit=self.unit)
            indicator.artifacts.add(self.artifact)
            first.indicators.add(indicator)
            if code == "IE A":
                second.indicators.add(indicator)
            if value:
                IndicatorMeasurement.objects.create(indicator=indicator, reference_period="Fim do plano", measured_value=value,
                    expected_value=Decimal("100"), baseline_value="0", baseline_date=date(2025, 1, 1),
                    period_end=date(2034, 12, 31), recorded_by=self.user)
        response = self.client.get("/indicadores/")
        summaries = {row["target"].pk: row["target"].achievement_summary for row in response.context["target_rows"]}
        self.assertAlmostEqual(sum(point["y"] for point in summaries[first.pk]["pie_points"]), 100)
        self.assertEqual([point["y"] for point in summaries[first.pk]["pie_points"]], [25, 50, 25])
        self.assertNotContains(response, 'data-current-result-source="')
        self.assertEqual(summaries[first.pk]["total"], 75)  # 50% and 150% capped at 100%.
        self.assertEqual(summaries[first.pk]["measured_count"], 2)
        self.assertEqual(summaries[first.pk]["indicator_count"], 3)
        self.assertTrue(summaries[first.pk]["partial"])
        self.assertEqual(summaries[second.pk]["total"], 25)  # Same indicator, different target value.
        self.assertContains(response, "Atingimento da meta no período")
        self.assertContains(response, "Resultado parcial")
        self.assertContains(response, "data-achievement-source")
        self.assertContains(response, "(este indicador)")

    def test_target_achievement_chart_respects_measurement_permission(self):
        self.client.force_login(self.user)
        self.user.user_permissions.remove(Permission.objects.get(codename="view_indicatormeasurement"))
        indicator = Indicator.objects.create(code="IE PRIVADO", name="Indicador", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        target = StrategicTarget.objects.create(artifact=self.artifact, code="MT PRIVADA", description="Meta", target_value="100")
        target.indicators.add(indicator)
        IndicatorMeasurement.objects.create(indicator=indicator, reference_period="2026", measured_value="50", expected_value=Decimal("100"), recorded_by=self.user)
        response = self.client.get("/indicadores/")
        self.assertNotContains(response, "data-achievement-source")
        self.assertIsNone(response.context["target_rows"][0]["target"].achievement_summary)

    def test_current_result_target_and_achievement_are_charted_outside_definition(self):
        self.client.force_login(self.user)
        indicator = Indicator.objects.create(code="IE GRAFICO ATUAL", name="Resultado atual em gráfico", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        IndicatorMeasurement.objects.create(indicator=indicator, reference_period="2026", measured_value="56", expected_value=Decimal("14.9"), recorded_by=self.user)
        response = self.client.get("/indicadores/")
        data = response.context["indicator_rows"][0]["current_chart"]
        self.assertEqual(data["result"], 56)
        self.assertEqual(data["expected"], 14.9)
        self.assertGreater(data["achievement"], 100)
        self.assertContains(response, "data-current-result-source")
        for field in ("Resultado atual", "Meta do período", "Atingimento"):
            self.assertNotContains(response, "<dt>" + field + "</dt>")
        self.user.user_permissions.remove(Permission.objects.get(codename="view_indicatormeasurement"))
        response = self.client.get("/indicadores/")
        self.assertNotContains(response, 'data-current-result-source="')

    def test_other_units_permission_allows_reading_but_never_writing(self):
        other_unit = OrganizationalUnit.objects.create(organization=self.unit.organization, name="Setor para consulta", acronym="CONSULTA", unit_type=OrganizationalUnit.UnitType.SECTOR)
        other_action = StrategicAction.objects.create(artifact=self.artifact, coordinating_unit=other_unit, code="AE CONSULTA", title="Ação de consulta externa")
        indicator = Indicator.objects.create(code="IE CONSULTA", name="Indicador externo", responsible_unit=other_unit)
        indicator.artifacts.add(self.artifact)
        measurement = IndicatorMeasurement.objects.create(indicator=indicator, reference_period="2026", measured_value="50", expected_value=Decimal("100"), recorded_by=self.user)
        target = StrategicTarget.objects.create(artifact=self.artifact, action=other_action, code="MT CONSULTA", description="Meta externa")
        target.indicators.add(indicator)
        risk = Risk.objects.create(action=other_action, owner=self.user, title="Risco externo", cause="Consulta", probability=2, impact=2)
        self.client.force_login(self.user)
        action_url = f"/planos-de-acao/{other_action.pk}/"
        self.assertEqual(self.client.get(action_url).status_code, 404)
        self.user.user_permissions.add(Permission.objects.get(codename="view_other_units"), Permission.objects.get(codename="change_indicator"), Permission.objects.get(codename="change_indicatormeasurement"))
        dashboard = self.client.get("/")
        self.assertEqual(dashboard.context["selected_unit"], str(self.unit.pk))
        self.assertEqual(dashboard.context["action_count"], 1)
        self.assertIn(other_unit, dashboard.context["units"])
        all_units = self.client.get("/", {"unit": ""})
        self.assertEqual(all_units.context["selected_unit"], "")
        self.assertEqual(all_units.context["action_count"], 2)
        self.assertEqual(self.client.get("/").context["selected_unit"], str(self.unit.pk))
        dashboard = self.client.get("/", {"unit": other_unit.pk})
        self.assertEqual(dashboard.context["selected_unit"], str(other_unit.pk))
        self.assertEqual(dashboard.context["action_count"], 1)
        self.assertEqual(dashboard.context["indicator_total"], 1)
        page = self.client.get("/indicadores/", {"unit": other_unit.pk})
        self.assertContains(page, "IE CONSULTA")
        self.assertNotContains(page, "Editar meta")
        self.assertNotContains(page, "Editar indicador")
        self.assertNotContains(page, "Remover aferição")
        self.assertNotContains(page, "Registrar aferição")
        detail = self.client.get(action_url)
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, 'value="start_plan"')
        self.assertEqual(self.client.post(action_url, {"operation": "start_plan"}).status_code, 404)
        indicator_url = f"/indicadores/{indicator.pk}/"
        detail = self.client.get(indicator_url)
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.context["can_add_measurement"])
        self.assertFalse(detail.context["can_edit_measurement"])
        self.assertEqual(self.client.post(indicator_url, {"operation": "edit_definition", "formula": "ALTERADA"}).status_code, 404)
        self.assertEqual(self.client.post(f"/indicadores/{indicator.pk}/afericoes/{measurement.pk}/excluir/").status_code, 404)
        risk_url = f"/planos-de-acao/{other_action.pk}/riscos/{risk.pk}/"
        self.assertEqual(self.client.get(risk_url).status_code, 200)
        self.assertEqual(self.client.post(risk_url, {"operation": "delete_acceptance"}).status_code, 404)
        self.assertEqual(self.client.post("/metas/", {"target_id": target.pk}).status_code, 404)
        self.assertTrue(IndicatorMeasurement.objects.filter(pk=measurement.pk).exists())
        self.assertFalse(ActionPlan.objects.filter(action=other_action).exists())
        self.assertEqual(self.client.post(f"/planos-de-acao/{self.action.pk}/", {"operation": "start_plan"}).status_code, 302)

    def test_other_units_permission_alone_grants_reading_across_modules(self):
        other_unit = OrganizationalUnit.objects.create(
            organization=self.unit.organization, name="Unidade externa", acronym="EXT",
            unit_type=OrganizationalUnit.UnitType.SECTOR,
        )
        other_action = StrategicAction.objects.create(
            artifact=self.artifact, coordinating_unit=other_unit,
            code="AE EXTERNA", title="Ação externa",
        )
        other_risk = Risk.objects.create(
            action=other_action, owner=self.user, title="Risco externo",
            cause="Causa externa", probability=2, impact=2,
        )
        RiskAssessment.objects.create(risk=other_risk, probability=2, impact=2,
                                      author=self.user, notes="Avaliação externa")
        indicator = Indicator.objects.create(code="IE EXTERNO", name="Indicador externo", responsible_unit=other_unit)
        indicator.artifacts.add(self.artifact)
        IndicatorMeasurement.objects.create(indicator=indicator, reference_period="2026",
                                            measured_value="50", recorded_by=self.user)
        reader = User.objects.create_user(username="leitor", password="senha-segura")
        UserProfile.objects.create(user=reader, unit=self.unit)
        reader.user_permissions.add(Permission.objects.get(codename="view_other_units"))
        self.client.force_login(reader)

        self.assertTrue(reader.has_perm("core.view_actionplan"))
        self.assertTrue(reader.has_perm("core.view_indicatormeasurement"))
        self.assertTrue(reader.has_perm("core.view_riskassessment"))
        self.assertFalse(reader.has_perm("core.add_risk"))
        self.assertFalse(reader.has_perm("core.change_indicator"))
        self.assertNotContains(self.client.get("/planos-de-acao/"), "AE EXTERNA")
        plans = self.client.get("/planos-de-acao/", {"unit": other_unit.pk})
        self.assertContains(plans, "AE EXTERNA")
        self.assertContains(plans, f'href="/planos-de-acao/{other_action.pk}/">Visualizar plano')
        self.assertContains(self.client.get("/indicadores/", {"unit": other_unit.pk}), "IE EXTERNO")
        self.assertContains(self.client.get("/riscos/", {"unit": other_unit.pk}), "Risco externo")
        self.assertContains(self.client.get(f"/planos-de-acao/{other_action.pk}/riscos/{other_risk.pk}/"), "Avaliação externa")
        self.assertEqual(self.client.post(f"/planos-de-acao/{other_action.pk}/", {"operation": "start_plan"}).status_code, 404)

    def test_target_and_indicator_status_filters_are_independent(self):
        self.client.force_login(self.user)
        measured = Indicator.objects.create(code="IE AFERIDO", name="Aferido", responsible_unit=self.unit)
        pending = Indicator.objects.create(code="IE PENDENTE", name="Pendente", responsible_unit=self.unit)
        for indicator in (measured, pending):
            indicator.artifacts.add(self.artifact)
        IndicatorMeasurement.objects.create(
            indicator=measured, reference_period="2026", measured_value="100",
            expected_value=Decimal("100"), recorded_by=self.user,
        )
        completed_target = StrategicTarget.objects.create(artifact=self.artifact, code="MT AFERIDA", description="Meta aferida")
        pending_target = StrategicTarget.objects.create(artifact=self.artifact, code="MT PENDENTE", description="Meta pendente")
        completed_target.indicators.add(measured)
        pending_target.indicators.add(pending)

        page = self.client.get("/indicadores/", {"target_status": "gray", "indicator_status": "green"})
        self.assertContains(page, 'name="target_status"')
        self.assertContains(page, 'name="indicator_status"')
        self.assertEqual([row["indicator"].code for row in page.context["indicator_rows"]], ["IE AFERIDO"])
        self.assertEqual([row["target"].code for row in page.context["target_rows"]], ["MT PENDENTE"])
        self.assertEqual(page.context["selected_target_status"], "gray")
        self.assertEqual(page.context["selected_indicator_status"], "green")

        page = self.client.get("/indicadores/", {"indicator_status": "green"})
        self.assertEqual(len(page.context["target_rows"]), 2)
        page = self.client.get("/metas/", {"target_status": "gray"})
        self.assertEqual(len(page.context["indicator_rows"]), 2)

    def test_execution_switches_columns_and_list_without_losing_filters(self):
        self.client.force_login(self.user)
        query = {"plan": self.artifact.plan_id, "unit": self.unit.pk, "objective": self.artifact.pk, "status": self.action.status}
        columns = self.client.get("/planos-de-acao/", query)
        self.assertEqual(columns.context["display_mode"], "columns")
        self.assertContains(columns, 'class="action-cards"')
        listing = self.client.get("/planos-de-acao/" + columns.context["list_url"])
        self.assertEqual(listing.context["display_mode"], "list")
        self.assertContains(listing, 'aria-label="Listagem de planos de ação"')
        self.assertContains(listing, self.action.title)
        self.assertEqual(list(listing.context["actions"]), list(columns.context["actions"]))
        from urllib.parse import parse_qs, urlparse
        preserved = parse_qs(urlparse(listing.context["columns_url"]).query)
        for key, value in query.items():
            self.assertEqual(preserved[key], [str(value)])
        self.assertContains(listing, 'name="view" value="list"')

    def test_target_sector_filter_does_not_include_other_sectors_via_shared_indicators(self):
        self.user.groups.add(Group.objects.create(name="Administrador"))
        self.client.force_login(self.user)
        foreign_unit = OrganizationalUnit.objects.create(organization=self.unit.organization, name="Setor fora do filtro", unit_type=OrganizationalUnit.UnitType.SECTOR)
        foreign_action = StrategicAction.objects.create(artifact=self.artifact, coordinating_unit=foreign_unit, code="AE FILTRO", title="Ação de fora")
        local = Indicator.objects.create(code="IE FILTRO LOCAL", name="Indicador local", responsible_unit=self.unit)
        local.artifacts.add(self.artifact)
        own = StrategicTarget.objects.create(artifact=self.artifact, code="MT LOCAL FILTRADA", description="Meta do setor")
        own.indicators.add(local)
        foreign = StrategicTarget.objects.create(artifact=self.artifact, action=foreign_action, code="MT FORA FILTRADA", description="Meta de outro setor")
        foreign.indicators.add(local)
        for url in ("/indicadores/", "/metas/"):
            response = self.client.get(url, {"unit": self.unit.pk})
            self.assertEqual([row["target"].pk for row in response.context["target_rows"]], [own.pk])
            self.assertContains(response, "MT LOCAL FILTRADA")
            self.assertNotContains(response, "MT FORA FILTRADA")
        ActionPlan.objects.create(action=self.action, manager=self.user)
        response = self.client.get(f"/planos-de-acao/{self.action.pk}/")
        self.assertIn("unit=" + str(self.unit.pk), response.context["indicators_url"])

    def test_participating_sector_sees_target_of_its_indicator(self):
        other_unit = OrganizationalUnit.objects.create(
            organization=self.unit.organization, name="Gabinete", unit_type=OrganizationalUnit.UnitType.UNIT
        )
        action = StrategicAction.objects.create(
            artifact=self.artifact, coordinating_unit=other_unit, code="AE PARTICIPANTE", title="Ação conjunta"
        )
        action.participating_units.add(self.unit)
        indicator = Indicator.objects.create(code="IE PARTICIPANTE", name="Indicador local", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        target = StrategicTarget.objects.create(
            artifact=self.artifact, action=action, code="MT PARTICIPANTE", description="Meta da ação conjunta"
        )
        target.indicators.add(indicator)
        self.client.force_login(self.user)

        response = self.client.get("/metas/")
        self.assertContains(response, "MT PARTICIPANTE")
        self.assertIn(target.pk, [row["target"].pk for row in response.context["target_rows"]])

    def test_activity_risk_report_selects_existing_and_registers_unforeseen_occurrence(self):
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user, title="Atividade com riscos", weight=100, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        risk = Risk.objects.create(action=self.action, owner=self.user, activity=activity, title="Risco já previsto", cause="Teste", probability=2, impact=2)
        url = f"/planos-de-acao/{self.action.pk}/atividades/{activity.pk}/acompanhar/"
        response = self.client.get(url)
        self.assertContains(response, "Qual risco?")
        self.assertContains(response, "O risco se materializou?")
        self.assertContains(response, "Cadastrar risco não previsto")
        self.assertEqual(self.client.post(url, {"operation": "report_risk", "risk-report-risk": risk.pk}).status_code, 200)
        response = self.client.post(url, {"operation": "report_risk", "risk-report-risk": risk.pk, "risk-report-materialized": "NAO"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Risk.objects.count(), 1)
        risk.refresh_from_db()
        self.assertEqual(risk.activity, activity)
        self.assertFalse(risk.materializations.exists())
        data = {"operation": "report_risk", "risk-report-risk": "",
                "unforeseen-title": "Risco não previsto no planejamento", "unforeseen-cause": "Evento inesperado", "unforeseen-owner": self.user.pk,
                "unforeseen-probability": 3, "unforeseen-impact": 4}
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.assertEqual(Risk.objects.count(), 1)  # No partial save without occurrence details.
        data.update({"occurrence-occurred_on": "2026-10-16", "occurrence-description": "Evento ocorrido", "occurrence-actual_impact": "Entrega adiada", "occurrence-actions_taken": "Equipe acionada"})
        self.assertEqual(self.client.post(url, data).status_code, 302)
        unforeseen = Risk.objects.get(is_unforeseen=True)
        self.assertEqual(unforeseen.activity, activity)
        self.assertEqual(unforeseen.status, Risk.Status.MATERIALIZED)
        self.assertEqual(unforeseen.materializations.count(), 1)
        self.assertEqual(unforeseen.assessments.count(), 1)
        other_action = StrategicAction.objects.create(artifact=self.artifact, coordinating_unit=self.unit, code="AE OUTRO RISCO", title="Outra ação")
        foreign = Risk.objects.create(action=other_action, owner=self.user, title="Risco de outra ação", cause="Teste", probability=1, impact=1)
        response = self.client.post(url, {"operation": "report_risk", "risk-report-risk": foreign.pk, "risk-report-materialized": "NAO"})
        self.assertEqual(response.status_code, 200)
        foreign.refresh_from_db()
        self.assertIsNone(foreign.activity_id)
        self.user.user_permissions.remove(Permission.objects.get(codename="change_risk"))
        self.assertEqual(self.client.post(url, {"operation": "report_risk", "risk-report-risk": risk.pk, "risk-report-materialized": "NAO"}).status_code, 403)

    def test_evidence_download_handles_missing_files_and_permissions(self):
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user, title="Arquivo da evidência", weight=100, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root):
            evidence = ActivityEvidence.objects.create(activity=activity, created_by=self.user, title="Documento", evidence_type="ANEXO", attachment=SimpleUploadedFile("evidencia.txt", b"comprovacao"))
            url = f"/planos-de-acao/{self.action.pk}/atividades/{activity.pk}/evidencias/{evidence.pk}/arquivo/"
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"comprovacao")
            response.close()
            evidence.attachment.storage.delete(evidence.attachment.name)
            self.assertEqual(self.client.get(url).status_code, 302)
            page = self.client.get(f"/planos-de-acao/{self.action.pk}/atividades/{activity.pk}/acompanhar/")
            self.assertContains(page, "Arquivo indisponível no servidor")
            self.user.user_permissions.remove(Permission.objects.get(codename="view_activityevidence"))
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_activity_occurrence_records_planned_or_new_measure(self):
        self.client.login(username="copin", password="senha-segura")
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(
            action_plan=action_plan, executor=self.user, title="Entrega",
            weight=100, end_date=date(2026, 12, 31),
        )
        risk = Risk.objects.create(
            action=self.action, activity=activity, owner=self.user,
            title="Atraso", cause="Teste", probability=2, impact=2,
        )
        RiskTreatment.objects.create(
            risk=risk, decision=RiskTreatment.Decision.MITIGATE,
            responsible=self.user, created_by=self.user,
            preventive_measure="Acionar equipe responsável",
        )
        url = f"/planos-de-acao/{self.action.id}/atividades/{activity.id}/acompanhar/"
        response = self.client.get(url)
        self.assertContains(response, "Tratamento previsto")
        self.assertContains(response, "Acionar equipe responsável")
        payload = {
            "operation": "report_risk", "risk-report-risk": risk.pk,
            "risk-report-materialized": "SIM", "occurrence-occurred_on": "2026-10-16",
            "occurrence-description": "Evento ocorrido", "occurrence-actual_impact": "Atraso",
            "occurrence-actions_taken": "Acionar equipe responsável",
        }
        self.assertEqual(self.client.post(url, payload).status_code, 200)
        self.assertFalse(risk.materializations.exists())
        response = self.client.post(url, {**payload, "occurrence-measure_source": "PREVISTA", "occurrence-actions_taken": "Acionar equipe e registrar ata"})
        self.assertEqual(response.status_code, 302)
        occurrence = risk.materializations.get()
        self.assertEqual(occurrence.actions_taken, "Acionar equipe e registrar ata")
        self.assertEqual(occurrence.measure_source, "PREVISTA")
        response = self.client.post(url, {
            **payload, "risk-report-edit_materialization": "on",
            "occurrence-measure_source": "NOVA", "occurrence-actions_taken": "Criar força tarefa",
        })
        self.assertEqual(response.status_code, 302)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.measure_source, "NOVA")
        self.assertEqual(occurrence.actions_taken, "Criar força tarefa")

    def test_activity_risk_prefills_and_updates_existing_materialization(self):
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user, title="Materialização cadastrada", weight=100, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        risk = Risk.objects.create(action=self.action, activity=activity, owner=self.user, title="Risco já ocorrido", cause="Teste", probability=2, impact=2, status=Risk.Status.MATERIALIZED)
        occurrence = RiskMaterialization.objects.create(risk=risk, occurred_on=date(2026, 10, 1), description="Ocorrência original", actual_impact="Atraso", actions_taken="Equipe acionada", evidence_reference="SEI 123", recorded_by=self.user)
        url = f"/planos-de-acao/{self.action.pk}/atividades/{activity.pk}/acompanhar/"
        page = self.client.get(url)
        data = page.context["risk_prefill"][str(risk.pk)]
        self.assertEqual(data["materialized"], "SIM")
        self.assertEqual(data["occurrence"]["description"], "Ocorrência original")
        self.assertEqual(data["occurrence"]["occurred_on"], "2026-10-01")
        payload = {"operation": "report_risk", "risk-report-risk": risk.pk, "risk-report-materialized": "SIM"}
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(risk.materializations.count(), 1)
        payload.update({"risk-report-edit_materialization": "on", "occurrence-occurred_on": "2026-10-02", "occurrence-description": "Ocorrência editada", "occurrence-actual_impact": "Atraso atualizado", "occurrence-actions_taken": "Correção", "occurrence-evidence_reference": "SEI 456"})
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(risk.materializations.count(), 1)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.description, "Ocorrência editada")
        self.user.user_permissions.remove(Permission.objects.get(codename="change_riskmaterialization"))
        self.assertEqual(self.client.post(url, payload).status_code, 403)
        payload.pop("risk-report-edit_materialization")
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.description, "Ocorrência editada")

    def test_risk_occurrence_attachment_upload_download_and_preservation(self):
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user, title="Risco com anexo", weight=100, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        risk = Risk.objects.create(action=self.action, activity=activity, owner=self.user, title="Risco documentado", cause="Teste", probability=2, impact=2)
        url = f"/planos-de-acao/{self.action.pk}/atividades/{activity.pk}/acompanhar/"
        payload = {"operation": "report_risk", "risk-report-risk": risk.pk, "risk-report-materialized": "SIM", "occurrence-occurred_on": "2026-10-16", "occurrence-description": "Ocorrência", "occurrence-actual_impact": "Atraso", "occurrence-actions_taken": "Correção"}
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root):
            response = self.client.post(url, {**payload, "occurrence-evidence_attachment": SimpleUploadedFile("prova.txt", b"prova do risco")})
            self.assertEqual(response.status_code, 302)
            occurrence = risk.materializations.get()
            original = occurrence.evidence_attachment.name
            self.assertTrue(occurrence.evidence_attachment.storage.exists(original))
            page = self.client.get(url)
            download_url = page.context["risk_prefill"][str(risk.pk)]["attachment_url"]
            download = self.client.get(download_url)
            self.assertEqual(download.status_code, 200)
            self.assertEqual(b"".join(download.streaming_content), b"prova do risco")
            download.close()
            payload["risk-report-edit_materialization"] = "on"
            payload["occurrence-description"] = "Texto atualizado"
            self.assertEqual(self.client.post(url, payload).status_code, 302)
            occurrence.refresh_from_db()
            self.assertEqual(occurrence.evidence_attachment.name, original)
            self.assertEqual(risk.materializations.count(), 1)
            self.user.user_permissions.remove(Permission.objects.get(codename="view_riskmaterialization"))
            self.assertEqual(self.client.get(download_url).status_code, 403)

    def test_quarterly_report_consolidates_sector_and_freezes_snapshot(self):
        self.client.force_login(self.user)
        indicator = Indicator.objects.create(code="IE TRIMESTRE", name="Indicador do trimestre", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        target = StrategicTarget.objects.create(artifact=self.artifact, code="MT TRIMESTRE", description="Meta consolidada", target_value="100")
        target.indicators.add(indicator)
        IndicatorMeasurement.objects.create(indicator=indicator, reference_period="3º trimestre", measured_value="50", baseline_value="0", baseline_date=date(2025, 1, 1), expected_value=Decimal("100"), period_end=date(2026, 9, 30), recorded_by=self.user)
        IndicatorMeasurement.objects.create(indicator=indicator, reference_period="4º trimestre", measured_value="90", expected_value=Decimal("100"), period_end=date(2026, 12, 31), recorded_by=self.user)
        data = {"plan": self.artifact.plan_id, "unit": self.unit.pk, "year": 2026, "quarter": 3}
        page = self.client.get("/relatorios/")
        self.assertContains(page, "Consolidar relatório")
        response = self.client.post("/relatorios/", data)
        self.assertEqual(response.status_code, 302)
        report = QuarterlySectorReport.objects.get()
        self.assertEqual(report.snapshot["period_start"], "2026-07-01")
        self.assertEqual(report.snapshot["period_end"], "2026-09-30")
        self.assertEqual(report.snapshot["targets"][0]["code"], "MT TRIMESTRE")
        self.assertEqual(report.snapshot["objectives"][0]["code"], self.artifact.code)
        self.assertEqual(report.snapshot["indicators"][0]["latest_result"], "50")
        self.assertEqual(report.snapshot["targets"][0]["progress"], 50.0)
        self.assertEqual(len(report.snapshot["indicators"][0]["measurements"]), 1)
        page = self.client.get(response.url)
        self.assertContains(page, "Meta consolidada")
        self.assertContains(page, "Consolidado")
        self.assertContains(page, "Consolidado por")
        self.assertContains(page, self.user.username)
        self.assertContains(page, 'href="#report-objectives"')
        self.assertContains(page, 'href="#report-targets"')
        self.assertContains(page, 'href="#report-indicators"')
        self.assertContains(page, 'id="report-indicators"')
        self.assertContains(page, 'href="#report-objective-1"')
        self.assertContains(page, 'id="report-objective-1"')
        self.assertContains(page, 'href="#report-target-1"')
        self.assertContains(page, 'id="report-target-1"')
        self.assertContains(page, 'href="#report-indicator-1"')
        self.assertContains(page, 'id="report-indicator-1"')
        self.assertContains(page, 'href="#report-action-1"')
        self.assertContains(page, 'id="report-action-1"')
        self.assertContains(page, "50%")
        self.assertTrue(page.context["has_indicator_charts"])
        self.assertEqual(page.context["indicator_rows"][0]["chart"]["categories"], ["3º trimestre"])
        self.assertEqual(page.context["indicator_rows"][0]["chart"]["result"], [{"y": 50.0}])
        self.assertContains(page, 'data-report-indicator-chart')
        original = report.snapshot
        target.description = "Modificado após consolidar"
        target.save()
        self.assertEqual(self.client.post("/relatorios/", data).status_code, 302)
        self.assertEqual(QuarterlySectorReport.objects.count(), 1)
        report.refresh_from_db()
        self.assertEqual(report.snapshot, original)
        self.assertNotContains(self.client.get(response.url), "Modificado após consolidar")
        self.assertEqual(self.client.get(response.url).context["indicator_rows"][0]["chart"]["result"], [{"y": 50.0}])
        self.assertContains(self.client.get("/relatorios/"), "quarterly-sector-consolidated")
        self.assertContains(self.client.get("/relatorios/"), "Ver relatório")
        incomplete = self.client.post("/relatorios/", {"unit": self.unit.pk, "plan": self.artifact.plan_id})
        self.assertEqual(incomplete.status_code, 200)
        self.assertEqual(QuarterlySectorReport.objects.count(), 1)

    def test_report_indicator_charts_require_measurements(self):
        self.client.force_login(self.user)
        indicator = Indicator.objects.create(code="IE GRAFICO", name="Indicador com gráfico", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        target = StrategicTarget.objects.create(
            artifact=self.artifact, code="MT GRAFICO", description="Meta com percentual", target_value="100",
        )
        target.indicators.add(indicator)
        cycle = ReportCycle.objects.create(
            plan=self.artifact.plan, name="Ciclo de gráficos", period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31), due_date=date(2027, 1, 15), created_by=self.user,
        )
        report = SectorReport.objects.create(cycle=cycle, unit=self.unit)
        url = f"/relatorios/{cycle.pk}/setores/{report.pk}/"
        page = self.client.get(url)
        self.assertFalse(page.context["has_indicator_charts"])
        self.assertContains(page, 'href="#report-objectives"')
        self.assertContains(page, 'href="#report-targets"')
        self.assertContains(page, 'href="#report-indicators"')
        self.assertContains(page, 'id="report-indicators"')
        self.assertContains(page, 'href="#report-objective-1"')
        self.assertContains(page, 'id="report-objective-1"')
        self.assertContains(page, 'href="#report-target-1"')
        self.assertContains(page, 'id="report-target-1"')
        self.assertContains(page, 'href="#report-indicator-1"')
        self.assertContains(page, 'id="report-indicator-1"')
        self.assertContains(page, 'href="#report-action-1"')
        self.assertContains(page, 'id="report-action-1"')
        self.assertContains(page, self.artifact.title)
        self.assertNotContains(page, 'data-report-indicator-chart')
        IndicatorMeasurement.objects.create(
            indicator=indicator, reference_period="2026", measured_value="42", baseline_value="0",
            baseline_date=date(2025, 1, 1), expected_value=Decimal("50"),
            period_end=date(2026, 12, 31), recorded_by=self.user,
        )
        page = self.client.get(url)
        self.assertTrue(page.context["has_indicator_charts"])
        self.assertContains(page, 'data-report-indicator-chart')
        self.assertContains(page, "vendor/highcharts.js")
        self.assertEqual(page.context["content"]["target_rows"][0]["progress"], 42.0)
        self.assertContains(page, "42%")

    def test_report_filters_by_year(self):
        self.client.force_login(self.user)
        older = QuarterlySectorReport.objects.create(
            plan=self.artifact.plan, unit=self.unit, year=2025, quarter=4, consolidated_by=self.user
        )
        newer = QuarterlySectorReport.objects.create(
            plan=self.artifact.plan, unit=self.unit, year=2026, quarter=1, consolidated_by=self.user
        )
        page = self.client.get("/relatorios/", {"year": "2025"})
        self.assertContains(page, 'name="year"')
        self.assertEqual([report.pk for row in page.context["sector_rows"] for report in row["reports"]], [older.pk])
        self.assertNotContains(page, f'/relatorios/trimestrais/{newer.pk}/')

        spanning = ReportCycle.objects.create(
            plan=self.artifact.plan, name="Ciclo 2025–2026", period_start=date(2025, 12, 1),
            period_end=date(2026, 1, 31), due_date=date(2026, 2, 15), created_by=self.user,
        )
        spanning.participating_units.add(self.unit)
        SectorReport.objects.create(cycle=spanning, unit=self.unit)
        later = ReportCycle.objects.create(
            plan=self.artifact.plan, name="Ciclo 2027", period_start=date(2027, 1, 1),
            period_end=date(2027, 12, 31), due_date=date(2028, 1, 15), created_by=self.user,
        )
        later.participating_units.add(self.unit)
        SectorReport.objects.create(cycle=later, unit=self.unit)
        page = self.client.get("/relatorios/ciclos/", {"year": "2026"})
        self.assertContains(page, 'name="year"')
        self.assertContains(page, ">Visualizar</a>", html=False)
        self.assertEqual([row["cycle"].pk for row in page.context["cycle_rows"]], [spanning.pk])

    def test_quarterly_consolidation_requires_permission_and_own_sector(self):
        self.client.force_login(self.user)
        other = OrganizationalUnit.objects.create(organization=self.unit.organization, name="Setor do outro relatório", unit_type=OrganizationalUnit.UnitType.SECTOR)
        self.user.user_permissions.add(Permission.objects.get(codename="view_other_units"))
        data = {"plan": self.artifact.plan_id, "unit": other.pk, "year": 2026, "quarter": 3}
        response = self.client.post("/relatorios/", data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(QuarterlySectorReport.objects.exists())
        foreign = QuarterlySectorReport.objects.create(plan=self.artifact.plan, unit=other, year=2026, quarter=3, consolidated_by=self.user, snapshot={"unit": other.name})
        self.assertEqual(self.client.get(f"/relatorios/trimestrais/{foreign.pk}/").status_code, 200)
        self.user.user_permissions.remove(Permission.objects.get(codename="consolidate_quarterlysectorreport"))
        data["unit"] = self.unit.pk
        self.assertEqual(self.client.post("/relatorios/", data).status_code, 403)
        page = self.client.get("/relatorios/")
        self.assertNotContains(page, "data-consolidate-unit")

    def test_quarterly_report_delete_requires_permission_and_own_sector(self):
        self.client.force_login(self.user)
        own = QuarterlySectorReport.objects.create(
            plan=self.artifact.plan, unit=self.unit, year=2026, quarter=3, consolidated_by=self.user
        )
        other_unit = OrganizationalUnit.objects.create(
            organization=self.unit.organization, name="Outro setor", unit_type=OrganizationalUnit.UnitType.SECTOR
        )
        foreign = QuarterlySectorReport.objects.create(
            plan=self.artifact.plan, unit=other_unit, year=2026, quarter=3, consolidated_by=self.user
        )
        own_url = f"/relatorios/trimestrais/{own.pk}/excluir/"
        foreign_url = f"/relatorios/trimestrais/{foreign.pk}/excluir/"
        self.assertContains(self.client.get("/relatorios/"), f'action="{own_url}"', html=False)
        self.assertContains(self.client.get(f"/relatorios/trimestrais/{own.pk}/"), "Excluir relatório")
        self.assertEqual(self.client.get(own_url).status_code, 405)
        self.assertEqual(self.client.post(foreign_url).status_code, 404)
        self.assertEqual(self.client.post(own_url).status_code, 302)
        self.assertFalse(QuarterlySectorReport.objects.filter(pk=own.pk).exists())
        self.assertTrue(QuarterlySectorReport.objects.filter(pk=foreign.pk).exists())

        self.user.user_permissions.remove(Permission.objects.get(codename="consolidate_quarterlysectorreport"))
        self.assertEqual(self.client.post(foreign_url).status_code, 403)

    def test_dashboard_links_and_indicator_card(self):
        self.client.login(username="copin", password="senha-segura")
        response = self.client.get("/")
        self.assertContains(response, "Desempenho e resultados")
        self.assertContains(response, "/indicadores/")
        self.assertContains(response, "/metas/")
        self.assertContains(response, "/planos-de-acao/?status=ATRASADA")

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
        self.assertContains(response, "<h1>Painel executivo</h1>", html=False)
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
        self.assertContains(response, "<h1>Metas e indicadores</h1>", html=False)
        self.assertContains(response, "Mt 01.1")
        self.assertContains(response, f'href="/indicadores/{indicator.id}/"', html=False)

        response = self.client.get("/indicadores/")
        self.assertContains(response, "<h1>Metas e indicadores</h1>", html=False)
        self.assertContains(response, "IE 01.1")
        self.assertContains(response, "Registrar aferição")

        response = self.client.post(
            f"/indicadores/{indicator.id}/",
            {
                "description": "Capacitação do semestre",
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
        self.assertEqual(measurement.description, "Capacitação do semestre")

        response = self.client.get(f"/indicadores/{indicator.id}/")
        self.assertContains(response, '<td class="measurement-description"><strong>Capacitação do semestre</strong></td>', html=False)
        self.assertContains(response, '<td class="measurement-period">01/01/2026 a 30/06/2026</td>', html=False)
        self.assertContains(response, '<td class="measurement-baseline">40</td>', html=False)
        self.assertContains(response, "Setor responsável")
        self.assertContains(response, "indicator-chart-data", html=False)
        self.assertContains(response, "vendor/highcharts.js", html=False)
        self.assertContains(response, "data-view-measurement", html=False)
        self.assertContains(response, 'type="date"', html=False)
        self.assertContains(response, "Conforme")
        self.assertContains(response, "[DEMONSTRAÇÃO] Planilha fictícia")
        self.assertContains(response, "Anexar evidência da aferição")
        self.assertContains(response, 'enctype="multipart/form-data"', html=False)

        overview = self.client.get("/indicadores/")
        self.assertContains(overview, '<td class="measurement-period">01/01/2026 a 30/06/2026</td>', html=False)
        self.assertContains(overview, '<td class="measurement-baseline">40</td>', html=False)
        self.assertContains(overview, "Capacitação do semestre")
        self.assertNotContains(overview, "Registrado por copin")

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
        validator.user_permissions.add(*Permission.objects.filter(codename__in=["view_sectorreport", "change_sectorreport"]))
        self.client.login(username="copin", password="senha-segura")
        response = self.client.post(
            "/relatorios/ciclos/",
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
        self.assertContains(self.client.get(response.url), "Responsável pelo relatório")
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

    def test_activity_can_be_created_with_initial_risk_atomically(self):
        self.client.login(username="copin", password="senha-segura")
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        detail_url = f"/planos-de-acao/{self.action.id}/"
        response = self.client.get(detail_url)
        self.assertContains(response, "Risco obrigatório da atividade")
        self.assertContains(response, 'name="initial-risk-title"')
        self.assertNotContains(response, 'name="include_initial_risk"')

        payload = {
            "operation": "add_activity",
            "title": "Preparar relatório",
            "executor": self.user.id,
            "weight": "30",
            "start_date": "2026-05-01",
            "end_date": "2026-06-30",
            "requires_financial_resource": "NAO",
            "initial-risk-title": "Atraso na coleta",
            "initial-risk-cause": "Dados incompletos",
            "initial-risk-owner": self.user.id,
            "initial-risk-probability": "3",
            "initial-risk-impact": "4",
            "initial-risk-treatment": "Mitigar",
        }
        response = self.client.post(detail_url, {key: value for key, value in payload.items() if not key.startswith("initial-risk-")})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Activity.objects.filter(action_plan=action_plan).exists())

        response = self.client.post(detail_url, {**payload, "initial-risk-impact": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-open-on-load')
        self.assertFalse(Activity.objects.filter(action_plan=action_plan).exists())
        self.assertFalse(Risk.objects.filter(action=self.action).exists())

        response = self.client.post(detail_url, payload)
        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(action_plan=action_plan)
        risk = Risk.objects.get(activity=activity)
        self.assertEqual(risk.action, self.action)
        self.assertEqual(risk.status, Risk.Status.IDENTIFIED)
        self.assertFalse(risk.is_unforeseen)
        self.assertEqual(RiskAssessment.objects.get(risk=risk).level, 12)
        self.assertEqual(RiskTreatment.objects.get(risk=risk).decision, RiskTreatment.Decision.MITIGATE)

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
        self.assertNotContains(response, 'name="progress"')
        self.assertNotContains(response, 'name="status"')

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
                "initial-risk-title": "Falha no levantamento",
                "initial-risk-cause": "Dados incompletos",
                "initial-risk-owner": self.user.id,
                "initial-risk-probability": "2",
                "initial-risk-impact": "3",
            },
        )
        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(action_plan=action_plan)
        self.assertEqual(activity.weight, 40)
        self.assertEqual(activity.start_date, date(2026, 5, 1))
        self.assertEqual(activity.end_date, date(2026, 6, 30))
        self.assertEqual(activity.funding_source, "FAF")
        self.assertEqual(activity.progress, 0)
        self.assertEqual(activity.status, StrategicAction.Status.NOT_STARTED)
        self.action.refresh_from_db()
        self.assertEqual(self.action.progress, 0)

        follow_up_url = f"/planos-de-acao/{self.action.id}/atividades/{activity.id}/acompanhar/"
        response = self.client.post(follow_up_url, {"operation": "update_progress", "progress-progress": "25"})
        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertEqual(activity.progress, 25)
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
            "initial-risk-title": "Atraso na entrega",
            "initial-risk-cause": "Equipe indisponível",
            "initial-risk-owner": self.user.id,
            "initial-risk-probability": "2",
            "initial-risk-impact": "3",
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
        self.assertEqual(self.action.progress, Decimal("30"))
        self.assertEqual(action_plan.activities.get(title="Terceira").progress, 0)
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

    def test_evidence_title_starts_with_expected_delivery_and_remains_editable(self):
        self.client.login(username="copin", password="senha-segura")
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(
            action_plan=action_plan,
            executor=self.user,
            title="Preparar relatório",
            expected_delivery="Relatório final",
            weight=100,
            end_date=date(2026, 12, 31),
        )
        url = f"/planos-de-acao/{self.action.id}/atividades/{activity.id}/acompanhar/"
        response = self.client.get(url)
        self.assertContains(response, 'name="evidence-title"')
        self.assertContains(response, 'value="Relatório final"')

        response = self.client.post(url, {
            "operation": "add_evidence",
            "evidence-title": "Produto revisado",
            "evidence-evidence_type": ActivityEvidence.EvidenceType.ATTACHMENT,
            "evidence-attachment": SimpleUploadedFile("prova.txt", b"Entrega realizada"),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(activity.evidences.get().title, "Produto revisado")

    def test_delete_last_activity_with_related_records_resets_action_progress(self):
        self.client.login(username="copin", password="senha-segura")
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(
            action_plan=action_plan, executor=self.user, title="Entrega",
            weight=100, progress=50, end_date=date(2026, 12, 31),
        )
        risk = Risk.objects.create(
            action=self.action, activity=activity, owner=self.user,
            title="Risco da entrega", cause="Teste", probability=2, impact=2,
        )
        ActivityEvidence.objects.create(
            activity=activity, created_by=self.user, title="Comprovante",
            evidence_type=ActivityEvidence.EvidenceType.ATTACHMENT,
        )
        ActivityBlocker.objects.create(
            activity=activity, created_by=self.user, description="Impedimento",
        )
        self.action.progress = 50
        self.action.status = StrategicAction.Status.IN_PROGRESS
        self.action.save(update_fields=["progress", "status"])

        url = f"/planos-de-acao/{self.action.id}/atividades/{activity.id}/excluir/"
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Activity.objects.filter(pk=activity.pk).exists())
        self.assertFalse(ActivityEvidence.objects.filter(activity_id=activity.pk).exists())
        self.assertFalse(ActivityBlocker.objects.filter(activity_id=activity.pk).exists())
        risk.refresh_from_db()
        self.assertIsNone(risk.activity_id)
        self.action.refresh_from_db()
        self.assertEqual(self.action.progress, 0)
        self.assertEqual(self.action.status, StrategicAction.Status.NOT_STARTED)

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
        follow_up_url = f"/planos-de-acao/{self.action.id}/atividades/{activity.id}/acompanhar/"
        edit_page = self.client.get(edit_url)
        self.assertNotContains(edit_page, 'name="progress"')
        self.assertNotContains(edit_page, 'name="status"')
        follow_up_page = self.client.get(follow_up_url)
        self.assertContains(follow_up_page, 'name="progress-progress"')
        self.assertContains(follow_up_page, 'value="update_progress"')
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
        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertEqual(activity.progress, 0)
        self.assertEqual(activity.status, StrategicAction.Status.DELAYED)

        response = self.client.post(follow_up_url, {"operation": "update_progress", "progress-progress": "100"})
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
        response = self.client.post(follow_up_url, {"operation": "update_progress", "progress-progress": "100"})
        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertEqual(activity.status, StrategicAction.Status.COMPLETED)

    def test_blocker_accepts_external_owners(self):
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(
            action_plan=plan, executor=self.user, title="Atividade externa", weight=100,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        url = f"/planos-de-acao/{self.action.pk}/atividades/{activity.pk}/acompanhar/"
        page = self.client.get(url)
        self.assertContains(page, "Ator externo ao órgão")
        self.assertContains(page, "Ator externo ao setor")
        for value, label in ActivityBlocker.ExternalOwnerType.choices:
            response = self.client.post(url, {
                "operation": "add_blocker",
                "blocker-description": f"Impedimento {value}",
                "blocker-resolution_owner_choice": f"external:{value}",
                "blocker-status": ActivityBlocker.Status.OPEN,
            })
            self.assertEqual(response.status_code, 302)
            blocker = ActivityBlocker.objects.get(description=f"Impedimento {value}")
            self.assertIsNone(blocker.resolution_owner)
            self.assertEqual(blocker.external_owner_type, value)
            self.assertContains(self.client.get(url), f"Responsável: {label}")

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
                "blocker-resolution_owner_choice": f"user:{self.user.id}",
                "blocker-expected_resolution_date": "2026-06-10",
                "blocker-status": ActivityBlocker.Status.PARTIALLY_RESOLVED,
                "blocker-resolution_note": "Cobrança encaminhada.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ActivityBlocker.objects.filter(activity=activity).count(), 1)
        blocker = ActivityBlocker.objects.get(activity=activity)
        self.assertEqual(blocker.get_status_display(), "Parcialmente resolvido")
        self.assertContains(self.client.get(follow_up_url), "Parcialmente resolvido")

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

    def test_risk_can_be_registered_from_overview_linked_to_chosen_action(self):
        self.client.login(username="copin", password="senha-segura")
        ActionPlan.objects.create(action=self.action, manager=self.user)
        payload = {
            "action": self.action.id,
            "title": "Atraso no envio",
            "cause": "Equipe sobrecarregada",
            "owner": self.user.id,
            "probability": 2,
            "impact": 3,
            "occurrence_timing": Risk.OccurrenceTiming.UNKNOWN,
            "treatment_decision": "",
        }
        response = self.client.get("/riscos/")
        self.assertContains(response, "Cadastrar risco")

        response = self.client.post("/riscos/", payload)
        self.assertEqual(response.status_code, 302)
        risk = Risk.objects.get(title="Atraso no envio")
        self.assertEqual(risk.action, self.action)
        self.assertEqual(risk.status, Risk.Status.IDENTIFIED)
        self.assertEqual(RiskAssessment.objects.get(risk=risk).level, 6)

        response = self.client.post("/riscos/", {**payload, "title": "Sem AE", "action": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Risk.objects.filter(title="Sem AE").exists())

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
        self.assertContains(response, "Dados e momento")
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
