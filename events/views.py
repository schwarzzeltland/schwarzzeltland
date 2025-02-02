import os
from collections import defaultdict

from _decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from unicodedata import decimal

from buildings.models import Construction, StockMaterial, ConstructionMaterial
from events.forms import TripForm, TripConstructionFormSet, LocationForm, ImportLocationForm, TripGroupFormSet
from events.models import Trip, TripConstruction, Location, PackedMaterial, TripGroup
from main.decorators import organization_admin_required, event_manager_required
from main.models import Membership


@login_required
def trip(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    # Suchlogik
    search_query = request.GET.get('search', '')
    selected_trip_type = request.GET.get('trip_type', '')  # Materialtyp
    # 2. Wenn keine GET-Filter vorhanden sind, die Filter aus der Session holen
    if request.session.get('previous_url'):
        previous_url = request.session.get('previous_url')
        if 'trip/edit/' in previous_url:
            if not search_query:
                search_query = request.session.get('search', '')
            if 'search' in request.session:
                del request.session['search']

            if not selected_trip_type:
                selected_trip_type = request.session.get('trip_type', '')
            if 'trip_type' in request.session:
                del request.session['trip_type']

    request.session['search'] = search_query
    request.session['trip_type'] = selected_trip_type
    request.session['previous_url'] = request.build_absolute_uri()
    # Filtere Konstruktionen basierend auf der Suchanfrage
    trips_query = Trip.objects.filter(owner=request.org)
    if search_query:
        trips_query = trips_query.filter(
            Q(name__icontains=search_query) | Q(owner__name__icontains=search_query)
        ).order_by('name')
    if selected_trip_type:
        trips_query = trips_query.filter(type=selected_trip_type).order_by('name')
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
    tripgroups = TripGroup.objects.filter(trip=trip)
    trip.type = trip.get_type_display()
    total_tn_count = sum(group.count for group in TripGroup.objects.filter(trip=trip))
    return render(request, 'events/show_trip.html', {
        'title': 'Veranstaltung anzeigen',
        'trip': trip,
        'tripconstructions': tripconstruction,
        'tripgroups': tripgroups,
        'total_tn_count': total_tn_count,
    })


@login_required
@event_manager_required
def delete_trip(request, pk=None):
    trip_d = get_object_or_404(Trip, pk=pk, owner=request.org)
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

    # Informationen zu eingepackten Materialien abrufen
    packed_materials = PackedMaterial.objects.filter(trip=trip).values_list('material_name', flat=True)

    # Markiere Materialien als "eingepackt"
    for material in available_materials + missing_materials:
        material['packed'] = material['material'] in packed_materials
    # Wenn das Formular abgeschickt wurde, Checkbox-Werte verarbeiten
    if request.method == 'POST':
        packed_materials = request.POST.getlist('packed_materials')

        # Vorhandene Einträge löschen, um nur die aktuellen zu speichern
        PackedMaterial.objects.filter(trip=trip).delete()

        # Neue Daten speichern
        for material_name in packed_materials:
            PackedMaterial.objects.create(trip=trip, material_name=material_name, packed=True)
        messages.success(request, f"Die eingepackten Materialien wurden gespeichert!")
        print(request.POST.getlist('packed_materials'))
        return redirect('check_trip_material', pk=pk)

    # Wenn Materialien fehlen, zeige eine Warnung und die Liste der fehlenden Materialien an
    if missing:
        messages.warning(request,
                         'Einige Materialien sind nicht ausreichend vorhanden.')
    else:
        # Alle Materialien sind verfügbar, also keine Fehlermeldung anzeigen
        messages.success(request, 'Alle Materialien sind ausreichend vorhanden.')
    total_weigth_av_m = 0
    for material in materials:
        # Angenommen, jedes Material hat ein Attribut `weight`, das das Gewicht pro Einheit beschreibt.
        if material.material.weight:
            total_weigth_av_m += material.count * material.material.weight
    # Weiterleitung zum Verfügbarkeitsfenster (immer, auch wenn keine Materialien fehlen)
    return render(request, 'events/check_trip_material.html', {
        'title': 'Materialübersicht',
        'trip': trip,
        'available_materials': available_materials,
        'missing_materials': missing_materials,
        'is_event_manager': m.event_manager,
        'total_weigth_av_m': total_weigth_av_m,
    })


@login_required
@event_manager_required
def edit_trip(request, pk=None):
    request.session['previous_url'] = request.build_absolute_uri()
    if pk:
        trip_d = get_object_or_404(Trip, pk=pk, owner=request.org)
    else:
        trip_d = None
    if request.method == 'POST':
        trip_form = TripForm(request.POST, request.FILES, instance=trip_d, organization=request.org)
        tripconstruction_formset = TripConstructionFormSet(request.POST, instance=trip_d,
                                                           form_kwargs={'organization': request.org})
        tripgroup_formset = TripGroupFormSet(request.POST, instance=trip_d, form_kwargs={'organization': request.org})
        if trip_form.is_valid() & tripconstruction_formset.is_valid() & tripgroup_formset.is_valid():
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
            total_tn_count = 0
            groups = tripgroup_formset.save(commit=False)
            for obj in tripgroup_formset.deleted_objects:  # Gelöschte Objekte entfernen
                obj.delete()
            for gr in groups:
                gr.trip = trip_d
                gr.save()
                total_tn_count += gr.count
            tripgroup_formset.save_m2m()

            # Unterscheidung der Weiterleitungen basierend auf dem Button
            if 'save' in request.POST:
                # Wenn der Speichern-Button gedrückt wurde, weiter zu Trips
                messages.success(request, f'Veranstaltung {trip_d.name} gespeichert.')
                return redirect('trip')  # Hier 'trip' zu deiner Trip-Liste oder Detail-Seite weiterleiten
            elif 'check_material' in request.POST:
                # Wenn der Materialverfügbarkeits-Button gedrückt wurde, weiter zu Materialverfügbarkeit prüfen
                return redirect('check_trip_material', trip_d.pk)  # Weiterleitung zur Materialverfügbarkeitsprüfung
            elif 'construction_summary' in request.POST:
                return redirect('construction_summary', trip_d.pk)
            elif 'find_construction_combination' in request.POST:
                min_sleeping_places = request.POST.get("min_sleeping_places")
                if min_sleeping_places:
                    request.session["min_sleeping_places"] = min_sleeping_places
                return redirect('find_construction_combination', trip_d.pk)
    else:
        trip_form = TripForm(instance=trip_d, organization=request.org)
        tripconstruction_formset = TripConstructionFormSet(instance=trip_d, form_kwargs={'organization': request.org})
        tripgroup_formset = TripGroupFormSet(instance=trip_d, form_kwargs={'organization': request.org})
        total_tn_count = sum(group.count for group in TripGroup.objects.filter(trip=trip_d))
    org_constructions = Construction.objects.filter(owner=request.org).order_by('name')
    # Externe Konstruktionen, entweder öffentlich oder ohne zugewiesenen Eigentümer
    external_constructions = Construction.objects.filter(
        Q(public=True) & ~Q(owner=request.org) & Q(owner__isnull=False)).order_by('name')
    public_constructions = Construction.objects.filter(Q(owner__isnull=True)).order_by('name')
    constructions = {
        "organization": org_constructions,
        "public": public_constructions,
        "external": external_constructions,
    }
    return render(request, 'events/edit_trip.html', {
        'title': 'Veranstaltung bearbeiten',
        'trip_form': trip_form,
        'trip': trip_d,
        'construction_formset': tripconstruction_formset,
        'group_formset': tripgroup_formset,
        'constructions': constructions,
        'total_tn_count': total_tn_count,
    })


@login_required
def location(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    # Suchlogik
    search_query = request.GET.get('search', '')
    selected_location_type = request.GET.get('location_type', '')  # Materialtyp
    # 2. Wenn keine GET-Filter vorhanden sind, die Filter aus der Session holen
    if request.session.get('previous_url'):
        previous_url = request.session.get('previous_url')
        if 'location/edit/' in previous_url:
            if not search_query:
                search_query = request.session.get('search', '')
            if 'search' in request.session:
                del request.session['search']

            if not selected_location_type:
                selected_location_type = request.session.get('location_type', '')
            if 'location_type' in request.session:
                del request.session['location_type']

    request.session['search'] = search_query
    request.session['location_type'] = selected_location_type
    request.session['previous_url'] = request.build_absolute_uri()
    locations_query = Location.objects.filter(owner=request.org)
    if search_query:
        locations_query = locations_query.filter(
            Q(name__icontains=search_query) | Q(owner__name__icontains=search_query)
        ).order_by('name')
    if selected_location_type:
        locations_query = locations_query.filter(type=selected_location_type).order_by('name')
    if m.event_manager:
        form = ImportLocationForm(organization=request.org)
        if request.method == 'POST':
            form = ImportLocationForm(request.POST, organization=request.org)
            if form.is_valid():
                original_location = form.cleaned_data['location']
                existing_location = Location.objects.filter(owner=request.org, name=original_location.name).first()
                if not existing_location:
                    # Neuen Ort erstellen, indem das Original kopiert wird
                    cloned_location = Location.objects.create(
                        name=original_location.name,
                        description=original_location.description,
                        type=original_location.type,
                        owner=request.org,
                        public=False,
                        latitude=original_location.latitude,
                        longitude=original_location.longitude,
                    )

                    messages.success(request, f'Ort "{original_location.name}" wurde hinzugefügt.')
                else:
                    # Existierendes Material verwenden
                    cloned_location = existing_location
                    messages.info(request,
                                  f'Ort "{original_location.name}" existiert bereits und wurde nicht erneut hinzugefügt.')
                return HttpResponseRedirect(reverse_lazy('location'))
    else:
        form = None
    TYPES = (
        (0, "Haus"),
        (1, "Pfadfinderzeltplatz"),
        (2, "Campingplatz"),
        (3, "Freier Platz"),
        (4, "Privater Platz"),
    )
    return render(request, 'events/locations.html', {
        'title': 'Orte',
        'locations': locations_query,
        'is_event_manager': m.event_manager,
        'search_query': search_query,
        'selected_location_type': selected_location_type,
        'location_types': TYPES,
        'form': form,
    })


@login_required
@event_manager_required
def delete_location(request, pk=None):
    location_d = get_object_or_404(Location, pk=pk, owner=request.org)
    if request.method == 'POST':
        location_d.delete()
        messages.success(request, f'Ort {location_d.name} erfolgreich gelöscht.')
        return HttpResponseRedirect(reverse_lazy('location'))
    return render(request, 'events/delete_location.html', {'title': 'Ort löschen', 'location': location_d})


@login_required
def show_location(request, pk=None):
    location = get_object_or_404(Location, pk=pk, owner=request.org)
    location.type = location.get_type_display()
    google_maps_api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    return render(request, 'events/show_location.html', {
        'title': 'Ort anzeigen',
        'location': location,
        'GOOGLE_MAPS_API_KEY': google_maps_api_key,
    })


@login_required
@event_manager_required
def edit_location(request, pk=None):
    request.session['previous_url'] = request.build_absolute_uri()
    if pk:
        location_d = get_object_or_404(Location, pk=pk, owner=request.org)
        print(location_d)
    else:
        location_d = None
    if request.method == 'POST':

        print(location_d)
        location_form = LocationForm(request.POST, request.FILES, instance=location_d)
        if location_form.is_valid():
            location_d = location_form.save(commit=False)
            location_d.owner = request.org
            location_d.save()
            messages.success(request, f'Ort {location_d.name} gespeichert.')
            return redirect('location')
    else:
        location_form = LocationForm(instance=location_d)
    google_maps_api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    return render(request, 'events/edit_location.html', {
        'title': 'Ort bearbeiten',
        'location_form': location_form,
        'location': location_d,
        'GOOGLE_MAPS_API_KEY': google_maps_api_key,
    })


@login_required
def construction_summary(request, pk=None):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)
    constructions = TripConstruction.objects.filter(trip=trip)
    # Initialisiere Variablen für Gesamtgewicht und Gesamtschlafplätze
    total_weight = 0
    total_sleep_place_count = 0
    total_covered_area = 0
    total_required_space = 0
    # Erstelle eine Liste aller Materialien und summiere die benötigten Mengen
    for tc in constructions:
        # Berechne Gesamtschlafplatzanzahl der Konstruktionen
        if tc.construction.sleep_place_count:
            total_sleep_place_count += tc.construction.sleep_place_count * tc.count
        if tc.construction.covered_area:
            total_covered_area += tc.construction.covered_area * tc.count
        if tc.construction.required_space:
            total_required_space += tc.construction.required_space * tc.count
        # Materialien der Konstruktionen holen
        construction_materials = ConstructionMaterial.objects.filter(construction=tc.construction)
        for cm in construction_materials:
            required_quantity = cm.count * tc.count  # Gesamtmenge = Anzahl der Konstruktionen * benötigte Menge pro Konstruktion
            # Gewicht berechnen
            if cm.material.weight:  # Falls ein Gewicht angegeben ist
                total_weight += cm.material.weight * required_quantity
    return render(request, 'events/construction_summary.html', {
        'title': 'Konstruktions-Zusammenfassung',
        'trip': trip,
        'total_weight': total_weight,
        'total_sleep_place_count': total_sleep_place_count,
        'total_covered_area': total_covered_area,
        'total_required_space': total_required_space,
        'is_event_manager': m.event_manager,
    })


def calculate_construction_weight(materials):
    total_weight = Decimal(0)
    for material in materials:
        if material.material.weight:
            total_weight += material.material.weight * material.count
    return total_weight


def calculate_total_weight_for_group(group_combination):
    total_weight = Decimal(0)
    for konstruktion in group_combination:
        materials = ConstructionMaterial.objects.filter(construction=konstruktion)
        konstruktion_weight = calculate_construction_weight(materials)
        total_weight += konstruktion_weight
    return total_weight


def find_optimal_construction_combination(teilnehmergruppen, konstruktionen, request,
                                          min_sleep_place_count_construction):
    # Maximal mögliche Schlafplätze (Summe aller Gruppengrößen)
    max_sleep_places = max(teilnehmergruppen)
    max_sleep_place_count = max(c.sleep_place_count for c in konstruktionen)

    # DP-Array initialisieren: dp[x] speichert das minimale Gewicht für genau x Schlafplätze (oder mehr)
    dp = [Decimal('Infinity')] * (max_sleep_places + max_sleep_place_count + 1)  # Ein hoher Wert für "Unendlich"
    dp[0] = Decimal(0)  # 0 Schlafplätze brauchen 0 Gewicht

    # Rückverfolgung für die Kombinationen der Konstruktionen
    backtrace = defaultdict(list)

    # Iteration durch alle Konstruktionen und alle möglichen Schlafplatzzahlen
    for konstruktion in konstruktionen:
        if konstruktion.sleep_place_count < min_sleep_place_count_construction:
            continue

        materials = ConstructionMaterial.objects.filter(construction=konstruktion)
        konstruktion_weight = calculate_construction_weight(materials)

        # Iteration durch alle möglichen Schlafplätze und auch die mit mehr Schlafplätzen
        for sleep_places in range(konstruktion.sleep_place_count, max_sleep_places + max_sleep_place_count):
            # Berechnung des neuen Gewichts, wenn wir diese Konstruktion zu einer bestehenden Gruppe hinzufügen
            new_weight = dp[sleep_places - konstruktion.sleep_place_count] + konstruktion_weight
            # Wenn das neue Gewicht besser (geringer) ist als das aktuelle Gewicht für diese Anzahl Schlafplätze
            if new_weight < dp[sleep_places]:
                dp[sleep_places] = new_weight
                backtrace[sleep_places] = backtrace[sleep_places - konstruktion.sleep_place_count] + [konstruktion]
    # Ergebnis für jede Gruppe berechnen
    result = []
    for group_size in teilnehmergruppen:
        best_combination = None
        min_weight = Decimal('Infinity')  # Setze das Anfangsgewicht auf "Unendlich"

        # Iteriere durch alle möglichen Schlafplätze für diese Gruppe
        for sleep_places in range(group_size, max_sleep_places + max_sleep_place_count):
            if dp[sleep_places] != Decimal('Infinity'):
                current_combination = backtrace[sleep_places]
                current_weight = calculate_total_weight_for_group(current_combination)

                # Wenn das aktuelle Gewicht geringer ist, als das bisher beste Gewicht
                if current_weight < min_weight:
                    best_combination = current_combination
                    min_weight = current_weight

        # Falls keine Kombination gefunden wird, warnen wir den Benutzer
        if best_combination is None:
            messages.warning(request,
                             f"Größe {group_size} kann mit den verfügbaren Konstruktionen nicht abgedeckt werden!")
            result.append([])  # Keine gültige Kombination für diese Gruppe
        else:
            result.append(best_combination)

    # Berechne das Gesamtgewicht für jede Gruppe
    group_weights = []
    for group_combination in result:
        group_weight = calculate_total_weight_for_group(group_combination)
        group_weights.append(group_weight)

    # Berechne das minimale Gesamtgewicht
    if group_weights:
        min_total_weight = sum(group_weights)
    else:
        min_total_weight = 0

    return result, min_total_weight


def find_construction_combination(request, pk=None):
    # Hole die Reise-Daten basierend auf der ID
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)
    # Teilnehmergruppen dynamisch aus TripGroups berechnen
    trip_groups = TripGroup.objects.filter(trip=trip)
    if not trip_groups.exists():
        messages.warning(request, "Es sind keine Teilnehmergruppen vorhanden.")
        return redirect('edit_trip', pk=pk)

    teilnehmergruppen = [group.count for group in trip_groups]

    konstruktionen = Construction.objects.filter(owner=request.org)
    if not konstruktionen.exists():
        messages.warning(request, "Du hast keine Konstruktionen.")
        return redirect('edit_trip', pk=pk)

    min_sleeping_places_c = request.session.get("min_sleeping_places")  # Wert aus Session holen
    if min_sleeping_places_c:
        min_sleeping_places_c = int(min_sleeping_places_c)
    else:
        min_sleeping_places_c = 1
    optimal_combination, min_total_weight = find_optimal_construction_combination(teilnehmergruppen, konstruktionen,
                                                                                  request, min_sleeping_places_c)

    group_construction_data = []
    for group, group_combination in zip(trip_groups, optimal_combination):
        group_data = {
            'group_name': group.name,  # Falls Gruppen Namen haben
            'constructs': [],
            'total_weight': calculate_total_weight_for_group(group_combination),
            'required_sleep_place_count': group.count
        }

        for konstruktion in group_combination:
            group_data['constructs'].append({
                'name': konstruktion.name,
                'sleep_places': konstruktion.sleep_place_count
            })

        group_construction_data.append(group_data)
    return render(request, 'events/find_construction_combination.html', {
        'title': 'Optimale Konstruktions-Kombination finden',
        'trip': trip,
        'group_construction_data': group_construction_data,
        'min_total_weight': min_total_weight,
    })


def save_constructions_for_trip(request, pk=None):
    # Hole die Reise-Daten basierend auf der ID
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)

    # Teilnehmergruppen dynamisch aus TripGroups berechnen
    trip_groups = TripGroup.objects.filter(trip=trip)
    if not trip_groups.exists():
        messages.warning(request, "Es sind keine Teilnehmergruppen vorhanden.")
        return redirect('edit_trip', pk=pk)

    teilnehmergruppen = [group.count for group in trip_groups]

    # Konstruktionen abrufen
    konstruktionen = Construction.objects.filter(owner=request.org)
    if not konstruktionen.exists():
        messages.warning(request, "Es sind keine Konstruktionen vorhanden.")
        return redirect('edit_trip', pk=pk)

    min_sleeping_places_c = request.session.get("min_sleeping_places")  # Wert aus Session holen
    if min_sleeping_places_c:
        min_sleeping_places_c = int(min_sleeping_places_c)

    # Finde die optimale Kombination der Konstruktionen und das minimalste Gesamtgewicht
    optimal_combination, min_total_weight = find_optimal_construction_combination(
        teilnehmergruppen, konstruktionen, request, min_sleeping_places_c
    )
    # Alte TripConstruction-Einträge für diesen Trip löschen
    TripConstruction.objects.filter(trip=trip).delete()

    # Speichere die Konstruktionen für jede Gruppe
    for group_index, group_combination in enumerate(optimal_combination):
        trip_group = trip_groups[group_index]  # Gruppe direkt aus TripGroup holen
        for konstruktion in group_combination:
            trip_construction = TripConstruction(
                trip=trip,
                construction=konstruktion,
                count=1,  # Kann angepasst werden, falls Konstruktionen mehrfach verwendet werden
                description=trip_group.name  # Dynamische Beschreibung
            )
            trip_construction.save()

    # Erfolgreiches Speichern
    messages.success(request, "Konstruktionen erfolgreich gespeichert!")
    return redirect('edit_trip', pk=pk)
