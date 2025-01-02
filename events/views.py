from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def trip(request):
    return render(request, 'events/trip.html', {
        'title': 'Veranstaltungen',
    })

@login_required
def location(request):
    return render(request, 'events/locations.html', {
        'title': 'Orte',
    })
