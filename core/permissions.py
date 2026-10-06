from django.contrib.auth.models import Permission
from django.db.models import Q

ACTION_LABELS = {"view": "Visualizar", "add": "Cadastrar", "change": "Editar", "delete": "Excluir"}

# Módulos exibidos no cadastro de grupos: (título, [(modelo, rótulo)]).
MODULES = [
    (
        "Planejamento estratégico",
        [
            ("plan", "Planos"),
            ("planartifact", "Eixos, objetivos e projetos"),
            ("strategicaction", "Ações estratégicas"),
            ("strategictarget", "Metas"),
            ("indicator", "Indicadores"),
            ("indicatormeasurement", "Aferições"),
            ("criticalsuccessfactor", "Fatores críticos de sucesso"),
        ],
    ),
    (
        "Execução",
        [
            ("actionplan", "Planos de ação"),
            ("activity", "Atividades"),
            ("activityevidence", "Evidências"),
            ("activityblocker", "Impedimentos"),
        ],
    ),
    (
        "Riscos",
        [
            ("risk", "Riscos"),
            ("riskassessment", "Avaliações"),
            ("risktreatment", "Tratamentos"),
            ("riskmaterialization", "Materializações"),
            ("riskacceptance", "Aceites"),
            ("riskremediationsubmission", "Remediações"),
        ],
    ),
    (
        "Relatórios",
        [
            ("reportcycle", "Ciclos de relatório"),
            ("sectorreport", "Relatórios setoriais"),
        ],
    ),
    (
        "Organização e usuários",
        [
            ("organization", "Órgãos"),
            ("organizationalunit", "Setores e unidades"),
            ("userprofile", "Perfis de usuário"),
            ("user", "Usuários"),
            ("group", "Grupos"),
        ],
    ),
]


def _action(permission):
    return permission.codename.split("_", 1)[0]


def permission_modules():
    """Permissões do sistema agrupadas por módulo e por cadastro, na ordem de exibição."""
    permissions = Permission.objects.filter(
        Q(content_type__app_label="core") | Q(content_type__app_label="auth", content_type__model__in=("user", "group"))
    ).select_related("content_type")
    by_model = {}
    for permission in permissions:
        by_model.setdefault(permission.content_type.model, []).append(permission)

    order = list(ACTION_LABELS)
    modules = []
    for index, (title, entities) in enumerate(MODULES):
        rows = []
        for model, label in entities:
            ordered = sorted(
                by_model.get(model, []),
                key=lambda p: (order.index(_action(p)) if _action(p) in order else len(order), p.id),
            )
            if ordered:
                rows.append(
                    {
                        "label": label,
                        "permissions": [
                            {"id": p.id, "label": ACTION_LABELS.get(_action(p), p.name)} for p in ordered
                        ],
                    }
                )
        if rows:
            modules.append({"key": f"modulo-{index}", "title": title, "entities": rows})
    return modules
