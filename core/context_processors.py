from .models import Plan


def navigation_plans(request):
    if not request.user.is_authenticated:
        return {"navigation_plans": []}
    return {"navigation_plans": Plan.objects.order_by("acronym", "name")}
