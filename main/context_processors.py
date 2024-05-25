def current_organization(request):
    org = None
    if request.user.is_authenticated:
        if "org" in request.POST:
            org = request.user.organization_set.filter(id=request.POST["org"]).first()
            request.session["org"] = org.id
        elif "org" in request.session:
            org = request.user.organization_set.filter(id=request.session["org"]).first()
        if org is None:
            org = request.user.organization_set.first()
    # Define variables you want to provide in every template
    return {
        'organization': org,
    }
