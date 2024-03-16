from django.db.models import Q
from django.shortcuts import render

from buildings.models import Construction


# Create your views here.
def main_view(request):
    return render(request, 'main/index.html', {
        'title': 'Schwarzzeltland',
        'constructions': Construction.objects.filter(Q(owner__isnull=True) | Q(public=True))
    })
