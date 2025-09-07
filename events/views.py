import csv
import datetime
import json
import os
from audioop import reverse
from collections import defaultdict
from copy import deepcopy
from itertools import combinations
from urllib.parse import unquote

from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from django.utils.timezone import now
from _decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, Sum
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from icalendar import Calendar, Event
from unicodedata import decimal
from django.urls import reverse
from datetime import datetime
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from .models import Trip, TripVacancy, EventPlanningChecklistItem

from decimal import Decimal, InvalidOperation

from buildings.models import Construction, StockMaterial, ConstructionMaterial, Material
from events.forms import TripForm, TripConstructionFormSet, LocationForm, ImportLocationForm, TripGroupFormSet, \
    TripMaterialFormSet, ShoppingListItemForm, TripVacancyForm, EventPlanningChecklistItemForm
from events.models import Trip, TripConstruction, Location, PackedMaterial, TripGroup, TripMaterial, ShoppingListItem, \
    TripVacancy
from main.decorators import organization_admin_required, event_manager_required, pro1_required
from main.models import Membership, Organization


@login_required
def trip(request):
    temp_stock = StockMaterial.objects.filter(temporary=True,
                                              valid_until__lt=now().date())  # ausgeliehens material löschen, wenn es abgelaufen ist
    for tm in temp_stock:
        tm.material.delete()
        tm.delete()
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    # Suchlogik
    search_query = request.GET.get('search', '')
    selected_trip_type = request.GET.get('trip_type', '')  # Materialtyp
    # 2. Wenn keine GET-Filter vorhanden sind, die Filter aus der Session holen
    if request.session.get('previous_url'):
        previous_url = request.session.get('previous_url')
        if 'trip/edit/' in previous_url or 'trip/show/' in previous_url or 'trip/delete/' in previous_url:
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
        (4, "Material-Verleih"),
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
    request.session['previous_url'] = request.build_absolute_uri()
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)
    tripconstruction = TripConstruction.objects.filter(trip=trip)
    tripgroups = TripGroup.objects.filter(trip=trip)
    tripmaterials = TripMaterial.objects.filter(trip=trip)
    trip.type = trip.get_type_display()
    total_tn_count = sum(group.count for group in TripGroup.objects.filter(trip=trip))
    return render(request, 'events/show_trip.html', {
        'title': 'Veranstaltung anzeigen',
        'trip': trip,
        'tripconstructions': tripconstruction,
        'tripmaterials': tripmaterials,
        'tripgroups': tripgroups,
        'total_tn_count': total_tn_count,
    })


@login_required
@event_manager_required
def delete_trip(request, pk=None):
    request.session['previous_url'] = request.build_absolute_uri()
    trip_d = get_object_or_404(Trip, pk=pk, owner=request.org)
    if request.method == 'POST':
        trip_d.delete()
        messages.success(request, f'Veranstaltung {trip_d.name} erfolgreich gelöscht.')
        return HttpResponseRedirect(reverse_lazy('trip'))
    return render(request, 'events/delete_trip.html', {'title': 'Veranstaltung löschen', 'trip': trip_d})


@login_required
def check_trip_material(request, pk=None):
    """ Prüft, ob Materialien für einen Trip verfügbar sind, unter Berücksichtigung paralleler Nutzung durch andere Trips. """

    # Mitgliedschaft abrufen
    m = request.user.membership_set.filter(organization=request.org).first()

    # Trip abrufen
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)

    # Alle Konstruktionen des Trips abrufen
    constructions = TripConstruction.objects.filter(trip=trip)

    # Material-Berechnung initialisieren
    material_summary = defaultdict(int)

    # Materialien aus Konstruktionen sammeln und summieren
    for tc in constructions:
        construction_materials = ConstructionMaterial.objects.filter(construction=tc.construction)
        for cm in construction_materials:
            material_summary[cm.material.name] += cm.count * tc.count

    # Manuell hinzugefügtes Material sammeln
    trip_materials = TripMaterial.objects.filter(trip=trip)
    for tm in trip_materials:
        material_summary[tm.material.name] += tm.count

    # Liste für verfügbare & fehlende Materialien
    available_materials = []
    missing_materials = []
    missing = False

    # Prüfung der Materialverfügbarkeit unter Berücksichtigung paralleler Nutzung
    for material_name, total_required_quantity in material_summary.items():
        # Gesamtbestand des Materials abrufen
        stock_materials = StockMaterial.objects.filter(
            material__name=material_name, organization=request.org
        )
        # Berechne die Gesamtmenge der verfügbaren Materialien
        available_quantity = sum(m.count for m in stock_materials) - sum(m.condition_broke for m in stock_materials)
        trip_materials_type_6 = trip_materials.filter(material__type=6, material__name=material_name)
        for tm in trip_materials_type_6:
            available_quantity += tm.reduced_from_stock  # Nur zur Berechnung der verfügbaren Menge hinzufügen

        # Trips abrufen, die das gleiche Material nutzen und **vor oder parallel** zum aktuellen Trip liegen
        conflicting_trips = Trip.objects.filter(
            start_date__lt=trip.end_date,  # Startet vor dem Ende des aktuellen Trips
            end_date__gt=trip.start_date, owner=request.org  # Endet nach dem Start des aktuellen Trips (also überlappt)
        ).exclude(pk=trip.pk)

        # Material aus `TripMaterial` dieser Trips summieren
        used_materials_trip = conflicting_trips.filter(
            tripmaterial__material__name=material_name
        ).annotate(
            total_used=Sum('tripmaterial__count')
        )

        used_in_trip_materials = sum(t.total_used or 0 for t in used_materials_trip)

        # Material aus `TripConstruction` dieser Trips summieren
        used_materials_construction = conflicting_trips.filter(
            tripconstruction__construction__constructionmaterial__material__name=material_name
        ).annotate(
            total_used=Sum('tripconstruction__construction__constructionmaterial__count')
        )

        used_in_construction_materials = sum(t.total_used or 0 for t in used_materials_construction)

        # Gesamtverbrauch aus beiden Quellen berechnen
        used_in_other_trips = used_in_trip_materials + used_in_construction_materials
        # Effektiv verfügbare Menge berechnen
        effective_available_quantity = max(available_quantity - used_in_other_trips, 0)

        # Lagerinfo abrufen
        storage_info = [
            {'storage_place': m.storage_place, 'available_quantity': m.count}
            for m in stock_materials
        ]

        # Verfügbarkeit prüfen
        if effective_available_quantity >= total_required_quantity:
            available_materials.append({
                'material': material_name,
                'required_quantity': total_required_quantity,
                'available_quantity': effective_available_quantity,
                'storage_info': storage_info
            })
        else:
            missing_materials.append({
                'material': material_name,
                'required_quantity': total_required_quantity,
                'available_quantity': effective_available_quantity,
                'missing_quantity': total_required_quantity - effective_available_quantity,
                'storage_info': storage_info
            })
            missing = True

    # ✅ Fix: Alle "PackedMaterial"-Einträge mit "packed"-Status abrufen
    packed_materials = {
        entry["material_name"]: entry["packed"]
        for entry in PackedMaterial.objects.filter(trip=trip).values("material_name", "packed")
    }

    # ✅ Fix: Setze den `packed`-Status basierend auf der Datenbank
    for material in available_materials + missing_materials:
        material['packed'] = packed_materials.get(material['material'], False)

    # Falls Materialien fehlen, zeige eine Warnung
    if missing:
        messages.warning(request, "Einige Materialien sind nicht ausreichend vorhanden.")
    else:
        messages.success(request, "Alle Materialien sind ausreichend vorhanden.")

    # Gesamtgewicht berechnen (falls Materialien eine Gewichtseigenschaft haben)
    total_weight_available = 0
    for mate in available_materials:
        try:
            material_obj = Material.objects.filter(name=mate['material'],
                                                   owner=request.org).first()  # Material-Objekt abrufen
            weight_per_unit = material_obj.weight if material_obj.weight else 0  # Gewicht pro Einheit
            total_weight_available += mate['required_quantity'] * weight_per_unit
        except ObjectDoesNotExist:
            pass  # Falls Material nicht gefunden wird, ignorieren

    # Seite rendern
    return render(request, 'events/check_trip_material.html', {
        'title': 'Materialübersicht',
        'trip': trip,
        'available_materials': available_materials,
        'missing_materials': missing_materials,
        'is_event_manager': m.event_manager,
        'total_weight_available': total_weight_available,
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
        tripmaterial_formset = TripMaterialFormSet(request.POST, instance=trip_d,
                                                   form_kwargs={'organization': request.org})

        if trip_form.is_valid() & tripconstruction_formset.is_valid() & tripgroup_formset.is_valid() & tripmaterial_formset.is_valid():

            trip_d = trip_form.save(commit=False)
            save_a_n = False
            if 'save_as_new' in request.POST:
                save_a_n = True
                og_trip = deepcopy(trip_d)
                trip_d.pk = None
            trip_d.owner = request.org
            trip_d.save()
            #  Wenn "Speichern als neu" => Alle Formset-Objekte kopieren
            if save_a_n:
                # 1. Konstruktionen duplizieren
                original_constructions = og_trip.tripconstruction_set.all()
                for con in original_constructions:
                    con.pk = None  # Neue Instanz erzwingen
                    con.trip = trip_d
                    con.save()

                # 2. Gruppen duplizieren
                original_groups = og_trip.tripgroup_set.all()
                for gr in original_groups:
                    gr.pk = None
                    gr.trip = trip_d
                    gr.save()

                # 3. Materialien duplizieren
                original_materials = og_trip.tripmaterial_set.all()
                for mat in original_materials:
                    mat.pk = None
                    mat.trip = trip_d
                    mat.previous_count = 0
                    mat.reduced_from_stock = 0
                    if mat.material.type == 6:
                        mat_stock = StockMaterial.objects.filter(material__name=mat.material.name)
                        av_stock = sum(stock.count for stock in mat_stock)
                        remaining = 0
                        if av_stock >= mat.count - mat.previous_count:
                            remaining = mat.count - mat.reduced_from_stock
                            mat.reduced_from_stock = mat.count
                            mat.previous_count = mat.count
                        else:
                            remaining = av_stock
                            mat.reduced_from_stock += av_stock
                            mat.previous_count = mat.count

                            if request.org.pro1:
                                missing_amount = mat.count - mat.reduced_from_stock
                                si,c = ShoppingListItem.objects.get_or_create(trip=trip_d, name=mat.material.name, unit="Stück")
                                si.amount=missing_amount
                                si.save()
                                messages.warning(request,
                                                 f"Das Verbaruchsmaterial '{mat.material.name}' ist nicht ausreichend im Lager vorhanden. Es wurde nur die verfügbare Menge abgezogen und die fehlende Menge auf die Einkaufsliste gesetzt.")
                            else:
                                messages.warning(request,
                                             f"Das Verbaruchsmaterial '{mat.material.name}' ist nicht ausreichend im Lager vorhanden. Es wurde nur die verfügbare Menge abgezogen.")
                        # Abzug durchführen

                        for stock in mat_stock:
                            if stock.count >= remaining:
                                stock.count -= remaining
                                stock.save()

                    mat.save()
                org = trip_d.recipient_org
                if trip_d.type == 4 and org and org.recipientcode == trip_d.recipientcode:
                    """ Prüft, ob Materialien für einen Trip verfügbar sind, unter Berücksichtigung paralleler Nutzung durch andere Trips. """

                    # Mitgliedschaft abrufen
                    m = request.user.membership_set.filter(organization=request.org).first()

                    # Trip abrufen
                    trip = trip_d

                    # Alle Konstruktionen des Trips abrufen
                    constructions = TripConstruction.objects.filter(trip=trip)

                    # Material-Berechnung initialisieren
                    material_summary = defaultdict(int)

                    # Materialien aus Konstruktionen sammeln und summieren
                    for tc in constructions:
                        construction_materials = ConstructionMaterial.objects.filter(construction=tc.construction)
                        for cm in construction_materials:
                            material_summary[cm.material.name] += cm.count * tc.count

                    # Manuell hinzugefügtes Material sammeln
                    trip_materials = TripMaterial.objects.filter(trip=trip)
                    for tm in trip_materials:
                        material_summary[tm.material.name] += tm.count

                    # Liste für verfügbare & fehlende Materialien
                    available_materials = []
                    missing_materials = []
                    missing = False

                    # Prüfung der Materialverfügbarkeit unter Berücksichtigung paralleler Nutzung
                    for material_name, total_required_quantity in material_summary.items():
                        # Gesamtbestand des Materials abrufen
                        stock_materials = StockMaterial.objects.filter(
                            material__name=material_name, organization=request.org
                        )
                        # Berechne die Gesamtmenge der verfügbaren Materialien
                        available_quantity = sum(m.count for m in stock_materials) - sum(
                            m.condition_broke for m in stock_materials)

                        trip_materials_type_6 = trip_materials.filter(material__type=6, material__name=material_name)
                        for tm in trip_materials_type_6:
                            available_quantity += tm.reduced_from_stock  # Nur zur Berechnung der verfügbaren Menge hinzufügen

                        # Trips abrufen, die das gleiche Material nutzen und **vor oder parallel** zum aktuellen Trip liegen
                        conflicting_trips = Trip.objects.filter(
                            start_date__lt=trip.end_date,  # Startet vor dem Ende des aktuellen Trips
                            end_date__gt=trip.start_date, owner=request.org
                            # Endet nach dem Start des aktuellen Trips (also überlappt)
                        ).exclude(pk=trip.pk)

                        # Material aus `TripMaterial` dieser Trips summieren
                        used_materials_trip = conflicting_trips.filter(
                            tripmaterial__material__name=material_name
                        ).annotate(
                            total_used=Sum('tripmaterial__count')
                        )

                        used_in_trip_materials = sum(t.total_used or 0 for t in used_materials_trip)

                        # Material aus `TripConstruction` dieser Trips summieren
                        used_materials_construction = conflicting_trips.filter(
                            tripconstruction__construction__constructionmaterial__material__name=material_name
                        ).annotate(
                            total_used=Sum('tripconstruction__construction__constructionmaterial__count')
                        )

                        used_in_construction_materials = sum(t.total_used or 0 for t in used_materials_construction)

                        # Gesamtverbrauch aus beiden Quellen berechnen
                        used_in_other_trips = used_in_trip_materials + used_in_construction_materials

                        # Effektiv verfügbare Menge berechnen
                        effective_available_quantity = max(available_quantity - used_in_other_trips, 0)

                        # Lagerinfo abrufen
                        storage_info = [
                            {'storage_place': m.storage_place, 'available_quantity': m.count}
                            for m in stock_materials
                        ]

                        # Verfügbarkeit prüfen
                        if effective_available_quantity >= total_required_quantity:
                            available_materials.append({
                                'material': material_name,
                                'required_quantity': total_required_quantity,
                                'available_quantity': effective_available_quantity,
                                'storage_info': storage_info
                            })
                        else:
                            missing_materials.append({
                                'material': material_name,
                                'required_quantity': total_required_quantity,
                                'available_quantity': effective_available_quantity,
                                'missing_quantity': total_required_quantity - effective_available_quantity,
                                'storage_info': storage_info
                            })
                            missing = True
                    if missing:
                        messages.warning(request,
                                         f"Es ist nicht genug Material zum Verleihen im Lager vorhanden.")
                        return redirect('edit_trip', trip_d.pk)
                    else:
                        for mat in TripMaterial.objects.filter(trip=trip_d):
                            new_mat = Material.objects.create(
                                name=f"{mat.material.name}#Geliehen von {request.org.name} von {trip_d.start_date.date()} bis {trip_d.end_date.date()}#",
                                description=mat.material.description,
                                owner=org,
                                public=False,
                                image=mat.material.image,
                                weight=mat.material.weight,
                                type=mat.material.type,
                                length_min=mat.material.length_min,
                                length_max=mat.material.length_max,
                                width=mat.material.width
                            )
                            StockMaterial.objects.create(
                                material=new_mat,
                                organization=org,
                                storage_place='Geliehen',
                                temporary=True,
                                valid_until=trip_d.end_date,
                                count=mat.count,
                                condition_healthy=mat.count,
                            )
            else:
                # 🚀 Normales Speichern wenn NICHT "Speichern als neu"
                constructions = tripconstruction_formset.save(commit=False)
                for obj in tripconstruction_formset.deleted_objects:
                    obj.delete()
                for con in constructions:
                    con.trip = trip_d
                    con.save()
                tripconstruction_formset.save_m2m()

                groups = tripgroup_formset.save(commit=False)
                for obj in tripgroup_formset.deleted_objects:
                    obj.delete()
                for gr in groups:
                    gr.trip = trip_d
                    gr.save()
                tripgroup_formset.save_m2m()

                other_materials = tripmaterial_formset.save(commit=False)
                for obj in tripmaterial_formset.deleted_objects:
                    mat_stock = StockMaterial.objects.filter(material__name=obj.material.name).first()
                    mat_stock.count += obj.reduced_from_stock
                    mat_stock.save()
                    org = trip_d.recipient_org
                    if trip_d.type == 4 and org and org.recipientcode == trip_d.recipientcode:
                        mat_rent = Material.objects.filter(
                            name=obj.material.name,
                            description=f"{obj.material.description} #Geliehen von {request.org.name} von {trip_d.start_date.date()} bis {trip_d.end_date.date()}#",
                            owner=org,
                            public=False,
                            image=obj.material.image,
                            weight=obj.material.weight,
                            type=obj.material.type,
                            length_min=obj.material.length_min,
                            length_max=obj.material.length_max,
                            width=obj.material.width
                        ).first()
                        stock_mat = StockMaterial.objects.filter(
                            material=mat_rent,
                            organization=org,
                            storage_place='Geliehen',
                            temporary=True,
                            valid_until=trip_d.end_date,
                        ).first()
                        stock_mat.delete()
                        mat_rent.delete()
                    obj.delete()
                for mat in other_materials:
                    mat.trip = trip_d
                    if mat.material.type == 6:
                        mat_stock = StockMaterial.objects.filter(material__name=mat.material.name)
                        av_stock = sum(stock.count for stock in mat_stock)
                        remaining = 0
                        if av_stock >= mat.count - mat.previous_count:
                            remaining = mat.count - mat.reduced_from_stock
                            mat.reduced_from_stock = mat.count
                            mat.previous_count = mat.count
                        else:
                            remaining = av_stock
                            mat.reduced_from_stock += av_stock
                            mat.previous_count = mat.count
                            if request.org.pro1:
                                missing_amount = mat.count - mat.reduced_from_stock
                                si,c = ShoppingListItem.objects.get_or_create(trip=trip_d, name=mat.material.name, unit="Stück")
                                si.amount=missing_amount
                                si.save()
                                messages.warning(request,
                                                 f"Das Verbaruchsmaterial '{mat.material.name}' ist nicht ausreichend im Lager vorhanden. Es wurde nur die verfügbare Menge abgezogen und die fehlende Menge auf die Einkaufsliste gesetzt.")
                            else:
                                messages.warning(request,
                                                 f"Das Verbaruchsmaterial '{mat.material.name}' ist nicht ausreichend im Lager vorhanden. Es wurde nur die verfügbare Menge abgezogen.")
                                # Abzug durchführen

                        for stock in mat_stock:
                            if stock.count >= remaining:
                                stock.count -= remaining
                                stock.save()
                    mat.save()
                tripmaterial_formset.save_m2m()
                org = trip_d.recipient_org
                if trip_d.type == 4 and org and org.recipientcode == trip_d.recipientcode:
                    """ Prüft, ob Materialien für einen Trip verfügbar sind, unter Berücksichtigung paralleler Nutzung durch andere Trips. """

                    # Mitgliedschaft abrufen
                    m = request.user.membership_set.filter(organization=request.org).first()

                    # Trip abrufen
                    trip = trip_d

                    # Alle Konstruktionen des Trips abrufen
                    constructions = TripConstruction.objects.filter(trip=trip)

                    # Material-Berechnung initialisieren
                    material_summary = defaultdict(int)

                    # Materialien aus Konstruktionen sammeln und summieren
                    for tc in constructions:
                        construction_materials = ConstructionMaterial.objects.filter(construction=tc.construction)
                        for cm in construction_materials:
                            material_summary[cm.material.name] += cm.count * tc.count

                    # Manuell hinzugefügtes Material sammeln
                    trip_materials = TripMaterial.objects.filter(trip=trip)
                    for tm in trip_materials:
                        material_summary[tm.material.name] += tm.count

                    # Liste für verfügbare & fehlende Materialien
                    available_materials = []
                    missing_materials = []
                    missing = False

                    # Prüfung der Materialverfügbarkeit unter Berücksichtigung paralleler Nutzung
                    for material_name, total_required_quantity in material_summary.items():
                        # Gesamtbestand des Materials abrufen
                        stock_materials = StockMaterial.objects.filter(
                            material__name=material_name, organization=request.org
                        )
                        # Berechne die Gesamtmenge der verfügbaren Materialien
                        available_quantity = sum(m.count for m in stock_materials) - sum(
                            m.condition_broke for m in stock_materials)

                        trip_materials_type_6 = trip_materials.filter(material__type=6, material__name=material_name)
                        for tm in trip_materials_type_6:
                            available_quantity += tm.reduced_from_stock  # Nur zur Berechnung der verfügbaren Menge hinzufügen

                        # Trips abrufen, die das gleiche Material nutzen und **vor oder parallel** zum aktuellen Trip liegen
                        conflicting_trips = Trip.objects.filter(
                            start_date__lt=trip.end_date,  # Startet vor dem Ende des aktuellen Trips
                            end_date__gt=trip.start_date, owner=request.org
                            # Endet nach dem Start des aktuellen Trips (also überlappt)
                        ).exclude(pk=trip.pk)

                        # Material aus `TripMaterial` dieser Trips summieren
                        used_materials_trip = conflicting_trips.filter(
                            tripmaterial__material__name=material_name
                        ).annotate(
                            total_used=Sum('tripmaterial__count')
                        )

                        used_in_trip_materials = sum(t.total_used or 0 for t in used_materials_trip)

                        # Material aus `TripConstruction` dieser Trips summieren
                        used_materials_construction = conflicting_trips.filter(
                            tripconstruction__construction__constructionmaterial__material__name=material_name
                        ).annotate(
                            total_used=Sum('tripconstruction__construction__constructionmaterial__count')
                        )

                        used_in_construction_materials = sum(t.total_used or 0 for t in used_materials_construction)

                        # Gesamtverbrauch aus beiden Quellen berechnen
                        used_in_other_trips = used_in_trip_materials + used_in_construction_materials

                        # Effektiv verfügbare Menge berechnen
                        effective_available_quantity = max(available_quantity - used_in_other_trips, 0)

                        # Lagerinfo abrufen
                        storage_info = [
                            {'storage_place': m.storage_place, 'available_quantity': m.count}
                            for m in stock_materials
                        ]

                        # Verfügbarkeit prüfen
                        if effective_available_quantity >= total_required_quantity:
                            available_materials.append({
                                'material': material_name,
                                'required_quantity': total_required_quantity,
                                'available_quantity': effective_available_quantity,
                                'storage_info': storage_info
                            })
                        else:
                            missing_materials.append({
                                'material': material_name,
                                'required_quantity': total_required_quantity,
                                'available_quantity': effective_available_quantity,
                                'missing_quantity': total_required_quantity - effective_available_quantity,
                                'storage_info': storage_info
                            })
                            missing = True
                    if missing:
                        messages.warning(request,
                                         f"Es ist nicht genug Material zum Verleihen im Lager vorhanden.")
                        return redirect('edit_trip', trip_d.pk)
                    else:
                        for mat in TripMaterial.objects.filter(trip=trip_d):
                            new_mat, created_mat = Material.objects.get_or_create(
                                name=mat.material.name,
                                description=f"{mat.material.description} #Geliehen von {request.org.name} von {trip_d.start_date.date()} bis {trip_d.end_date.date()}#",
                                owner=org,
                                public=False,
                                image=mat.material.image,
                                weight=mat.material.weight,
                                type=mat.material.type,
                                length_min=mat.material.length_min,
                                length_max=mat.material.length_max,
                                width=mat.material.width
                            )
                            stock_mat, created = StockMaterial.objects.get_or_create(
                                material=new_mat,
                                organization=org,
                                storage_place='Geliehen',
                                temporary=True,
                                valid_until=trip_d.end_date,
                                defaults={
                                    "count": mat.count,
                                    "condition_healthy": mat.count,
                                }
                            )
                            if not created:
                                stock_mat.count = mat.count
                                stock_mat.condition_healthy = mat.count
                                stock_mat.save()
            # Unterscheidung der Weiterleitungen basierend auf dem Button
            if 'save' in request.POST or 'save_as_new' in request.POST:
                # Wenn der Speichern-Button gedrückt wurde, weiter zu Trips
                messages.success(request, f'Veranstaltung {trip_d.name} gespeichert.')
                return redirect('trip')  # Hier 'trip' zu deiner Trip-Liste oder Detail-Seite weiterleiten
            elif 'check_material' in request.POST:
                # Wenn der Materialverfügbarkeits-Button gedrückt wurde, weiter zu Materialverfügbarkeit prüfen
                return redirect('check_trip_material', trip_d.pk)  # Weiterleitung zur Materialverfügbarkeitsprüfung
            elif 'construction_summary' in request.POST:
                return redirect('construction_summary', trip_d.pk)
            elif 'find_construction_combination' in request.POST:
                min_sleeping_places = request.POST.get("min_sleeping_places_o_mp")
                if min_sleeping_places:
                    request.session["min_sleeping_places"] = min_sleeping_places
                return redirect('find_construction_combination', trip_d.pk)
            elif 'find_construction_combination_w_check_material' in request.POST:
                min_sleeping_places = request.POST.get("min_sleeping_places_m_mp")
                max_weight_increase_percent = request.POST.get("max_weight_increase_percent")
                if min_sleeping_places:
                    request.session["min_sleeping_places"] = min_sleeping_places
                if max_weight_increase_percent:
                    request.session["max_weight_increase_percent"] = max_weight_increase_percent
                return redirect('find_construction_combination_w_check_material', trip_d.pk)
    else:
        if trip_d == None:
            trip_form = TripForm(instance=trip_d, organization=request.org)
        else:
            trip_form = TripForm(instance=trip_d, organization=request.org, initial={
                'recipient_org_name': trip_d.recipient_org.name if trip_d.recipient_org else ''})
        tripconstruction_formset = TripConstructionFormSet(instance=trip_d, form_kwargs={'organization': request.org})
        tripgroup_formset = TripGroupFormSet(instance=trip_d, form_kwargs={'organization': request.org})
        tripmaterial_formset = TripMaterialFormSet(instance=trip_d, form_kwargs={'organization': request.org})
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
    org_materials = Material.objects.filter(owner=request.org).order_by('name')
    external_materials = Material.objects.filter(
        Q(public=True) & ~Q(owner=request.org) & Q(owner__isnull=False)).order_by('name')
    public_materials = Material.objects.filter(Q(owner__isnull=True)).order_by('name')
    materials = {
        "organization": org_materials,
        "public": public_materials,
        "external": external_materials,
    }
    return render(request, 'events/edit_trip.html', {
        'title': 'Veranstaltung bearbeiten',
        'trip_form': trip_form,
        'trip': trip_d,
        'construction_formset': tripconstruction_formset,
        'group_formset': tripgroup_formset,
        'material_formset': tripmaterial_formset,
        'constructions': constructions,
        'materials': materials,
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
        if 'location/edit/' in previous_url or 'location/show/' in previous_url or 'location/delete/' in previous_url:
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
    locations_query = Location.objects.filter(owner=request.org).order_by('name')
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
    request.session['previous_url'] = request.build_absolute_uri()
    location_d = get_object_or_404(Location, pk=pk, owner=request.org)
    if request.method == 'POST':
        location_d.delete()
        messages.success(request, f'Ort {location_d.name} erfolgreich gelöscht.')
        return HttpResponseRedirect(reverse_lazy('location'))
    return render(request, 'events/delete_location.html', {'title': 'Ort löschen', 'location': location_d})


@login_required
def show_location(request, pk=None):
    request.session['previous_url'] = request.build_absolute_uri()
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

    referer_url = request.META.get('HTTP_REFERER', '')

    if 'find_construction_combination_w_check_material' in referer_url:
        vorherige_seite = 'find_construction_combination_w_check_material'
    elif 'find_construction_combination' in referer_url:
        vorherige_seite = 'find_construction_combination'
    else:
        vorherige_seite = None  # Keine bekannte vorherige URL

    # Falls du basierend auf der vorherigen Seite etwas tun willst:
    if vorherige_seite == 'find_construction_combination':
        # Finde die optimale Kombination der Konstruktionen und das minimalste Gesamtgewicht
        optimal_combination, min_total_weight = find_optimal_construction_combination(
            teilnehmergruppen, konstruktionen, request, min_sleeping_places_c
        )
    elif vorherige_seite == 'find_construction_combination_w_check_material':
        # Finde die optimale Kombination der Konstruktionen und das minimalste Gesamtgewicht
        optimal_combination, min_total_weight = find_optimal_construction_combination_w_check_material(
            teilnehmergruppen, konstruktionen, request, min_sleeping_places_c, trip)

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


def find_optimal_construction_combination_w_check_material(teilnehmergruppen, konstruktionen, request,
                                                           min_sleep_place_count_construction, trip):
    max_sleep_places = max(teilnehmergruppen)
    print(max(c.sleep_place_count for c in konstruktionen))
    max_sleep_place_count = max(c.sleep_place_count for c in konstruktionen)

    dp = [Decimal('Infinity')] * (max_sleep_places + max_sleep_place_count + 1)
    dp[0] = Decimal(0)
    backtrace = defaultdict(list)

    # Iteriere über alle möglichen Kombinationen von Konstruktionen
    for count in range(1, len(konstruktionen) + 1):
        for konstruktion_combination in combinations(konstruktionen, count):
            total_sleep_places = sum(k.sleep_place_count for k in konstruktion_combination)
            total_weight = sum(
                calculate_construction_weight(ConstructionMaterial.objects.filter(construction=k)) for k in
                konstruktion_combination)

            if total_sleep_places >= min_sleep_place_count_construction:
                for sleep_places in range(total_sleep_places, max_sleep_places + max_sleep_place_count + 1):
                    new_weight = dp[sleep_places - total_sleep_places] + total_weight
                    if new_weight < dp[sleep_places]:
                        dp[sleep_places] = new_weight
                        backtrace[sleep_places] = backtrace[sleep_places - total_sleep_places] + list(
                            konstruktion_combination)

    result = []
    total_material_usage = defaultdict(int)
    # Ursprüngliche Reihenfolge speichern
    original_order = list(enumerate(teilnehmergruppen))
    # Sortiere absteigend nach Gruppengröße
    teilnehmergruppen.sort(reverse=True)
    result = []
    total_material_usage = defaultdict(int)

    for idx, group_size in original_order:
        valid_combinations = []

        for sleep_places in range(group_size, max_sleep_places + max_sleep_place_count + 1):
            if dp[sleep_places] != Decimal('Infinity') and sleep_places >= group_size:
                current_combination = backtrace[sleep_places]
                current_weight = calculate_total_weight_for_group(current_combination)
                material_counts = calculate_material_usage(current_combination)
                temp_material_usage = total_material_usage.copy()

                for material, count in material_counts.items():
                    temp_material_usage[material] += count

                if check_material_availability(temp_material_usage, request, trip):
                    valid_combinations.append((current_weight, current_combination))

        if not valid_combinations:
            messages.warning(request,
                             f"Größe {group_size} kann mit den verfügbaren Konstruktionen nicht abgedeckt werden!")
            result.append((idx, []))
        else:
            best_combination = min(valid_combinations, key=lambda x: x[0])[1]
            for material, count in calculate_material_usage(best_combination).items():
                total_material_usage[material] += count
            result.append((idx, best_combination))

    # Wiederherstellung der ursprünglichen Reihenfolge
    result.sort(key=lambda x: x[0])
    result = [combination for _, combination in result]

    group_weights = [calculate_total_weight_for_group(group_combination) for group_combination in result]
    min_total_weight = sum(group_weights) if group_weights else 0
    return result, min_total_weight


def calculate_material_usage(combination):
    material_counts = defaultdict(int)
    for konstruktion in combination:
        for material in ConstructionMaterial.objects.filter(construction=konstruktion):
            material_counts[material.material.name] += material.count
    return material_counts


def check_material_availability(total_material_counts, request, trip):
    material_lager = defaultdict(int)
    for mat in StockMaterial.objects.filter(organization=request.org):
        material_lager[mat.material.name] += mat.count - mat.condition_broke

    conflicting_trips = Trip.objects.filter(
        start_date__lt=trip.end_date,
        end_date__gt=trip.start_date, owner=request.org
    ).exclude(pk=trip.pk)

    material_used_parallel = defaultdict(int)

    used_materials_trip = conflicting_trips.values('tripmaterial__material__name').annotate(
        total_used=Sum('tripmaterial__count')
    )
    used_materials_construction = conflicting_trips.values(
        'tripconstruction__construction__constructionmaterial__material__name'
    ).annotate(total_used=Sum('tripconstruction__construction__constructionmaterial__count'))

    for entry in used_materials_trip:
        material_used_parallel[entry['tripmaterial__material__name']] += entry['total_used'] or 0
    for entry in used_materials_construction:
        material_used_parallel[entry['tripconstruction__construction__constructionmaterial__material__name']] += \
            entry['total_used'] or 0

    for material_type, required_amount in total_material_counts.items():
        available_amount = material_lager.get(material_type, 0) - material_used_parallel.get(material_type, 0)
        if required_amount > available_amount:
            return False
    return True


def find_construction_combination_w_check_material(request, pk=None):
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
    optimal_combination, min_total_weight = find_optimal_construction_combination_w_check_material(teilnehmergruppen,
                                                                                                   konstruktionen,
                                                                                                   request,
                                                                                                   min_sleeping_places_c,
                                                                                                   trip)

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
        'title': 'Optimale Konstruktions-Kombination finden mit Materialverfügbarkeits-Prüfung',
        'trip': trip,
        'group_construction_data': group_construction_data,
        'min_total_weight': min_total_weight,
    })


@require_POST
@event_manager_required
def change_packed_material(request):
    raw_name = request.GET.get("material_name")
    trip_id = request.GET.get("trip_id")

    if not raw_name or not trip_id:
        # Optional: Fehlermeldung oder redirect
        return redirect("trip")

    material_name = unquote(raw_name)
    trip = get_object_or_404(Trip, pk=trip_id, owner=request.org)
    packed_value = request.POST.get("packed")
    packed = packed_value.lower() == "true"

    packed_material, created = PackedMaterial.objects.get_or_create(
        trip=trip, material_name=material_name
    )
    packed_material.packed = packed
    packed_material.save()
    print(packed_material.packed)

    return JsonResponse({"status": "success", "packed": packed})


def download_trip_ics(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id)

    cal = Calendar()
    event = Event()
    event.add('summary', trip.name)
    event.add('description', trip.description)
    event.add('dtstart', trip.start_date)
    event.add('dtend', trip.end_date)
    if trip.location:
        event.add('location', str(trip.location))
    cal.add_component(event)

    response = HttpResponse(cal.to_ical(), content_type='text/calendar')
    response['Content-Disposition'] = f'attachment; filename="{trip.name}.ics"'
    return response


@login_required
@pro1_required
def shoppinglist(request, pk=None):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)
    items = trip.shoppinglist.all()
    search_query = request.GET.get('search', '')
    if search_query:
        items = items.filter(
            Q(name__icontains=search_query)).order_by('name')
    for item in items:
        item.amount_str = "{0:.2f}".format(item.amount)
    form = ShoppingListItemForm()  # <-- Form muss erstellt werden
    return render(request, 'events/shoppinglist.html', {
        'title': f"Einkaufsliste zur Veranstaltung: {trip.name}",
        'trip': trip,
        'shoppinglist': items,
        'form': form,
    })


@require_POST
def add_shoppinglist_item(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id)
    form = ShoppingListItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        item.trip = trip

        # amount sauber in Decimal umwandeln
        try:
            item.amount = Decimal(str(form.cleaned_data["amount"]).replace(",", "."))
        except (InvalidOperation, TypeError):
            item.amount = Decimal("0")

        item.save()

        return JsonResponse({
            "success": True,
            "item": {
                "id": item.pk,
                "name": item.name,
                "amount": str(item.amount),
                "unit": item.unit,
                "delete_url": reverse("delete_shoppinglist_item", args=[item.pk])
            }
        })
    else:
        return JsonResponse({"success": False, "error": form.errors})


@require_POST
def update_shoppinglist_item(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    try:
        data = json.loads(request.body)
        item = get_object_or_404(ShoppingListItem, pk=data.get("id"))
        field = data.get("field")
        value = data.get("value")

        if field not in ["amount", "unit"]:
            return JsonResponse({"success": False, "error": "Ungültiges Feld"})

        if field == "amount":
            try:
                value = Decimal(str(value).replace(",", "."))
            except (InvalidOperation, TypeError):
                return JsonResponse({"success": False, "error": "Ungültige Zahl"})

        setattr(item, field, value)
        item.save()

        return JsonResponse({
            "success": True,
            "item": {
                "id": item.pk,
                "name": item.name,
                "amount": str(item.amount),
                "unit": item.unit
            }
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@require_POST
def delete_shoppinglist_item(request, item_id):
    item = get_object_or_404(ShoppingListItem, pk=item_id)
    item.delete()
    return JsonResponse({"success": True})


@login_required
@pro1_required
def trip_vacancies(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, owner=request.org)
    form = TripVacancyForm()
    vacancies = trip.vacancies.all()
    search_query = request.GET.get('search', '')
    if search_query:
        vacancies = vacancies.filter(
            Q(name__icontains=search_query)).order_by('name')
    return render(request, "events/trip_vacancies.html", {
        'title': f"Teilnehmer-Vakanzen zur Veranstaltung: {trip.name}",
        'trip': trip,
        'vacancies': vacancies,
        'form': form,
    })


@require_POST
def add_vacancy(request, trip_id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    trip = get_object_or_404(Trip, pk=trip_id)

    # FormData aus request.POST
    name = request.POST.get("name", "").strip()
    arrival_str = request.POST.get("arrival", "")
    departure_str = request.POST.get("departure", "")

    if not name:
        return JsonResponse({"success": False, "error": "Name darf nicht leer sein"})

    # Datum umwandeln
    arrival = None
    departure = None
    try:
        if arrival_str:
            arrival = datetime.strptime(arrival_str, "%Y-%m-%dT%H:%M")
            arrival = timezone.make_aware(arrival, timezone.get_current_timezone())
        if departure_str:
            departure = datetime.strptime(departure_str, "%Y-%m-%dT%H:%M")
            departure = timezone.make_aware(departure, timezone.get_current_timezone())
    except ValueError:
        return JsonResponse({"success": False, "error": "Ungültiges Datum/Zeit"})

    # Prüfen, dass Ankunft ≤ Abreise
    if arrival and departure and arrival > departure:
        return JsonResponse({"success": False, "error": "Ankunft darf nicht nach Abreise liegen"})

    # Neues Vacancy erstellen
    item = TripVacancy.objects.create(
        trip=trip,
        name=name,
        arrival=arrival,
        departure=departure
    )

    return JsonResponse({
        "success": True,
        "item": {
            "id": item.pk,
            "name": item.name,
            "arrival": item.arrival.strftime("%Y-%m-%dT%H:%M") if item.arrival else "",
            "departure": item.departure.strftime("%Y-%m-%dT%H:%M") if item.departure else "",
            "delete_url": reverse("delete_vacancy", args=[item.pk])
        }
    })


@require_POST
def update_vacancy(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    try:
        data = json.loads(request.body)
        item = get_object_or_404(TripVacancy, pk=data.get("id"))
        field = data.get("field")
        value = data.get("value")

        if field not in ["arrival", "departure"]:
            return JsonResponse({"success": False, "error": "Ungültiges Feld"})

        # Datum umwandeln
        if value:
            try:
                value_dt = datetime.strptime(value, "%Y-%m-%dT%H:%M")
                value_dt = timezone.make_aware(value_dt, timezone.get_current_timezone())
            except ValueError:
                return JsonResponse({"success": False, "error": "Ungültiges Datum/Zeit"})
        else:
            value_dt = None

        # Temporär setzen, um Reihenfolge prüfen zu können
        if field == "arrival":
            arrival = value_dt
            departure = item.departure
        else:
            arrival = item.arrival
            departure = value_dt

        if arrival and departure and arrival > departure:
            return JsonResponse({"success": False, "error": "Ankunft darf nicht nach Abreise liegen"})

        setattr(item, field, value_dt)
        item.save()

        return JsonResponse({
            "success": True,
            "item": {
                "id": item.pk,
                "name": item.name,
                "arrival": item.arrival.strftime("%Y-%m-%dT%H:%M") if item.arrival else "",
                "departure": item.departure.strftime("%Y-%m-%dT%H:%M") if item.departure else ""
            }
        })

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@require_POST
def delete_vacancy(request, vacancy_id):
    item = get_object_or_404(TripVacancy, pk=vacancy_id)
    item.delete()
    return JsonResponse({"success": True})


def export_vacancies_csv(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id)
    vacancies = trip.vacancies.all()

    # CSV Response vorbereiten (UTF-8)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f'Vakanzen_Veranstaltung_{slugify(trip.name)}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Name', 'Anwesenheit'])  # Header

    for v in vacancies:
        # Anwesenheit-Text zusammenbauen
        arrival_str = v.arrival.strftime('%d-%m-%Y %H:%M') if v.arrival else 'unbekannt '
        departure_str = v.departure.strftime('%d-%m-%Y %H:%M') if v.departure else 'unbekannt '
        presence_text = f'Von {arrival_str} bis {departure_str} anwesend'

        writer.writerow([
            v.name or '',
            presence_text
        ])
    return response


def import_vacancies_csv(request, trip_id):
    if request.method == "POST" and request.FILES.get("csv_file"):
        csv_file = request.FILES["csv_file"].read().decode("utf-8-sig").splitlines()
        reader = csv.DictReader(csv_file, delimiter=",", quotechar='"')
        trip = get_object_or_404(Trip, pk=trip_id)
        created = 0
        vorname_col = next((f for f in reader.fieldnames if "vorname" in f.lower()), None)
        nachname_col = next((f for f in reader.fieldnames if "nachname" in f.lower()), None)
        for row in reader:
            vorname = row.get(vorname_col)
            nachname = row.get(nachname_col)
            if nachname and vorname:
                name = f"{vorname} {nachname}".strip()
            else:
                name = None
            arrival = None
            departure = None
            try:
                if row.get("Ankunft"):
                    arrival = datetime.strptime(row["Ankunft"].strip(), "%d-%m-%YT%H:%M")
            except ValueError:
                arrival = None

            try:
                if row.get("Abreise"):
                    departure = datetime.strptime(row["Abreise"].strip(), "%d-%m-%YT%H:%M")
            except ValueError:
                departure = None
            if name:  # nur mit Name speichern
                TripVacancy.objects.create(
                    trip=trip,
                    name=name,
                    arrival=arrival,
                    departure=departure,
                )
                created += 1

        messages.success(request, f"{created} Teilnehmer erfolgreich importiert.")
    else:
        messages.error(request, "Bitte eine CSV-Datei hochladen.")

    return redirect("trip_vacancies", trip_id=trip_id)

@login_required
@pro1_required
def checklist(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, owner=request.org)
    items = trip.checklist.all().order_by("due_date")
    form = EventPlanningChecklistItemForm()
    return render(request, "events/checklist.html", {
        "title":f"To-Do's zur Veranstaltung: {trip.name}",
        "trip": trip,
        "items": items,
        "form": form,
    })

@login_required
@require_POST
def add_checklist_item(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, owner=request.org)
    title = request.POST.get("title")
    due_date = request.POST.get("due_date") or None
    if due_date:
        # Falls dein Input vom Frontend als "2025-09-06T14:30" kommt (datetime-local input)
        try:
            naive_dt = datetime.strptime(due_date, "%Y-%m-%dT%H:%M")
        except ValueError:
            # Falls nur Datum kommt ("2025-09-06"), setze 00:00 Uhr
            naive_dt = datetime.strptime(due_date, "%Y-%m-%d")
        due_date = timezone.make_aware(naive_dt)  # Zeitzone sicher machen

    item = EventPlanningChecklistItem.objects.create(
        trip=trip,
        title=title,
        due_date=due_date
    )
    return JsonResponse({
        "success": True,
        "item": {
            "id": item.id,
            "title": item.title,
            "done": item.done,
            "due_date": item.due_date.strftime("%Y-%m-%dT%H:%M") if item.due_date else "",
            "delete_url": reverse("delete_checklist_item", args=[item.id])
        }
    })

@login_required
@require_POST
def toggle_checklist_item(request, item_id):
    item = get_object_or_404(EventPlanningChecklistItem, pk=item_id)
    item.done = not item.done
    item.save()
    return JsonResponse({"success": True, "done": item.done})

@login_required
@require_POST
def delete_checklist_item(request, item_id):
    item = get_object_or_404(EventPlanningChecklistItem, pk=item_id)
    item.delete()
    return JsonResponse({"success": True})

@login_required
@require_POST
@csrf_exempt
def update_checklist_due_date(request):
    import json
    data = json.loads(request.body)
    item_id = data.get("id")
    value = data.get("value")  # ISO Format: "YYYY-MM-DDTHH:MM"

    item = get_object_or_404(EventPlanningChecklistItem, pk=item_id)

    if value:
        try:
            naive_dt = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        except ValueError:
            naive_dt = datetime.strptime(value, "%Y-%m-%d")
        item.due_date = timezone.make_aware(naive_dt)
    else:
        item.due_date = None

    item.save()
    return JsonResponse({
        "success": True,
        "due_date": item.due_date.strftime("%Y-%m-%dT%H:%M") if item.due_date else ""
    })
