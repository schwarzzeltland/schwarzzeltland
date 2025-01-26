from django.http import HttpResponseRedirect
from django.utils.deprecation import MiddlewareMixin

from main.models import Organization


class OrganizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        org: Organization | None = None
        membership = None
        if request.user.is_authenticated:
            if "org" in request.POST:
                org = request.user.organization_set.filter(id=request.POST["org"]).first()
                request.session["org"] = org.id
                return HttpResponseRedirect(request.get_full_path())
            elif "org" in request.session:
                org = request.user.organization_set.filter(id=request.session["org"]).first()
            if org is None:
                org = request.user.organization_set.first()
            if org:
                membership = org.membership_set.filter(user=request.user).get()

        setattr(request, "org", org)
        setattr(request, "membership", membership)

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        return response
