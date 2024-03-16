from django.db.models import Q
from django.shortcuts import render

from buildings.models import Construction
from main.forms import ConstructionForm


# Create your views here.
def home_view(request):
    form = ConstructionForm()
    return render(request, 'main/index.html', {
        'title': 'Home',
        'constructions': Construction.objects.filter(Q(owner__isnull=True) | Q(public=True)),
        'form': form
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