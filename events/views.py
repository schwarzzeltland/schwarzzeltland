from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from main.models import Membership


@login_required
def trip(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    if m.admin:
        print('Hallo')

    return render(request, 'events/trip.html', {
        'title': 'Veranstaltungen',
    })


@login_required
def location(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    if m.admin:
        print('Hallo')


    return render(request, 'events/locations.html', {
        'title': 'Orte',
    })
