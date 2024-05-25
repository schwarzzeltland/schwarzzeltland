from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse_lazy


def current_organization(request):
    # Define variables you want to provide in every template
    return {
        'organization': request.org,
    }
