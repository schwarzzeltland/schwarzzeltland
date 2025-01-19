from functools import wraps
from django.core.exceptions import PermissionDenied

def material_manager_required(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        membership = request.user.membership_set.filter(organization=request.org).first()
        if not membership or not membership.material_manager:
            raise PermissionDenied("Sie haben keine Berechtigung für diese Aktion.")
        return func(request, *args, **kwargs)
    return wrapper

def organization_admin_required(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        membership = request.user.membership_set.filter(organization=request.org).first()
        if not membership or not membership.admin:
            raise PermissionDenied("Sie haben keine Berechtigung für diese Aktion.")
        return func(request, *args, **kwargs)
    return wrapper

def event_manager_required(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        membership = request.user.membership_set.filter(organization=request.org).first()
        if not membership or not membership.event_manager:
            raise PermissionDenied("Sie haben keine Berechtigung für diese Aktion.")
        return func(request, *args, **kwargs)
    return wrapper