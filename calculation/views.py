from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.text import slugify

from cashbook.models import CashBookEntry, EventExpense
from main.decorators import pro7_required
from .forms import CalculationEducationSessionForm, CalculationLineForm, CalculationParticipantGroupForm, EventCalculationForm, SubsidyProfileForm
from .models import CalculationEducationSession, CalculationLine, CalculationParticipantGroup, EventCalculation, SubsidyProfile


def _default_profile(organization):
    return SubsidyProfile.objects.get_or_create(organization=organization, name="VCP Nordrhein 2026", defaults={"registration_deadline": "2026-04-01", "notes": "Vorbelegt nach Zuschussbrief VCP Nordrhein 2026. Werte und Fristen bitte bei abweichender Fördergrundlage anpassen."})[0]


DEFAULT_COST_CATEGORIES = ("Essen", "Platz", "Transport", "Sonstiges")


def _can_manage_calculation(request):
    membership = request.user.membership_set.filter(organization=request.org).first()
    return membership and (membership.admin or membership.cashier_manager or membership.event_manager)


def _apply_event_data(calculation, trip, program_education_hours):
    calculation.eligible_participants = trip.total_persons()
    calculation.total_participants = trip.total_persons()
    calculation.event_days = max(1, (trip.end_date.date() - trip.start_date.date()).days + 1)
    if trip.owner.pro4:
        calculation.education_hours = program_education_hours
    calculation.save(update_fields=["eligible_participants", "total_participants", "event_days", "education_hours"])


def _ensure_default_cost_lines(calculation):
    existing_categories = set(calculation.lines.values_list("category", flat=True))
    CalculationLine.objects.bulk_create([
        CalculationLine(calculation=calculation, category=category)
        for category in DEFAULT_COST_CATEGORIES if category not in existing_categories
    ])


def _participant_values(calculation):
    discounts = calculation.leader_count * calculation.leader_discount_per_person
    income = calculation.total_participants * calculation.participant_fee - discounts
    guest_subsidies = calculation.guest_count * calculation.guest_subsidy_per_person
    return calculation.eligible_participants, income, discounts, guest_subsidies


def _line_amount(line, amount, participant_count, event_days):
    if line.calculation_mode == CalculationLine.MODE_PER_PERSON:
        return amount * participant_count
    if line.calculation_mode == CalculationLine.MODE_PER_PERSON_DAY:
        return amount * participant_count * event_days
    return amount


def _money(amount):
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _category_key(category):
    return " ".join(category.casefold().split())


def _actual_costs_by_category(trip):
    amounts = {}
    entries = CashBookEntry.objects.filter(
        cashbook__organization=trip.owner, trip=trip, entry_type=CashBookEntry.TYPE_EXPENSE,
    ).exclude(category="")
    for entry in entries:
        key = _category_key(entry.category)
        amounts[key] = amounts.get(key, Decimal("0")) + entry.amount
    expenses = EventExpense.objects.filter(trip=trip, cashbook_entry__isnull=True).exclude(
        status=EventExpense.STATUS_REJECTED,
    ).exclude(category="")
    for expense in expenses:
        key = _category_key(expense.category)
        amounts[key] = amounts.get(key, Decimal("0")) + expense.amount
    return amounts


def _values(calculation, trip, use_cashbook):
    profile, submitted = calculation.profile, calculation.documents_received_at
    full_deadline = trip.end_date.date() + timedelta(days=profile.full_rate_days)
    reduced_deadline = trip.end_date.date() + timedelta(days=profile.reduced_rate_days)
    factor = Decimal("1") if not submitted or submitted <= full_deadline else profile.reduced_rate_factor if submitted <= reduced_deadline else profile.late_rate_factor
    eligible_count, participant_income, leader_discounts, guest_subsidies = _participant_values(calculation)
    manual_education_hours = calculation.education_sessions.aggregate(total=Sum("hours"))["total"] or Decimal("0")
    education_hours = calculation.education_hours + manual_education_hours
    base = eligible_count * (calculation.event_days * profile.rate_per_person_day + education_hours * profile.rate_per_person_hour) * factor
    total_people = calculation.total_participants
    eligible_lines = calculation.lines.filter(eligible=True)
    planned = sum((_line_amount(line, line.planned_amount, total_people, calculation.event_days) for line in eligible_lines), Decimal("0"))
    actual_by_category = _actual_costs_by_category(trip) if use_cashbook else {}
    manual_actual = sum((
        _line_amount(line, line.actual_amount, total_people, calculation.event_days) if line.actual_amount is not None
        else actual_by_category.get(_category_key(line.category), Decimal("0"))
        for line in eligible_lines
    ), Decimal("0"))
    booked = sum(actual_by_category.values(), Decimal("0")) if use_cashbook else Decimal("0")
    booked_income = CashBookEntry.objects.filter(cashbook__organization=trip.owner, trip=trip, entry_type=CashBookEntry.TYPE_INCOME).aggregate(total=Sum("amount"))["total"] or Decimal("0") if use_cashbook else calculation.actual_income_manual or Decimal("0")
    actual = calculation.actual_eligible_costs_override if calculation.actual_eligible_costs_override is not None else manual_actual
    planned_subsidy = max(Decimal("0"), min(base, planned * profile.maximum_cost_share) - calculation.other_subsidies)
    actual_subsidy = max(Decimal("0"), min(base, actual * profile.maximum_cost_share) - calculation.other_subsidies)
    minimum_participants_met = eligible_count >= profile.minimum_eligible_participants
    minimum_days_met = (calculation.is_education_or_qs and profile.education_qs_exempt_from_minimum_days) or calculation.event_days >= profile.minimum_event_days
    requirements_met = minimum_participants_met and minimum_days_met
    if not requirements_met:
        planned_subsidy = Decimal("0")
        actual_subsidy = Decimal("0")
    return {"planned_costs": _money(planned), "actual_costs": _money(actual), "booked_costs": _money(booked), "booked_income": _money(booked_income), "total_people": total_people, "education_hours": education_hours, "eligible_count": eligible_count, "leader_discounts": _money(leader_discounts), "guest_subsidies": _money(guest_subsidies), "participant_income": _money(participant_income), "planned_result": _money(participant_income + guest_subsidies + planned_subsidy - planned), "actual_result": _money(booked_income + actual_subsidy - actual), "base_subsidy": _money(base), "planned_subsidy": _money(planned_subsidy), "actual_subsidy": _money(actual_subsidy), "requirements": {"met": requirements_met, "minimum_participants_met": minimum_participants_met, "minimum_days_met": minimum_days_met, "minimum_participants": profile.minimum_eligible_participants, "minimum_days": profile.minimum_event_days}, "full_deadline": full_deadline, "reduced_deadline": reduced_deadline}


@login_required
@pro7_required
def calculation_category_autocomplete(request):
    query = request.GET.get("q", "").strip().casefold()
    calculation_categories = CalculationLine.objects.filter(
        calculation__trip__owner=request.org,
    ).exclude(category="").values_list("category", flat=True)
    cashbook_categories = CashBookEntry.objects.filter(cashbook__organization=request.org).exclude(category="").values_list("category", flat=True)
    expense_categories = EventExpense.objects.filter(trip__owner=request.org).exclude(category="").values_list("category", flat=True)
    suggestions = sorted(set(calculation_categories).union(cashbook_categories, expense_categories), key=str.casefold)
    if query:
        suggestions = [category for category in suggestions if query in category.casefold()]
    return JsonResponse(suggestions[:20], safe=False)


@login_required
@pro7_required
def calculation_list(request):
    from events.models import Trip
    membership = request.user.membership_set.filter(organization=request.org).first()
    if not membership or not (membership.event_manager or membership.cashier_manager):
        raise PermissionDenied
    return render(request, "calculation/calculation_list.html", {
        "trips": Trip.objects.filter(owner=request.org).order_by("-start_date"),
    })


@login_required
@pro7_required
def calculation_detail(request, trip_pk):
    from events.models import Trip
    trip = get_object_or_404(Trip, pk=trip_pk, owner=request.org)
    if not _can_manage_calculation(request):
        raise PermissionDenied
    program_education_hours = (
        trip.programm.aggregate(total=Sum("education_hours"))["total"] or Decimal("0")
        if request.org.pro4 else Decimal("0")
    )
    calculation, created = EventCalculation.objects.get_or_create(trip=trip, defaults={"profile": _default_profile(request.org), "event_days": max(1, (trip.end_date.date() - trip.start_date.date()).days + 1), "eligible_participants": trip.total_persons(), "total_participants": trip.total_persons(), "education_hours": program_education_hours})
    if created or not calculation.lines.exists():
        _ensure_default_cost_lines(calculation)
    if request.method == "POST":
        if "sync_event_data" in request.POST:
            _apply_event_data(calculation, trip, program_education_hours)
            return redirect("calculation_detail", trip_pk=trip.pk)
        if "save_calculation" in request.POST:
            form = EventCalculationForm(request.POST, instance=calculation, organization=request.org)
            if form.is_valid(): form.save(); return redirect("calculation_detail", trip_pk=trip.pk)
        else:
            line_form = CalculationLineForm(request.POST)
            if line_form.is_valid():
                line = line_form.save(commit=False); line.calculation = calculation; line.save()
                return redirect("calculation_detail", trip_pk=trip.pk)
    program_education_items = trip.programm.filter(education_hours__gt=0).order_by("start_time", "name") if request.org.pro4 else []
    values = _values(calculation, trip, request.org.pro5)
    actual_by_category = _actual_costs_by_category(trip) if request.org.pro5 else {}
    line_rows = [{"line": line, "planned_total": _line_amount(line, line.planned_amount, values["total_people"], calculation.event_days), "actual_total": _line_amount(line, line.actual_amount, values["total_people"], calculation.event_days) if line.actual_amount is not None else actual_by_category.get(_category_key(line.category), Decimal("0")), "actual_is_automatic": line.actual_amount is None and _category_key(line.category) in actual_by_category} for line in calculation.lines.all()]
    return render(request, "calculation/calculation_detail.html", {"trip": trip, "form": EventCalculationForm(instance=calculation, organization=request.org), "line_form": CalculationLineForm(), "calculation": calculation, "program_education_hours": program_education_hours, "program_education_items": program_education_items, "line_rows": line_rows, "values": values, "is_event_manager": request.user.membership_set.filter(organization=request.org, event_manager=True).exists()})


@login_required
@pro7_required
def calculation_export_pdf(request, trip_pk, report_type):
    from events.models import Trip

    if report_type not in {"planning", "actual"}:
        raise PermissionDenied
    trip = get_object_or_404(Trip, pk=trip_pk, owner=request.org)
    if not _can_manage_calculation(request):
        raise PermissionDenied
    calculation = get_object_or_404(EventCalculation, trip=trip)
    values = _values(calculation, trip, request.org.pro5)
    actual_by_category = _actual_costs_by_category(trip) if request.org.pro5 else {}
    line_rows = [{
        "line": line,
        "planned_total": _line_amount(line, line.planned_amount, values["total_people"], calculation.event_days),
        "actual_total": _line_amount(line, line.actual_amount, values["total_people"], calculation.event_days) if line.actual_amount is not None else actual_by_category.get(_category_key(line.category), Decimal("0")),
        "actual_is_automatic": line.actual_amount is None and _category_key(line.category) in actual_by_category,
    } for line in calculation.lines.all()]
    is_actual = report_type == "actual"
    context = {"trip": trip, "calculation": calculation, "values": values, "line_rows": line_rows, "is_actual": is_actual}
    try:
        from weasyprint import CSS, HTML
        html = render_to_string("calculation/pdf/calculation_export.html", context, request=request)
        pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf(stylesheets=[CSS(string="""
            @page { size: A4; margin: 12mm; }
            body { font-family: sans-serif; font-size: 10px; color: #111827; }
            h1 { margin: 0 0 2mm; font-size: 18px; } h2 { margin: 6mm 0 2mm; font-size: 13px; }
            table { width: 100%; border-collapse: collapse; margin: 2mm 0 4mm; }
            th, td { border: 1px solid #d1d5db; padding: 2mm; text-align: left; vertical-align: top; }
            th { background: #f3f4f6; } .number { text-align: right; } .summary td { border: 0; padding: 1mm 2mm; }
            .result { font-size: 13px; font-weight: bold; } .muted { color: #6b7280; }
        """)])
    except (ImportError, OSError):
        from cashbook.views import _build_text_pdf
        lines = [f"Veranstaltung: {trip.name}", f"Zeitraum: {trip.start_date:%d.%m.%Y} - {trip.end_date:%d.%m.%Y}", ""]
        for row in line_rows:
            amount = row["actual_total"] if is_actual else row["planned_total"]
            lines.append(f"{row['line'].category}: {amount:.2f} EUR")
        lines.extend(["", f"Förderfähige Kosten: {(values['actual_costs'] if is_actual else values['planned_costs']):.2f} EUR", f"Zuschuss: {(values['actual_subsidy'] if is_actual else values['planned_subsidy']):.2f} EUR", f"Ergebnis: {(values['actual_result'] if is_actual else values['planned_result']):.2f} EUR"])
        pdf = _build_text_pdf("Nachkalkulation" if is_actual else "Kalkulation", lines)
    response = HttpResponse(pdf, content_type="application/pdf")
    suffix = "nachkalkulation" if is_actual else "kalkulation"
    response["Content-Disposition"] = f'attachment; filename="{slugify(trip.name) or trip.pk}-{suffix}.pdf"'
    return response


@login_required
@pro7_required
def calculation_line_delete(request, trip_pk, pk):
    line = get_object_or_404(CalculationLine, pk=pk, calculation__trip_id=trip_pk, calculation__trip__owner=request.org)
    if not _can_manage_calculation(request):
        raise PermissionDenied
    if request.method == "POST": line.delete()
    return redirect("calculation_detail", trip_pk=trip_pk)


@login_required
@pro7_required
def calculation_line_edit(request, trip_pk, pk):
    line = get_object_or_404(CalculationLine, pk=pk, calculation__trip_id=trip_pk, calculation__trip__owner=request.org)
    if not _can_manage_calculation(request):
        raise PermissionDenied
    form = CalculationLineForm(request.POST or None, instance=line)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("calculation_detail", trip_pk=trip_pk)
    return render(request, "calculation/calculation_line_form.html", {"form": form, "trip": line.calculation.trip, "line": line})


@login_required
@pro7_required
def calculation_participant_group_edit(request, trip_pk, pk=None):
    calculation = get_object_or_404(EventCalculation, trip_id=trip_pk, trip__owner=request.org)
    if not _can_manage_calculation(request):
        raise PermissionDenied
    group = get_object_or_404(CalculationParticipantGroup, pk=pk, calculation=calculation) if pk else None
    form = CalculationParticipantGroupForm(request.POST or None, instance=group)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.calculation = calculation
        item.save()
        return redirect("calculation_detail", trip_pk=trip_pk)
    return render(request, "calculation/participant_group_form.html", {"form": form, "trip": calculation.trip, "group": group})


@login_required
@pro7_required
def calculation_participant_group_delete(request, trip_pk, pk):
    group = get_object_or_404(CalculationParticipantGroup, pk=pk, calculation__trip_id=trip_pk, calculation__trip__owner=request.org)
    if not _can_manage_calculation(request):
        raise PermissionDenied
    if request.method == "POST":
        group.delete()
    return redirect("calculation_detail", trip_pk=trip_pk)


def _calculation_detail_object(request, trip_pk):
    calculation = get_object_or_404(EventCalculation, trip_id=trip_pk, trip__owner=request.org)
    if not _can_manage_calculation(request):
        raise PermissionDenied
    return calculation


@login_required
@pro7_required
def calculation_education_edit(request, trip_pk, pk=None):
    calculation = _calculation_detail_object(request, trip_pk)
    item = get_object_or_404(CalculationEducationSession, pk=pk, calculation=calculation) if pk else None
    form = CalculationEducationSessionForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        session = form.save(commit=False); session.calculation = calculation; session.save()
        return redirect("calculation_detail", trip_pk=trip_pk)
    return render(request, "calculation/item_form.html", {"form": form, "trip": calculation.trip, "heading": "Bildungsblock"})


@login_required
@pro7_required
def subsidy_profile_list(request):
    membership = request.user.membership_set.filter(organization=request.org).first()
    if not membership or not (membership.admin or membership.cashier_manager): raise PermissionDenied
    profile = get_object_or_404(SubsidyProfile, pk=request.GET["edit"], organization=request.org) if request.GET.get("edit") else None
    form = SubsidyProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False); item.organization = request.org; item.save()
        return redirect("subsidy_profiles")
    return render(request, "calculation/profile_list.html", {"profiles": SubsidyProfile.objects.filter(organization=request.org), "form": form, "editing_profile": profile})
