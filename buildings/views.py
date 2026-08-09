from collections import defaultdict
from functools import wraps
from pickle import LIST
import re
import io
from pathlib import Path

from django.utils import timezone
from django.utils.timezone import now
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse, reverse_lazy

from buildings.forms import AddMaterialStockForm, MaterialForm, ConstructionForm, ImportConstructionForm, \
    ConstructionMaterialFormSet, StockMaterialForm, PlainMaterialForm, MaterialContainerForm, MaterialContainerContentsForm, MaterialContainerQrSheetForm
from buildings.models import StockMaterial, Construction, ConstructionMaterial, Material, MaterialContainer
from events.models import ShoppingListItem, Trip, TripMaterial
from main.models import Membership
from main.decorators import material_manager_required


def _load_qr_pdf_font(size):
    from PIL import ImageFont

    candidates = (
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    )
    for font_path in candidates:
        if Path(font_path).is_file():
            return ImageFont.truetype(font_path, size=size)
    raise RuntimeError("Kein Unicode-fähiger TrueType-Font für den QR-PDF-Export gefunden.")


@login_required
def constructions(request):
    temp_stock = StockMaterial.objects.filter(temporary=True,
                                              valid_until__lt=now().date())  # ausgeliehens material löschen, wenn es abgelaufen ist
    for tm in temp_stock:
        tm.material.delete()
        tm.delete()
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    # Suchlogik
    search_query = request.GET.get('search', '')
    # 2. Wenn keine GET-Filter vorhanden sind, die Filter aus der Session holen
    if request.session.get('previous_url'):
        previous_url = request.session.get('previous_url')

        if 'construction/edit/' in previous_url or 'construction/show' in previous_url or 'construction/delete' in previous_url:
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

                base_name = c.name.strip()  # Leerzeichen am Anfang/Ende entfernen
                # Prüft, ob der Name eine Zahl am Ende hat und entfernt diese
                match = re.search(r'\s*(\d+)\s*$', base_name)
                if match:
                    base_name = base_name[:match.start()].strip()  # Alles vor der Zahl behalten
                # Alle existierenden Namen mit diesem Basisnamen abrufen
                existing_names = Construction.objects.filter(
                    owner=request.org,
                    name__regex=rf'^{re.escape(base_name)}\s*\d*$'
                ).values_list("name", flat=True)
                # Höchste vorhandene Nummer extrahieren
                numbers = []
                for name in existing_names:
                    match = re.search(r'(\d+)\s*$', name)
                    if match:
                        numbers.append(int(match.group(1)))
                new_number = max(numbers, default=0) + 1  # Höchste gefundene Zahl + 1
                # Neuen Namen generieren
                new_name = f"{base_name} {new_number}"

                # Neue Konstruktion erstellen
                new_construction = Construction.objects.create(
                    owner=request.org,
                    name=new_name,
                    public=False,
                    description=c.description,
                    sleep_place_count=c.sleep_place_count,
                    covered_area=c.covered_area,
                    required_space=c.required_space
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
    request.session['previous_url'] = request.build_absolute_uri()
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
                                count=material.count,
                                condition_healthy=material.count,
                                condition_medium_healthy=0,
                                condition_broke=0)

                material_formset.save_m2m()

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
        available_quantity = sum(m.count for m in stock_materials) - sum(m.condition_broke for m in stock_materials)

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


def update_trip_material_stock_for_org(request, organization):
    """
    Prüft alle offenen TripMaterialien vom Typ 6 der Organisation
    und zieht verfügbares Material vom Lager ab.
    Fehlende Mengen werden in ShoppingListItem gespeichert.
    Zeigt Nachrichten über actions.
    """
    # Alle Trips der Organisation durchlaufen
    trips = Trip.objects.filter(owner=organization,
                                tripmaterial__material__type=6  # "materials" ist das related_name von TripMaterial
                                ).distinct()  # ggf. filter auf relevante Trips
    for trip in trips:
        trip_materials = TripMaterial.objects.filter(trip=trip, material__type=6)
        for mat in trip_materials:
            needed = mat.count - mat.reduced_from_stock
            if needed <= 0:
                continue  # schon komplett abgezogen

            mat_stock = StockMaterial.objects.filter(material__name=mat.material.name)
            av_stock = sum(stock.count for stock in mat_stock)

            if av_stock >= needed:
                # genug Material verfügbar
                remaining = needed
                mat.reduced_from_stock += remaining
                mat.previous_count = mat.count
                sl_item = ShoppingListItem.objects.filter(trip=trip, name=mat.material.name).first()
                if sl_item:
                    sl_item.delete()
                messages.success(request,
                                 f"'{mat.material.name}' wurde für Trip '{trip}' vollständig aus dem Lager abgezogen.")
            else:
                # nicht genug Material
                remaining = av_stock
                mat.reduced_from_stock += remaining
                mat.previous_count = mat.count
                missing_amount = mat.count - mat.reduced_from_stock
                if remaining > 0 and organization.pro1:
                    sl_item, created = ShoppingListItem.objects.get_or_create(
                        trip=trip,
                        name=mat.material.name,
                        defaults={"unit": "Stück", "amount": missing_amount}
                    )
                    if not created:
                        sl_item.amount = missing_amount
                    sl_item.save()
                    messages.warning(request,
                                     f"'{mat.material.name}' für Trip '{trip}' ist nicht ausreichend im Lager. "
                                     f"{remaining} vom Lager abgezogen, {missing_amount} auf Einkaufsliste aktualisiert.")
                elif remaining > 0:
                    messages.warning(request,
                                     f"'{mat.material.name}' für Trip '{trip}' ist nicht ausreichend im Lager. "
                                     f"{remaining} vom Lager abgezogen.")

            # Lagerbestand abziehen
            rem = remaining
            for stock in mat_stock:
                if stock.count >= rem:
                    stock.count -= rem
                    stock.save()
                    break
                else:
                    rem -= stock.count
                    stock.count = 0
                    stock.save()
            mat.save()


@login_required
def material(request):
    temp_stock = StockMaterial.objects.filter(temporary=True,
                                              valid_until__lt=now().date())  # ausgeliehens material löschen, wenn es abgelaufen ist
    for tm in temp_stock:
        tm.material.delete()
        tm.delete()



    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    # Suchlogik
    search_query = request.GET.get('search', '')
    selected_material_type = request.GET.get('material_type', '')  # Materialtyp
    selected_material_condition = request.GET.get('material_condition', '')
    # 2. Wenn keine GET-Filter vorhanden sind, die Filter aus der Session holen
    if request.session.get('previous_url'):
        previous_url = request.session.get('previous_url')
        if 'material/edit/' in previous_url or 'material/show/' in previous_url or 'material/delete/' in previous_url:
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
            Q(storage_place__icontains=search_query) |
            Q(container__name__icontains=search_query) |
            Q(container__storage_place__icontains=search_query),
            organization=request.org
        ).select_related("container", "material").order_by('material__name')
    else:
        materials = StockMaterial.objects.filter(organization=request.org).select_related("container", "material").order_by('material__name')
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
        (7, "Werkzeug"),
        (8, "Ersatzteil"),
    )
    if selected_material_condition:
        print(selected_material_condition)
        if selected_material_condition == "healthy":
            materials = materials.filter(condition_healthy__gt=0)
        elif selected_material_condition == "medium":
            materials = materials.filter(condition_medium_healthy__gt=0)
        elif selected_material_condition == "broke":
            materials = materials.filter(condition_broke__gt=0)
    material_groups_by_id = {}
    for stock in materials:
        group = material_groups_by_id.setdefault(stock.material_id, {
            "material": stock.material,
            "stocks": [],
            "total_count": 0,
            "condition_healthy": 0,
            "condition_medium_healthy": 0,
            "condition_broke": 0,
        })
        group["stocks"].append(stock)
        group["total_count"] += stock.count
        group["condition_healthy"] += stock.condition_healthy
        group["condition_medium_healthy"] += stock.condition_medium_healthy
        group["condition_broke"] += stock.condition_broke
    material_groups = list(material_groups_by_id.values())
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
                    container=form.cleaned_data.get('container'),
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
        'material_groups': material_groups,
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
                                         storage_place=form.cleaned_data['storage_place'],
                                         condition_healthy=form.cleaned_data['count'],
                                         condition_medium_healthy=0,
                                         condition_broke=0)
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
        form = StockMaterialForm(request.POST, instance=mat, organization=request.org)
        mat_form = PlainMaterialForm(request.POST, request.FILES, instance=mat.material)
        if form.is_valid() and mat_form.is_valid():
            if 'save' in request.POST:
                form.save()
                mat_form.save()
                messages.success(request, f'Material {mat.material.name} gespeichert')
                update_trip_material_stock_for_org(request, request.org)
                return HttpResponseRedirect(reverse_lazy('material'))
            elif 'save-as-new' in request.POST:
                form.instance.owner = request.org
                mat_form.instance.pk = None
                material = mat_form.save()
                StockMaterial.objects.create(material=material, organization=request.org,
                                             count=form.cleaned_data['count'],
                                             storage_place=form.cleaned_data['storage_place'],
                                             container=form.cleaned_data.get('container'),
                                             condition_healthy=form.cleaned_data['condition_healthy'],
                                             condition_medium_healthy=form.cleaned_data['condition_medium_healthy'],
                                             condition_broke=form.cleaned_data['condition_broke'],
                                             material_condition_description=form.cleaned_data[
                                                 'material_condition_description'])
                stm = StockMaterial.objects.last()
                messages.success(request, f'Material {stm.material.name} als neues Material gespeichert')
                update_trip_material_stock_for_org(request, request.org)
            return HttpResponseRedirect(reverse_lazy('material'))
    else:
        form = StockMaterialForm(instance=mat, organization=request.org)
        mat_form = PlainMaterialForm(instance=mat.material)
    return render(request, 'buildings/edit_material.html', {
        'title': 'Material berabeiten',
        'form': form,
        'mat_form': mat_form,
    })


@login_required
@material_manager_required
def delete_construction(request, pk=None):
    request.session['previous_url'] = request.build_absolute_uri()
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
    request.session['previous_url'] = request.build_absolute_uri()
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
    request.session['previous_url'] = request.build_absolute_uri()
    material = get_object_or_404(StockMaterial, pk=pk, organization=request.org)
    material.material.type = material.material.get_type_display()
    return render(request, 'buildings/show_material.html', {
        'title': 'Material anzeigen',
        'material': material
    })


@login_required
def material_container_list(request):
    containers = MaterialContainer.objects.filter(organization=request.org).prefetch_related("stock_items__material")
    search_query = request.GET.get("search", "").strip()
    if search_query:
        containers = containers.filter(
            Q(name__icontains=search_query)
            | Q(storage_place__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(stock_items__material__name__icontains=search_query)
        ).distinct()
    return render(request, "buildings/material_container_list.html", {
        "title": "Materialkisten", "containers": containers,
        "is_material_manager": bool(request.membership and request.membership.material_manager),
        "search_query": search_query,
    })


@login_required
@material_manager_required
def material_container_create(request):
    form = MaterialContainerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        container = form.save(commit=False)
        container.organization = request.org
        container.save()
        messages.success(request, f'Materialkiste „{container.name}“ angelegt.')
        return redirect("material_container_edit", pk=container.pk)
    return render(request, "buildings/material_container_form.html", {"title": "Materialkiste anlegen", "form": form, "container": None})


@login_required
def material_container_detail(request, pk):
    container = get_object_or_404(MaterialContainer.objects.prefetch_related("stock_items__material"), pk=pk, organization=request.org)
    return render(request, "buildings/material_container_detail.html", {
        "title": container.name, "container": container,
        "is_material_manager": bool(request.membership and request.membership.material_manager),
    })


@login_required
@material_manager_required
def material_container_edit(request, pk):
    container = get_object_or_404(MaterialContainer, pk=pk, organization=request.org)
    form = MaterialContainerForm(request.POST or None, instance=container)
    contents_form = MaterialContainerContentsForm(request.POST or None, organization=request.org, container=container)
    if request.method == "POST" and form.is_valid() and contents_form.is_valid():
        form.save()
        contents_form.save()
        messages.success(request, f'Materialkiste „{container.name}“ gespeichert.')
        return redirect("material_container_detail", pk=container.pk)
    return render(request, "buildings/material_container_form.html", {"title": "Materialkiste bearbeiten", "form": form, "contents_form": contents_form, "container": container})


@login_required
@material_manager_required
def material_container_delete(request, pk):
    container = get_object_or_404(MaterialContainer, pk=pk, organization=request.org)
    if request.method == "POST":
        name = container.name
        container.delete()
        messages.success(request, f'Materialkiste „{name}“ gelöscht. Die Materialbestände bleiben erhalten.')
        return redirect("material_container_list")
    return render(request, "buildings/material_container_delete.html", {"title": "Materialkiste löschen", "container": container})


@login_required
def material_container_qr(request, pk):
    container = get_object_or_404(MaterialContainer, pk=pk, organization=request.org)
    import qrcode
    scan_url = request.build_absolute_uri(reverse("material_container_scan", args=[container.scan_code]))
    image = qrcode.make(scan_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    response = HttpResponse(buffer.getvalue(), content_type="image/png")
    response["Content-Disposition"] = f'inline; filename="materialkiste-{container.pk}-qr.png"'
    return response


@login_required
def material_container_qr_sheet(request):
    form = MaterialContainerQrSheetForm(request.POST or None, organization=request.org)
    if request.method != "POST" or not form.is_valid():
        return render(request, "buildings/material_container_qr_sheet.html", {"title": "QR-Codes für Materialkisten", "form": form})
    containers = list(form.cleaned_data["containers"])
    output_type = form.cleaned_data["output_type"]

    import qrcode
    from PIL import Image, ImageDraw, ImageFont

    page_size = (1240, 1754)  # A4 bei ca. 150 dpi
    margin = 60
    if output_type == MaterialContainerQrSheetForm.TYPE_QR_ONLY:
        columns, rows = 3, 4
    elif output_type == MaterialContainerQrSheetForm.TYPE_WITH_CONTENTS:
        columns, rows = 2, 2
    else:
        columns, rows = 2, 4
    cell_width = (page_size[0] - 2 * margin) // columns
    cell_height = (page_size[1] - 2 * margin) // rows
    font = _load_qr_pdf_font(24)
    small_font = _load_qr_pdf_font(18)
    pages = []

    def wrap_label_text(draw, value, text_font, max_width, max_lines):
        words = str(value).split()
        lines = []
        current = ""
        while words and len(lines) < max_lines:
            word = words.pop(0)
            candidate = f"{current} {word}".strip()
            if draw.textbbox((0, 0), candidate, font=text_font)[2] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
                words.insert(0, word)
                continue
            part = ""
            for char in word:
                candidate = part + char
                if draw.textbbox((0, 0), candidate, font=text_font)[2] <= max_width:
                    part = candidate
                else:
                    lines.append(part)
                    part = char
                    if len(lines) >= max_lines:
                        break
            current = part
        if current and len(lines) < max_lines:
            lines.append(current)
        if words and lines:
            last = lines[-1]
            while last and draw.textbbox((0, 0), last + "…", font=text_font)[2] > max_width:
                last = last[:-1]
            lines[-1] = last + "…"
        return "\n".join(lines)

    for index, container in enumerate(containers):
        page_index = index // (columns * rows)
        while len(pages) <= page_index:
            pages.append(Image.new("RGB", page_size, "white"))
        position = index % (columns * rows)
        col, row = position % columns, position // columns
        x, y = margin + col * cell_width, margin + row * cell_height
        draw = ImageDraw.Draw(pages[page_index])
        scan_url = request.build_absolute_uri(reverse("material_container_scan", args=[container.scan_code]))
        qr_image = qrcode.make(scan_url).convert("RGB")
        qr_size = min(300 if output_type == MaterialContainerQrSheetForm.TYPE_QR_ONLY else 260, cell_height - 70, cell_width - 70)
        qr_image = qr_image.resize((qr_size, qr_size))
        if output_type == MaterialContainerQrSheetForm.TYPE_QR_ONLY:
            pages[page_index].paste(qr_image, (x + (cell_width - qr_size) // 2, y + (cell_height - qr_size) // 2))
            continue
        draw.rectangle((x + 8, y + 8, x + cell_width - 8, y + cell_height - 8), outline="#adb5bd", width=2)
        pages[page_index].paste(qr_image, (x + 24, y + 34))
        text_x = x + qr_size + 45
        text_width = x + cell_width - 24 - text_x
        wrapped_name = wrap_label_text(draw, container.name, font, text_width, 3)
        draw.multiline_text((text_x, y + 45), wrapped_name, fill="black", font=font, spacing=5)
        location = container.storage_place or "Kein Lagerort"
        wrapped_location = wrap_label_text(draw, location, small_font, text_width, 3)
        draw.multiline_text((text_x, y + 155), wrapped_location, fill="#495057", font=small_font, spacing=5)
        if output_type == MaterialContainerQrSheetForm.TYPE_WITH_CONTENTS:
            content_y = y + qr_size + 55
            draw.text((x + 24, content_y), "Inhalt", fill="black", font=font)
            content_y += 38
            max_content_width = cell_width - 55
            max_lines = max(1, (y + cell_height - 30 - content_y) // 24)
            content_lines = []
            for stock_item in container.stock_items.all():
                remaining_lines = max_lines - len(content_lines)
                if remaining_lines <= 0:
                    break
                wrapped = wrap_label_text(draw, f"{stock_item.material.name}: {stock_item.count}", small_font, max_content_width, remaining_lines)
                content_lines.extend(wrapped.splitlines())
            if not content_lines:
                content_lines = ["Kiste ist leer"]
            draw.multiline_text((x + 24, content_y), "\n".join(content_lines[:max_lines]), fill="#495057", font=small_font, spacing=5)

    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:], resolution=150)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="materialkisten-qr-codes.pdf"'
    return response


@login_required
def material_container_scan(request, scan_code):
    container = get_object_or_404(MaterialContainer, scan_code=scan_code)
    if not request.user.membership_set.filter(organization=container.organization).exists():
        raise PermissionDenied("Keine Berechtigung für diese Materialkiste.")
    return redirect(f'{reverse("material_container_detail", args=[container.pk])}?org={container.organization_id}')
