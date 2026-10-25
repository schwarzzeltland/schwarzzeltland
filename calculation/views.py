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
from .forms import CalculationEducationSessionForm, CalculationIncomeLineForm, CalculationLineForm, EventCalculationForm, SubsidyProfileForm
from .models import CalculationEducationSession, CalculationIncomeLine, CalculationLine, EventCalculation, SubsidyProfile


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
    gross_income = calculation.total_participants * calculation.participant_fee
    income = gross_income - discounts
    guest_subsidies = calculation.guest_count * calculation.guest_subsidy_per_person
    return calculation.eligible_participants, gross_income, income, discounts, guest_subsidies


def _line_amount(line, amount, participant_count, event_days):
    if line.calculation_mode == CalculationLine.MODE_PER_PERSON:
        return amount * participant_count
    if line.calculation_mode == CalculationLine.MODE_PER_PERSON_DAY:
        return amount * participant_count * event_days
    return amount


def _money(amount):
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _category_key(category):
    return " ".join(category.casefold().split())


def _actual_costs_by_category(trip):
    amounts = {}
    entries = CashBookEntry.objects.filter(
        cashbook__organization=trip.owner, trip=trip, entry_type=CashBookEntry.TYPE_EXPENSE,
    ).exclude(category="").exclude(settlement_metadata__eligible=False).exclude(advance_budget_payment__isnull=False).exclude(advance_budget_settlement__isnull=False).exclude(event_expense__eligible=False)
    for entry in entries:
        key = _category_key(entry.category)
        amounts[key] = amounts.get(key, Decimal("0")) + entry.amount
    expenses = EventExpense.objects.filter(trip=trip, cashbook_entry__isnull=True, eligible=True).exclude(
        status=EventExpense.STATUS_REJECTED,
    ).exclude(category="")
    for expense in expenses:
        key = _category_key(expense.category)
        amounts[key] = amounts.get(key, Decimal("0")) + expense.amount
    return amounts


def _actual_incomes_by_category(trip):
    amounts = {}
    entries = CashBookEntry.objects.filter(
        cashbook__organization=trip.owner, trip=trip, entry_type=CashBookEntry.TYPE_INCOME,
    ).exclude(category="").exclude(advance_budget_settlement__isnull=False)
    for entry in entries:
        key = _category_key(entry.category)
        amounts[key] = amounts.get(key, Decimal("0")) + entry.amount
    return amounts


def _cost_line_rows(calculation, total_people, actual_by_category):
    rows, assigned_categories = [], set()
    for line in calculation.lines.all():
        key = _category_key(line.category)
        automatic = line.actual_amount is None and key in actual_by_category
        grouped = automatic and key in assigned_categories
        if automatic:
            assigned_categories.add(key)
        rows.append({
            "line": line,
            "planned_total": _line_amount(line, line.planned_amount, total_people, calculation.event_days),
            "actual_total": _line_amount(line, line.actual_amount, total_people, calculation.event_days) if line.actual_amount is not None else (Decimal("0") if grouped else actual_by_category.get(key, Decimal("0"))),
            "actual_is_automatic": automatic and not grouped,
            "actual_is_grouped": grouped,
        })
    return rows


def _income_line_rows(calculation, actual_by_category):
    rows, assigned_categories = [], set()
    for income in calculation.income_lines.all():
        key = _category_key(income.category)
        automatic = income.actual_amount is None and key in actual_by_category
        grouped = automatic and key in assigned_categories
        if automatic:
            assigned_categories.add(key)
        rows.append({
            "income": income,
            "actual_total": income.actual_amount if income.actual_amount is not None else (Decimal("0") if grouped else actual_by_category.get(key, Decimal("0"))),
            "actual_is_automatic": automatic and not grouped,
            "actual_is_grouped": grouped,
        })
    return rows


def _group_cost_rows(line_rows, actual_by_category):
    groups = []
    groups_by_category = {}
    for row in line_rows:
        key = _category_key(row["line"].category)
        group = groups_by_category.get(key)
        if group is None:
            group = {"category": row["line"].category, "rows": [], "planned_total": Decimal("0"), "actual_total": Decimal("0"), "automatic_total": Decimal("0"), "manual_total": Decimal("0"), "has_actual": False}
            groups_by_category[key] = group
            groups.append(group)
        group["rows"].append(row)
        group["planned_total"] += row["planned_total"]
        if row["line"].actual_amount is not None or row["actual_is_automatic"] or row["actual_is_grouped"]:
            group["has_actual"] = True
        group["actual_total"] += row["actual_total"]
        if row["line"].actual_amount is not None:
            group["manual_total"] += row["actual_total"]
        elif row["actual_is_automatic"]:
            group["automatic_total"] += row["actual_total"]
    for category_key, amount in actual_by_category.items():
        if category_key in groups_by_category:
            continue
        category = category_key or "Sonstige Ausgaben"
        group = {
            "category": category,
            "rows": [],
            "planned_total": Decimal("0"),
            "actual_total": _money(amount),
            "automatic_total": _money(amount),
            "manual_total": Decimal("0"),
            "has_actual": True,
            "automatic_only": True,
        }
        groups_by_category[category_key] = group
        groups.append(group)
    return groups


def _group_income_rows(income_rows, actual_by_category):
    groups = []
    groups_by_category = {}
    for row in income_rows:
        category = row["income"].category or "Sonstige Einnahmen"
        key = _category_key(category)
        group = groups_by_category.get(key)
        if group is None:
            group = {"category": category, "rows": [], "planned_total": Decimal("0"), "actual_total": Decimal("0"), "has_actual": False}
            groups_by_category[key] = group
            groups.append(group)
        group["rows"].append(row)
        group["planned_total"] += _money(row["income"].planned_amount)
        if row["income"].actual_amount is not None or row["actual_is_automatic"]:
            group["actual_total"] += _money(row["actual_total"])
            group["has_actual"] = True
    for category_key, amount in actual_by_category.items():
        if category_key in groups_by_category or category_key == _category_key("TN-Beitrag"):
            continue
        category = category_key or "Sonstige Einnahmen"
        group = {"category": category, "rows": [], "planned_total": Decimal("0"), "actual_total": _money(amount), "has_actual": True, "automatic_only": True}
        groups_by_category[category_key] = group
        groups.append(group)
    return groups


def _values(calculation, trip, use_cashbook):
    profile, submitted = calculation.profile, calculation.documents_received_at
    full_deadline = trip.end_date.date() + timedelta(days=profile.full_rate_days)
    reduced_deadline = trip.end_date.date() + timedelta(days=profile.reduced_rate_days)
    factor = Decimal("1") if not submitted or submitted <= full_deadline else profile.reduced_rate_factor if submitted <= reduced_deadline else profile.late_rate_factor
    eligible_count, participant_income_gross, participant_income, leader_discounts, guest_subsidies = _participant_values(calculation)
    manual_education_hours = calculation.education_sessions.aggregate(total=Sum("hours"))["total"] or Decimal("0")
    education_hours = calculation.education_hours + manual_education_hours
    base = eligible_count * (calculation.event_days * profile.rate_per_person_day + education_hours * profile.rate_per_person_hour) * factor
    total_people = calculation.total_participants
    all_lines = calculation.lines.all()
    eligible_lines = all_lines.filter(eligible=True)
    planned = sum((_line_amount(line, line.planned_amount, total_people, calculation.event_days) for line in eligible_lines), Decimal("0"))
    planned_total_costs = sum((_line_amount(line, line.planned_amount, total_people, calculation.event_days) for line in all_lines), Decimal("0"))
    actual_by_category = _actual_costs_by_category(trip) if use_cashbook else {}
    actual_incomes_by_category = _actual_incomes_by_category(trip) if use_cashbook else {}
    planned_category_keys = {_category_key(line.category) for line in all_lines}

    def actual_costs_for(lines, include_unplanned=False):
        assigned_categories = set()
        amount = Decimal("0")
        for line in lines:
            if line.actual_amount is not None:
                amount += _line_amount(line, line.actual_amount, total_people, calculation.event_days)
                continue
            category_key = _category_key(line.category)
            if category_key not in assigned_categories:
                amount += actual_by_category.get(category_key, Decimal("0"))
                assigned_categories.add(category_key)
        if include_unplanned:
            amount += sum((value for key, value in actual_by_category.items() if key not in planned_category_keys), Decimal("0"))
        return amount

    manual_actual = actual_costs_for(eligible_lines, include_unplanned=True)
    actual_total_costs = actual_costs_for(all_lines, include_unplanned=True)
    booked = sum(actual_by_category.values(), Decimal("0")) if use_cashbook else Decimal("0")
    booked_income = sum(actual_incomes_by_category.values(), Decimal("0")) if use_cashbook else calculation.actual_income_manual or Decimal("0")
    actual = calculation.actual_eligible_costs_override if calculation.actual_eligible_costs_override is not None else manual_actual
    manual_planned_income = calculation.income_lines.aggregate(total=Sum("planned_amount"))["total"] or Decimal("0")
    planned_subsidy = max(Decimal("0"), min(base, planned * profile.maximum_cost_share) - calculation.other_subsidies)
    actual_subsidy = max(Decimal("0"), min(base, actual * profile.maximum_cost_share) - calculation.other_subsidies)
    minimum_participants_met = eligible_count >= profile.minimum_eligible_participants
    minimum_days_met = (calculation.is_education_or_qs and profile.education_qs_exempt_from_minimum_days) or calculation.event_days >= profile.minimum_event_days
    requirements_met = minimum_participants_met and minimum_days_met
    if not requirements_met:
        planned_subsidy = Decimal("0")
        actual_subsidy = Decimal("0")
    return {"planned_costs": _money(planned), "planned_total_costs": _money(planned_total_costs), "actual_costs": _money(actual_total_costs), "actual_eligible_costs": _money(actual), "booked_costs": _money(booked), "booked_income": _money(booked_income), "participant_income_actual": _money(actual_incomes_by_category.get(_category_key("TN-Beitrag"), Decimal("0"))), "total_people": total_people, "education_hours": education_hours, "eligible_count": eligible_count, "leader_discounts": _money(leader_discounts), "guest_subsidies": _money(guest_subsidies), "participant_income_gross": _money(participant_income_gross), "participant_income": _money(participant_income), "manual_planned_income": _money(manual_planned_income), "planned_income_total": _money(participant_income + guest_subsidies + manual_planned_income), "planned_result": _money(participant_income + guest_subsidies + manual_planned_income + planned_subsidy - planned_total_costs), "actual_result": _money(booked_income + actual_subsidy - actual_total_costs), "base_subsidy": _money(base), "planned_subsidy": _money(planned_subsidy), "actual_subsidy": _money(actual_subsidy), "requirements": {"met": requirements_met, "minimum_participants_met": minimum_participants_met, "minimum_days_met": minimum_days_met, "minimum_participants": profile.minimum_eligible_participants, "minimum_days": profile.minimum_event_days}, "full_deadline": full_deadline, "reduced_deadline": reduced_deadline}


@login_required
@pro7_required
def calculation_category_autocomplete(request):
    query = request.GET.get("q", "").strip().casefold()
    calculation_categories = CalculationLine.objects.filter(
        calculation__trip__owner=request.org,
    ).exclude(category="").values_list("category", flat=True)
    income_categories = CalculationIncomeLine.objects.filter(
        calculation__trip__owner=request.org,
    ).exclude(category="").values_list("category", flat=True)
    cashbook_categories = CashBookEntry.objects.filter(cashbook__organization=request.org).exclude(category="").values_list("category", flat=True)
    expense_categories = EventExpense.objects.filter(trip__owner=request.org).exclude(category="").values_list("category", flat=True)
    suggestions_by_key = {}
    for category in (*calculation_categories, *income_categories, *cashbook_categories, *expense_categories):
        suggestions_by_key.setdefault(_category_key(category), category)
    suggestions = sorted(suggestions_by_key.values(), key=str.casefold)
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
    if request.method == "POST":
        if "sync_event_data" in request.POST:
            _apply_event_data(calculation, trip, program_education_hours)
            return redirect("calculation_detail", trip_pk=trip.pk)
        if "save_calculation" in request.POST:
            form = EventCalculationForm(request.POST, instance=calculation, organization=request.org)
            if form.is_valid(): form.save(); return redirect("calculation_detail", trip_pk=trip.pk)
        elif "income_form" in request.POST:
            income_form = CalculationIncomeLineForm(request.POST)
            if income_form.is_valid():
                income = income_form.save(commit=False); income.calculation = calculation; income.save()
                return redirect("calculation_detail", trip_pk=trip.pk)
        else:
            line_form = CalculationLineForm(request.POST)
            if line_form.is_valid():
                line = line_form.save(commit=False); line.calculation = calculation; line.save()
                return redirect("calculation_detail", trip_pk=trip.pk)
    program_education_items = trip.programm.filter(education_hours__gt=0).order_by("start_time", "name") if request.org.pro4 else []
    values = _values(calculation, trip, request.org.pro5)
    actual_by_category = _actual_costs_by_category(trip) if request.org.pro5 else {}
    line_rows = _cost_line_rows(calculation, values["total_people"], actual_by_category)
    cost_groups = _group_cost_rows(line_rows, actual_by_category)
    actual_incomes_by_category = _actual_incomes_by_category(trip) if request.org.pro5 else {}
    income_rows = _income_line_rows(calculation, actual_incomes_by_category)
    income_groups = _group_income_rows(income_rows, actual_incomes_by_category)
    return render(request, "calculation/calculation_detail.html", {"trip": trip, "form": EventCalculationForm(instance=calculation, organization=request.org), "line_form": CalculationLineForm(), "income_form": CalculationIncomeLineForm(), "calculation": calculation, "program_education_hours": program_education_hours, "program_education_items": program_education_items, "line_rows": line_rows, "cost_groups": cost_groups, "income_rows": income_rows, "income_groups": income_groups, "values": values, "is_event_manager": request.user.membership_set.filter(organization=request.org, event_manager=True).exists()})


@login_required
@pro7_required
def calculation_income_delete(request, trip_pk, pk):
    income = get_object_or_404(CalculationIncomeLine, pk=pk, calculation__trip_id=trip_pk, calculation__trip__owner=request.org)
    if not _can_manage_calculation(request):
        raise PermissionDenied
    if request.method == "POST":
        income.delete()
    return redirect("calculation_detail", trip_pk=trip_pk)


@login_required
@pro7_required
def calculation_income_edit(request, trip_pk, pk):
    income = get_object_or_404(CalculationIncomeLine, pk=pk, calculation__trip_id=trip_pk, calculation__trip__owner=request.org)
    if not _can_manage_calculation(request):
        raise PermissionDenied
    form = CalculationIncomeLineForm(request.POST or None, instance=income)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("calculation_detail", trip_pk=trip_pk)
    return render(request, "calculation/calculation_income_form.html", {"form": form, "trip": income.calculation.trip, "income": income})


@login_required
def calculation_export_pdf(request, trip_pk, report_type):
    from events.models import Trip

    if report_type not in {"planning", "actual", "settlement"}:
        raise PermissionDenied
    trip = get_object_or_404(Trip, pk=trip_pk, owner=request.org)
    if report_type == "settlement":
        membership = request.user.membership_set.filter(organization=request.org).first()
        if not request.org.pro5 or not membership or not (membership.admin or membership.cashier_manager or membership.event_manager):
            raise PermissionDenied
        direct_entries = CashBookEntry.objects.filter(
            cashbook__organization=request.org,
            trip=trip,
            entry_type=CashBookEntry.TYPE_EXPENSE,
            event_expense__isnull=True,
        ).exclude(advance_budget_payment__isnull=False).exclude(advance_budget_settlement__isnull=False).select_related("cashbook")
        settlement_rows = [
            {
                "date": entry.booking_date,
                "title": entry.title,
                "category": entry.category,
                "description": entry.description,
                "amount": entry.amount,
                "booking": f"Kassenbuch #{entry.entry_number or '–'}",
            }
            for entry in direct_entries
        ]
        for expense in trip.event_expenses.exclude(status=EventExpense.STATUS_REJECTED).select_related("cashbook", "advance_budget__cashbook", "cashbook_entry"):
            cashbook = expense.cashbook or expense.advance_budget.cashbook
            booking = f"Kassenbuch #{expense.cashbook_entry.entry_number}" if expense.cashbook_entry_id else ("Vorschussbudget" if expense.advance_budget_id else expense.get_status_display())
            settlement_rows.append({
                "date": expense.expense_date,
                "title": expense.title,
                "category": expense.category,
                "description": expense.description,
                "amount": expense.amount,
                "booking": booking,
            })
        settlement_rows.sort(key=lambda row: (row["date"], row["title"] or ""))
        settlement_total = sum((row["amount"] for row in settlement_rows), Decimal("0"))
        context = {"trip": trip, "settlement_rows": settlement_rows, "settlement_total": settlement_total}
        try:
            from weasyprint import CSS, HTML
            html = render_to_string("calculation/pdf/settlement_export.html", context, request=request)
            pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf(stylesheets=[CSS(string="""
                @page { size: A4; margin: 12mm; }
                body { font-family: sans-serif; font-size: 10px; color: #111827; }
                h1 { margin: 0 0 2mm; font-size: 18px; } table { width: 100%; border-collapse: collapse; margin-top: 5mm; }
                th, td { border: 1px solid #d1d5db; padding: 2mm; text-align: left; } th { background: #f3f4f6; } .number { text-align: right; } .muted { color: #6b7280; }
            """)])
        except (ImportError, OSError):
            from cashbook.views import _build_text_pdf
            lines = [f"Veranstaltung: {trip.name}", f"Zeitraum: {trip.start_date:%d.%m.%Y} - {trip.end_date:%d.%m.%Y}", ""]
            lines.extend(f"{row['date']:%d.%m.%Y} | {row['title']} | {row['category']} | {row['description']} | {row['amount']:.2f} EUR | {row['booking']}" for row in settlement_rows)
            lines.extend(["", f"Gesamtsumme: {settlement_total:.2f} EUR"])
            pdf = _build_text_pdf("Abrechnung", lines)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{slugify(trip.name) or trip.pk}-abrechnung.pdf"'
        return response

    if not request.org.pro7 or not _can_manage_calculation(request):
        raise PermissionDenied
    calculation = get_object_or_404(EventCalculation, trip=trip)
    values = _values(calculation, trip, request.org.pro5)
    actual_by_category = _actual_costs_by_category(trip) if request.org.pro5 else {}
    line_rows = _cost_line_rows(calculation, values["total_people"], actual_by_category)
    cost_groups = _group_cost_rows(line_rows, actual_by_category)
    actual_incomes_by_category = _actual_incomes_by_category(trip) if request.org.pro5 else {}
    income_rows = _income_line_rows(calculation, actual_incomes_by_category)
    income_groups = _group_income_rows(income_rows, actual_incomes_by_category)
    is_actual = report_type == "actual"
    context = {"trip": trip, "calculation": calculation, "values": values, "line_rows": line_rows, "cost_groups": cost_groups, "income_groups": income_groups, "is_actual": is_actual}
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
        for group in cost_groups:
            amount = group["actual_total"] if is_actual else group["planned_total"]
            lines.append(f"{group['category']}: {amount:.2f} EUR")
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
def calculation_education_delete(request, trip_pk, pk):
    calculation = _calculation_detail_object(request, trip_pk)
    session = get_object_or_404(CalculationEducationSession, pk=pk, calculation=calculation)
    if request.method == "POST":
        session.delete()
    return redirect("calculation_detail", trip_pk=trip_pk)


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
