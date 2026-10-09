from django.contrib.auth.models import Permission
from django.db.models import Q

ACTION_LABELS = {"view": "Visualizar", "add": "Cadastrar", "change": "Editar", "delete": "Excluir"}

# Módulos exibidos no cadastro de perfis: (título, [(modelo, rótulo)]).
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
            ("group", "Perfis"),
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

# Escopo por setor ---------------------------------------------------------
ADMINISTRATOR_GROUP_NAME = "Administrador"


def is_administrator(user):
    """Superusuário ou integrante do perfil "Administrador" enxerga todos os setores."""
    if user.is_superuser:
        return True
    return user.groups.filter(name__iexact=ADMINISTRATOR_GROUP_NAME).exists()


def user_unit_ids(user):
    """IDs do setor do usuário e dos setores abaixo dele; `None` quando não há restrição."""
    if is_administrator(user):
        return None
    cached = getattr(user, "_unit_scope_ids", None)
    if cached is not None:
        return cached
    from .models import OrganizationalUnit

    profile = getattr(user, "profile", None)
    ids = set()
    if profile and profile.unit_id:
        ids.add(profile.unit_id)
        pending = [profile.unit_id]
        while pending:
            children = set(
                OrganizationalUnit.objects.filter(parent_id__in=pending).values_list("id", flat=True)
            ) - ids
            ids |= children
            pending = list(children)
    user._unit_scope_ids = ids
    return ids


def scope_units(queryset, user):
    ids = user_unit_ids(user)
    return queryset if ids is None else queryset.filter(pk__in=ids)


def scope_actions(queryset, user):
    """Ações coordenadas ou com participação do setor do usuário."""
    ids = user_unit_ids(user)
    if ids is None:
        return queryset
    from .models import StrategicAction

    visible = StrategicAction.objects.filter(
        Q(coordinating_unit_id__in=ids) | Q(participating_units__in=ids)
    ).values("pk")
    return queryset.filter(pk__in=visible)


def scope_by_unit(queryset, user, field, include_unassigned=False):
    """Restringe `queryset` a registros cujo campo de setor (`field`) esteja no escopo do usuário.

    Com `include_unassigned`, registros sem setor (institucionais) continuam visíveis.
    """
    ids = user_unit_ids(user)
    if ids is None:
        return queryset
    condition = Q(**{f"{field}__in": ids})
    if include_unassigned:
        condition |= Q(**{f"{field}__isnull": True})
    return queryset.filter(condition)
