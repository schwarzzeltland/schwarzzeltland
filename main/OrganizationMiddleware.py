from django.http import HttpResponseRedirect
from django.utils.deprecation import MiddlewareMixin


class OrganizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        org = None
        if request.user.is_authenticated:
            if "org" in request.POST:
                org = request.user.organization_set.filter(id=request.POST["org"]).first()
                request.session["org"] = org.id
                return HttpResponseRedirect(request.get_full_path())
            elif "org" in request.session:
                org = request.user.organization_set.filter(id=request.session["org"]).first()
            if org is None:
                org = request.user.organization_set.first()

        setattr(request, "org", org)

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        return response
