from .models import Plan


def navigation_plans(request):
    if not request.user.is_authenticated:
        return {"navigation_plans": []}
    return {"navigation_plans": Plan.objects.order_by("acronym", "name")}


def unit_read_permissions(request):
    from django.contrib.auth.context_processors import PermWrapper, PermLookupDict
    from .permissions import selected_unit_for_request, user_unit_ids

    if not request.user.is_authenticated:
        return {}
    ids = user_unit_ids(request.user)
    unit = selected_unit_for_request(request)
    read_only = getattr(request, "read_only_other_unit", False) or (
        ids is not None and unit.isdigit() and int(unit) not in ids
    )
    if not read_only:
        return {}

    class ReadOnlyLookup(PermLookupDict):
        def __getitem__(self, perm_name):
            if perm_name.startswith(("add_", "change_", "delete_")):
                return False
            return super().__getitem__(perm_name)

    class ReadOnlyPermissions(PermWrapper):
        def __getitem__(self, app_label):
            return ReadOnlyLookup(self.user, app_label)

    return {"perms": ReadOnlyPermissions(request.user), "read_only_other_unit": True}
