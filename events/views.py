from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def events(request):
    return render(request, 'events/events.html', {
        'title': 'Veranstaltungen',
    })
