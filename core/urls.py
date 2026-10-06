from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("pei/", views.pei_overview, name="pei_overview"),
    path("metas/", views.target_overview, name="target_overview"),
    path("indicadores/", views.indicator_overview, name="indicator_overview"),
    path("indicadores/<int:indicator_id>/", views.indicator_detail, name="indicator_detail"),
    path("relatorios/", views.report_cycle_overview, name="report_cycle_overview"),
    path("relatorios/<int:cycle_id>/", views.report_cycle_detail, name="report_cycle_detail"),
    path("relatorios/<int:cycle_id>/setores/<int:report_id>/", views.sector_report_detail, name="sector_report_detail"),
    path("planos-de-acao/", views.action_plan_list, name="action_plan_list"),
    path("riscos/", views.risk_overview, name="risk_overview"),
    path("planos-de-acao/<int:action_id>/", views.action_plan_detail, name="action_plan_detail"),
    path("planos-de-acao/<int:action_id>/riscos/", views.risk_map, name="risk_map"),
    path("planos-de-acao/<int:action_id>/riscos/<int:risk_id>/", views.risk_detail, name="risk_detail"),
    path("planos-de-acao/<int:action_id>/atividades/<int:activity_id>/editar/", views.activity_edit, name="activity_edit"),
    path("planos-de-acao/<int:action_id>/atividades/<int:activity_id>/acompanhar/", views.activity_follow_up, name="activity_follow_up"),
    path("planos-de-acao/<int:action_id>/atividades/<int:activity_id>/excluir/", views.activity_delete, name="activity_delete"),
    path("planos-de-acao/<int:action_id>/atividades/<int:activity_id>/mover/<str:direction>/", views.activity_move, name="activity_move"),
    path("usuarios/", views.user_list, name="user_list"),
    path("usuarios/novo/", views.user_create, name="user_create"),
    path("usuarios/<int:user_id>/editar/", views.user_edit, name="user_edit"),
    path("usuarios/<int:user_id>/excluir/", views.user_delete, name="user_delete"),
    path("usuarios/setores/", views.unit_suggestions, name="unit_suggestions"),
    path("usuarios/grupos/", views.group_list, name="group_list"),
    path("usuarios/grupos/novo/", views.group_create, name="group_create"),
    path("usuarios/grupos/<int:group_id>/editar/", views.group_edit, name="group_edit"),
    path("usuarios/grupos/<int:group_id>/excluir/", views.group_delete, name="group_delete"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
