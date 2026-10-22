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
        self.user.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="core").exclude(codename__in=["change_indicator", "change_indicatormeasurement", "view_other_units"])
        )

    def create_risk(self, **kwargs):
        if "activity" not in kwargs:
            action = kwargs["action"]
            plan, _ = ActionPlan.objects.get_or_create(action=action, defaults={"manager": self.user})
            kwargs["activity"] = Activity.objects.create(
                action_plan=plan, executor=self.user, title="Atividade do risco",
                weight=0, end_date=action.due_date or date(2026, 12, 31),
            )
        return Risk.objects.create(**kwargs)

    def test_risk_sections_require_their_own_permissions(self):
        action_plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        risk = self.create_risk(
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
        risk = self.create_risk(
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
            self.create_risk(action=self.action, owner=self.user, title=f"Risco {score}", cause="Teste", probability=score, impact=score)
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

    def test_risk_record_cards_contain_actions_and_materialization_can_be_managed(self):
        from html.parser import HTMLParser

        class CardActions(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []
                self.actions = {}

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag in ("button", "a") and "record-action" in attrs.get("class", "").split():
                    self.actions[attrs.get("aria-label")] = any("record-card" in classes for _, classes in self.stack)
                if tag not in ("input", "br", "hr", "img", "meta", "link", "path"):
                    self.stack.append((tag, attrs.get("class", "").split()))

            def handle_endtag(self, tag):
                for index in range(len(self.stack) - 1, -1, -1):
                    if self.stack[index][0] == tag:
                        del self.stack[index:]
                        break

        self.client.force_login(self.user)
        risk = self.create_risk(action=self.action, owner=self.user, title="Risco dos cards", cause="Teste", probability=2, impact=3, status=Risk.Status.MATERIALIZED)
        RiskAssessment.objects.create(risk=risk, probability=2, impact=3, author=self.user)
        RiskTreatment.objects.create(risk=risk, decision="MITIGAR", responsible=self.user, created_by=self.user)
        RiskAcceptance.objects.create(risk=risk, authority=self.user, recorded_by=self.user, decision="ACEITO", justification="Aceite")
        occurrence = RiskMaterialization.objects.create(risk=risk, occurred_on=date(2026, 10, 1), description="Original", actual_impact="Atraso", actions_taken="Acompanhar", recorded_by=self.user)
        url = f"/planos-de-acao/{self.action.pk}/riscos/{risk.pk}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        parser = CardActions()
        parser.feed(response.content.decode())
        for label in ("Editar identificação do risco", "Excluir risco", "Editar momento de ocorrência", "Editar avaliação", "Excluir avaliação", "Editar resposta e tratamento", "Excluir resposta", "Editar materialização", "Excluir materialização", "Editar aceite", "Excluir aceite"):
            with self.subTest(label=label):
                self.assertTrue(parser.actions.get(label))
        self.assertNotContains(response, "<summary>Editar resposta e tratamento</summary>")
        self.assertNotContains(response, "<summary>Revisar momento ou condição</summary>")
        response = self.client.get(url, {"editar_materializacao": occurrence.pk})
        self.assertContains(response, 'value="edit_materialization"')
        payload = {"operation": "edit_materialization", "materialization_id": occurrence.pk, "materialization-occurred_on": "2026-10-02", "materialization-description": "Revisado", "materialization-actual_impact": "Impacto revisado", "materialization-actions_taken": "Corrigir"}
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.description, "Revisado")
        self.assertEqual(risk.materializations.count(), 1)
        self.user.user_permissions.remove(Permission.objects.get(codename="delete_riskmaterialization"), Permission.objects.get(codename="change_riskmaterialization"))
        self.assertEqual(self.client.post(url, payload).status_code, 403)
        self.assertEqual(self.client.post(url, {"operation": "delete_materialization", "materialization_id": occurrence.pk}).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename="delete_riskmaterialization"))
        self.assertEqual(self.client.post(url, {"operation": "delete_materialization", "materialization_id": occurrence.pk}).status_code, 302)
        self.assertFalse(risk.materializations.exists())
        risk.refresh_from_db()
        self.assertEqual(risk.status, Risk.Status.MONITORING)
        self.assertRedirects(self.client.post(url, {"operation": "delete_risk"}), "/riscos/")
        self.assertFalse(Risk.objects.filter(pk=risk.pk).exists())

    def test_materialized_risks_without_started_plan_are_reclassified(self):
        from importlib import import_module
        from types import SimpleNamespace
        from django.apps import apps
        from django.core.exceptions import ValidationError
        from django.db import connection

        risk = self.create_risk(action=self.action, owner=self.user, title="Sem execução iniciada", cause="Teste", probability=2, impact=3, status=Risk.Status.MATERIALIZED)
        treated = self.create_risk(action=self.action, owner=self.user, title="Com tratamento", cause="Teste", probability=2, impact=3, status=Risk.Status.MATERIALIZED)
        RiskTreatment.objects.create(risk=treated, decision="MITIGAR", responsible=self.user, created_by=self.user)
        occurrence = RiskMaterialization.objects.create(risk=risk, occurred_on=date(2026, 10, 22), description="Histórico preservado", actual_impact="Atraso", actions_taken="Correção", recorded_by=self.user)
        missing_plan_action = StrategicAction.objects.create(artifact=self.artifact, coordinating_unit=self.unit, code="AE SEM PLANO", title="Sem plano", status=StrategicAction.Status.IN_PROGRESS)
        orphan = Risk.objects.create(action=missing_plan_action, activity=risk.activity, owner=self.user, title="Legado sem plano", cause="Teste", probability=2, impact=3, status=Risk.Status.MATERIALIZED)
        correction = import_module("core.migrations.0028_reclassify_risks_without_started_plan").reclassify_risks
        correction(apps, SimpleNamespace(connection=connection))
        risk.refresh_from_db()
        treated.refresh_from_db()
        orphan.refresh_from_db()
        self.assertEqual(risk.status, Risk.Status.IDENTIFIED)
        self.assertEqual(treated.status, Risk.Status.IN_TREATMENT)
        self.assertEqual(orphan.status, Risk.Status.IDENTIFIED)
        self.assertTrue(RiskMaterialization.objects.filter(pk=occurrence.pk).exists())
        new_occurrence = RiskMaterialization(risk=risk, occurred_on=date(2026, 10, 22), description="Nova", actual_impact="Atraso", actions_taken="Correção", recorded_by=self.user)
        with self.assertRaises(ValidationError):
            new_occurrence.clean()
        self.action.status = StrategicAction.Status.IN_PROGRESS
        self.action.save()
        risk.refresh_from_db()
        new_occurrence.clean()
        risk.status = Risk.Status.MATERIALIZED
        risk.save()
        correction(apps, SimpleNamespace(connection=connection))
        risk.refresh_from_db()
        self.assertEqual(risk.status, Risk.Status.MATERIALIZED)

    def test_materialization_requires_an_action_plan_in_progress(self):
        self.client.force_login(self.user)
        self.assertFalse(self.action.can_materialize_risks)
        self.action.status = StrategicAction.Status.IN_PROGRESS
        self.action.save()
        self.assertFalse(self.action.can_materialize_risks)  # Status alone is insufficient.
        risk = self.create_risk(action=self.action, owner=self.user, title="Materialização controlada", cause="Teste", probability=2, impact=3)
        self.assertTrue(self.action.can_materialize_risks)
        url = f"/planos-de-acao/{self.action.pk}/riscos/{risk.pk}/"
        activity_url = f"/planos-de-acao/{self.action.pk}/atividades/{risk.activity_id}/acompanhar/"
        payload = {"operation": "materialize", "materialization-occurred_on": "2026-10-22", "materialization-description": "Ocorrência", "materialization-actual_impact": "Atraso", "materialization-actions_taken": "Correção"}
        for status in StrategicAction.Status.values:
            if status == StrategicAction.Status.IN_PROGRESS:
                continue
            with self.subTest(status=status):
                self.action.status = status
                self.action.save()
                response = self.client.post(url, payload)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["materialization_form"].non_field_errors())
                self.assertContains(response, "o plano de ação precisa estar em andamento")
                self.assertFalse(risk.materializations.exists())
                response = self.client.post(activity_url, {
                    "operation": "report_risk", "risk-report-risk": risk.pk,
                    "risk-report-materialized": "SIM", "occurrence-occurred_on": "2026-10-22",
                    "occurrence-description": "Ocorrência", "occurrence-actual_impact": "Atraso", "occurrence-actions_taken": "Correção",
                })
                self.assertEqual(response.status_code, 200)
                self.assertIn("materialized", response.context["risk_report_form"].errors)
                self.assertFalse(risk.materializations.exists())
                response = self.client.post(activity_url, {
                    "operation": "add_risk", "risk-title": "Não deve ser criado", "risk-cause": "Teste",
                    "risk-treatment_responsible": self.user.pk, "risk-probability": 2, "risk-impact": 3,
                    "risk-status": Risk.Status.MATERIALIZED, "risk-occurrence_timing": Risk.OccurrenceTiming.ANY_TIME, "risk-treatment": "Mitigar",
                })
                self.assertEqual(response.status_code, 200)
                self.assertIn("status", response.context["risk_form"].errors)
                self.assertFalse(Risk.objects.filter(title="Não deve ser criado").exists())
        self.action.status = StrategicAction.Status.IN_PROGRESS
        self.action.save()
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(risk.materializations.count(), 1)
        risk.refresh_from_db()
        self.assertEqual(risk.status, Risk.Status.MATERIALIZED)
        # Completing the plan must not erase a past occurrence or prevent its correction.
        self.action.status = StrategicAction.Status.COMPLETED
        self.action.save()
        occurrence = risk.materializations.get()
        self.assertEqual(self.client.post(url, {**payload, "operation": "edit_materialization", "materialization_id": occurrence.pk}).status_code, 302)
        self.assertEqual(risk.materializations.count(), 1)

    def test_execution_risk_map_handles_risks_without_treatment(self):
        self.client.force_login(self.user)
        risk = self.create_risk(action=self.action, owner=self.user, title="Sem tratamento", cause="Teste", probability=2, impact=3)
        execution = self.client.get(f"/planos-de-acao/{self.action.pk}/")
        url = f"/planos-de-acao/{self.action.pk}/riscos/"
        self.assertContains(execution, f'href="{url}">Riscos e aceites</a>')
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Sem tratamento")
        self.assertContains(page, "Não definido")
        responsible = User.objects.create_user(username="responsavel-tratamento", first_name="Pessoa", last_name="Responsável")
        RiskTreatment.objects.create(risk=risk, decision="MITIGAR", responsible=responsible, created_by=self.user)
        self.assertContains(self.client.get(url), "Pessoa Responsável")
        responsible.first_name = ""
        responsible.last_name = ""
        responsible.save()
        self.assertContains(self.client.get(url), "responsavel-tratamento")
        self.user.user_permissions.remove(Permission.objects.get(codename="view_risktreatment"))
        self.assertNotContains(self.client.get(url), "<td>responsavel-tratamento</td>")

    def test_risk_has_one_editable_response_and_acceptance(self):
        risk = self.create_risk(action=self.action, owner=self.user, title="Risco único", cause="Teste", probability=2, impact=2)
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
        risk = self.create_risk(action=self.action, owner=self.user, title="Risco sem duplicatas", cause="Teste", probability=2, impact=2)
        for Model, fields in (
            (RiskTreatment, dict(responsible=self.user, created_by=self.user, decision="MITIGAR")),
            (RiskAcceptance, dict(authority=self.user, recorded_by=self.user, decision="ACEITO", justification="Aceito")),
        ):
            Model.objects.create(risk=risk, **fields)
            with self.assertRaises(IntegrityError), transaction.atomic():
                Model.objects.create(risk=risk, **fields)

    def test_existing_risk_records_require_change_and_delete_permissions(self):
        risk = self.create_risk(action=self.action, owner=self.user, title="Risco protegido", cause="Teste", probability=2, impact=2)
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
        risk = self.create_risk(action=self.action, owner=self.user, title="Excluir avaliação", cause="Teste", probability=5, impact=5)
        old = RiskAssessment.objects.create(risk=risk, author=self.user, probability=2, impact=3)
        latest = RiskAssessment.objects.create(risk=risk, author=self.user, probability=5, impact=5)
        url = f"/planos-de-acao/{self.action.id}/riscos/{risk.id}/"
        self.client.force_login(self.user)
        self.assertContains(self.client.get(url), "Excluir avaliação")
        response = self.client.post(url, {"operation": "delete_assessment", "assessment_id": latest.id})
        self.assertRedirects(response, url + "#analise")
        risk.refresh_from_db()
        self.assertEqual((risk.probability, risk.impact), (2, 3))
        other = self.create_risk(action=self.action, owner=self.user, title="Outro risco", cause="Teste", probability=1, impact=1)
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
        risk = self.create_risk(action=self.action, owner=self.user, title="Uma avaliação", cause="Teste", probability=2, impact=2)
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
            self.create_risk(action=action, owner=self.user, title=f"Risco {code}", cause="Teste", probability=4, impact=4)
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
        from unittest.mock import patch
        with patch("core.views.timezone.localdate", return_value=date(2034, 12, 31)):
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
        risk = self.create_risk(action=other_action, owner=self.user, title="Risco externo", cause="Consulta", probability=2, impact=2)
        self.client.force_login(self.user)
        action_url = f"/planos-de-acao/{other_action.pk}/"
        self.assertEqual(self.client.get(action_url).status_code, 404)
        self.user.user_permissions.add(Permission.objects.get(codename="view_other_units"), Permission.objects.get(codename="change_indicator"), Permission.objects.get(codename="change_indicatormeasurement"))
        dashboard = self.client.get("/")
        self.assertEqual(dashboard.context["selected_unit"], str(self.unit.pk))
        self.assertEqual(dashboard.context["action_count"], 1)
        self.assertIn(other_unit, dashboard.context["units"])
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
        self.assertEqual(ActionPlan.objects.get(action=other_action).pk, risk.activity.action_plan_id)
        self.assertEqual(self.client.post(f"/planos-de-acao/{self.action.pk}/", {"operation": "start_plan"}).status_code, 302)

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

    def test_activity_risk_report_selects_existing_and_registers_unforeseen_occurrence(self):
        self.action.status = StrategicAction.Status.IN_PROGRESS
        self.action.save(update_fields=["status"])
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user, title="Atividade com riscos", weight=100, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        risk = self.create_risk(action=self.action, owner=self.user, activity=activity, title="Risco já previsto", cause="Teste", probability=2, impact=2)
        url = f"/planos-de-acao/{self.action.pk}/atividades/{activity.pk}/acompanhar/"
        response = self.client.get(url)
        self.assertContains(response, "Qual risco?")
        self.assertContains(response, "O risco se materializou?")
        self.assertContains(response, "Cadastrar risco não previsto")
        response = self.client.post(url, {"operation": "report_risk", "risk-report-risk": risk.pk, "risk-report-materialized": "NAO"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Risk.objects.count(), 1)
        risk.refresh_from_db()
        self.assertEqual(risk.activity, activity)
        self.assertFalse(risk.materializations.exists())
        data = {"operation": "report_risk", "risk-report-risk": "", "risk-report-materialized": "SIM",
                "unforeseen-title": "Risco não previsto no planejamento", "unforeseen-cause": "Evento inesperado", "unforeseen-treatment_responsible": self.user.pk, "unforeseen-occurrence_timing": Risk.OccurrenceTiming.ANY_TIME,
                "unforeseen-probability": 3, "unforeseen-impact": 4, "unforeseen-treatment": "Mitigar"}
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.assertEqual(Risk.objects.count(), 1)  # No partial save without occurrence details.
        data.update({"occurrence-occurred_on": "2026-10-16", "occurrence-description": "Evento ocorrido", "occurrence-actual_impact": "Entrega adiada", "occurrence-actions_taken": "Equipe acionada"})
        data["unforeseen-register_another"] = "on"
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        unforeseen = Risk.objects.get(is_unforeseen=True)
        self.assertEqual(response["Location"], url + f"?new=1&registered={unforeseen.pk}#riscos")
        page = self.client.get(response["Location"])
        self.assertEqual([item.pk for item in page.context["registered_risks"]], [unforeseen.pk])
        self.assertContains(page, '<details class="registered-risk">')
        self.assertContains(page, 'data-next-risk')
        self.assertEqual(unforeseen.activity, activity)
        self.assertEqual(unforeseen.status, Risk.Status.MATERIALIZED)
        self.assertEqual(unforeseen.materializations.count(), 1)
        self.assertEqual(unforeseen.assessments.count(), 1)
        other_action = StrategicAction.objects.create(artifact=self.artifact, coordinating_unit=self.unit, code="AE OUTRO RISCO", title="Outra ação")
        foreign = self.create_risk(action=other_action, owner=self.user, title="Risco de outra ação", cause="Teste", probability=1, impact=1)
        response = self.client.post(url, {"operation": "report_risk", "risk-report-risk": foreign.pk, "risk-report-materialized": "NAO"})
        self.assertEqual(response.status_code, 200)
        foreign.refresh_from_db()
        self.assertEqual(foreign.activity.action_plan.action_id, other_action.pk)
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

    def test_activity_risk_prefills_and_updates_existing_materialization(self):
        self.action.status = StrategicAction.Status.IN_PROGRESS
        self.action.save(update_fields=["status"])
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user, title="Materialização cadastrada", weight=100, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        risk = self.create_risk(action=self.action, activity=activity, owner=self.user, title="Risco já ocorrido", cause="Teste", probability=2, impact=2, status=Risk.Status.MATERIALIZED)
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
        self.action.status = StrategicAction.Status.IN_PROGRESS
        self.action.save(update_fields=["status"])
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user, title="Risco com anexo", weight=100, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        risk = self.create_risk(action=self.action, activity=activity, owner=self.user, title="Risco documentado", cause="Teste", probability=2, impact=2)
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

    def test_quarterly_report_includes_participation_summary_charts_and_evidence(self):
        from copy import deepcopy
        from .quarterly_reports import _snapshot, repair_report_scope
        self.client.force_login(self.user)
        other_unit = OrganizationalUnit.objects.create(organization=self.unit.organization, name="Coordenadora parceira")
        objective = PlanArtifact.objects.create(plan=self.artifact.plan, artifact_type=PlanArtifact.ArtifactType.OBJECTIVE, code="OE PARCERIA", title="Objetivo compartilhado")
        project = PlanArtifact.objects.create(plan=self.artifact.plan, parent=objective, artifact_type=PlanArtifact.ArtifactType.PROJECT, title="Projeto compartilhado")
        shared = StrategicAction.objects.create(artifact=project, coordinating_unit=other_unit, code="AE PARCERIA", title="Ação em participação")
        shared.participating_units.add(self.unit)
        second = StrategicAction.objects.create(artifact=project, coordinating_unit=other_unit, code="AE PARCERIA 2", title="Outra ação do mesmo projeto")
        second.participating_units.add(self.unit)
        target = StrategicTarget.objects.create(artifact=objective, code="MT PARCERIA", description="Meta do objetivo compartilhado", target_value="100")
        indicator = Indicator.objects.create(code="IE PARCERIA", name="Indicador compartilhado", responsible_unit=other_unit)
        indicator.artifacts.add(objective)
        target.indicators.add(indicator)
        plan = ActionPlan.objects.create(action=shared, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user, title="Entrega compartilhada", weight=100, end_date=date(2026, 9, 30))
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root):
            measurement = IndicatorMeasurement.objects.create(indicator=indicator, reference_period="3º trimestre", period_end=date(2026, 9, 30), measured_value="50", expected_value=100, recorded_by=self.user, evidence_attachment=SimpleUploadedFile("afericao.txt", b"prova da afericao"))
            evidence = ActivityEvidence.objects.create(activity=activity, title="Evidência compartilhada", created_by=self.user, evidence_type="ANEXO", attachment=SimpleUploadedFile("entrega.txt", b"prova da entrega"))
            ActivityEvidence.objects.filter(pk=evidence.pk).update(created_at="2026-09-01T12:00:00Z")
            snapshot = _snapshot(self.artifact.plan, self.unit, 2026, 3)
            self.assertEqual(len(snapshot["actions"]), 3)  # Own action + two participation actions.
            self.assertEqual([item["code"] for item in snapshot["targets"]], [target.code])
            self.assertEqual(len(snapshot["indicators"]), 1)
            self.assertEqual(len(snapshot["objectives"]), 2)
            report = QuarterlySectorReport.objects.create(plan=self.artifact.plan, unit=self.unit, year=2026, quarter=3, consolidated_by=self.user, snapshot=snapshot)
            url = f"/relatorios/trimestrais/{report.pk}/"
            page = self.client.get(url)
            self.assertEqual(page.status_code, 200)
            html = page.content.decode()
            self.assertLess(html.index('quarterly-report-metrics'), html.index('aria-label="Sumário do relatório"'))
            for section in ("objetivos", "metas", "indicadores", "acoes", "riscos", "evidencias", "financeiro"):
                self.assertContains(page, f'href="#{section}"')
                self.assertContains(page, f'id="{section}"')
            row = page.context["data"]["indicators"][0]
            grouped = {item["id"]: item for item in page.context["data"]["actions"]}
            self.assertEqual([item["id"] for item in grouped[shared.pk]["activities"]], [activity.pk])
            self.assertEqual(grouped[second.pk]["activities"], [])
            self.assertEqual(grouped[self.action.pk]["activities"], [])
            self.assertEqual(page.context["data"]["unassigned_activities"], [])
            self.assertContains(page, 'class="report-action-block"', count=3)
            self.assertContains(page, 'class="report-activity-table"', count=1)
            self.assertEqual(row["chart"]["result"], [50])
            self.assertEqual([item["id"] for item in row["targets"]], [target.pk])
            self.assertContains(page, "Meta planejada: 100")
            self.assertContains(page, "Executado — Indicador compartilhado")
            self.assertContains(page, "data-report-chart")
            evidence_url = page.context["data"]["evidences"][0]["download_url"]
            measurement_url = row["measurements"][0]["download_url"]
            for link, body in ((evidence_url, b"prova da entrega"), (measurement_url, b"prova da afericao")):
                download = self.client.get(link)
                self.assertEqual(download.status_code, 200)
                self.assertEqual(b"".join(download.streaming_content), body)
                download.close()
            self.user.user_permissions.remove(Permission.objects.get(codename="view_activityevidence"), Permission.objects.get(codename="view_indicatormeasurement"))
            self.assertEqual(self.client.get(evidence_url).status_code, 403)
            self.assertEqual(self.client.get(measurement_url).status_code, 403)
            self.user.user_permissions.add(Permission.objects.get(codename="view_activityevidence"), Permission.objects.get(codename="view_indicatormeasurement"))
            # Upgrade a legacy report while preserving previously consolidated values.
            legacy = deepcopy(snapshot)
            legacy.pop("scope_version")
            legacy["actions"] = [row for row in legacy["actions"] if row["code"] == self.action.code]
            legacy["actions"][0]["title"] = "Título preservado da consolidação"
            legacy["targets"] = []
            legacy["indicators"] = []
            report.snapshot = legacy
            report.save()
            self.assertTrue(repair_report_scope(report))
            self.assertEqual(len(report.snapshot["actions"]), 3)
            self.assertEqual(report.snapshot["actions"][0]["title"], "Título preservado da consolidação")
            self.assertEqual(len(report.snapshot["targets"]), 1)
            self.assertEqual(len(report.snapshot["indicators"]), 1)
            self.assertFalse(repair_report_scope(report))
            self.assertEqual(self.client.get(url + "evidencias/999/arquivo/").status_code, 404)
            # Another sector's consolidated attachment remains inaccessible.
            self.user.user_permissions.remove(Permission.objects.get(codename="view_other_units"))
            report.unit = other_unit
            report.save()
            self.assertEqual(self.client.get(evidence_url).status_code, 404)

    def test_consolidated_reports_can_be_selected_edited_and_deleted_with_scope(self):
        from copy import deepcopy
        self.client.force_login(self.user)
        report = QuarterlySectorReport.objects.create(plan=self.artifact.plan, unit=self.unit, year=2026, quarter=3, consolidated_by=self.user, snapshot={"unit": self.unit.name, "original": "preservar esta versão"})
        second = QuarterlySectorReport.objects.create(plan=self.artifact.plan, unit=self.unit, year=2026, quarter=2, consolidated_by=self.user, snapshot={})
        edit_url = f"/relatorios/trimestrais/{report.pk}/editar/"
        delete_url = f"/relatorios/trimestrais/{report.pk}/excluir/"
        page = self.client.get("/relatorios/")
        self.assertContains(page, "data-select-report")
        for item in (report, second):
            self.assertContains(page, f'value="/relatorios/trimestrais/{item.pk}/"')
            self.assertContains(page, f'data-delete-report="{item.pk}"')
        page = self.client.get("/relatorios/", {"year": "2026", "quarter": "2"})
        listed = [r.pk for row in page.context["sector_rows"] for r in row["reports"]]
        self.assertEqual(listed, [second.pk])
        page = self.client.get("/relatorios/", {"period": "2026-3"})
        self.assertEqual(page.context["selected_period"], "2026-3")
        self.assertContains(page, '<option value="2026-3" selected>3º trimestre de 2026</option>')
        self.assertNotContains(page, "Consultar ciclos de relatório anteriores")
        listed = [r.pk for row in page.context["sector_rows"] for r in row["reports"]]
        self.assertEqual(listed, [report.pk])
        page = self.client.get("/relatorios/", {"period": "2025-1"})
        self.assertEqual(page.context["sector_rows"], [])
        self.assertContains(page, "Nenhum relatório consolidado encontrado para o período selecionado.")
        page = self.client.get(edit_url)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["form"].initial["quarter"], 3)
        original = deepcopy(report.snapshot)
        payload = {"plan": self.artifact.plan_id, "unit": self.unit.pk, "year": "2026", "quarter": "3"}
        page = self.client.post(edit_url, {**payload, "quarter": "2"})
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context["form"].non_field_errors())
        report.refresh_from_db()
        self.assertEqual(report.snapshot, original)
        self.assertRedirects(self.client.post(edit_url, payload), f"/relatorios/trimestrais/{report.pk}/")
        report.refresh_from_db()
        self.assertEqual(report.snapshot["previous_versions"][0]["snapshot"], original)
        self.assertIn("last_edited_at", report.snapshot)
        self.assertEqual(QuarterlySectorReport.objects.count(), 2)
        self.user.user_permissions.remove(Permission.objects.get(codename="consolidate_quarterlysectorreport"))
        self.assertEqual(self.client.get(edit_url).status_code, 403)
        self.assertEqual(self.client.post(edit_url, payload).status_code, 403)
        self.assertEqual(self.client.post(delete_url).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename="consolidate_quarterlysectorreport"), Permission.objects.get(codename="view_other_units"))
        other_unit = OrganizationalUnit.objects.create(organization=self.unit.organization, name="Setor apenas para consulta")
        foreign = QuarterlySectorReport.objects.create(plan=self.artifact.plan, unit=other_unit, year=2026, quarter=3, consolidated_by=self.user, snapshot={})
        self.assertEqual(self.client.get(f"/relatorios/trimestrais/{foreign.pk}/editar/").status_code, 404)
        self.assertEqual(self.client.post(f"/relatorios/trimestrais/{foreign.pk}/excluir/").status_code, 404)
        self.assertEqual(self.client.get(delete_url).status_code, 405)
        self.assertEqual(self.client.post(delete_url).status_code, 302)
        self.assertFalse(QuarterlySectorReport.objects.filter(pk=report.pk).exists())
        self.assertTrue(QuarterlySectorReport.objects.filter(pk=second.pk).exists())
        self.assertTrue(StrategicAction.objects.filter(pk=self.action.pk).exists())

    def test_quarterly_report_consolidates_sector_and_freezes_snapshot(self):
        self.client.force_login(self.user)
        indicator = Indicator.objects.create(code="IE TRIMESTRE", name="Indicador do trimestre", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        target = StrategicTarget.objects.create(artifact=self.artifact, code="MT TRIMESTRE", description="Meta consolidada", target_value="100")
        target.indicators.add(indicator)
        IndicatorMeasurement.objects.create(indicator=indicator, reference_period="3º trimestre", measured_value="50", expected_value=Decimal("100"), period_end=date(2026, 9, 30), recorded_by=self.user)
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
        self.assertEqual(len(report.snapshot["indicators"][0]["measurements"]), 1)
        page = self.client.get(response.url)
        self.assertContains(page, "Meta consolidada")
        self.assertContains(page, "Consolidado")
        self.assertContains(page, 'class="signal signal-red"')
        self.assertContains(page, "quarterly-report-metrics")
        for theme in ("objectives", "targets", "indicators", "actions", "risks", "evidences", "financial"):
            self.assertContains(page, "quarterly-report-block report-theme-" + theme)
        self.assertEqual(page.context["data"]["indicators"][0]["signal_class"], "red")
        report.refresh_from_db()
        self.assertNotIn("signal_class", report.snapshot["indicators"][0])
        original = report.snapshot
        target.description = "Modificado após consolidar"
        target.save()
        self.assertEqual(self.client.post("/relatorios/", data).status_code, 302)
        self.assertEqual(QuarterlySectorReport.objects.count(), 1)
        report.refresh_from_db()
        self.assertEqual(report.snapshot, original)
        self.assertNotContains(self.client.get(response.url), "Modificado após consolidar")
        self.assertContains(self.client.get("/relatorios/"), "quarterly-sector-consolidated")
        self.assertContains(self.client.get("/relatorios/"), "Ver relatório")
        incomplete = self.client.post("/relatorios/", {"unit": self.unit.pk, "plan": self.artifact.plan_id})
        self.assertEqual(incomplete.status_code, 200)
        self.assertEqual(QuarterlySectorReport.objects.count(), 1)

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
        self.assertContains(response, "Alerta")
        self.assertEqual(response.context["signal"]["achievement"], 76.7)
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
        risk = self.create_risk(
            action=self.action,
            owner=self.user,
            title="Contingenciamento orçamentário",
            cause="Restrição de recursos",
            probability=4,
            impact=5,
        )
        self.assertEqual(risk.level, 20)

    def test_indicator_situation_accounts_for_elapsed_time_and_baseline(self):
        from unittest.mock import patch
        from .views import _indicator_signal, _indicator_pace

        plan = self.artifact.plan
        plan.start_date = date(2024, 12, 31)
        plan.end_date = date(2026, 12, 31)
        plan.save()
        indicator = Indicator.objects.create(code="IE RITMO", name="Avanço no prazo", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        target = StrategicTarget.objects.create(artifact=self.artifact, action=self.action, code="META RITMO", target_value="100")
        target.indicators.add(indicator)
        measurement = IndicatorMeasurement.objects.create(indicator=indicator, reference_period="2025", baseline_value="0", baseline_date=date(2024, 12, 31), period_end=date(2025, 12, 31), measured_value="30", expected_value=100, recorded_by=self.user)
        # The default remains the full plan regardless of today's date.
        for today in (date(2025, 1, 1), date(2026, 6, 1)):
            with patch("core.views.timezone.localdate", return_value=today):
                signal = _indicator_signal(indicator)
                self.assertEqual(signal["evaluation_date"], plan.end_date)
                self.assertEqual(signal["achievement"], 30)
                self.assertEqual(signal["expected_value"], 100)
        # Selecting 2025 changes the expected progress to exactly half the plan.
        signal = _indicator_signal(indicator, year="2025")
        self.assertEqual(signal["achievement"], 60)
        self.assertEqual(signal["expected_value"], 50)
        for result, code in (("50", "green"), ("45", "yellow"), ("35", "orange"), ("34", "red")):
            measurement.measured_value = result
            measurement.save()
            self.assertEqual(_indicator_signal(indicator, year="2025")["code"], code)
        measurement.baseline_value = "80"
        measurement.measured_value = "85"
        measurement.save()
        self.assertEqual(_indicator_signal(indicator, year="2025")["achievement"], 50)
        indicator.direction = Indicator.Direction.LOWER_IS_BETTER
        indicator.save()
        target.target_value = "10"
        target.save()
        measurement.baseline_value = "20"
        for result, code in (("15", "green"), ("15.5", "yellow"), ("16.5", "orange"), ("17", "red"), ("22", "red")):
            measurement.measured_value = result
            measurement.save()
            self.assertEqual(_indicator_signal(indicator, year="2025")["code"], code)
        self.assertEqual(_indicator_signal(indicator, year="2025")["achievement"], 0)
        signal = _indicator_pace(indicator, measurement, Decimal("15"), year="2024")
        self.assertEqual(signal["label"], "Período não iniciado")
        measurement.baseline_date = None
        measurement.expected_value = 100
        measurement.measured_value = "90"
        measurement.save()
        indicator.direction = Indicator.Direction.HIGHER_IS_BETTER
        indicator.save()
        signal = _indicator_signal(indicator)
        self.assertEqual(signal["calculation_mode"], "period")
        self.assertEqual(signal["achievement"], 90)

    def test_indicator_pace_respects_historical_year_and_displays_legend(self):
        from unittest.mock import patch
        self.client.force_login(self.user)
        plan = self.artifact.plan
        plan.start_date = date(2025, 1, 1)
        plan.end_date = date(2027, 1, 1)
        plan.save()
        indicator = Indicator.objects.create(code="IE HIST RITMO", name="Ritmo histórico", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        target = StrategicTarget.objects.create(artifact=self.artifact, action=self.action, code="MT HIST RITMO", target_value="100")
        target.indicators.add(indicator)
        IndicatorMeasurement.objects.create(indicator=indicator, reference_period="2025", baseline_value="0", baseline_date=date(2025, 1, 1), period_end=date(2025, 12, 31), measured_value="30", expected_value=50, recorded_by=self.user)
        with patch("core.views.timezone.localdate", return_value=date(2026, 12, 31)):
            page = self.client.get("/indicadores/", {"year": "2025"})
        self.assertEqual(page.status_code, 200)
        signal = page.context["indicator_rows"][0]["signal"]
        self.assertEqual(signal["evaluation_date"], date(2025, 12, 31))
        self.assertAlmostEqual(signal["achievement"], 60.2, places=1)
        self.assertEqual(signal["code"], "red")
        self.assertContains(page, "Como o tempo entra no cálculo")
        self.assertContains(page, "Índice de cumprimento do ritmo")
        self.assertContains(page, "Ritmo avaliado em 31/12/2025")
        page = self.client.get("/indicadores/")
        self.assertEqual(page.context["selected_year"], "")
        self.assertEqual(page.context["indicator_rows"][0]["signal"]["evaluation_date"], plan.end_date)
        self.assertEqual(page.context["indicator_rows"][0]["signal"]["achievement"], 30)
        self.assertContains(page, "Todos os anos")

    def test_results_year_filter_limits_measurements_signals_and_charts(self):
        self.client.force_login(self.user)
        indicator = Indicator.objects.create(code="IE ANO", name="Indicador por ano", responsible_unit=self.unit)
        indicator.artifacts.add(self.artifact)
        target = StrategicTarget.objects.create(artifact=self.artifact, action=self.action, code="META ANO", description="Meta anual", target_value="100")
        target.indicators.add(indicator)
        older = IndicatorMeasurement.objects.create(indicator=indicator, reference_period="Resultado de 2025", period_start=date(2025, 1, 1), period_end=date(2025, 12, 31), measured_value="80", expected_value=100, recorded_by=self.user)
        newer = IndicatorMeasurement.objects.create(indicator=indicator, reference_period="Resultado de 2026", period_start=date(2026, 1, 1), period_end=date(2026, 12, 31), measured_value="100", expected_value=100, recorded_by=self.user)
        for url in ("/indicadores/", "/metas/"):
            with self.subTest(url=url):
                page = self.client.get(url, {"year": "2025", "plan": self.artifact.plan_id, "unit": self.unit.pk})
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, 'name="year"')
                self.assertContains(page, '<option value="2025" selected>2025</option>')
                self.assertEqual(page.context["selected_year"], "2025")
                row = page.context["indicator_rows"][0]
                self.assertEqual(row["signal"]["measurement"].pk, older.pk)
                self.assertEqual(row["signal"]["code"], "orange")
                self.assertEqual([m.pk for m in row["measurements"]], [older.pk])
                self.assertContains(page, "Resultado de 2025")
                self.assertNotContains(page, "Resultado de 2026")
                self.assertEqual(page.context["target_rows"][0]["code"], "orange")
                page = self.client.get(url, {"year": "2026"})
                self.assertEqual(page.context["indicator_rows"][0]["signal"]["code"], "green")
                self.assertEqual(page.context["target_rows"][0]["last_measurement"].pk, newer.pk)
                page = self.client.get(url, {"year": "2027"})
                self.assertEqual(page.context["indicator_count"], 1)
                self.assertEqual(page.context["indicator_rows"][0]["signal"]["code"], "gray")
                self.assertIsNone(page.context["indicator_rows"][0]["chart"])
                self.assertEqual(page.context["indicator_rows"][0]["measurements"], [])
                page = self.client.get(url, {"year": "2025", "status": "orange"})
                self.assertEqual(page.context["indicator_count"], 1)
                self.assertEqual(len(page.context["target_rows"]), 1)
                page = self.client.get(url, {"year": "inválido"})
                self.assertEqual(page.context["selected_year"], "")
                self.assertEqual(len(page.context["indicator_rows"][0]["measurements"]), 2)
        dateless = IndicatorMeasurement.objects.create(indicator=indicator, reference_period="1º trimestre/2028", measured_value="90", expected_value=100, recorded_by=self.user)
        page = self.client.get("/indicadores/", {"year": "2028"})
        self.assertEqual(page.context["indicator_rows"][0]["signal"]["measurement"].pk, dateless.pk)
        self.assertEqual(page.context["indicator_rows"][0]["signal"]["code"], "yellow")

    def test_execution_plan_information_can_be_edited_with_permissions(self):
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        url = f"/planos-de-acao/{self.action.pk}/editar/"
        detail_url = f"/planos-de-acao/{self.action.pk}/"
        self.assertContains(self.client.get(detail_url), "Editar plano de ação")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["action_form"].initial["title"], self.action.title)
        self.assertEqual(response.context["manager_form"].initial["manager"], self.user.pk)
        manager = User.objects.create_user(username="gestor-do-plano")
        payload = {"plan-manager": manager.pk, "action-title": "Plano atualizado", "action-description": "Nova descrição", "action-due_date": "2026-11-30", "action-status": StrategicAction.Status.IN_PROGRESS, "action-participating_units": [self.unit.pk], "action-funding_sources": "FAF"}
        response = self.client.post(url, {**payload, "action-title": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("title", response.context["action_form"].errors)
        plan.refresh_from_db()
        self.assertEqual(plan.manager, self.user)
        self.assertRedirects(self.client.post(url, payload), detail_url)
        plan.refresh_from_db()
        self.action.refresh_from_db()
        self.assertEqual(plan.manager, manager)
        self.assertEqual(self.action.title, "Plano atualizado")
        self.assertEqual(self.action.description, "Nova descrição")
        self.assertEqual(self.action.due_date, date(2026, 11, 30))
        self.assertEqual(self.action.funding_sources, "FAF")
        self.assertEqual(list(self.action.participating_units.all()), [self.unit])
        self.user.user_permissions.remove(Permission.objects.get(codename="change_strategicaction"))
        response = self.client.get(url)
        self.assertIsNone(response.context["action_form"])
        self.assertRedirects(self.client.post(url, {**payload, "action-title": "Sem permissão", "plan-manager": self.user.pk}), detail_url)
        self.action.refresh_from_db()
        self.assertEqual(self.action.title, "Plano atualizado")
        self.user.user_permissions.remove(Permission.objects.get(codename="change_actionplan"))
        self.assertNotContains(self.client.get(detail_url), "Editar plano de ação")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, payload).status_code, 403)
        other_unit = OrganizationalUnit.objects.create(organization=self.unit.organization, name="Outra unidade")
        other_action = StrategicAction.objects.create(artifact=self.artifact, coordinating_unit=other_unit, code="AE EXTERNA", title="Plano externo")
        ActionPlan.objects.create(action=other_action, manager=self.user)
        self.user.user_permissions.add(Permission.objects.get(codename="view_other_units"), Permission.objects.get(codename="change_actionplan"), Permission.objects.get(codename="change_strategicaction"))
        self.assertNotContains(self.client.get(f"/planos-de-acao/{other_action.pk}/"), "Editar plano de ação")
        self.assertEqual(self.client.get(f"/planos-de-acao/{other_action.pk}/editar/").status_code, 404)
        self.assertEqual(self.client.post(f"/planos-de-acao/{other_action.pk}/editar/", payload).status_code, 404)

    def test_new_activity_can_include_multiple_risks_without_partial_saves(self):
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        url = f"/planos-de-acao/{self.action.pk}/"
        page = self.client.get(url)
        self.assertContains(page, "Riscos da atividade")
        self.assertContains(page, "data-add-activity-risk")
        self.assertContains(page, 'name="activity-risks-TOTAL_FORMS" value="0"')
        payload = {"operation": "add_activity", "title": "Atividade com riscos", "executor": self.user.pk, "weight": "100", "start_date": "2026-10-01", "end_date": "2026-12-31", "progress": "0", "status": StrategicAction.Status.NOT_STARTED, "requires_financial_resource": "NAO", "activity-risks-TOTAL_FORMS": "2", "activity-risks-INITIAL_FORMS": "0"}
        for index in range(2):
            prefix = f"activity-risks-{index}-"
            payload.update({prefix + "title": f"Risco {index}", prefix + "cause": "Causa do risco", prefix + "probability": "2", prefix + "impact": "3", prefix + "occurrence_timing": Risk.OccurrenceTiming.ANY_TIME, prefix + "treatment_decision": RiskTreatment.Decision.MITIGATE, prefix + "treatment_responsible": self.user.pk})
        response = self.client.post(url, {**payload, "activity-risks-1-occurrence_timing": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("occurrence_timing", response.context["activity_risk_formset"].forms[1].errors)
        self.assertContains(response, "data-open-on-load")
        self.assertFalse(plan.activities.exists())
        self.assertFalse(Risk.objects.exists())
        self.user.user_permissions.remove(Permission.objects.get(codename="add_risk"))
        self.assertNotContains(self.client.get(url), "data-add-activity-risk")
        self.assertEqual(self.client.post(url, payload).status_code, 403)
        self.assertFalse(plan.activities.exists())
        self.user.user_permissions.add(Permission.objects.get(codename="add_risk"))
        self.assertRedirects(self.client.post(url, payload), url)
        activity = plan.activities.get()
        self.assertEqual(activity.risks.count(), 2)
        for risk in activity.risks.all():
            self.assertEqual(risk.action, self.action)
            self.assertEqual(risk.treatments.get().responsible, self.user)
            self.assertEqual(risk.assessments.count(), 1)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, StrategicAction.Status.NOT_STARTED)
        response = self.client.post(url, {**payload, "title": "Outra atividade", "weight": "1", "confirm_rebalance": "1", "activity-risks-1-DELETE": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(plan.activities.get(title="Outra atividade").risks.count(), 1)

    def test_activity_execution_starts_with_progress_and_evidence_completes_it(self):
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        detail_url = f"/planos-de-acao/{self.action.pk}/"
        payload = {"title": "Atividade aguardando execução", "description": "Teste", "executor": self.user.pk, "weight": "100", "start_date": "2026-10-01", "end_date": "2026-12-31", "progress": "0", "status": StrategicAction.Status.IN_PROGRESS, "requires_financial_resource": "NAO"}
        self.assertEqual(self.client.post(detail_url, {**payload, "operation": "add_activity"}).status_code, 302)
        activity = plan.activities.get()
        self.action.refresh_from_db()
        self.assertEqual(activity.status, StrategicAction.Status.NOT_STARTED)
        self.assertEqual(activity.progress, 0)
        self.assertEqual(self.action.status, StrategicAction.Status.NOT_STARTED)
        self.assertEqual(self.action.progress, 0)
        edit_url = f"/planos-de-acao/{self.action.pk}/atividades/{activity.pk}/editar/"
        self.assertEqual(self.client.post(edit_url, {**payload, "progress": "25", "status": StrategicAction.Status.NOT_STARTED}).status_code, 302)
        activity.refresh_from_db()
        self.action.refresh_from_db()
        self.assertEqual(activity.status, StrategicAction.Status.IN_PROGRESS)
        self.assertEqual(self.action.status, StrategicAction.Status.IN_PROGRESS)
        self.assertEqual(self.action.progress, 25)
        self.assertEqual(self.client.post(edit_url, {**payload, "progress": "100"}).status_code, 200)
        activity.refresh_from_db()
        self.assertEqual(activity.progress, 25)
        follow_url = f"/planos-de-acao/{self.action.pk}/atividades/{activity.pk}/acompanhar/"
        evidence_payload = {"operation": "add_evidence", "evidence-title": "Entrega", "evidence-evidence_type": "ANEXO"}
        self.assertEqual(self.client.post(follow_url, evidence_payload).status_code, 200)
        activity.refresh_from_db()
        self.assertEqual(activity.progress, 25)
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root):
            response = self.client.post(follow_url, {**evidence_payload, "evidence-attachment": SimpleUploadedFile("entrega.txt", b"Entrega concluida")})
            self.assertEqual(response.status_code, 302)
            activity.refresh_from_db()
            self.action.refresh_from_db()
            self.assertEqual(activity.progress, 100)
            self.assertEqual(activity.status, StrategicAction.Status.COMPLETED)
            self.assertEqual(self.action.progress, 100)
            self.assertEqual(self.action.status, StrategicAction.Status.COMPLETED)

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

    def test_follow_up_cards_edit_evidence_and_blocker_with_scope_and_permissions(self):
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user, title="Atividade editável", weight=100, end_date=date(2026, 12, 31))
        other = Activity.objects.create(action_plan=plan, executor=self.user, title="Outra atividade", weight=0, end_date=date(2026, 12, 31))
        risk = self.create_risk(action=self.action, activity=activity, owner=self.user, title="Risco editável", cause="Teste", probability=2, impact=3)
        blocker = ActivityBlocker.objects.create(activity=activity, created_by=self.user, resolution_owner=self.user, description="Impedimento original", status=ActivityBlocker.Status.IN_TREATMENT)
        url = f"/planos-de-acao/{self.action.pk}/atividades/{activity.pk}/acompanhar/"
        other_url = f"/planos-de-acao/{self.action.pk}/atividades/{other.pk}/acompanhar/"
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root):
            evidence = ActivityEvidence.objects.create(activity=activity, created_by=self.user, title="Original", evidence_type="ANEXO", attachment=SimpleUploadedFile("original.txt", b"arquivo original"))
            filename = evidence.attachment.name
            page = self.client.get(url)
            for label in ("Editar evidência", "Editar impedimento", "Editar risco"):
                self.assertContains(page, f'aria-label="{label}"')
            self.assertContains(page, f'/planos-de-acao/{self.action.pk}/riscos/{risk.pk}/?editar_identificacao=1#dados')
            page = self.client.get(url, {"editar_evidencia": evidence.pk})
            self.assertEqual(page.context["edit_evidence_form"].initial["title"], "Original")
            evidence_payload = {"operation": "edit_evidence", "evidence_id": evidence.pk, "evidence-edit-title": "Atualizada", "evidence-edit-evidence_type": "ANEXO", "evidence-edit-description": "Nova descrição", "evidence-edit-reference": "SEI 42"}
            response = self.client.post(url, {**evidence_payload, "evidence-edit-title": ""})
            self.assertEqual(response.status_code, 200)
            self.assertIn("title", response.context["edit_evidence_form"].errors)
            evidence.refresh_from_db()
            self.assertEqual(evidence.title, "Original")
            self.assertRedirects(self.client.post(url, evidence_payload), url + "#evidencias")
            evidence.refresh_from_db()
            self.assertEqual(evidence.title, "Atualizada")
            self.assertEqual(evidence.attachment.name, filename)
            self.assertEqual(evidence.created_by, self.user)
            self.assertEqual(activity.evidences.count(), 1)
            self.assertEqual(self.client.post(url, {**evidence_payload, "evidence-edit-attachment": SimpleUploadedFile("substituto.txt", b"novo arquivo")}).status_code, 302)
            evidence.refresh_from_db()
            self.assertNotEqual(evidence.attachment.name, filename)
            self.assertEqual(activity.evidences.count(), 1)
            blocker_payload = {"operation": "edit_blocker", "blocker_id": blocker.pk, "blocker-edit-description": "Impedimento atualizado", "blocker-edit-resolution_owner": self.user.pk, "blocker-edit-status": ActivityBlocker.Status.RESOLVED, "blocker-edit-resolution_note": "Resolvido pela equipe"}
            page = self.client.get(url, {"editar_impedimento": blocker.pk})
            self.assertEqual(page.context["edit_blocker_form"].initial["description"], "Impedimento original")
            self.assertRedirects(self.client.post(url, blocker_payload), url + "#impedimentos")
            blocker.refresh_from_db()
            self.assertEqual(blocker.description, "Impedimento atualizado")
            self.assertEqual(blocker.status, ActivityBlocker.Status.RESOLVED)
            self.assertEqual(activity.blockers.count(), 1)
            for payload, query in ((evidence_payload, {"editar_evidencia": evidence.pk}), (blocker_payload, {"editar_impedimento": blocker.pk})):
                self.assertEqual(self.client.get(other_url, query).status_code, 404)
                self.assertEqual(self.client.post(other_url, payload).status_code, 404)
            self.user.user_permissions.remove(Permission.objects.get(codename="change_activityevidence"), Permission.objects.get(codename="change_activityblocker"), Permission.objects.get(codename="change_risk"))
            page = self.client.get(url)
            for label in ("Editar evidência", "Editar impedimento", "Editar risco"):
                self.assertNotContains(page, f'aria-label="{label}"')
            self.assertEqual(self.client.post(url, evidence_payload).status_code, 403)
            self.assertEqual(self.client.post(url, blocker_payload).status_code, 403)

    def test_active_blockers_pause_activity_until_all_are_resolved(self):
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user,
            title="Atividade impedida", weight=100, progress=30,
            status=StrategicAction.Status.IN_PROGRESS, end_date=date(2026, 12, 31))
        blockers = []
        for status in (ActivityBlocker.Status.OPEN, ActivityBlocker.Status.IN_TREATMENT):
            blockers.append(ActivityBlocker.objects.create(activity=activity,
                created_by=self.user, resolution_owner=self.user,
                description="Aguardando liberação", status=status))
            activity.refresh_from_db()
            self.assertEqual(activity.status, Activity.PAUSED)
            self.assertEqual(activity.get_status_display(), "Pausada")
        # Updating progress/evidence must not bypass an unresolved blocker.
        activity.progress = 100
        activity.status = StrategicAction.Status.COMPLETED
        activity.save(update_fields=["progress", "status"])
        activity.refresh_from_db()
        self.assertEqual(activity.status, Activity.PAUSED)
        blockers[0].status = ActivityBlocker.Status.RESOLVED
        blockers[0].save()
        activity.refresh_from_db()
        self.assertEqual(activity.status, Activity.PAUSED)
        blockers[1].status = ActivityBlocker.Status.RESOLVED
        blockers[1].save()
        activity.refresh_from_db()
        self.assertEqual(activity.status, StrategicAction.Status.COMPLETED)
        blockers[0].status = ActivityBlocker.Status.OPEN
        blockers[0].save()
        activity.refresh_from_db()
        self.assertEqual(activity.status, Activity.PAUSED)

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
                "risk-treatment_responsible": self.user.id,
                "risk-occurrence_timing": Risk.OccurrenceTiming.ANY_TIME,
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
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user, title="Coletar dados", weight=100, end_date=self.action.due_date)
        payload = {
            "activity": activity.id,
            "action": self.action.id,
            "title": "Atraso no envio",
            "cause": "Equipe sobrecarregada",
            "owner": self.user.id,
            "probability": 2,
            "impact": 3,
            "occurrence_timing": Risk.OccurrenceTiming.UNKNOWN,
            "treatment_decision": RiskTreatment.Decision.MITIGATE,
            "treatment_responsible": self.user.id,
        }
        response = self.client.get("/riscos/")
        self.assertContains(response, "Cadastrar risco")

        response = self.client.post("/riscos/", payload)
        self.assertEqual(response.status_code, 302)
        risk = Risk.objects.get(title="Atraso no envio")
        self.assertEqual(risk.action, self.action)
        self.assertEqual(risk.status, Risk.Status.IN_TREATMENT)
        self.assertEqual(RiskAssessment.objects.get(risk=risk).level, 6)

        response = self.client.post("/riscos/", {**payload, "title": "Sem AE", "action": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Risk.objects.filter(title="Sem AE").exists())

    def test_risk_creation_requires_context_timing_and_response_and_can_continue(self):
        self.client.force_login(self.user)
        plan = ActionPlan.objects.create(action=self.action, manager=self.user)
        activity = Activity.objects.create(action_plan=plan, executor=self.user, title="Coletar dados", weight=100, end_date=self.action.due_date)
        responsible = User.objects.create_user(username="tratamento")
        payload = {
            "action": self.action.pk, "activity": activity.pk,
            "title": "Risco obrigatório", "cause": "Dados pendentes",
            "probability": 2, "impact": 3,
            "occurrence_timing": Risk.OccurrenceTiming.ANY_TIME,
            "treatment_decision": RiskTreatment.Decision.MITIGATE,
            "treatment_responsible": responsible.pk,
        }
        page = self.client.get("/riscos/")
        self.assertNotContains(page, 'name="owner"')
        self.assertContains(page, "Cadastrar outro risco")
        for field in ("action", "activity", "occurrence_timing", "treatment_decision", "treatment_responsible"):
            with self.subTest(field=field):
                response = self.client.post("/riscos/", {**payload, field: ""})
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["create_form"].errors)
                self.assertFalse(Risk.objects.exists())
        other_action = StrategicAction.objects.create(artifact=self.artifact, coordinating_unit=self.unit, code="AE OUTRA", title="Outra ação")
        other_plan = ActionPlan.objects.create(action=other_action, manager=self.user)
        other_activity = Activity.objects.create(action_plan=other_plan, executor=self.user, title="Outra atividade", weight=100, end_date=self.action.due_date)
        response = self.client.post("/riscos/", {**payload, "activity": other_activity.pk})
        self.assertIn("activity", response.context["create_form"].errors)
        self.assertFalse(Risk.objects.exists())
        response = self.client.post("/riscos/", {**payload, "register_another": "on"}, follow=True)
        risk_id = Risk.objects.get().pk
        self.assertEqual(response.redirect_chain, [(f"/riscos/?new=1&registered={risk_id}", 302)])
        self.assertEqual([item.pk for item in response.context["registered_risks"]], [risk_id])
        self.assertContains(response, '<details class="registered-risk">')
        self.assertContains(response, 'data-next-risk')
        self.assertEqual(response.context["create_form"].initial["activity"], activity.pk)
        self.assertContains(response, "data-open-on-load")
        self.assertFalse(response.context["create_form"].is_bound)
        risk = Risk.objects.get()
        self.assertEqual(risk.treatments.get().responsible, responsible)
        self.assertEqual(risk.activity, activity)
        map_url = f"/planos-de-acao/{self.action.pk}/riscos/"
        response = self.client.post(map_url, {**payload, "title": "Segundo risco", "register_another": "on", "registered_risks": str(risk_id)}, follow=True)
        second_id = Risk.objects.get(title="Segundo risco").pk
        self.assertEqual(response.redirect_chain, [(map_url + f"?new=1&registered={risk_id}%2C{second_id}", 302)])
        self.assertEqual([item.pk for item in response.context["registered_risks"]], [risk_id, second_id])
        self.assertContains(response, "data-open-on-load")
        self.assertEqual(activity.risks.count(), 2)
        registered_ids = f"{risk_id},{second_id}"
        response = self.client.post(map_url, {**payload, "title": "", "register_another": "on", "registered_risks": registered_ids})
        self.assertEqual(response.status_code, 200)
        self.assertIn("title", response.context["form"].errors)
        self.assertEqual([item.pk for item in response.context["registered_risks"]], [risk_id, second_id])
        self.assertEqual(activity.risks.count(), 2)
        response = self.client.post(map_url, {**payload, "title": "Terceiro risco", "register_another": "on", "registered_risks": registered_ids}, follow=True)
        third = Risk.objects.get(title="Terceiro risco")
        self.assertEqual([item.pk for item in response.context["registered_risks"]], [risk_id, second_id, third.pk])
        self.assertEqual(activity.risks.count(), 3)

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
                "treatment_responsible": self.user.id,
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


class PeiDocumentResponsibilityTests(TestCase):
    def setUp(self):
        call_command("load_pei_pilot", stdout=StringIO())
        self.plan = Plan.objects.get(acronym="PEI")
        self.units = {unit.acronym: unit for unit in OrganizationalUnit.objects.all()}

    def test_document_shared_responsibilities_match_all_objectives(self):
        from .pei_responsibility_data import OBJECTIVE_RESPONSIBILITIES
        for objective, names in OBJECTIVE_RESPONSIBILITIES.items():
            expected = {self.units[name].pk for name in names}
            for indicator in Indicator.objects.filter(artifacts__plan=self.plan, code__startswith=f"IE {objective}."):
                self.assertEqual(indicator.responsible_unit_ids, expected)
                self.assertIn(indicator.responsible_unit_id, expected)
                number = indicator.code.split()[1]
                self.assertEqual(list(indicator.targets.values_list("code", flat=True)), [f"Mt {number}"])
                self.assertEqual(indicator.targets.get().artifact.code, f"OE {objective}")
        self.assertEqual(Indicator.objects.count(), 37)

    def test_shared_sector_sees_indicators_targets_and_report_without_duplicates(self):
        from .quarterly_reports import _snapshot
        from .permissions import scope_by_unit
        user = User.objects.create_user(username="ciosp-compartilhado")
        UserProfile.objects.create(user=user, unit=self.units["CIOSP"])
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label="core"))
        user.user_permissions.remove(Permission.objects.get(codename="view_other_units"))
        shared = Indicator.objects.get(code="IE 05.1")
        self.assertEqual(shared.responsible_unit, self.units["CTINF"])
        self.assertTrue(scope_by_unit(Indicator.objects.all(), user, "responsible_unit_id").filter(pk=shared.pk).exists())
        self.client.force_login(user)
        page = self.client.get("/indicadores/", {"unit": self.units["CIOSP"].pk})
        self.assertEqual(page.status_code, 200)
        codes = [row["indicator"].code for row in page.context["indicator_rows"]]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(len(codes), 8)  # OE 05 (4), OE 09 (2), OE 11 (2).
        self.assertEqual(len(page.context["target_rows"]), 8)
        self.assertIn("IE 05.1", codes)
        self.assertContains(page, "CIOSP, CTINF")
        dashboard = self.client.get("/")
        self.assertEqual(dashboard.context["indicator_total"], 8)
        snapshot = _snapshot(self.plan, self.units["CIOSP"], 2026, 3)
        self.assertEqual(len(snapshot["indicators"]), 8)
        self.assertEqual(len(snapshot["targets"]), 8)
        self.assertEqual(len(snapshot["actions"]), 11)
        foreign = Indicator.objects.get(code="IE 01.1")
        self.assertFalse(scope_by_unit(Indicator.objects.all(), user, "responsible_unit_id").filter(pk=foreign.pk).exists())

    def test_audit_corrects_mislinked_records_and_rebuilds_consolidated_report(self):
        from .quarterly_reports import _snapshot
        unit = self.units["CIOSP"]
        user = User.objects.create_user(username="autor-relatorio")
        report = QuarterlySectorReport.objects.create(plan=self.plan, unit=unit, year=2026, quarter=3, consolidated_by=user, snapshot={"original": "versão preservada"})
        indicator = Indicator.objects.get(code="IE 05.1")
        target = StrategicTarget.objects.get(code="Mt 05.1", artifact__plan=self.plan)
        indicator.responsible_units.clear()
        indicator.responsible_unit = self.units["COPIN"]
        indicator.save()
        indicator.targets.set([StrategicTarget.objects.get(code="Mt 08.1", artifact__plan=self.plan)])
        target.artifact = PlanArtifact.objects.get(plan=self.plan, code="OE 08")
        target.save()
        action = StrategicAction.objects.get(code="AE 05.1", artifact__plan=self.plan)
        action.participating_units.clear()
        call_command("sync_pei_responsibilities", stdout=StringIO())
        indicator.refresh_from_db()
        self.assertEqual(indicator.responsible_unit, self.units["COPIN"])
        call_command("sync_pei_responsibilities", apply=True, rebuild_reports=True, stdout=StringIO())
        indicator.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(indicator.responsible_unit_ids, {unit.pk, self.units["CTINF"].pk})
        self.assertEqual(target.artifact.code, "OE 05")
        self.assertEqual(indicator.targets.get(), target)
        self.assertEqual(set(action.participating_units.values_list("acronym", flat=True)), {"CIOSP"})
        report.refresh_from_db()
        self.assertEqual(report.snapshot["previous_versions"][0]["snapshot"], {"original": "versão preservada"})
        self.assertEqual(len(report.snapshot["targets"]), 8)
        self.assertEqual(len(report.snapshot["indicators"]), 8)
        self.assertEqual(len(report.snapshot["actions"]), 11)
        count = Indicator.responsible_units.through.objects.count()
        call_command("sync_pei_responsibilities", apply=True, stdout=StringIO())
        self.assertEqual(Indicator.responsible_units.through.objects.count(), count)
        self.assertEqual(QuarterlySectorReport.objects.count(), 1)


class TestExecutionDataTests(TestCase):
    def test_test_data_is_labelled_idempotent_reported_and_removable(self):
        from pathlib import Path
        from .quarterly_reports import _report_display_data
        call_command("load_pei_pilot", stdout=StringIO())
        plan = Plan.objects.get(acronym="PEI")
        action = StrategicAction.objects.filter(artifact__plan=plan).first()
        before = (action.status, action.progress)
        user = User.objects.create_user(username="auditor")
        original_plan = ActionPlan.objects.create(action=action, manager=user)
        original_activity = Activity.objects.create(action_plan=original_plan, executor=user,
            title="Atividade existente", weight=100, end_date=date(2026, 12, 31))
        old_report = QuarterlySectorReport.objects.create(plan=plan, unit=action.coordinating_unit,
            year=2026, quarter=3, consolidated_by=user, snapshot={"original": "preservar"})
        with tempfile.TemporaryDirectory() as root, override_settings(BASE_DIR=Path(root), MEDIA_ROOT=Path(root) / "media"):
            call_command("load_test_execution", year=2026, stdout=StringIO())
            counts = (Activity.objects.count(), IndicatorMeasurement.objects.count(), ActivityEvidence.objects.count(), QuarterlySectorReport.objects.count())
            self.assertEqual(counts[:3], (157, 148, 156))
            self.assertFalse(Activity.objects.exclude(pk=original_activity.pk).exclude(title__startswith="[TESTE]").exists())
            self.assertFalse(IndicatorMeasurement.objects.exclude(reference_period__startswith="[TESTE]").exists())
            self.assertFalse(ActivityEvidence.objects.exclude(title__startswith="[TESTE]").exists())
            self.assertFalse(ActivityBlocker.objects.exists())
            self.assertFalse(Activity.objects.filter(title__startswith="[TESTE]", status="NAO_INICIADA").exists())
            action.refresh_from_db()
            self.assertEqual((action.status, action.progress), before)
            self.assertFalse(User.objects.filter(username__startswith="[TESTE]").exists())
            old_report.refresh_from_db()
            self.assertEqual(old_report.snapshot["previous_versions"][0]["snapshot"], {"original": "preservar"})
            self.assertTrue(old_report.snapshot["contains_test_data"])
            self.assertTrue(old_report.snapshot["evidences"])
            data = _report_display_data(old_report.snapshot, old_report)
            self.assertTrue(all(row["targets"] for row in data["indicators"]))
            self.assertTrue(all(len(row["chart"]["result"]) == 3 for row in data["indicators"]))
            self.assertTrue(all(row["download_url"] for row in data["evidences"]))
            self.assertTrue(all(Path(root, "media", row["file"]).exists() for row in data["evidences"]))
            call_command("load_test_execution", year=2026, stdout=StringIO())
            self.assertEqual(counts, (Activity.objects.count(), IndicatorMeasurement.objects.count(), ActivityEvidence.objects.count(), QuarterlySectorReport.objects.count()))
            with self.captureOnCommitCallbacks(execute=True):
                call_command("load_test_execution", year=2026, remove=True, stdout=StringIO())
            self.assertEqual(list(Activity.objects.values_list("pk", flat=True)), [original_activity.pk])
            self.assertFalse(list(Path(root, "media/test_data").rglob("*.txt")))
            self.assertFalse(IndicatorMeasurement.objects.exists())
            self.assertFalse(Risk.objects.exists())
            old_report.refresh_from_db()
            self.assertEqual(old_report.snapshot, {"original": "preservar"})
            self.assertEqual(QuarterlySectorReport.objects.count(), 1)
            action.refresh_from_db()
            self.assertEqual((action.status, action.progress), before)
            self.assertFalse(Path(root, ".test-data/pei-2026.json").exists())

    def test_varied_test_activities_preserve_originals_and_cover_progress_scale(self):
        from pathlib import Path
        from django.db.models import Count
        call_command('load_pei_pilot', stdout=StringIO())
        user = User.objects.create_user(username='auditor')
        action = StrategicAction.objects.first()
        plan = ActionPlan.objects.create(action=action, manager=user)
        original = Activity.objects.create(action_plan=plan, executor=user, title='Atividade original',
            weight=100, progress=12, status='EM_ANDAMENTO', end_date=date(2026, 12, 31))
        before = list(StrategicAction.objects.values_list('code', 'title'))
        with tempfile.TemporaryDirectory() as root, override_settings(BASE_DIR=Path(root), MEDIA_ROOT=Path(root) / 'media'):
            call_command('load_test_execution', year=2026, stdout=StringIO())
            call_command('vary_test_execution', year=2026, stdout=StringIO())
            grouped = Activity.objects.filter(title__startswith='[TESTE]').values('action_plan').annotate(total=Count('pk'))
            self.assertEqual({row['total'] for row in grouped}, {3, 4, 5, 6, 7, 8})
            self.assertTrue(StrategicAction.objects.filter(status='CONCLUIDA').exists())
            self.assertTrue(StrategicAction.objects.filter(progress__lt=15, progress__gt=0).exists())
            self.assertTrue(StrategicAction.objects.filter(progress__gt=90).exists())
            self.assertFalse(Activity.objects.filter(title__startswith='[TESTE]', progress=0).exists())
            original.refresh_from_db()
            self.assertEqual((original.weight, original.progress, original.title), (100, 12, 'Atividade original'))
            self.assertEqual(list(StrategicAction.objects.values_list('code', 'title')), before)
            ids = set(Activity.objects.values_list('pk', flat=True))
            call_command('vary_test_execution', year=2026, stdout=StringIO())
            call_command('load_test_execution', year=2026, stdout=StringIO())
            self.assertEqual(set(Activity.objects.values_list('pk', flat=True)), ids)
            for report in QuarterlySectorReport.objects.all():
                self.assertTrue(report.snapshot['evidences'])
                self.assertTrue(all(row['target_ids'] for row in report.snapshot['indicators']))

    def test_progress_colors_change_gradually_and_keep_decimal_widths(self):
        from .templatetags.progress import progress_bar, progress_color
        self.assertEqual(progress_color(0), '#d32f2f')
        self.assertEqual(progress_color(50), '#ffd166')
        self.assertEqual(progress_color(100), '#198754')
        self.assertNotEqual(progress_color(40), progress_color(41))
        self.assertIn('width: 12.50%', progress_bar(Decimal('12.50')))
        self.assertIn('--progress-color:', progress_bar(50))


class IndicatorDocumentReferenceTests(TestCase):
    def setUp(self):
        call_command('load_pei_pilot', stdout=StringIO())
        self.user = User.objects.create_user(username='auditor-documental')

    def test_document_import_preserves_plan_and_updates_only_test_measurements(self):
        from pathlib import Path
        from .quarterly_reports import _report_display_data
        original_targets = list(StrategicTarget.objects.values())
        original_actions = list(StrategicAction.objects.values())
        indicator = Indicator.objects.get(code='IE 01.1')
        real = IndicatorMeasurement.objects.create(indicator=indicator, recorded_by=self.user,
            reference_period='Aferição existente', measured_value='56', baseline_value='10',
            baseline_date=date(2026, 1, 1), period_end=date(2026, 6, 30))
        with tempfile.TemporaryDirectory() as root, override_settings(BASE_DIR=Path(root), MEDIA_ROOT=Path(root) / 'media'):
            call_command('load_test_execution', year=2026, stdout=StringIO())
            call_command('load_indicator_reference', stdout=StringIO())
            indicator.refresh_from_db()
            self.assertFalse(indicator.reference_parameters)
            call_command('load_indicator_reference', apply=True, update_tests=True, refresh_reports=True, stdout=StringIO())
            indicator.refresh_from_db()
            self.assertEqual(indicator.baseline, '31.5')
            self.assertEqual(indicator.reference_parameters['projections']['2026'], '45.2')
            self.assertEqual(Indicator.objects.get(code='IE 02.1').measurement_unit, 'servidores')
            self.assertIsNone(Indicator.objects.get(code='IE 07.3').reference_parameters['baseline_value'])
            real.refresh_from_db()
            self.assertEqual((real.measured_value, real.baseline_value, real.baseline_date), ('56', '10', date(2026, 1, 1)))
            self.assertEqual(list(StrategicTarget.objects.values()), original_targets)
            self.assertEqual(list(StrategicAction.objects.values()), original_actions)
            test = indicator.measurements.get(reference_period='[TESTE] 4º trimestre de 2026')
            self.assertEqual(test.expected_value, Decimal('45.2'))
            self.assertEqual(test.baseline_date, date(2024, 12, 31))
            self.assertIn('[TESTE]', Path(root, 'media', test.evidence_attachment.name).read_text())
            report = QuarterlySectorReport.objects.filter(unit__acronym='COPIN', quarter=3).get()
            data = _report_display_data(report.snapshot, report)
            self.assertTrue(all(row['reference_parameters'] for row in data['indicators']))
            self.assertTrue(any(row['chart']['categories'][0] == 'Base 2024' for row in data['indicators']))
            count = IndicatorMeasurement.objects.count()
            call_command('load_test_execution', year=2026, stdout=StringIO())
            test.refresh_from_db()
            self.assertEqual(test.baseline_date, date(2024, 12, 31))
            self.assertEqual(IndicatorMeasurement.objects.count(), count)

    def test_document_projection_calculation_handles_reductions_and_annual_totals(self):
        from .indicator_reference import expected_at
        from .pei_baseline_data import REFERENCE_PARAMETERS
        from .views import _indicator_signal
        call_command('load_indicator_reference', apply=True, stdout=StringIO())
        self.assertEqual(expected_at(REFERENCE_PARAMETERS['01.1'], date(2026, 12, 31)), Decimal('45.2'))
        self.assertEqual(expected_at(REFERENCE_PARAMETERS['02.1'], date(2026, 12, 31)), Decimal('514'))
        self.assertEqual(expected_at(REFERENCE_PARAMETERS['12.2'], date(2026, 12, 31)), Decimal('25.04'))
        self.assertEqual(expected_at(REFERENCE_PARAMETERS['03.2'], date(2034, 12, 31), aggregate=True), Decimal('27'))
        self.assertIsNone(expected_at(REFERENCE_PARAMETERS['11.1'], date(2027, 12, 31)))
        decreasing = Indicator.objects.get(code='IE 12.2')
        IndicatorMeasurement.objects.create(indicator=decreasing, recorded_by=self.user,
            reference_period='[TESTE] 2026', baseline_value='26.30', baseline_date=date(2024, 12, 31),
            period_end=date(2026, 12, 31), measured_value='25.04')
        self.assertEqual(_indicator_signal(decreasing, year='2026')['achievement'], 100)
        self.assertEqual(_indicator_signal(decreasing)['achievement'], 20)
        annual = Indicator.objects.get(code='IE 10.1')
        for year, month, value in [(2025, 12, '10'), (2026, 6, '5'), (2026, 12, '10')]:
            IndicatorMeasurement.objects.create(indicator=annual, recorded_by=self.user,
                reference_period=f'[TESTE] {year}-{month}', baseline_value='0', baseline_date=date(2024, 12, 31),
                period_end=date(year, month, 30), measured_value=value)
        self.assertEqual(_indicator_signal(annual)['achievement'], 20)
        strict = Indicator.objects.get(code='IE 03.3')
        IndicatorMeasurement.objects.create(indicator=strict, recorded_by=self.user,
            reference_period='[TESTE] 2026', baseline_value='0', baseline_date=date(2024, 12, 31),
            period_end=date(2026, 12, 31), measured_value='70')
        self.assertEqual(_indicator_signal(strict, year='2026')['label'], 'Atenção')
