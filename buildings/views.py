from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from setuptools._distutils.command.config import config
from urllib3 import request

from buildings.forms import AddMaterialStockForm, MaterialForm, ConstructionForm, ImportConstructionForm, \
    ConstructionMaterialForm, ConstructionMaterialFormSet
from buildings.models import StockMaterial, Construction, ConstructionMaterial
from main.models import Membership


def constructions(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    if m.material_manager:
        form = ImportConstructionForm(organization=request.org)
        if request.method == 'POST':
            form = ImportConstructionForm(request.POST, organization=request.org)
            if form.is_valid():
                c: Construction = form.cleaned_data["construction"]
                # Extrahieren Sie den ersten Teil des Namens (bis zum ersten Leerzeichen)
                first_part = c.name.split(' ', 1)[0]
                # Überprüfen, ob ein Objekt mit dem ersten Teil des Namens bereits existiert
                existing_constructions = Construction.objects.filter(owner=request.org, name__startswith=first_part)
                if existing_constructions.exists():
                    # Wenn ein Objekt mit diesem Namen gefunden wird, zählen Sie die Anzahl
                    existing_count = existing_constructions.count()
                    new_name = f"{first_part} {existing_count + 1}"
                else:
                    # Andernfalls verwenden Sie den Namen wie gewohnt
                    new_name = c.name + ' 1'
                c.pk = None
                c.owner = request.org
                c.name = new_name
                c.public = False
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
    if request.method == 'POST':
        construction_form = ConstructionForm(request.POST)
        material_formset = ConstructionMaterialFormSet(request.POST)

        if construction_form.is_valid() and material_formset.is_valid():
            construction = construction_form.save(commit=False)
            construction.owner = request.org
            construction.save()
            messages.success(request, 'Konstruktion hinzugefügt')
            materials = material_formset.save(commit=False)
            for material in materials:
                material.construction = construction
                material.save()
            return HttpResponseRedirect(reverse_lazy('constructions'))  # Beispiel-URL für die Weiterleitung
    else:
        construction_form = ConstructionForm()
        material_formset = ConstructionMaterialFormSet()
    return render(request, 'buildings/edit_constructions.html', {
        'title' : 'Konstruktion hinzufügen',
        'construction_form': construction_form,
        'material_formset': material_formset,
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
        'title': 'Material hinzufügen',
        'form': form,
    })
