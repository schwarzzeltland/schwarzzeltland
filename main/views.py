from django.shortcuts import render


# Create your views here.
def home_view(request):
    return render(request, 'main/index.html', {
        'title': 'Home',
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