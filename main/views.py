from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from buildings.models import Construction


# Create your views here.
def home_view(request):
    return render(request, 'main/index.html', {
        'title': 'Home',
        'constructions': Construction.objects.filter(Q(owner__isnull=True) | Q(public=True)),
    })


@login_required
def organization_view(request):
    return render(request, 'main/organization.html', {
        'title': 'Organisation',
    })


def contacts_view(request):
    return render(request, 'main/contacts.html', {
        'title': 'Kontakt',
    })


def impressum_view(request):
    return render(request, 'main/impressum.html', {
        'title': 'Impressum',
    })


def disclaimer_view(request):
    return render(request, 'main/disclaimer.html', {
        'title': 'Haftungsausschluss',
    })


def privacypolice_view(request):
    return render(request, 'main/privacypolice.html', {
        'title': 'Datenschutzerklärung',
    })


def help_view(request):
    return render(request, 'main/help.html', {
        'title': 'Was ist Schwarzzeltland?',
    })
