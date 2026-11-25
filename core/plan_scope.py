from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import Plan


def available_plans(user):
    plans = Plan.objects.filter(active=True).order_by("acronym", "pk")
    if user.is_superuser:
        return plans
    groups = user.groups.all()
    if not groups.exists():
        # Usuários antigos com permissões individuais mantêm o plano institucional.
        return plans.filter(plan_type=Plan.PlanType.PEI)
    return plans.filter(access_groups__in=groups).distinct()


def current_plans(request):
    return Plan.objects.filter(pk=getattr(request.user, "_active_plan_id", None))


def units_for_plan(queryset, user):
    if not hasattr(user, "_active_plan_id"):
        return queryset
    if user._active_plan_type == Plan.PlanType.PESP:
        return queryset.filter(exclusive_plan_id=user._active_plan_id)
    if user._active_plan_id is None:
        return queryset.none()
    return queryset.filter(Q(exclusive_plan__isnull=True) | Q(exclusive_plan_id=user._active_plan_id))


class ActivePlanMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            plans = list(available_plans(request.user))
            request.available_plans = plans
            by_id = {str(plan.pk): plan for plan in plans}
            requested = request.GET.get("plan")
            stored = by_id.get(str(request.session.get("active_plan_id")))
            active = stored or by_id.get(requested) or next(iter(plans), None)
            request.active_plan = active
            request.user._active_plan_id = active.pk if active else None
            request.user._active_plan_type = active.plan_type if active else None
            if requested or request.GET.get("unit"):
                filters = request.GET.copy()
                if active:
                    filters["plan"] = str(active.pk)
                else:
                    filters.pop("plan", None)
                if active and active.plan_type == Plan.PlanType.PESP and filters.get("unit", "").isdigit():
                    if not active.exclusive_units.filter(pk=filters["unit"]).exists():
                        filters.pop("unit")
                request.GET = filters
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        if request.resolver_match.namespace != "admin" or not user.is_staff or user.is_superuser:
            return
        # O admin do Django opera sobre o catálogo inteiro, fora do recorte de plano.
        granted = Plan.objects.filter(access_groups__in=user.groups.all()).values("pk")
        if Plan.objects.exclude(pk__in=granted).exists():
            raise PermissionDenied

