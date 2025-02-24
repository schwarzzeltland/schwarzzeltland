from collections import defaultdict
from functools import wraps
from pickle import LIST

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy

from buildings.forms import AddMaterialStockForm, MaterialForm, ConstructionForm, ImportConstructionForm, \
    ConstructionMaterialFormSet, StockMaterialForm, PlainMaterialForm
from buildings.models import StockMaterial, Construction, ConstructionMaterial, Material
from main.models import Membership
from main.decorators import material_manager_required


@login_required
def constructions(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    # Suchlogik
    search_query = request.GET.get('search', '')
    # 2. Wenn keine GET-Filter vorhanden sind, die Filter aus der Session holen
    if request.session.get('previous_url'):
        previous_url = request.session.get('previous_url')

        if 'construction/edit/' in previous_url:
            if not search_query:
                search_query = request.session.get('search', '')
            if 'search' in request.session:
                del request.session['search']

    request.session['search'] = search_query
    request.session['previous_url'] = request.build_absolute_uri()
    # Filtere Konstruktionen basierend auf der Suchanfrage
    constructions_query = Construction.objects.filter(owner=request.org).order_by('name')
    if search_query:
        constructions_query = constructions_query.filter(
            Q(name__icontains=search_query) | Q(owner__name__icontains=search_query)
        ).order_by('name')
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
    request.session['previous_url'] = request.build_absolute_uri()
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
                                length_min=original_material.length_min,
                                length_max=original_material.length_max,
                                width=original_material.width
                            )
                        else:
                            # Existierendes Material verwenden
                            cloned_material = existing_material

                        ##
                        # Versuche, StockMaterial zu holen oder zu erstellen
                        stock_material = StockMaterial.objects.filter(material=cloned_material,
                                                                      organization=request.org,
                                                                      storage_place=material.storage_place)
                        if stock_material:
                            st_mat = stock_material.first()
                            # Aktualisiere die Menge im Lager
                            st_mat.count += material.count
                            st_mat.save()
                        else:
                            stock_material = StockMaterial.objects.create(
                                material=cloned_material,
                                organization=request.org,
                                storage_place=material.storage_place,
                                count=material.count
                            )

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

                # Unterscheidung der Weiterleitungen basierend auf dem Button
                if 'save' in request.POST:
                    # Wenn der Speichern-Button gedrückt wurde, weiter zu Trips
                    messages.success(request, f'Konstruktion {construction.name} gespeichert.')
                    return redirect('constructions')
                elif 'check_material' in request.POST:
                    # Wenn der Materialverfügbarkeits-Button gedrückt wurde, weiter zu Materialverfügbarkeit prüfen
                    return redirect('check_material', construction.pk)  # Weiterleitung zur Materialverfügbarkeitspr
    else:
        construction_form = ConstructionForm(instance=construction)
        material_formset = ConstructionMaterialFormSet(instance=construction, form_kwargs={'organization': request.org})
    org_materials = Material.objects.filter(owner=request.org).order_by('name')
    external_materials = Material.objects.filter(
        Q(public=True) & ~Q(owner=request.org) & Q(owner__isnull=False)).order_by('name')
    public_materials = Material.objects.filter(Q(owner__isnull=True)).order_by('name')
    materials = {
        "organization": org_materials,
        "public": public_materials,
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
    selected_material_type = request.GET.get('material_type', '')  # Materialtyp
    selected_material_condition = request.GET.get('material_condition', '')
    # 2. Wenn keine GET-Filter vorhanden sind, die Filter aus der Session holen
    if request.session.get('previous_url'):
        previous_url = request.session.get('previous_url')
        if 'material/edit/' in previous_url:
            if not search_query:
                search_query = request.session.get('search', '')
            if 'search' in request.session:
                del request.session['search']

            if not selected_material_type:
                selected_material_type = request.session.get('material_type', '')
            if 'material_type' in request.session:
                del request.session['material_type']

            if not selected_material_condition:
                selected_material_condition = request.session.get('material_condition', '')
            if 'material_condition' in request.session:
                del request.session['material_condition']
    request.session['search'] = search_query
    request.session['material_type'] = selected_material_type
    request.session['material_condition'] = selected_material_condition
    request.session['previous_url'] = request.build_absolute_uri()
    # Filtere nach Name oder Lagerort, wenn eine Suchanfrage vorliegt
    if search_query:
        materials = StockMaterial.objects.filter(
            Q(material__name__icontains=search_query) |
            Q(storage_place__icontains=search_query),
            organization=request.org
        ).order_by('material__name')
    else:
        materials = StockMaterial.objects.filter(organization=request.org).order_by('material__name')
    # Filterung nach Materialtyp
    if selected_material_type:
        materials = materials.filter(material__type=selected_material_type).order_by('material__name')
    # Alle Materialtypen abrufen (für Dropdown-Menü)
    TYPES = (
        (0, "Dachplane"),
        (1, "Zeltplane"),
        (2, "Stange"),
        (3, "Seil"),
        (4, "Hering"),
        (5, "Küchenmaterial"),
        (6, "Verbrauchsmaterial"),
    )
    if selected_material_condition:
        print(selected_material_condition)
        if selected_material_condition=="healthy":
            materials = materials.filter(condition_healthy__gt=0)
        elif selected_material_condition=="medium":
            materials = materials.filter(condition_medium_healthy__gt=0)
        elif selected_material_condition == "broke":
            materials = materials.filter(condition_broke__gt=0)
    if m.material_manager:
        form = AddMaterialStockForm(organization=request.org)
        if request.method == 'POST':
            form = AddMaterialStockForm(request.POST, organization=request.org)
            print(form.errors)
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
                        length_min=original_material.length_min,
                        length_max=original_material.length_max,
                        width=original_material.width
                    )
                else:
                    # Existierendes Material verwenden
                    cloned_material = existing_material

                # `StockMaterial` mit dem geklonten oder existierenden Material erstellen
                StockMaterial.objects.create(
                    material=cloned_material,
                    organization=request.org,
                    count=form.cleaned_data['count'],
                    storage_place=form.cleaned_data['storage_place'],
                    condition_healthy=form.cleaned_data['count'],
                    condition_medium_healthy=0,
                    condition_broke=0)

                messages.success(request,
                                 f'Material "{original_material.name}" wurde kopiert und einsortiert. Änderungen an einer der Kopien werden auf alle Kopien angewandt!')
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
        'selected_material_type': selected_material_type,
        'selected_material_condition': selected_material_condition,
        'material_types': TYPES,
    })


@login_required
@material_manager_required
def create_material(request):
    form = MaterialForm(organization=request.org)
    if request.method == 'POST':
        form = MaterialForm(request.POST, request.FILES, organization=request.org)
        if form.is_valid():
            form.instance.owner = request.org
            material = form.save()
            StockMaterial.objects.create(material=material, organization=request.org,
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
    request.session['previous_url'] = request.build_absolute_uri()
    mat = get_object_or_404(StockMaterial, pk=pk, organization=request.org)
    if request.method == 'POST':
        form = StockMaterialForm(request.POST, instance=mat)
        mat_form = PlainMaterialForm(request.POST, request.FILES, instance=mat.material)
        if form.is_valid() and mat_form.is_valid():
            if 'save' in request.POST:
                form.save()
                mat_form.save()
                messages.success(request, f'Material {mat.material.name} gespeichert')
                return HttpResponseRedirect(reverse_lazy('material'))
            elif 'save-as-new' in request.POST:
                form.instance.owner = request.org
                print(mat_form.instance.pk)
                mat_form.instance.pk = None
                material = mat_form.save()
                print(material.pk)
                StockMaterial.objects.create(material=material, organization=request.org,
                                             count=form.cleaned_data['count'],
                                             storage_place=form.cleaned_data['storage_place'],
                                             condition_healthy=form.cleaned_data['condition_healthy'],
                                             condition_medium_healthy=form.cleaned_data['condition_medium_healthy'],
                                             condition_broke=form.cleaned_data['condition_broke'],
                                             material_condition_description=form.cleaned_data[
                                                 'material_condition_description'])
                stm = StockMaterial.objects.last()
                print(stm)
                print(mat.pk)
                mat.delete()
                messages.success(request, f'Material {mat.material.name} als neues Material gespeichert')
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
    mat = get_object_or_404(StockMaterial, pk=pk, organization=request.org)
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
    material.material.type = material.material.get_type_display()
    return render(request, 'buildings/show_material.html', {
        'title': 'Material anzeigen',
        'material': material
    })
