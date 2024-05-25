from django.shortcuts import render


def constructions(request):
    return render(request, 'buildings/constructions.html', {
        'title': 'Konstruktionen',
    })


def material(request):
    return render(request, 'buildings/material.html', {
        'title': 'Material',
    })
