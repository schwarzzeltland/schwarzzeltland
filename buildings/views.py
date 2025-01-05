from functools import wraps
from pickle import LIST

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse_lazy

from buildings.forms import AddMaterialStockForm, MaterialForm, ConstructionForm, ImportConstructionForm, \
    ConstructionMaterialFormSet, StockMaterialForm, PlainMaterialForm
from buildings.models import StockMaterial, Construction, ConstructionMaterial, Material
from main.models import Membership
from main.decorators import material_manager_required


@login_required
def constructions(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    search_query = request.GET.get('search', '')  # Hole die Suchanfrage
    # Filtere Konstruktionen basierend auf der Suchanfrage
    constructions_query = Construction.objects.filter(owner=request.org)
    if search_query:
        constructions_query = constructions_query.filter(
            Q(name__icontains=search_query) | Q(owner__name__icontains=search_query)
        )
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
        'construction': constructions_query,
        'form': form,
        'is_material_manager': m.material_manager,
        'search_query': search_query,
    })


@login_required
@material_manager_required
def edit_construction(request, pk=None):
    # Bestehende Konstruktion abrufen, falls PK übergeben wurde
    if pk:
        construction = get_object_or_404(Construction, pk=pk, owner=request.org)
    else:
        construction = None
    available_materials = []
    missing_materials = []
    if request.method == 'POST':
        construction_form = ConstructionForm(request.POST, request.FILES, instance=construction)
        material_formset = ConstructionMaterialFormSet(request.POST, instance=construction,
                                                       form_kwargs={'organization': request.org})
        if construction_form.is_valid():
            construction = construction_form.save(commit=False)
            construction.owner = request.org
            construction.save()
            if material_formset.is_valid():
                materials = material_formset.save(commit=False)  # Holen Sie alle geänderten/neu hinzugefügten Objekte
                for obj in material_formset.deleted_objects:  # Gelöschte Objekte entfernen
                    obj.delete()

                # Konstruktion speichern
                for material in materials:
                    material.construction = construction
                    material.save()

                material_formset.save_m2m()

                # Überprüfung der Materialverfügbarkeit für alle Materialien (alte + neue)
                all_materials = construction.constructionmaterial_set.all()  # Alle zugeordneten Materialien

                for material in materials:
                    # Wenn das Material neu ist, füge es hinzu
                    print(material.pk)
                    if not material.pk:
                        all_materials = all_materials | ConstructionMaterial.objects.filter(construction=construction,
                                                                                      material=material.material)
                    else:
                        # Das Material existiert bereits, aktualisiere es
                        all_materials = all_materials | ConstructionMaterial.objects.filter(pk=material.pk)

                missing = False
                print(all_materials)
                for material in all_materials:  # Überprüfung aller Materialien
                    stock_materials = StockMaterial.objects.filter(
                        material=material.material,
                        organization=request.org
                    )
                    available_quantity = sum(m.count for m in stock_materials)
                    # Speichere die Lagerorte und verfügbaren Mengen
                    storage_info = [{'storage_place': m.storage_place, 'available_quantity': m.count} for m in
                                    stock_materials]

                    print("material wird verfügbar ")
                    if available_quantity >= material.count:
                        available_materials.append({
                            'material': material.material.name,
                            'required_quantity': material.count,  # Benötigte Menge hier einfügen
                            'available_quantity': available_quantity,
                            'storage_info': storage_info
                        })
                    else:
                        missing_materials.append({
                            'material': material.material.name,
                            'required_quantity': material.count,
                            'available_quantity': available_quantity,
                            'missing_quantity': material.count - available_quantity,
                            'storage_info': storage_info
                        })
                        missing = True

                    # Wenn Materialien fehlen, zeige eine Warnung und die Liste der fehlenden Materialien an
                if missing:
                    messages.warning(request, 'Konstruktion gespeichert. Einige Materialien sind jedoch nicht vorhanden.')
                else:
                    # Alle Materialien sind verfügbar, also keine Fehlermeldung anzeigen
                    messages.success(request, 'Alle Materialien sind ausreichend vorhanden.')

                # Weiterleitung zum Verfügbarkeitsfenster (immer, auch wenn keine Materialien fehlen)
                return render(request, 'buildings/edit_construction_check_material.html', {
                    'title': 'Materialübersicht',
                    'construction': construction,
                    'available_materials': available_materials,
                    'missing_materials': missing_materials,
                })
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
    # Suchlogik
    search_query = request.GET.get('search', '')

    # Filtere nach Name oder Lagerort, wenn eine Suchanfrage vorliegt
    if search_query:
        materials = StockMaterial.objects.filter(
            Q(material__name__icontains=search_query) |
            Q(storage_place__icontains=search_query),
            organization=request.org
        )
    else:
        materials = StockMaterial.objects.filter(organization=request.org)

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
        'materials': materials,
        'form': form,
        'is_material_manager': m.material_manager,
        'organization': request.org,
        'search_query': search_query,
    })


@login_required
@material_manager_required
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
@material_manager_required
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
@material_manager_required
def delete_construction(request, pk=None):
    construction = get_object_or_404(Construction, pk=pk, owner=request.org)
    if request.method == 'POST':
        construction.delete()
        messages.success(request, f'Konstruktion {construction.name} erfolgreich gelöscht.')
        return HttpResponseRedirect(reverse_lazy('constructions'))
    return render(request, 'buildings/delete_construction.html',
                  {'title': 'Konstruktion löschen', 'construction': construction})


@login_required
@material_manager_required
def delete_material(request, pk=None):
    mat = get_object_or_404(StockMaterial, pk=pk)
    if request.method == 'POST':
        mat.delete()
        messages.success(request, f'Material {mat.material.name} erfolgreich gelöscht.')
        return HttpResponseRedirect(reverse_lazy('material'))
    return render(request, 'buildings/delete_material.html', {'title': 'Material löschen', 'material': mat.material})
