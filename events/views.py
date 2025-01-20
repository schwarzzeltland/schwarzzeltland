from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy

from buildings.models import Construction, StockMaterial, ConstructionMaterial
from events.forms import TripForm, TripConstructionFormSet
from events.models import Trip, TripConstruction
from main.decorators import organization_admin_required, event_manager_required
from main.models import Membership


@login_required
def trip(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()

    search_query = request.GET.get('search', '')  # Hole die Suchanfrage
    # Filtere Konstruktionen basierend auf der Suchanfrage
    trips_query = Trip.objects.filter(owner=request.org)
    selected_trip_type = request.GET.get('trip_type', '')
    if search_query:
        trips_query = trips_query.filter(
            Q(name__icontains=search_query) | Q(owner__name__icontains=search_query)
        )
    if selected_trip_type:
        trips_query = trips_query.filter(type=selected_trip_type)
    TYPES = (
        (0, "Lager"),
        (1, "Fahrt"),
        (2, "Haik"),
        (3, "Tagesaktion"),
    )
    return render(request, 'events/trip.html', {
        'title': 'Veranstaltungen',
        'trips': trips_query,
        'is_event_manager': m.event_manager,
        'search_query': search_query,
        'selected_trip_type': selected_trip_type,
        'trip_types': TYPES,
    })


@login_required
def show_trip(request, pk=None):
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)
    tripconstruction = TripConstruction.objects.filter(trip=trip)
    return render(request, 'events/show_trip.html', {
        'title': 'Konstruktion anzeigen',
        'trip': trip,
        'tripconstructions': tripconstruction,
    })


@login_required
@event_manager_required
def delete_trip(request, pk=None):
    trip_d = get_object_or_404(Trip, pk=pk)
    if request.method == 'POST':
        trip_d.delete()
        messages.success(request, f'Veranstaltung {trip_d.name} erfolgreich gelöscht.')
        return HttpResponseRedirect(reverse_lazy('trip'))
    return render(request, 'events/delete_trip.html', {'title': 'Veranstaltung löschen', 'trip': trip_d})


@login_required
def check_trip_material(request, pk=None):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()

    # Überprüfen Trip
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)

    constructions = TripConstruction.objects.filter(trip=trip)
    materials = []  # Liste für alle Materialien

    for tc in constructions:
        for i in range(tc.count):
            # Materialien für die aktuelle Konstruktion abrufen
            construction_materials = ConstructionMaterial.objects.filter(construction=tc.construction)

            # Materialien zur zentralen Liste hinzufügen
            materials.extend(construction_materials)

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
    return render(request, 'events/check_trip_material.html', {
        'title': 'Materialübersicht',
        'trip': trip,
        'available_materials': available_materials,
        'missing_materials': missing_materials,
        'is_event_manager': m.event_manager,
    })


@login_required
@event_manager_required
def edit_trip(request, pk=None):
    if pk:
        trip_d = get_object_or_404(Trip, pk=pk)
    else:
        trip_d = None
    if request.method == 'POST':
        trip_form = TripForm(request.POST, request.FILES, instance=trip_d)
        tripconstruction_formset = TripConstructionFormSet(request.POST, instance=trip_d,
                                                           form_kwargs={'organization': request.org})
        if trip_form.is_valid() & tripconstruction_formset.is_valid():
            trip_d = trip_form.save(commit=False)
            trip_d.owner = request.org
            trip_d.save()
            constructions = tripconstruction_formset.save(commit=False)
            for obj in tripconstruction_formset.deleted_objects:  # Gelöschte Objekte entfernen
                obj.delete()
            for con in constructions:
                con.trip = trip_d
                con.save()
            tripconstruction_formset.save_m2m()
            # Unterscheidung der Weiterleitungen basierend auf dem Button
            if 'save' in request.POST:
                # Wenn der Speichern-Button gedrückt wurde, weiter zu Trips
                messages.success(request, f'Veranstaltung {trip_d.name} gespeichert.')
                return redirect('trip')  # Hier 'trip' zu deiner Trip-Liste oder Detail-Seite weiterleiten
            elif 'check_material' in request.POST:
                # Wenn der Materialverfügbarkeits-Button gedrückt wurde, weiter zu Materialverfügbarkeit prüfen
                return redirect('check_trip_material', trip_d.pk)  # Weiterleitung zur Materialverfügbarkeitsprüfung
    else:
        trip_form = TripForm(instance=trip_d)
        construction_formset = TripConstructionFormSet(instance=trip_d, form_kwargs={'organization': request.org})
    org_constructions = Construction.objects.filter(owner=request.org).order_by('name')
    external_constructions = Construction.objects.filter(
        Q(owner__isnull=True) | Q(public=True) & ~Q(owner=request.org)
    ).order_by('name')
    constructions = {
        "organization": org_constructions,
        "external": external_constructions,
    }
    return render(request, 'events/edit_trip.html', {
        'title': 'Veranstaltung bearbeiten',
        'trip_form': trip_form,
        'trip': trip_d,
        'construction_formset': construction_formset,
        'constructions': constructions,
    })


@login_required
def location(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()

    search_query = request.GET.get('search', '')  # Hole die Suchanfrage
    # Filtere Konstruktionen basierend auf der Suchanfrage
    locations_query = Trip.objects.filter(owner=request.org)
    selected_location_type = request.GET.get('location_type', '')
    if search_query:
        locations_query = locations_query.filter(
            Q(name__icontains=search_query) | Q(owner__name__icontains=search_query)
        )
    if selected_location_type:
        locations_query = locations_query.filter(type=selected_trip_type)
    TYPES = (
        (0, "Lager"),
        (1, "Fahrt"),
        (2, "Haik"),
        (3, "Tagesaktion"),
    )
    return render(request, 'events/trip.html', {
        'title': 'Veranstaltungen',
        'trips': trips_query,
        'is_event_manager': m.event_manager,
        'search_query': search_query,
        'selected_trip_type': selected_trip_type,
        'trip_types': TYPES,
    })
