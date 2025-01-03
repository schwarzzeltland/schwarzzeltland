from pickle import LIST

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse_lazy

from buildings.forms import AddMaterialStockForm, MaterialForm, ConstructionForm, ImportConstructionForm, \
    ConstructionMaterialFormSet, StockMaterialForm, PlainMaterialForm
from buildings.models import StockMaterial, Construction, ConstructionMaterial, Material
from main.models import Membership


@login_required
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

                new_construction = Construction.objects.create(
                    owner=request.org,
                    name=new_name,
                    public=False,
                )

                # Materialien der Vorlage kopieren und der neuen Konstruktion zuordnen
                materials = c.constructionmaterial_set.all()
                for material in materials:
                    material.pk = None  # Primärschlüssel entfernen, um ein neues Objekt zu erstellen
                    material.construction = new_construction  # Der neuen Konstruktion zuordnen
                    material.save()
                messages.success(request, 'Konstruktion hinzugefügt')
                return HttpResponseRedirect(reverse_lazy('constructions'))
    else:
        form = None
    return render(request, 'buildings/constructions.html', {
        'title': 'Konstruktionen',
        'construction': Construction.objects.filter(owner=request.org),
        'form': form,
    })


@login_required
def edit_construction(request, pk=None):
    # Bestehende Konstruktion abrufen, falls PK übergeben wurde
    if pk:
        construction = get_object_or_404(Construction, pk=pk, owner=request.org)
    else:
        construction = None
    if request.method == 'POST':
        construction_form = ConstructionForm(request.POST, instance=construction)
        material_formset = ConstructionMaterialFormSet(request.POST, instance=construction)
        if construction_form.is_valid():
            construction = construction_form.save(commit=False)
            construction.owner = request.org
            construction.save()
            if material_formset.is_valid():
                # Material Speichern
                materials = material_formset.save(commit=False)  # Holen Sie alle geänderten/neu hinzugefügten Objekte
                for obj in material_formset.deleted_objects:  # Gelöschte Objekte entfernen
                    obj.delete()
                for material in materials:  # Konstruktion zu neuen Materialien hinzufügen
                    material.construction = construction
                    material.save()
                material_formset.save_m2m()
                messages.success(request, 'Konstruktion gespeichert')
                return HttpResponseRedirect(reverse_lazy('constructions'))  # Beispiel-URL für die Weiterleitung
    else:
        construction_form = ConstructionForm(instance=construction)
        material_formset = ConstructionMaterialFormSet(instance=construction, form_kwargs={'organization': request.org})
    materials = Material.objects.filter(Q(owner=request.org) | Q(owner__isnull=True) | Q(public=True))
    return render(request, 'buildings/edit_constructions.html', {
        'title': 'Konstruktion bearbeiten',
        'construction_form': construction_form,
        'material_formset': material_formset,
        'materials': materials,
    })


@login_required
def material(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    if m.material_manager:
        form = AddMaterialStockForm(organization=request.org)
        if request.method == 'POST':
            form = AddMaterialStockForm(request.POST, organization=request.org)
            if form.is_valid():
                form.save()
                messages.success(request, 'Material einsortiert')
                return HttpResponseRedirect(reverse_lazy('material'))
    else:
        form = None

    return render(request, 'buildings/material.html', {
        'title': 'Material-Lager',
        'material': StockMaterial.objects.filter(organization=request.org),
        'form': form,
    })


@login_required
def create_material(request):
    form = MaterialForm(organization=request.org)
    if request.method == 'POST':
        form = MaterialForm(request.POST, organization=request.org)
        if form.is_valid():
            form.instance.owner = request.org
            form.save()
            StockMaterial.objects.create(material=form.instance, organization=request.org,
                                         count=form.cleaned_data['count'],
                                         storage_place=form.cleaned_data['storage_place'])

            messages.success(request, 'Material einsortiert')
        return HttpResponseRedirect(reverse_lazy('material'))
    return render(request, 'buildings/create_material.html', {
        'title': 'Material erstellen',
        'form': form,
    })


@login_required
def edit_material(request, pk=None):
    mat = get_object_or_404(StockMaterial, pk=pk)
    if request.method == 'POST':
        form = StockMaterialForm(request.POST, instance=mat)
        mat_form = PlainMaterialForm(request.POST, instance=mat.material)
        if form.is_valid() and mat_form.is_valid():
            form.save()
            mat_form.save()
            messages.success(request, f'Material {mat.material.name} gespeichert')
            return HttpResponseRedirect(reverse_lazy('material'))
    else:
        form = StockMaterialForm(instance=mat)
        mat_form = PlainMaterialForm(instance=mat.material)
    return render(request, 'buildings/edit_material.html', {
        'title': 'Material berabeiten',
        'form': form,
        'mat_form': mat_form,
    })


@login_required
def delete_construction(request, pk=None):
    construction = get_object_or_404(Construction, pk=pk, owner=request.org)
    if request.method == 'POST':
        construction.delete()
        messages.success(request, f'Konstruktion {construction.name} erfolgreich gelöscht.')
        return HttpResponseRedirect(reverse_lazy('constructions'))
    return render(request, 'buildings/delete_construction.html',
                  {'title': 'Konstruktion löschen', 'construction': construction})


@login_required
def delete_material(request, pk=None):
    mat = get_object_or_404(StockMaterial, pk=pk)
    if request.method == 'POST':
        mat.delete()
        messages.success(request, f'Material {mat.material.name} erfolgreich gelöscht.')
        return HttpResponseRedirect(reverse_lazy('material'))
    return render(request, 'buildings/delete_material.html', {'title': 'Material löschen', 'material': mat.material})
