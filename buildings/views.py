from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse_lazy
from urllib3 import request

from buildings.forms import AddMaterialStockForm, MaterialForm, ConstructionForm,ImportConstructionForm
from buildings.models import StockMaterial, Construction
from main.models import Membership


def constructions(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    if m.material_manager:
        form = ImportConstructionForm()
        if request.method == 'POST':
             form = ImportConstructionForm(request.POST)
             if form.is_valid():
                c: Construction=form.cleaned_data["construction"]
                c.pk=None
                c.owner=request.org
                c.save()
                messages.success(request, 'Konstruktion hinzugefügt')
                return HttpResponseRedirect(reverse_lazy('constructions'))
    else:
        form = None
    return render(request, 'buildings/constructions.html', {
        'title': 'Konstruktionen',
        'construction': Construction.objects.filter(owner=request.org),
        'form': form,
    })


def edit_construction(request):
    form = ConstructionForm(organization=request.org)
    if request.method == 'POST':
        form = ConstructionForm(request.POST, organization=request.org)
        if form.is_valid():
            Construction.objects.create(name=form.instance, owner=request.org)
            messages.success(request, 'Konstruktion hinzugefügt')
            return HttpResponseRedirect(reverse_lazy('constructions'))

    return render(request, 'buildings/edit_constructions.html', {
        'title': 'Konstruktion hinzufügen',
        'form': form,
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
        'title': 'Materialien',
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
