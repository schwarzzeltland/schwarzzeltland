from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse_lazy

from buildings.forms import AddMaterialStockForm, MaterialForm
from buildings.models import Material, StockMaterial
from main.models import Membership


def constructions(request):
    return render(request, 'buildings/constructions.html', {
        'title': 'Konstruktionen',
    })


def material(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    if m.material_manager:
        form = AddMaterialStockForm(organization=request.org)
        if request.method == 'POST':
            form = AddMaterialStockForm(request.POST, organization=request.org)
            if form.is_valid():
                form.save()
                messages.success(request, 'Material Added')
                return HttpResponseRedirect(reverse_lazy('material'))
    else:
        form = None

    return render(request, 'buildings/material.html', {
        'title': 'Material',
        'material': StockMaterial.objects.filter(organization=request.org),
        'form': form,
    })


def edit_material(request):
    form = MaterialForm(organization=request.org)
    if request.method == 'POST':
        form = MaterialForm(request.POST, organization=request.org)
        if form.is_valid():
            form.save()
            StockMaterial.objects.create(material=form.instance, organization=request.org,
                                         count=form.cleaned_data['count'],
                                         storage_place=form.cleaned_data['storage_place'])
            messages.success(request, 'Material Added')
            return HttpResponseRedirect(reverse_lazy('material'))

    return render(request, 'buildings/edit_material.html', {
        'title': 'Add Material',
        'form': form,
    })
