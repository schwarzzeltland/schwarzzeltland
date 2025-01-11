from collections import defaultdict
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

                # Berechnung des neuen Namens basierend auf dem ersten Teil
                first_part = c.name.split(' ', 1)[0]
                existing_names = Construction.objects.filter(owner=request.org, name__startswith=first_part)
                count = existing_names.count()
                new_name = f"{first_part} {count + 1}" if count > 0 else f"{first_part} 1"

                # Neue Konstruktion erstellen
                new_construction = Construction.objects.create(
                    owner=request.org,
                    name=new_name,
                    public=False,
                    description=c.description,
                    sleep_place_count=c.sleep_place_count,
                    covered_area=c.covered_area,
                    required_space=c.required_space,
                    image=c.image
                )

                # Materialien der Vorlage kopieren
                materials = c.constructionmaterial_set.all()
                for material in materials:
                    material.pk = None  # Primärschlüssel entfernen, um ein neues Objekt zu erstellen
                    material.construction = new_construction
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
def show_construction(request, pk=None):
    construction = get_object_or_404(Construction, pk=pk, owner=request.org)
    construction_material = ConstructionMaterial.objects.filter(construction=construction)
    return render(request, 'buildings/show_construction.html', {
        'title': 'Konstruktion anzeigen',
        'construction': construction,
        'construction_material': construction_material,
    })


@login_required
@material_manager_required
def edit_construction(request, pk=None):
    # Bestehende Konstruktion abrufen, falls PK übergeben wurde
    if pk:
        construction = get_object_or_404(Construction, pk=pk, owner=request.org)
    else:
        construction = None
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
                for material in materials:
                    material.construction = construction
                    material.save()
                for form in material_formset:
                    if form.cleaned_data.get('add_to_stock'):  # Prüfen, ob die Checkbox ausgewählt wurde
                        # Hole das Material- und Lager-Objekt
                        material = form.save(commit=False)
                        material.construction = construction
                        material.save()
                        # Originalmaterial aus dem Formular holen
                        original_material = form.cleaned_data['material']

                        # Prüfen, ob das Material bereits existiert
                        existing_material = Material.objects.filter(owner=request.org,
                                                                    name=original_material.name).first()

                        if not existing_material:
                            # Neues Material erstellen, indem das Original kopiert wird
                            cloned_material = Material.objects.create(
                                name=original_material.name,
                                description=original_material.description,
                                owner=request.org,
                                public=False,
                                image=original_material.image,
                                weight=original_material.weight,
                                type=original_material.type,
                                length_min=original_material.lenghth_min,
                                length_max=original_material.lenghth_max,
                                width=original_material.witdh
                            )
                        else:
                            # Existierendes Material verwenden
                            cloned_material = existing_material

                        ##
                        # Versuche, StockMaterial zu holen oder zu erstellen
                        stock_material, created = StockMaterial.objects.get_or_create(
                            material=cloned_material,
                            organization=request.org,
                            storage_place=material.storage_place,
                            defaults={'count': 0}  # Standardwert, falls StockMaterial neu ist
                        )

                        # Aktualisiere die Menge im Lager
                        stock_material.count += material.count
                        stock_material.save()
                material_formset.save_m2m()

                # Materialzuordnungen für diese Konstruktion
                materials = ConstructionMaterial.objects.filter(construction=construction)

                # Sammlung von Materialien nach Namen gruppieren
                material_names = defaultdict(list)

                # Gruppiere Materialien nach Namen
                for material in materials:
                    material_names[material.material.name].append(material)

                available_materials = []
                missing_materials = []
                missing = False  # Trackt, ob Materialien fehlen

                # Überprüfung der Materialverfügbarkeit
                for material_name, materials_group in material_names.items():
                    # Berechne die Gesamtmenge der verfügbaren Materialien (basierend auf dem Namen)
                    stock_materials = StockMaterial.objects.filter(
                        material__name=material_name,
                        organization=request.org
                    )

                    # Berechne die Gesamtmenge der verfügbaren Materialien
                    available_quantity = sum(m.count for m in stock_materials)

                    # Sammle Informationen über Lagerorte und Mengen
                    storage_info = [{'storage_place': m.storage_place, 'available_quantity': m.count} for m in
                                    stock_materials]

                    # Berechne die gesamte benötigte Menge für dieses Material
                    total_required_quantity = sum(material.count for material in materials_group)

                    # Verfügbarkeit prüfen
                    if available_quantity >= total_required_quantity:
                        available_materials.append({
                            'material': material_name,  # Materialname für dieses Material
                            'required_quantity': total_required_quantity,
                            'available_quantity': available_quantity,
                            'storage_info': storage_info
                        })
                    else:
                        missing_materials.append({
                            'material': material_name,  # Materialname für dieses Material
                            'required_quantity': total_required_quantity,
                            'available_quantity': available_quantity,
                            'missing_quantity': total_required_quantity - available_quantity,
                            'storage_info': storage_info
                        })
                        missing = True

                    # Wenn Materialien fehlen, zeige eine Warnung und die Liste der fehlenden Materialien an
                if missing:
                    messages.warning(request,
                                     'Konstruktion gespeichert. Einige Materialien sind jedoch nicht vorhanden.')
                else:
                    # Alle Materialien sind verfügbar, also keine Fehlermeldung anzeigen
                    messages.success(request, 'Alle Materialien sind ausreichend vorhanden.')
                m: Membership = request.user.membership_set.filter(organization=request.org).first()
                # Weiterleitung zum Verfügbarkeitsfenster (immer, auch wenn keine Materialien fehlen)
                return render(request, 'buildings/check_material.html', {
                    'title': 'Materialübersicht',
                    'construction': construction,
                    'available_materials': available_materials,
                    'missing_materials': missing_materials,
                    'is_material_manager': m.material_manager,
                })
    else:
        construction_form = ConstructionForm(instance=construction)
        material_formset = ConstructionMaterialFormSet(instance=construction, form_kwargs={'organization': request.org})
    org_materials = Material.objects.filter(owner=request.org).order_by('name')
    external_materials = Material.objects.filter(
        Q(owner__isnull=True) | Q(public=True) & ~Q(owner=request.org)
    ).order_by('name')
    materials = {
        "organization": org_materials,
        "external": external_materials,
    }

    return render(request, 'buildings/edit_constructions.html', {
        'title': 'Konstruktion bearbeiten',
        'construction_form': construction_form,
        'construction': construction,
        'material_formset': material_formset,
        'materials': materials,
    })


@login_required
def check_material(request, pk=None):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()

    # Überprüfen der Konstruktion
    construction = get_object_or_404(Construction, pk=pk, owner=request.org)

    # Materialzuordnungen für diese Konstruktion
    materials = ConstructionMaterial.objects.filter(construction=construction)

    # Sammlung von Materialien nach Namen gruppieren
    material_names = defaultdict(list)

    # Gruppiere Materialien nach Namen
    for material in materials:
        material_names[material.material.name].append(material)

    available_materials = []
    missing_materials = []
    missing = False  # Trackt, ob Materialien fehlen

    # Überprüfung der Materialverfügbarkeit
    for material_name, materials_group in material_names.items():
        # Berechne die Gesamtmenge der verfügbaren Materialien (basierend auf dem Namen)
        stock_materials = StockMaterial.objects.filter(
            material__name=material_name,
            organization=request.org
        )

        # Berechne die Gesamtmenge der verfügbaren Materialien
        available_quantity = sum(m.count for m in stock_materials)

        # Sammle Informationen über Lagerorte und Mengen
        storage_info = [{'storage_place': m.storage_place, 'available_quantity': m.count} for m in stock_materials]

        # Berechne die gesamte benötigte Menge für dieses Material
        total_required_quantity = sum(material.count for material in materials_group)

        # Verfügbarkeit prüfen
        if available_quantity >= total_required_quantity:
            available_materials.append({
                'material': material_name,  # Materialname für dieses Material
                'required_quantity': total_required_quantity,
                'available_quantity': available_quantity,
                'storage_info': storage_info
            })
        else:
            missing_materials.append({
                'material': material_name,  # Materialname für dieses Material
                'required_quantity': total_required_quantity,
                'available_quantity': available_quantity,
                'missing_quantity': total_required_quantity - available_quantity,
                'storage_info': storage_info
            })
            missing = True

        # Wenn Materialien fehlen, zeige eine Warnung und die Liste der fehlenden Materialien an
    if missing:
        messages.warning(request,
                         'Einige Materialien sind nicht ausreichend vorhanden.')
    else:
        # Alle Materialien sind verfügbar, also keine Fehlermeldung anzeigen
        messages.success(request, 'Alle Materialien sind ausreichend vorhanden.')

    # Weiterleitung zum Verfügbarkeitsfenster (immer, auch wenn keine Materialien fehlen)
    return render(request, 'buildings/check_material.html', {
        'title': 'Materialübersicht',
        'construction': construction,
        'available_materials': available_materials,
        'missing_materials': missing_materials,
        'is_material_manager': m.material_manager,
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
                # Originalmaterial aus dem Formular holen
                original_material = form.cleaned_data['material']

                # Prüfen, ob das Material bereits existiert
                existing_material = Material.objects.filter(owner=request.org, name=original_material.name).first()

                if not existing_material:
                    # Neues Material erstellen, indem das Original kopiert wird
                    cloned_material = Material.objects.create(
                        name=original_material.name,
                        description=original_material.description,
                        owner=request.org,
                        public=False,
                        image=original_material.image,
                        weight=original_material.weight,
                        type=original_material.type,
                        length_min=original_material.lenghth_min,
                        length_max=original_material.lenghth_max,
                        width=original_material.witdh
                    )
                else:
                    # Existierendes Material verwenden
                    cloned_material = existing_material

                # `StockMaterial` mit dem geklonten oder existierenden Material erstellen
                StockMaterial.objects.create(
                    material=cloned_material,
                    organization=request.org,
                    count=form.cleaned_data['count'],
                    storage_place=form.cleaned_data['storage_place']
                )

                messages.success(request, f'Material "{original_material.name}" wurde kopiert und einsortiert.')
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
        deleted_st_mat = mat.material
        mat.delete()
        all_stockmaterials = StockMaterial.objects.filter(organization=request.org)
        second_st_mat = False
        for st_mat in all_stockmaterials:
            if st_mat.material == deleted_st_mat:
                second_st_mat = True
        if not second_st_mat:
            deleted_st_mat.delete()
        messages.success(request, f'Material {mat.material.name} erfolgreich gelöscht.')
        return HttpResponseRedirect(reverse_lazy('material'))
    return render(request, 'buildings/delete_material.html', {'title': 'Material löschen', 'material': mat.material})


@login_required
def show_material(request, pk=None):
    material = get_object_or_404(StockMaterial, pk=pk, organization=request.org)
    return render(request, 'buildings/show_material.html', {
        'title': 'Material anzeigen',
        'material': material
    })
