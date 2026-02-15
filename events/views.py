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
from django.utils.timezone import now, localtime
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
from datetime import datetime, timedelta
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404

from buildings.views import update_trip_material_stock_for_org
from .models import Trip, TripVacancy, EventPlanningChecklistItem, ProgrammItem

from decimal import Decimal, InvalidOperation

from buildings.models import Construction, StockMaterial, ConstructionMaterial, Material
from events.forms import TripForm, TripConstructionFormSet, LocationForm, ImportLocationForm, TripGroupFormSet, \
    TripMaterialFormSet, ShoppingListItemForm, TripVacancyForm, EventPlanningChecklistItemForm, ProgrammItemForm, \
    ProgrammItemEditForm
from events.models import Trip, TripConstruction, Location, PackedMaterial, TripGroup, TripMaterial, ShoppingListItem, \
    TripVacancy
from main.decorators import organization_admin_required, event_manager_required, pro1_required, pro2_required, \
    pro3_required, pro4_required
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
    trips_query = Trip.objects.filter(owner=request.org).order_by('-start_date')
    if search_query:
        trips_query = trips_query.filter(
            Q(name__icontains=search_query) | Q(owner__name__icontains=search_query)
        ).order_by('-start_date')
    if selected_trip_type:
        trips_query = trips_query.filter(type=selected_trip_type).order_by('-start_date')
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
            trip_form.save_m2m()
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
                                si, c = ShoppingListItem.objects.get_or_create(trip=trip_d, name=mat.material.name,
                                                                               unit="Stück",
                                                                               stockmaterial=mat_stock.first())
                                si.amount = missing_amount
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
                                si, c = ShoppingListItem.objects.get_or_create(trip=trip_d, name=mat.material.name,
                                                                               unit="Stück",
                                                                               stockmaterial=mat_stock.first())
                                si.amount = missing_amount
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
                return redirect('edit_trip',
                                trip_d.pk)  # Hier 'trip' zu deiner Trip-Liste oder Detail-Seite weiterleiten
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
    """
    Effizienter Algorithmus ohne Materialprüfung.
    Berechnet die optimale Konstruktion je Gruppe (minimales Gewicht),
    unter Beachtung der Mindest-Schlafplätze pro Einzelkonstruktion.
    """

    # Filtere Konstruktionen nach Mindest-Schlafplatzanzahl
    valid_konstruktionen = [
        k for k in konstruktionen
        if k.sleep_place_count >= min_sleep_place_count_construction
    ]

    if not valid_konstruktionen:
        # Keine gültigen Konstruktionen vorhanden
        for g in teilnehmergruppen:
            messages.warning(
                request,
                f"Größe {g} kann mit den verfügbaren Konstruktionen nicht abgedeckt werden!"
            )
        return [[] for _ in teilnehmergruppen], Decimal(0)

    # Preload der Gewichte und Schlafplätze, um DB-Abfragen zu minimieren
    preloaded_data = {}
    for k in valid_konstruktionen:
        materials = ConstructionMaterial.objects.filter(construction=k)
        preloaded_data[k.id] = {
            "obj": k,
            "sleep": k.sleep_place_count,
            "weight": calculate_construction_weight(materials),
        }

    # DP-Array vorbereiten
    max_sleep = max(teilnehmergruppen)
    max_konstruktion_sleep = max(d["sleep"] for d in preloaded_data.values())
    max_dp = max_sleep + max_konstruktion_sleep

    INF = Decimal("1000000000")
    dp = [INF] * (max_dp + 1)
    dp[0] = Decimal(0)

    # Parent-Array für Backtracking
    parent = [-1] * (max_dp + 1)

    # Dynamic Programming
    for k_id, d in preloaded_data.items():
        sleep = d["sleep"]
        weight = d["weight"]
        for s in range(sleep, len(dp)):  # aufsteigend
            if dp[s - sleep] + weight < dp[s]:
                dp[s] = dp[s - sleep] + weight
                parent[s] = k_id

    # Rekonstruktion je Gruppe
    result = []
    for group_size in teilnehmergruppen:
        best_s = None
        best_weight = INF
        for s in range(group_size, len(dp)):
            if dp[s] < best_weight:
                best_weight = dp[s]
                best_s = s

        if best_s is None:
            # Keine Kombination für diese Gruppe
            messages.warning(
                request,
                f"Größe {group_size} kann mit den verfügbaren Konstruktionen nicht abgedeckt werden!"
            )
            result.append([])
            continue

        # Backtracking für die beste Kombination
        combo = []
        s = best_s
        while s > 0 and parent[s] != -1:
            k_id = parent[s]
            combo.append(preloaded_data[k_id]["obj"])
            s -= preloaded_data[k_id]["sleep"]

        result.append(combo)

    # Gesamtgewicht berechnen
    min_total_weight = sum(
        sum(preloaded_data[k.id]["weight"] for k in combo)
        for combo in result
    )

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
            teilnehmergruppen, konstruktionen, request, trip)

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


##NEUER ALGO

def preload_construction_data(constructions):
    weight_cache = {}
    material_cache = {}
    materials = (
        ConstructionMaterial.objects
        .filter(construction__in=constructions)
        .select_related("material", "construction")
    )
    for cm in materials:
        cid = cm.construction_id
        if cid not in weight_cache:
            weight_cache[cid] = Decimal(0)
            material_cache[cid] = defaultdict(int)
        weight_cache[cid] += (cm.material.weight or 0) * cm.count
        material_cache[cid][cm.material.name] += cm.count
    return weight_cache, material_cache


def calculate_material_usage_from_cache(combination, material_cache):
    usage = defaultdict(int)
    for c in combination:
        for mat, cnt in material_cache.get(c.id, {}).items():
            usage[mat] += cnt
    return usage


def check_material_availability(total_material_counts, request, trip):
    material_lager = defaultdict(int)
    for mat in StockMaterial.objects.filter(organization=request.org):
        material_lager[mat.material.name] += mat.count - mat.condition_broke

    conflicting_trips = Trip.objects.filter(
        start_date__lt=trip.end_date,
        end_date__gt=trip.start_date,
        owner=request.org
    ).exclude(pk=trip.pk)

    material_used_parallel = defaultdict(int)

    used_trip_materials = conflicting_trips.values(
        'tripmaterial__material__name'
    ).annotate(total=Sum('tripmaterial__count'))

    used_construction_materials = conflicting_trips.values(
        'tripconstruction__construction__constructionmaterial__material__name'
    ).annotate(total=Sum('tripconstruction__construction__constructionmaterial__count'))

    for e in used_trip_materials:
        material_used_parallel[e['tripmaterial__material__name']] += e['total'] or 0
    for e in used_construction_materials:
        material_used_parallel[e['tripconstruction__construction__constructionmaterial__material__name']] += e[
                                                                                                                 'total'] or 0

    for material, required in total_material_counts.items():
        available = material_lager.get(material, 0) - material_used_parallel.get(material, 0)
        if required > available:
            return False
    return True


def find_best_construction_for_group(constructions, group_size, used_materials_global,
                                     request, trip, weight_cache, material_cache):
    """
    Unbounded Knapsack für eine Gruppe. Flache DP, iterative Materialprüfung.
    """
    if not constructions:
        return None

    # Große Konstruktionen zuerst
    constructions = sorted(constructions, key=lambda c: c.sleep_place_count, reverse=True)

    # DP Array: minimalgewicht für s Schlafplätze
    max_sleep = group_size + max(c.sleep_place_count for c in constructions) * 2
    dp = [Decimal('Infinity')] * (max_sleep + 1)
    dp[0] = Decimal(0)
    backtrace = [[] for _ in range(max_sleep + 1)]

    # Unbounded Knapsack (flach)
    for c in constructions:
        sleep = c.sleep_place_count
        weight = weight_cache[c.id]
        for s in range(sleep, len(dp)):
            new_weight = dp[s - sleep] + weight
            if new_weight < dp[s]:
                dp[s] = new_weight
                backtrace[s] = backtrace[s - sleep] + [c]

    # Suche erste Kombination >= group_size, die Material erfüllt
    for s in range(group_size, len(dp)):
        if dp[s] == Decimal('Infinity'):
            continue
        combination = backtrace[s]
        temp_usage = used_materials_global.copy()
        for mat, cnt in calculate_material_usage_from_cache(combination, material_cache).items():
            temp_usage[mat] += cnt
        if check_material_availability(temp_usage, request, trip):
            return dp[s], combination

    # Fallback: Greedy – fülle mit großen Konstruktionen bis Group_Size
    combination = []
    remaining = group_size
    temp_usage = used_materials_global.copy()
    for c in constructions:
        while remaining > 0:
            temp_usage_try = temp_usage.copy()
            for mat, cnt in material_cache[c.id].items():
                temp_usage_try[mat] += cnt
            if not check_material_availability(temp_usage_try, request, trip):
                break
            combination.append(c)
            for mat, cnt in material_cache[c.id].items():
                temp_usage[mat] += cnt
            remaining -= c.sleep_place_count
    if sum(c.sleep_place_count for c in combination) >= group_size:
        return sum(weight_cache[c.id] for c in combination), combination

    return None


def find_optimal_construction_combination_w_check_material(teilnehmergruppen, konstruktionen, request, trip):
    weight_cache, material_cache = preload_construction_data(konstruktionen)
    min_sleep = int(request.session.get("min_sleeping_places", 1))
    valid_konstruktionen = [k for k in konstruktionen if k.sleep_place_count >= min_sleep]
    if not valid_konstruktionen:
        messages.warning(request, "Keine Konstruktionen mit ausreichender Schlafplatzanzahl verfügbar.")
        return redirect('edit_trip', pk=trip.pk)
    # Große Gruppen zuerst
    original_order = list(enumerate(teilnehmergruppen))
    teilnehmergruppen_sorted = sorted(original_order, key=lambda x: x[1], reverse=True)

    used_materials_global = defaultdict(int)
    result = []

    for idx, group_size in teilnehmergruppen_sorted:
        solution = find_best_construction_for_group(
            valid_konstruktionen,
            group_size,
            used_materials_global,
            request,
            trip,
            weight_cache,
            material_cache
        )
        if solution is None:
            messages.warning(request, f"Größe {group_size} kann nicht abgedeckt werden!")
            result.append((idx, []))
            continue

        weight, combination = solution
        for mat, cnt in calculate_material_usage_from_cache(combination, material_cache).items():
            used_materials_global[mat] += cnt
        result.append((idx, combination))

    result.sort(key=lambda x: x[0])
    final_result = [comb for _, comb in result]

    total_weight = sum(weight_cache[c.id] for group in final_result for c in group)
    return final_result, total_weight


def find_construction_combination_w_check_material(request, pk=None):
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)
    trip_groups = TripGroup.objects.filter(trip=trip)
    if not trip_groups.exists():
        messages.warning(request, "Keine Teilnehmergruppen vorhanden.")
        return redirect('edit_trip', pk=pk)

    teilnehmergruppen = [g.count for g in trip_groups]
    min_sleep = int(request.session.get("min_sleeping_places", 1))
    konstruktionen = Construction.objects.filter(owner=request.org)
    valid_konstruktionen = [k for k in konstruktionen if k.sleep_place_count >= min_sleep]
    if not valid_konstruktionen:
        messages.warning(request, "Keine Konstruktionen mit ausreichender Schlafplatzanzahl verfügbar.")
        return redirect('edit_trip', pk=pk)

    optimal, total_weight = find_optimal_construction_combination_w_check_material(
        teilnehmergruppen,
        valid_konstruktionen,
        request,
        trip
    )

    group_data = []
    for group, combo in zip(trip_groups, optimal):
        group_data.append({
            "group_name": group.name,
            "required_sleep_place_count": group.count,
            "total_weight": sum(c.sleep_place_count for c in combo),
            "constructs": [{"name": c.name, "sleep_places": c.sleep_place_count} for c in combo]
        })

    return render(request, "events/find_construction_combination.html", {
        "trip": trip,
        "group_construction_data": group_data,
        "min_total_weight": total_weight,
        "title": "Optimale Konstruktionen mit Materialprüfung"
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


@event_manager_required
@login_required
def download_trip_ics(request, trip_id):
    trip = get_object_or_404(Trip, id=trip_id, owner=request.org)

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
@event_manager_required
def shoppinglist(request, pk=None):
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)
    items = trip.shoppinglist.all()
    search_query = request.GET.get('search', '').strip()
    selected_product_group = request.GET.get('product_group', '')
    if search_query:
        items = items.filter(name__icontains=search_query)

    if selected_product_group != "":
        items = items.filter(product_group=selected_product_group)

    items = items.order_by('product_group', 'name')
    for item in items:
        item.amount_str = "{0:.2f}".format(item.amount)
    form = ShoppingListItemForm()  # <-- Form muss erstellt werden
    return render(request, 'events/shoppinglist.html', {
        'title': f"Einkaufsliste zur Veranstaltung: {trip.name}",
        'trip': trip,
        'shoppinglist': items,
        'form': form,
        'search_query': search_query,
        'product_groups': ShoppingListItem.GROUPS,
        'selected_product_group': selected_product_group,
    })

@login_required
@pro1_required
def shoppinglist_auto_complete(request):
    q = request.GET.get("q", "").strip()
    if not q:
        materials = (
            StockMaterial.objects
            .filter(organization=request.org,material__type=6)
            .order_by("material__name").distinct()
            .values_list("material__name", flat=True)[:15]
        )
        return JsonResponse(list(materials), safe=False)

    materials = (
        StockMaterial.objects
        .filter(organization=request.org,material__name__icontains=q,material__type=6)
        .order_by("material__name").distinct()
        .values_list("material__name", flat=True)[:15]
    )
    return JsonResponse(list(materials), safe=False)

@require_POST
@login_required
@pro1_required
@event_manager_required
def add_shoppinglist_item(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, owner=request.org)
    form = ShoppingListItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        consum_material = StockMaterial.objects.filter(organization=request.org,material__name= item.name,material__type=6).first()
        item.trip = trip
        if consum_material :
            item.stockmaterial=consum_material
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
                "product_group": item.product_group,
                "delete_url": reverse("delete_shoppinglist_item", args=[item.pk])
            }
        })
    else:
        return JsonResponse({"success": False, "error": form.errors})


@require_POST
@login_required
@pro1_required
@event_manager_required
def update_shoppinglist_item(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    try:
        data = json.loads(request.body)
        item = get_object_or_404(ShoppingListItem, pk=data.get("id"))
        field = data.get("field")
        value = data.get("value")

        if field not in ["amount", "unit", "product_group"]:
            return JsonResponse({"success": False, "error": "Ungültiges Feld"})

        if field == "amount":
            try:
                value = Decimal(str(value).replace(",", "."))
            except (InvalidOperation, TypeError):
                return JsonResponse({"success": False, "error": "Ungültige Zahl"})
        if field == "product_group":
            if value == "":
                item.product_group = None
            else:
                try:
                    item.product_group = int(value)
                except (TypeError, ValueError):
                    return JsonResponse({"success": False, "error": "Ungültige Warengruppe"})

            item.save()
            return JsonResponse({"success": True})

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
@login_required
@pro1_required
@event_manager_required
def delete_shoppinglist_item(request, item_id):
    item = get_object_or_404(ShoppingListItem, pk=item_id, trip__owner=request.org)
    msg = None
    if item.stockmaterial is not None:
        item.stockmaterial.count += item.amount
        item.stockmaterial.save()
        msg = f"{item.amount} × {item.name} wurde dem Lager hinzugefügt."
        update_trip_material_stock_for_org(request, request.org)
    item.delete()
    return JsonResponse({"success": True, "message": msg})


@login_required
@pro2_required
@event_manager_required
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
@login_required
@event_manager_required
@pro2_required
def add_vacancy(request, trip_id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    trip = get_object_or_404(Trip, pk=trip_id, owner=request.org)

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
@login_required
@pro2_required
@event_manager_required
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
@login_required
@pro2_required
@event_manager_required
def delete_vacancy(request, vacancy_id):
    item = get_object_or_404(TripVacancy, pk=vacancy_id, trip__owner=request.org)
    item.delete()
    return JsonResponse({"success": True})


@login_required
@pro2_required
@event_manager_required
def export_vacancies_csv(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, owner=request.org)
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


@login_required
@pro2_required
@event_manager_required
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
@pro3_required
@event_manager_required
def checklist(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, owner=request.org)
    items = trip.checklist.all().order_by("done", "due_date")
    form = EventPlanningChecklistItemForm()
    return render(request, "events/checklist.html", {
        "title": f"To-Do's zur Veranstaltung: {trip.name}",
        "trip": trip,
        "items": items,
        "form": form,
    })


@login_required
@pro3_required
@require_POST
@event_manager_required
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
@pro3_required
@event_manager_required
def toggle_checklist_item(request, item_id):
    item = get_object_or_404(EventPlanningChecklistItem,
                             Q(pk=item_id) & (Q(trip__owner=request.org) | Q(organization=request.org)))
    item.done = not item.done
    item.save()
    return JsonResponse({"success": True, "done": item.done})


@login_required
@require_POST
@pro3_required
@event_manager_required
def delete_checklist_item(request, item_id):
    item = get_object_or_404(EventPlanningChecklistItem,
                             Q(pk=item_id) & (Q(trip__owner=request.org) | Q(organization=request.org)))
    item.delete()
    return JsonResponse({"success": True})


@login_required
@require_POST
@csrf_exempt
@pro3_required
@event_manager_required
def update_checklist_due_date(request):
    import json
    data = json.loads(request.body)
    item_id = data.get("id")
    value = data.get("value")  # ISO Format: "YYYY-MM-DDTHH:MM"

    item = get_object_or_404(EventPlanningChecklistItem,
                             Q(pk=item_id) & (Q(trip__owner=request.org) | Q(organization=request.org)))

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


def overlaps(a_start, a_end, b_start, b_end):
    return not (a_end <= b_start or a_start >= b_end)


def create_clusters(day_list):
    clusters = []
    current_cluster = []
    for item in sorted(day_list, key=lambda x: x.start_time):
        if not current_cluster:
            current_cluster.append(item)
        else:
            # Prüfen, ob sich das aktuelle Item mit einem im Cluster überschneidet
            if any(overlaps(item.start_time, item.end_time, other.start_time, other.end_time) for other in
                   current_cluster):
                current_cluster.append(item)
            else:
                clusters.append(current_cluster)
                current_cluster = [item]
    if current_cluster:
        clusters.append(current_cluster)
    return clusters


@login_required
@pro4_required
def programm(request, pk):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)
    items = trip.programm.all()

    # Suchfeld
    search_query = request.GET.get('search', '').strip()

    # Multi-Select Typen
    selected_type_list = request.GET.getlist('type')  # List[str], z.B. ["0", "2", "4"]

    if selected_type_list:
        # In Integer umwandeln
        type_list = [int(t) for t in selected_type_list if t.strip()]
        if type_list:
            items = items.filter(type__in=type_list)

    # Name-Filter
    if search_query:
        items = items.filter(name__icontains=search_query)

    items = items.order_by('start_time', 'name')

    # Für Select2: alle Typen vorbereiten
    types_for_select2 = [{"id": str(t[0]), "text": t[1]} for t in ProgrammItem.TYPES]

    # Auswahl-Liste vorbereiten (Template braucht Liste, keine Strings)
    if selected_type_list:
        selected_type_list = [str(t) for t in type_list] if selected_type_list else []
    else:
        selected_type_list = []

    # Layout-Parameter
    scale = 2
    min_height = 80
    day_width = 350
    gap = 10
    # container_height = (end_hour - start_hour) * 60 * scale
    # Dynamische Anpassung des Zeitrasters
    all_start_times = [localtime(item.start_time).time() for item in items if item.start_time]
    all_end_times = [localtime(item.end_time).time() for item in items if item.end_time]

    default_start = 7
    default_end = 22
    if all_start_times and all_end_times:
        start_hour = min(default_start, min(t.hour for t in all_start_times))
        end_hour = max(default_end, max(t.hour for t in all_end_times) + 1)
    else:
        start_hour = default_start
        end_hour = default_end

    container_height = (end_hour - start_hour) * 60 * scale
    grouped_by_day = defaultdict(list)
    for item in items:
        if item.start_time and item.end_time:
            start = localtime(item.start_time)
            end = localtime(item.end_time)
            duration_minutes = int((end - start).total_seconds() / 60)
            item.duration = max(duration_minutes * scale, min_height)
            offset_minutes = (start.hour * 60 + start.minute) - (start_hour * 60)
            item.offset = max(offset_minutes, 0) * scale
        else:
            item.duration = min_height
            item.offset = 0
        grouped_by_day[start.date()].append(item)

    # Cluster- und Spaltenberechnung
    for day, day_list in grouped_by_day.items():
        clusters = create_clusters(day_list)
        for cluster_idx, cluster in enumerate(clusters):
            columns = []
            for item in cluster:
                placed = False
                for col_idx, col in enumerate(columns):
                    if all(not overlaps(item.start_time, item.end_time, other.start_time, other.end_time) for other in
                           col):
                        col.append(item)
                        item.column = col_idx
                        placed = True
                        break
                if not placed:
                    columns.append([item])
                    item.column = len(columns) - 1

            max_columns = len(columns)
            for itm in cluster:
                itm.width = round((day_width - (gap * (max_columns))) / max_columns, 2)
                itm.left = itm.column * (itm.width + gap)

                # Debug-Infos hinzufügen
                itm.debug_info = f"Cluster: {cluster_idx}, Spalte: {itm.column}, Breite: {itm.width:.1f}px"

    # Stundenlinien
    hours = [(hour, (hour - start_hour) * 60 * scale) for hour in range(start_hour, end_hour + 1)]

    # Tage sortieren
    all_days = []
    current_day = trip.start_date
    while current_day <= trip.end_date:
        all_days.append(current_day.date())
        current_day += timedelta(days=1)

    grouped_by_day_sorted = [(day, grouped_by_day.get(day, [])) for day in all_days]

    return render(request, "events/programm.html", {
        "title": f"Programm der Veranstaltung: {trip.name}",
        "trip": trip,
        "grouped_by_day": grouped_by_day_sorted,
        'types': types_for_select2,
        'selected_type_list': selected_type_list,
        'search_query': search_query,
        'hours': hours,
        'container_height': container_height,
        'day_width': day_width,
        'is_event_manager': m.event_manager,
        'is_pro_1': request.org.pro1,
    })


@login_required
@pro4_required
@event_manager_required
def add_programm_item(request, pk):
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)

    if request.method == "POST":
        form = ProgrammItemForm(request.POST, trip=trip)
        if form.is_valid():

            name = form.cleaned_data['name']
            short_description = form.cleaned_data['short_description']
            description = form.cleaned_data['description']
            type = form.cleaned_data['type']
            recipe = form.cleaned_data['recipe']  # <-- Rezept übernehmen
            start_time = form.cleaned_data['start_time']
            end_time = form.cleaned_data['end_time']
            selected_days = form.cleaned_data['days']

            for day_str in selected_days:
                day = datetime.fromisoformat(day_str).date()
                start_dt = datetime.combine(day, start_time) if start_time else None
                end_dt = datetime.combine(day, end_time) if end_time else None
                ProgrammItem.objects.create(
                    trip=trip,
                    name=name,
                    short_description=short_description,
                    description=description,
                    type=type,
                    recipe=recipe,
                    start_time=start_dt,
                    end_time=end_dt
                )
            messages.success(request, f'Programmpunkt {name} gespeichert.')
            return redirect('programm', pk=trip.pk)
    else:
        form = ProgrammItemForm(trip=trip)

    return render(request, "events/add_programm_item.html", {
        "form": form,
        "trip": trip,
        "title": f"Neuen Programmpunkt für {trip.name} hinzufügen"
    })


@login_required
@pro4_required
@event_manager_required
def edit_programm_item(request, item_id):
    item = get_object_or_404(ProgrammItem, id=item_id, trip__owner=request.org)

    if request.method == "POST":
        if 'save' in request.POST or 'save_add_ingredients' in request.POST:
            form = ProgrammItemEditForm(request.POST, instance=item,org=request.org)
            if form.is_valid():
                # Speichert Änderungen am bestehenden Programmpunkt
                form.save()
                messages.success(request, f'Programmpunkt {item.name} gespeichert.')
                if 'save_add_ingredients' in request.POST:
                    add_recipe_to_shoppinglist(request, item.pk)
                else:
                    return redirect('programm', pk=item.trip.pk)
        elif 'delete' in request.POST:
            trip_id = item.trip.pk
            messages.success(request, f'Programmpunkt {item.name} gelöscht.')
            item.delete()
            return redirect('programm', trip_id)

    else:
        form = ProgrammItemEditForm(instance=item,org=request.org)

    return render(request, "events/edit_programm_item.html", {
        "form": form,
        "item": item,
        "title": f"Programmpunkt bearbeiten: {item.name}"
    })


@login_required
@pro4_required
@event_manager_required
def print_programm(request, pk):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)
    items = trip.programm.all()

    # Suchfeld
    search_query = request.GET.get('search', '').strip()

    # Multi-Select Typen
    selected_type = request.GET.get('type', '')  # z.B. "1,2"
    type_list = []
    if selected_type:
        type_list = [int(t) for t in selected_type.split(',') if t.strip()]

    if type_list:
        items = items.filter(type__in=type_list)

    # Name-Filter
    if search_query:
        items = items.filter(name__icontains=search_query)

    items = items.order_by('start_time', 'name')

    # Layout-Parameter
    scale = 2
    min_height = 95
    day_width = 1350
    gap = 25
    # container_height = (end_hour - start_hour) * 60 * scale
    # Dynamische Anpassung des Zeitrasters
    all_start_times = [localtime(item.start_time).time() for item in items if item.start_time]
    all_end_times = [localtime(item.end_time).time() for item in items if item.end_time]

    default_start = 7
    default_end = 22
    if all_start_times and all_end_times:
        start_hour = min(default_start, min(t.hour for t in all_start_times))
        end_hour = max(default_end, max(t.hour for t in all_end_times) + 1)
    else:
        start_hour = default_start
        end_hour = default_end

    container_height = (end_hour - start_hour) * 60 * scale
    grouped_by_day = defaultdict(list)
    for item in items:
        if item.start_time and item.end_time:
            start = localtime(item.start_time)
            end = localtime(item.end_time)
            duration_minutes = int((end - start).total_seconds() / 60)
            item.duration = max(duration_minutes * scale, min_height)
            offset_minutes = (start.hour * 60 + start.minute) - (start_hour * 60)
            item.offset = max(offset_minutes, 0) * scale
        else:
            item.duration = min_height
            item.offset = 0
        grouped_by_day[start.date()].append(item)

    # Cluster- und Spaltenberechnung
    for day, day_list in grouped_by_day.items():
        clusters = create_clusters(day_list)
        for cluster_idx, cluster in enumerate(clusters):
            columns = []
            for item in cluster:
                placed = False
                for col_idx, col in enumerate(columns):
                    if all(not overlaps(item.start_time, item.end_time, other.start_time, other.end_time) for other in
                           col):
                        col.append(item)
                        item.column = col_idx
                        placed = True
                        break
                if not placed:
                    columns.append([item])
                    item.column = len(columns) - 1

            max_columns = len(columns)
            for itm in cluster:
                itm.width = round((day_width - (gap * (max_columns))) / max_columns, 2)
                itm.left = itm.column * (itm.width + gap)

                # Debug-Infos hinzufügen
                itm.debug_info = f"Cluster: {cluster_idx}, Spalte: {itm.column}, Breite: {itm.width:.1f}px"

    # Stundenlinien
    hours = [(hour, (hour - start_hour) * 60 * scale) for hour in range(start_hour, end_hour + 1)]

    # Tage sortieren
    all_days = []
    current_day = trip.start_date
    while current_day <= trip.end_date:
        all_days.append(current_day.date())
        current_day += timedelta(days=1)

    grouped_by_day_sorted = [(day, grouped_by_day.get(day, [])) for day in all_days]

    return render(request, "events/print_programm.html", {
        "title": f"Programm der Veranstaltung: {trip.name}",
        "trip": trip,
        "grouped_by_day": grouped_by_day_sorted,
        'search_query': search_query,
        'hours': hours,
        'container_height': container_height,
        'day_width': day_width,
        'is_event_manager': m.event_manager,
    })


@login_required
@pro4_required
def show_program_item(request, item_id):
    item = get_object_or_404(ProgrammItem, pk=item_id, trip__owner=request.org)
    return render(request, "events/show_program_item.html", {
        "item": item,
        "title": "Programmpunkt anzeigen",
    })

@login_required
@event_manager_required
@pro1_required
def add_recipe_to_shoppinglist(request, item_pk):
    item = get_object_or_404(
        ProgrammItem.objects.select_related("trip", "recipe"),
        pk=item_pk,
        trip__owner=request.org
    )

    if item.type != ProgrammItem.TYPE_MEAL or not item.recipe:
        messages.error(request, "Kein gültiges Rezept zugeordnet.")
        return redirect(request.GET.get("next", "programm", pk=item.trip.pk))

    trip = item.trip
    recipe = item.recipe

    # Personenanzahl (GET -> Fallback)
    try:
        persons = int(request.GET.get("persons", trip.total_persons()))
    except (TypeError, ValueError):
        persons = trip.total_persons()

    persons = max(persons, 1)
    weekdays = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    start_date = localtime(item.start_time)
    formatted = f"{weekdays[start_date.weekday()]}, {start_date:%d.%m.}"
    recipe_suffix = f"(Rezept: {recipe.title} für {formatted})"

    # 🔥 Alte Einträge dieses Rezepts löschen
    ShoppingListItem.objects.filter(
        trip=trip,
        name__endswith=recipe_suffix
    ).delete()

    # ➕ Neue Zutaten anlegen
    items_to_create = []
    for ing in recipe.ingredients.all():
        if ing.quantity is None:
            continue

        items_to_create.append(
            ShoppingListItem(
                trip=trip,
                name=f"{ing.name} {recipe_suffix}",
                amount=ing.quantity * persons,
                unit=ing.unit or "",
                product_group=ing.product_group if hasattr(ing, "product_group") else None
            )
        )

    ShoppingListItem.objects.bulk_create(items_to_create)

    messages.success(
        request,
        f"Zutaten aus „{recipe.title}“ zur Einkaufsliste hinzugefügt ({persons} Personen)."
    )

    # 🔹 einfach wieder zur vorherigen Seite zurück
    return redirect(request.META.get("HTTP_REFERER", request.path))

@login_required
@event_manager_required
@pro1_required
def add_accumulated_ingredients(request, pk):
    trip = get_object_or_404(Trip, pk=pk, owner=request.org)
    programm_items = list(
        trip.programm.select_related("recipe")
        .prefetch_related("recipe__ingredients")
        .filter(type=ProgrammItem.TYPE_MEAL, recipe__isnull=False)
        .order_by("start_time", "name", "pk")
    )

    weekdays = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    group_label_map = {str(group_id): label for group_id, label in ShoppingListItem.GROUPS}
    group_label_map["__none__"] = "Ohne Warengruppe"

    days = []
    day_keys_seen = set()
    programm_items_data = []
    item_meta_by_id = {}

    for item in programm_items:
        if item.start_time:
            start_local = localtime(item.start_time)
            day_key = start_local.date().isoformat()
            day_label = f"{weekdays[start_local.weekday()]}, {start_local:%d.%m.%Y}"
            time_label = start_local.strftime("%H:%M")
        else:
            day_key = "no_date"
            day_label = "Ohne Datum"
            time_label = "--:--"

        if day_key not in day_keys_seen:
            day_keys_seen.add(day_key)
            days.append({"key": day_key, "label": day_label})

        ingredient_groups = sorted(
            set(item.recipe.ingredients.values_list("product_group", flat=True)),
            key=lambda value: (value is None, value if value is not None else -1),
        )
        ingredient_groups_serialized = [
            "__none__" if group is None else str(group)
            for group in ingredient_groups
        ]

        item_label = f"{time_label} - {item.recipe.title}"
        if item.name and item.name != item.recipe.title:
            item_label = f"{item_label} ({item.name})"

        programm_items_data.append({
            "id": item.pk,
            "day_key": day_key,
            "label": item_label,
            "groups": ingredient_groups_serialized,
        })
        item_meta_by_id[item.pk] = {"day_key": day_key}

    day_label_by_key = {day["key"]: day["label"] for day in days}
    selected_day_keys_raw = request.POST.getlist("selected_days") if request.method == "POST" else []
    selected_item_ids_raw = request.POST.getlist("programm_items") if request.method == "POST" else []
    selected_group_tokens = request.POST.getlist("product_groups") if request.method == "POST" else []

    if request.method == "POST":
        selected_day_keys = [key for key in selected_day_keys_raw if key in day_label_by_key]
        valid_item_ids = []
        for raw_id in selected_item_ids_raw:
            try:
                item_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if item_id in item_meta_by_id and item_meta_by_id[item_id]["day_key"] in selected_day_keys:
                valid_item_ids.append(item_id)

        include_without_group = "__none__" in selected_group_tokens
        selected_group_ids = set()
        for token in selected_group_tokens:
            if token == "__none__":
                continue
            try:
                selected_group_ids.add(int(token))
            except (TypeError, ValueError):
                continue

        if not selected_day_keys:
            messages.error(request, "Bitte mindestens einen Tag auswählen.")
        elif not valid_item_ids:
            messages.error(request, "Bitte mindestens ein Rezept auswählen.")
        elif not selected_group_tokens:
            messages.error(request, "Bitte mindestens eine Warengruppe auswählen.")
        elif not (include_without_group or selected_group_ids):
            messages.error(request, "Die ausgewählten Warengruppen sind ungültig.")
        else:
            persons = max(trip.total_persons(), 1)
            selected_programm_items = [
                item for item in programm_items if item.pk in valid_item_ids
            ]

            recipe_suffix = "(Rezepte)"

            aggregated = defaultdict(lambda: Decimal("0"))
            meta = {}

            for program_item in selected_programm_items:
                for ingredient in program_item.recipe.ingredients.all():
                    if ingredient.quantity is None:
                        continue
                    if ingredient.product_group is None and not include_without_group:
                        continue
                    if ingredient.product_group is not None and ingredient.product_group not in selected_group_ids:
                        continue

                    ingredient_name = ingredient.name.strip()
                    ingredient_unit = (ingredient.unit or "").strip()
                    key = (ingredient_name, ingredient_unit, ingredient.product_group)
                    aggregated[key] += ingredient.quantity * persons

                    ingredient_label = ingredient_name
                    if len(ingredient_label) > 188:
                        ingredient_label = f"{ingredient_label[:187]}…"
                    item_name = f"{ingredient_label} {recipe_suffix}"

                    meta[key] = {
                        "name": item_name,
                        "unit": ingredient_unit,
                        "group": ingredient.product_group,
                    }

            if not aggregated:
                messages.warning(request, "Für diese Auswahl wurden keine passenden Zutaten gefunden.")
                return redirect("programm", pk=trip.pk)

            ShoppingListItem.objects.filter(
                trip=trip,
                name__endswith=recipe_suffix,
            ).delete()

            created_count = 0
            for key, amount in aggregated.items():
                item_info = meta[key]
                ShoppingListItem.objects.create(
                    trip=trip,
                    name=item_info["name"],
                    amount=amount,
                    unit=item_info["unit"],
                    product_group=item_info["group"],
                )
                created_count += 1

            messages.success(
                request,
                f"{created_count} Zutatenpositionen zur Einkaufsliste übernommen."
            )
            return redirect("programm", pk=trip.pk)

    return render(request, "events/add_accumulated_ingredients.html", {
        "title": "Rezept-Zutaten bündeln & zur Einkaufsliste hinzufügen",
        "trip": trip,
        "days": days,
        "programm_items_data": programm_items_data,
        "group_labels": group_label_map,
        "selected_day_keys": selected_day_keys_raw,
        "selected_item_ids": [str(item_id) for item_id in selected_item_ids_raw],
        "selected_group_tokens": selected_group_tokens,
    })
