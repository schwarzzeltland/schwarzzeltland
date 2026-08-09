import csv
import io
import zipfile
import uuid
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.text import slugify
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from cashbook.forms import CashBookEntryForm, CashBookForm, ReimbursementRequestForm, ReimbursementReviewForm
from cashbook.models import CashBook, CashBookAuditLog, CashBookEntry, ReimbursementRequest
from cashbook.notifications import notify_requester_about_decision, notify_responsible_about_request
from main.decorators import cashier_manager_required, organization_admin_required, pro5_required

CASHBOOK_AUDIT_FIELDS = ["name", "description", "currency", "opening_balance", "responsible_id", "account_holder", "iban", "bic", "active"]

def _can_edit_cashbook(request, cashbook):
    membership = getattr(request, "membership", None)
    return bool(membership and membership.cashier_manager and (
        cashbook.responsible_id == membership.id or cashbook.responsible_id is None
    ))


def _can_manage_cashbook(request):
    membership = getattr(request, "membership", None)
    return bool(membership and membership.admin and membership.cashier_manager)


def _require_cashbook_editor(request, cashbook):
    if not _can_edit_cashbook(request, cashbook):
        raise PermissionDenied("Nur der verantwortliche Kassenwart darf dieses Kassenbuch bearbeiten.")


def _cashbook_running_rows(entries, opening_balance):
    balance = Decimal(opening_balance)
    rows = []
    for entry in entries:
        balance += entry.signed_amount
        rows.append((entry, balance))
    return rows, balance


def _cashbook_filter_entries(entries, request):
    search_query = request.GET.get("search", "").strip()
    selected_trip = request.GET.get("trip", "").strip()
    selected_type = request.GET.get("entry_type", "").strip()
    start_date = request.GET.get("start_date", "").strip()
    end_date = request.GET.get("end_date", "").strip()

    if search_query:
        entries = entries.filter(
            Q(title__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(category__icontains=search_query)
            | Q(counterparty__icontains=search_query)
            | Q(reference__icontains=search_query)
        )
    if selected_trip:
        entries = entries.filter(trip_id=selected_trip)
    if selected_type:
        entries = entries.filter(entry_type=selected_type)
    if start_date:
        entries = entries.filter(booking_date__gte=start_date)
    if end_date:
        entries = entries.filter(booking_date__lte=end_date)

    return entries, {
        "search_query": search_query,
        "selected_trip": selected_trip,
        "selected_type": selected_type,
        "start_date": start_date,
        "end_date": end_date,
    }


def _cashbook_audit_value(value):
    if value is None:
        return ""
    if hasattr(value, "name"):
        return value.name or ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _cashbook_snapshot(instance, fields):
    return {field: _cashbook_audit_value(getattr(instance, field)) for field in fields}


def _cashbook_changes(before, after):
    changes = {}
    for field, previous in before.items():
        current = after.get(field)
        if previous != current:
            changes[field] = {"before": previous, "after": current}
    return changes


def _create_cashbook_audit_log(*, organization, actor, target_type, action, label, cashbook=None, entry=None, changes=None):
    CashBookAuditLog.objects.create(
        organization=organization,
        actor=actor,
        target_type=target_type,
        action=action,
        label=label,
        cashbook=cashbook,
        entry=entry,
        changes=changes or {},
    )


def _cashbook_audit_field_label(field):
    labels = {
        "name": "Name",
        "description": "Beschreibung",
        "currency": "Währung",
        "opening_balance": "Startsaldo",
        "active": "Aktiv",
        "entry_number": "Nummer",
        "entry_type": "Art",
        "booking_date": "Buchungsdatum",
        "receipt_date": "Belegdatum",
        "amount": "Betrag",
        "title": "Titel",
        "category": "Kategorie",
        "counterparty": "Zahlungspartner",
        "reference": "Belegnummer / Referenz",
        "attachment": "Beleg",
        "trip_id": "Veranstaltung",
    }
    return labels.get(field, field)


def _cashbook_audit_lines(audit_log):
    lines = []
    for field, values in audit_log.changes.items():
        label = _cashbook_audit_field_label(field)
        if isinstance(values, dict) and "before" in values and "after" in values:
            before = values.get("before") or "-"
            after = values.get("after") or "-"
            lines.append(f"{label}: {before} -> {after}")
        else:
            lines.append(f"{label}: {values or '-'}")
    return lines


def _pdf_safe_text(value):
    return "-" if value in (None, "") else str(value)


def _build_text_pdf(title, lines):
    page_width, page_height = 1654, 2339
    margin = 120
    line_height = 38
    title_height = 70
    usable_height = page_height - (margin * 2) - title_height
    lines_per_page = max(1, usable_height // line_height)
    font = ImageFont.load_default()
    pages = []

    chunks = [lines[index:index + lines_per_page] for index in range(0, len(lines), lines_per_page)] or [[]]
    for page_index, chunk in enumerate(chunks):
        image = Image.new("RGB", (page_width, page_height), "white")
        draw = ImageDraw.Draw(image)
        y = margin
        if page_index == 0:
            draw.text((margin, y), title, fill="black", font=font)
            y += title_height
        for line in chunk:
            draw.text((margin, y), line, fill="black", font=font)
            y += line_height
        pages.append(image)

    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:])
    return buffer.getvalue()


def _build_cashbook_fallback_pdf(cashbook, running_rows):
    lines = []
    for entry, balance in running_rows:
        lines.extend([
            f"#{entry.entry_number} | {entry.booking_date} | {entry.get_entry_type_display()} | {_pdf_safe_text(entry.title)}",
            f"Betrag: {_pdf_safe_text(entry.signed_amount)} {cashbook.currency} | Saldo: {_pdf_safe_text(balance)} {cashbook.currency}",
            f"Kategorie: {_pdf_safe_text(entry.category)} | Zahlungspartner: {_pdf_safe_text(entry.counterparty)}",
            f"Belegdatum: {_pdf_safe_text(entry.receipt_date)} | Referenz: {_pdf_safe_text(entry.reference)} | Veranstaltung: {_pdf_safe_text(entry.trip.name if entry.trip else '')}",
            f"Beschreibung: {_pdf_safe_text(entry.description)}",
            "",
        ])
    return _build_text_pdf(f"Kassenbuch {cashbook.name}", lines or ["Keine Einträge vorhanden."])


def _build_cashbook_summary_fallback_pdf(rows):
    lines = []
    for row in rows:
        cashbook = row["cashbook"]
        lines.extend([
            cashbook.name,
            f"Währung: {cashbook.currency} | Startsaldo: {cashbook.opening_balance}",
            f"Einnahmen: {row['income_total']} | Ausgaben: {row['expense_total']} | Aktueller Saldo: {cashbook.current_balance}",
            f"Einträge: {row['entry_count']} | Aktiv: {'Ja' if cashbook.active else 'Nein'}",
            "",
        ])
    return _build_text_pdf("Kassenbuch-Übersicht", lines or ["Keine Kassenbücher vorhanden."])


def _render_pdf_response(*, request, template_name, context, filename, css):
    try:
        from weasyprint import CSS, HTML
    except (ImportError, OSError):
        fallback_pdf = context.get("fallback_pdf")
        if fallback_pdf is None:
            raise
        pdf = fallback_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    html = render_to_string(template_name, context, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf(
        stylesheets=[CSS(string=css)]
    )
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@cashier_manager_required
@pro5_required
def cashbook_category_autocomplete(request):
    query = request.GET.get("q", "").strip()
    categories = CashBookEntry.objects.filter(
        cashbook__organization=request.org
    ).exclude(category="").values_list("category", flat=True).distinct().order_by("category")
    if query:
        categories = [category for category in categories if query.lower() in category.lower()]
    else:
        categories = list(categories[:20])
    return JsonResponse(list(categories[:20]), safe=False)


@login_required
@cashier_manager_required
@pro5_required
def cashbook_list(request):
    cashbooks = CashBook.objects.filter(organization=request.org).prefetch_related("entries")
    cashbooks_with_balances = []
    for cashbook in cashbooks:
        income_total = sum(entry.amount for entry in cashbook.entries.all() if entry.entry_type == CashBookEntry.TYPE_INCOME)
        expense_total = sum(entry.amount for entry in cashbook.entries.all() if entry.entry_type == CashBookEntry.TYPE_EXPENSE)
        cashbooks_with_balances.append({
            "cashbook": cashbook,
            "income_total": income_total,
            "expense_total": expense_total,
            "current_balance": cashbook.current_balance,
            "entry_count": cashbook.entries.count(),
        })

    return render(request, "cashbook/cashbook_list.html", {
        "title": "Kassenbücher",
        "cashbooks_with_balances": cashbooks_with_balances,
    })


@login_required
@cashier_manager_required
@pro5_required
def cashbook_create(request):
    if request.method == "POST":
        form = CashBookForm(request.POST, organization=request.org)
        if form.is_valid():
            cashbook = form.save(commit=False)
            cashbook.organization = request.org
            cashbook.save()
            _create_cashbook_audit_log(
                organization=request.org,
                actor=request.user,
                target_type=CashBookAuditLog.TARGET_CASHBOOK,
                action=CashBookAuditLog.ACTION_CREATE,
                label=cashbook.name,
                cashbook=cashbook,
                changes=_cashbook_snapshot(cashbook, CASHBOOK_AUDIT_FIELDS),
            )
            messages.success(request, "Kassenbuch erstellt.")
            return redirect("cashbook_detail", pk=cashbook.pk)
    else:
        form = CashBookForm(organization=request.org)

    return render(request, "cashbook/cashbook_form.html", {
        "title": "Kassenbuch erstellen",
        "form": form,
        "cashbook": None,
    })


@login_required
@organization_admin_required
@cashier_manager_required
@pro5_required
def cashbook_edit(request, pk):
    cashbook = get_object_or_404(CashBook, pk=pk, organization=request.org)
    if request.method == "POST":
        before = _cashbook_snapshot(cashbook, CASHBOOK_AUDIT_FIELDS)
        form = CashBookForm(request.POST, instance=cashbook, organization=request.org)
        if form.is_valid():
            cashbook = form.save()
            changes = _cashbook_changes(before, _cashbook_snapshot(cashbook, CASHBOOK_AUDIT_FIELDS))
            if changes:
                _create_cashbook_audit_log(
                    organization=request.org,
                    actor=request.user,
                    target_type=CashBookAuditLog.TARGET_CASHBOOK,
                    action=CashBookAuditLog.ACTION_UPDATE,
                    label=cashbook.name,
                    cashbook=cashbook,
                    changes=changes,
                )
            messages.success(request, "Kassenbuch gespeichert.")
            return redirect("cashbook_detail", pk=cashbook.pk)
    else:
        form = CashBookForm(instance=cashbook, organization=request.org)

    return render(request, "cashbook/cashbook_form.html", {
        "title": "Kassenbuch bearbeiten",
        "form": form,
        "cashbook": cashbook,
    })


@login_required
@organization_admin_required
@cashier_manager_required
@pro5_required
def cashbook_delete(request, pk):
    cashbook = get_object_or_404(CashBook, pk=pk, organization=request.org)
    if request.method == "POST":
        _create_cashbook_audit_log(
            organization=request.org,
            actor=request.user,
            target_type=CashBookAuditLog.TARGET_CASHBOOK,
            action=CashBookAuditLog.ACTION_DELETE,
            label=cashbook.name,
            changes=_cashbook_snapshot(cashbook, CASHBOOK_AUDIT_FIELDS),
        )
        cashbook.delete()
        messages.success(request, "Kassenbuch gelöscht.")
        return redirect("cashbook_list")
    return render(request, "cashbook/cashbook_delete.html", {
        "title": "Kassenbuch löschen",
        "cashbook": cashbook,
    })


@login_required
@cashier_manager_required
@pro5_required
def cashbook_detail(request, pk):
    cashbook = get_object_or_404(CashBook, pk=pk, organization=request.org)
    all_entries = cashbook.entries.select_related("trip", "created_by").all()
    entries = all_entries
    audit_rows = [
        {
            "created_at": audit.created_at,
            "actor": audit.actor.username if audit.actor else "-",
            "action": audit.get_action_display(),
            "label": audit.label,
            "change_lines": _cashbook_audit_lines(audit),
        }
        for audit in cashbook.audit_logs.select_related("actor", "entry")[:20]
    ]

    entries, filters = _cashbook_filter_entries(entries, request)

    entries = entries.order_by("booking_date", "id")
    selection_opening_balance = cashbook.opening_balance
    first_entry = entries.first()
    if first_entry is not None:
        prior_entries = all_entries.filter(
            Q(booking_date__lt=first_entry.booking_date)
            | (Q(booking_date=first_entry.booking_date) & Q(id__lt=first_entry.id))
        )
        selection_opening_balance += sum(entry.signed_amount for entry in prior_entries)

    running_rows, _ = _cashbook_running_rows(entries, selection_opening_balance)
    filtered_balance = sum(entry.signed_amount for entry in entries)
    income_total = sum(entry.amount for entry in entries if entry.entry_type == CashBookEntry.TYPE_INCOME)
    expense_total = sum(entry.amount for entry in entries if entry.entry_type == CashBookEntry.TYPE_EXPENSE)

    return render(request, "cashbook/cashbook_detail.html", {
        "title": cashbook.name,
        "cashbook": cashbook,
        "selection_opening_balance": selection_opening_balance,
        "running_rows": running_rows,
        "income_total": income_total,
        "expense_total": expense_total,
        "filtered_balance": filtered_balance,
        **filters,
        "trip_options": request.org.trip_set.order_by("-start_date", "name"),
        "entry_types": CashBookEntry.TYPE_CHOICES,
        "audit_rows": audit_rows,
        "can_edit": _can_edit_cashbook(request, cashbook),
        "can_manage": _can_manage_cashbook(request),
        "reimbursement_requests": cashbook.reimbursement_requests.select_related("requester").all()[:20],
    })


@login_required
@cashier_manager_required
@pro5_required
def cashbook_entry_create(request, cashbook_pk):
    cashbook = get_object_or_404(CashBook, pk=cashbook_pk, organization=request.org)
    _require_cashbook_editor(request, cashbook)
    if request.method == "POST":
        form = CashBookEntryForm(request.POST, request.FILES, organization=request.org)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.cashbook = cashbook
            entry.created_by = request.user
            entry.save()
            _create_cashbook_audit_log(
                organization=request.org,
                actor=request.user,
                target_type=CashBookAuditLog.TARGET_ENTRY,
                action=CashBookAuditLog.ACTION_CREATE,
                label=f"#{entry.entry_number} {entry.title}",
                cashbook=cashbook,
                entry=entry,
                changes=_cashbook_snapshot(entry, [
                    "entry_number", "entry_type", "booking_date", "receipt_date", "amount", "title",
                    "category", "counterparty", "reference", "description", "attachment", "trip_id",
                ]),
            )
            messages.success(request, "Eintrag erstellt.")
            return redirect("cashbook_detail", pk=cashbook.pk)
    else:
        form = CashBookEntryForm(organization=request.org)

    return render(request, "cashbook/cashbook_entry_form.html", {
        "title": "Kassenbucheintrag erstellen",
        "form": form,
        "cashbook": cashbook,
        "entry": None,
    })


@login_required
@cashier_manager_required
@pro5_required
def cashbook_entry_edit(request, cashbook_pk, pk):
    cashbook = get_object_or_404(CashBook, pk=cashbook_pk, organization=request.org)
    _require_cashbook_editor(request, cashbook)
    entry = get_object_or_404(CashBookEntry, pk=pk, cashbook=cashbook)
    if request.method == "POST":
        before = _cashbook_snapshot(entry, [
            "entry_type", "booking_date", "receipt_date", "amount", "title",
            "category", "counterparty", "reference", "description", "attachment", "trip_id",
        ])
        form = CashBookEntryForm(request.POST, request.FILES, instance=entry, organization=request.org)
        if form.is_valid():
            entry = form.save()
            changes = _cashbook_changes(before, _cashbook_snapshot(entry, [
                "entry_type", "booking_date", "receipt_date", "amount", "title",
                "category", "counterparty", "reference", "description", "attachment", "trip_id",
            ]))
            if changes:
                _create_cashbook_audit_log(
                    organization=request.org,
                    actor=request.user,
                    target_type=CashBookAuditLog.TARGET_ENTRY,
                    action=CashBookAuditLog.ACTION_UPDATE,
                    label=f"#{entry.entry_number} {entry.title}",
                    cashbook=cashbook,
                    entry=entry,
                    changes=changes,
                )
            messages.success(request, "Eintrag gespeichert.")
            return redirect("cashbook_detail", pk=cashbook.pk)
    else:
        form = CashBookEntryForm(instance=entry, organization=request.org)

    return render(request, "cashbook/cashbook_entry_form.html", {
        "title": "Kassenbucheintrag bearbeiten",
        "form": form,
        "cashbook": cashbook,
        "entry": entry,
    })


@login_required
@cashier_manager_required
@pro5_required
def cashbook_entry_delete(request, cashbook_pk, pk):
    cashbook = get_object_or_404(CashBook, pk=cashbook_pk, organization=request.org)
    _require_cashbook_editor(request, cashbook)
    entry = get_object_or_404(CashBookEntry, pk=pk, cashbook=cashbook)
    if request.method == "POST":
        _create_cashbook_audit_log(
            organization=request.org,
            actor=request.user,
            target_type=CashBookAuditLog.TARGET_ENTRY,
            action=CashBookAuditLog.ACTION_DELETE,
            label=f"#{entry.entry_number} {entry.title}",
            cashbook=cashbook,
            changes=_cashbook_snapshot(entry, [
                "entry_number", "entry_type", "booking_date", "receipt_date", "amount", "title",
                "category", "counterparty", "reference", "description", "attachment", "trip_id",
            ]),
        )
        entry.delete()
        messages.success(request, "Eintrag gelöscht.")
        return redirect("cashbook_detail", pk=cashbook.pk)
    return render(request, "cashbook/cashbook_entry_delete.html", {
        "title": "Kassenbucheintrag löschen",
        "cashbook": cashbook,
        "entry": entry,
    })


@login_required
@cashier_manager_required
@pro5_required
def cashbook_export_csv(request, pk):
    cashbook = get_object_or_404(CashBook, pk=pk, organization=request.org)
    entries = cashbook.entries.select_related("trip").order_by("booking_date", "id")
    running_rows, _ = _cashbook_running_rows(entries, cashbook.opening_balance)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{cashbook.name}-entries.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "Buchungsnummer", "Buchungsdatum", "Belegdatum", "Art", "Titel", "Kategorie", "Zahlungspartner",
        "Belegnummer / Referenz", "Veranstaltung", "Betrag", "Laufender Saldo", "Beschreibung", "Beleg"
    ])
    for entry, balance in running_rows:
        writer.writerow([
            entry.entry_number,
            entry.booking_date,
            entry.receipt_date or "",
            entry.get_entry_type_display(),
            entry.title,
            entry.category,
            entry.counterparty,
            entry.reference,
            entry.trip.name if entry.trip else "",
            entry.signed_amount,
            balance,
            entry.description,
            entry.attachment.url if entry.attachment else "",
    ])
    return response


@login_required
@cashier_manager_required
@pro5_required
def cashbook_export_pdf(request, pk):
    cashbook = get_object_or_404(CashBook, pk=pk, organization=request.org)
    all_entries = cashbook.entries.select_related("trip")
    entries, filters = _cashbook_filter_entries(all_entries, request)
    entries = entries.order_by("booking_date", "id")
    selection_opening_balance = cashbook.opening_balance
    first_entry = entries.first()
    if first_entry is not None:
        prior_entries = all_entries.filter(
            Q(booking_date__lt=first_entry.booking_date)
            | (Q(booking_date=first_entry.booking_date) & Q(id__lt=first_entry.id))
        )
        selection_opening_balance += sum(entry.signed_amount for entry in prior_entries)

    running_rows, closing_balance = _cashbook_running_rows(entries, selection_opening_balance)
    income_total = sum(entry.amount for entry in entries if entry.entry_type == CashBookEntry.TYPE_INCOME)
    expense_total = sum(entry.amount for entry in entries if entry.entry_type == CashBookEntry.TYPE_EXPENSE)
    filtered_balance = sum(entry.signed_amount for entry in entries)
    trip_filter_label = ""
    if filters["selected_trip"]:
        trip_filter_label = request.org.trip_set.filter(pk=filters["selected_trip"]).values_list("name", flat=True).first() or ""
    type_filter_label = dict(CashBookEntry.TYPE_CHOICES).get(filters["selected_type"], "")

    return _render_pdf_response(
        request=request,
        template_name="cashbook/pdf/cashbook_export.html",
        context={
            "cashbook": cashbook,
            "running_rows": running_rows,
            "selection_opening_balance": selection_opening_balance,
            "income_total": income_total,
            "expense_total": expense_total,
            "filtered_balance": filtered_balance,
            "closing_balance": closing_balance,
            "filters": filters,
            "trip_filter_label": trip_filter_label,
            "type_filter_label": type_filter_label,
            "fallback_pdf": lambda: _build_cashbook_fallback_pdf(cashbook, running_rows),
        },
        filename=f'{slugify(cashbook.name) or "kassenbuch"}-entries.pdf',
        css="""
            @page { size: A4 landscape; margin: 8mm; }
            body { font-family: sans-serif; font-size: 10px; color: #111827; }
            h1 { margin: 0 0 3mm; font-size: 15px; }
            .meta { margin-bottom: 3mm; color: #4b5563; }
            .summary { width: 100%; border-collapse: collapse; margin-bottom: 3mm; table-layout: fixed; }
            .summary td { border: 1px solid #d1d5db; padding: 1.2mm; }
            table.entries { width: 100%; border-collapse: collapse; table-layout: fixed; }
            table.entries th, table.entries td { border: 1px solid #d1d5db; padding: 0.8mm; vertical-align: top; }
            table.entries th { background: #f3f4f6; text-align: left; }
            .amount { text-align: right; white-space: nowrap; font-size: 10px; }
            .muted { color: #6b7280; }
            .wrap { white-space: pre-wrap; word-break: break-word; }
            .small { font-size: 7px; }
        """,
    )


@login_required
@cashier_manager_required
@pro5_required
def cashbook_export_receipts_zip(request, pk):
    cashbook = get_object_or_404(CashBook, pk=pk, organization=request.org)
    entries = cashbook.entries.exclude(attachment="").exclude(attachment__isnull=True).order_by("booking_date", "id")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            attachment_field = entry.attachment
            if not attachment_field:
                continue
            try:
                if not attachment_field.storage.exists(attachment_field.name):
                    continue
            except Exception:
                continue
            zip_name = Path(attachment_field.name).name
            with attachment_field.open("rb") as uploaded_file:
                archive.writestr(zip_name, uploaded_file.read())

    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{slugify(cashbook.name) or "kassenbuch"}-belege.zip"'
    return response


@login_required
@cashier_manager_required
@pro5_required
def cashbook_export_summary_csv(request):
    cashbooks = CashBook.objects.filter(organization=request.org).prefetch_related("entries")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="cashbooks-summary.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Kassenbuch", "Währung", "Startsaldo", "Einnahmen", "Ausgaben", "Aktueller Saldo", "Einträge", "Aktiv"])
    for cashbook in cashbooks:
        income_total = sum(entry.amount for entry in cashbook.entries.all() if entry.entry_type == CashBookEntry.TYPE_INCOME)
        expense_total = sum(entry.amount for entry in cashbook.entries.all() if entry.entry_type == CashBookEntry.TYPE_EXPENSE)
        writer.writerow([
            cashbook.name,
            cashbook.currency,
            cashbook.opening_balance,
            income_total,
            expense_total,
            cashbook.current_balance,
            cashbook.entries.count(),
            "Ja" if cashbook.active else "Nein",
        ])
    return response


@login_required
@cashier_manager_required
@pro5_required
def cashbook_export_summary_pdf(request):
    cashbooks = CashBook.objects.filter(organization=request.org).prefetch_related("entries")
    rows = []
    for cashbook in cashbooks:
        income_total = sum(entry.amount for entry in cashbook.entries.all() if entry.entry_type == CashBookEntry.TYPE_INCOME)
        expense_total = sum(entry.amount for entry in cashbook.entries.all() if entry.entry_type == CashBookEntry.TYPE_EXPENSE)
        rows.append({
            "cashbook": cashbook,
            "income_total": income_total,
            "expense_total": expense_total,
            "entry_count": cashbook.entries.count(),
        })

    return _render_pdf_response(
        request=request,
        template_name="cashbook/pdf/cashbook_summary_export.html",
        context={
            "rows": rows,
            "organization": request.org,
            "fallback_pdf": lambda: _build_cashbook_summary_fallback_pdf(rows),
        },
        filename="cashbooks-summary.pdf",
        css="""
            @page { size: A4 landscape; margin: 8mm; }
            body { font-family: sans-serif; font-size: 8.5px; color: #111827; }
            h1 { margin: 0 0 3mm; font-size: 15px; }
            .meta { margin-bottom: 3mm; color: #4b5563; }
            table { width: 100%; border-collapse: collapse; table-layout: fixed; }
            th, td { border: 1px solid #d1d5db; padding: 1.2mm; vertical-align: top; }
            th { background: #f3f4f6; text-align: left; }
            .amount { text-align: right; white-space: nowrap; font-size: 8px; }
        """,
    )


@login_required
@pro5_required
def reimbursement_list(request):
    membership = getattr(request, "membership", None)
    if not membership or not (membership.cashier_manager or membership.leiterrundenmitglied):
        raise PermissionDenied("Keine Berechtigung für Auszahlungsanfragen.")
    requests = ReimbursementRequest.objects.filter(cashbook__organization=request.org).select_related("cashbook", "requester")
    if not membership.cashier_manager:
        requests = requests.filter(requester=request.user)
    return render(request, "cashbook/reimbursement_list.html", {"title": "Auszahlungsanfragen", "reimbursement_requests": requests})


@login_required
@pro5_required
def reimbursement_create(request):
    membership = getattr(request, "membership", None)
    if not membership or not membership.leiterrundenmitglied:
        raise PermissionDenied("Nur Leiterrundenmitglieder können Auszahlungsanfragen stellen.")
    form = ReimbursementRequestForm(request.POST or None, request.FILES or None, organization=request.org, requester=request.user)
    if request.method == "POST" and form.is_valid():
        reimbursement = form.save(commit=False)
        reimbursement.requester = request.user
        reimbursement.save()
        transaction.on_commit(lambda: notify_responsible_about_request(reimbursement))
        messages.success(request, "Auszahlungsanfrage wurde eingereicht.")
        return redirect("reimbursement_list")
    return render(request, "cashbook/reimbursement_form.html", {
        "title": "Auszahlungsanfrage stellen", "form": form,
        "bank_cashbook_ids": list(CashBook.objects.filter(organization=request.org, active=True).exclude(iban="").values_list("pk", flat=True)),
    })


@login_required
@cashier_manager_required
@pro5_required
@transaction.atomic
def reimbursement_review(request, pk):
    reimbursement = get_object_or_404(ReimbursementRequest.objects.select_for_update(), pk=pk, cashbook__organization=request.org)
    _require_cashbook_editor(request, reimbursement.cashbook)
    if reimbursement.status != ReimbursementRequest.STATUS_PENDING:
        messages.info(request, "Diese Anfrage wurde bereits geprüft.")
        return redirect("reimbursement_list")
    form = ReimbursementReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reimbursement.review_note = form.cleaned_data["review_note"]
        reimbursement.reviewed_by = request.user
        reimbursement.reviewed_at = timezone.now()
        if form.cleaned_data["decision"] == "approve":
            entry = CashBookEntry.objects.create(
                cashbook=reimbursement.cashbook, entry_type=CashBookEntry.TYPE_EXPENSE,
                booking_date=timezone.localdate(), receipt_date=reimbursement.expense_date,
                amount=reimbursement.amount, title=reimbursement.title,
                category="Auslagenerstattung",
                counterparty=reimbursement.recipient_name,
                reference=f"Auszahlungsanfrage #{reimbursement.pk}", description=reimbursement.description,
                created_by=request.user,
            )
            old_attachment_name = reimbursement.attachment.name
            attachment_storage = reimbursement.attachment.storage
            with attachment_storage.open(old_attachment_name, "rb") as source_file:
                entry.attachment.save(Path(old_attachment_name).name, source_file, save=True)
            reimbursement.attachment.name = entry.attachment.name
            if old_attachment_name != entry.attachment.name:
                attachment_storage.delete(old_attachment_name)
            reimbursement.status = ReimbursementRequest.STATUS_APPROVED
            reimbursement.cashbook_entry = entry
            _create_cashbook_audit_log(organization=request.org, actor=request.user, target_type=CashBookAuditLog.TARGET_ENTRY,
                action=CashBookAuditLog.ACTION_CREATE, label=f"#{entry.entry_number} {entry.title}", cashbook=entry.cashbook,
                entry=entry, changes={"Auszahlungsanfrage": reimbursement.pk})
        else:
            reimbursement.status = ReimbursementRequest.STATUS_REJECTED
        reimbursement.save()
        transaction.on_commit(lambda: notify_requester_about_decision(reimbursement))
        messages.success(request, "Auszahlungsanfrage wurde geprüft.")
        return redirect("reimbursement_list")
    return render(request, "cashbook/reimbursement_review.html", {"title": "Auszahlungsanfrage prüfen", "reimbursement": reimbursement, "form": form})


@login_required
@cashier_manager_required
@pro5_required
def cashbook_export_sepa(request, pk):
    cashbook = get_object_or_404(CashBook, pk=pk, organization=request.org)
    _require_cashbook_editor(request, cashbook)
    if cashbook.currency != "EUR" or not cashbook.account_holder or not cashbook.iban:
        messages.error(request, "Für SEPA werden EUR, Kontoinhaber und IBAN am Kassenbuch benötigt.")
        return redirect("cashbook_detail", pk=pk)
    payments = list(cashbook.reimbursement_requests.filter(status=ReimbursementRequest.STATUS_APPROVED, sepa_exported_at__isnull=True))
    if not payments:
        messages.info(request, "Es liegen keine noch nicht exportierten genehmigten Auszahlungen vor.")
        return redirect("cashbook_detail", pk=pk)
    ns = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
    ET.register_namespace("", ns)
    root = ET.Element(f"{{{ns}}}Document")
    init = ET.SubElement(root, f"{{{ns}}}CstmrCdtTrfInitn")
    msg_id = f"SZL-{timezone.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"
    hdr = ET.SubElement(init, f"{{{ns}}}GrpHdr")
    for tag, value in (("MsgId", msg_id), ("CreDtTm", timezone.now().isoformat()), ("NbOfTxs", str(len(payments))), ("CtrlSum", f"{sum(p.amount for p in payments):.2f}")):
        ET.SubElement(hdr, f"{{{ns}}}{tag}").text = value
    ET.SubElement(ET.SubElement(hdr, f"{{{ns}}}InitgPty"), f"{{{ns}}}Nm").text = cashbook.account_holder[:70]
    info = ET.SubElement(init, f"{{{ns}}}PmtInf")
    for tag, value in (("PmtInfId", msg_id), ("PmtMtd", "TRF"), ("BtchBookg", "true"), ("NbOfTxs", str(len(payments))), ("CtrlSum", f"{sum(p.amount for p in payments):.2f}"), ("ReqdExctnDt", str(timezone.localdate()))):
        ET.SubElement(info, f"{{{ns}}}{tag}").text = value
    ET.SubElement(ET.SubElement(info, f"{{{ns}}}Dbtr"), f"{{{ns}}}Nm").text = cashbook.account_holder[:70]
    ET.SubElement(ET.SubElement(ET.SubElement(info, f"{{{ns}}}DbtrAcct"), f"{{{ns}}}Id"), f"{{{ns}}}IBAN").text = cashbook.iban.replace(" ", "").upper()
    agent = ET.SubElement(ET.SubElement(info, f"{{{ns}}}DbtrAgt"), f"{{{ns}}}FinInstnId")
    if cashbook.bic:
        ET.SubElement(agent, f"{{{ns}}}BIC").text = cashbook.bic.replace(" ", "").upper()
    else:
        ET.SubElement(ET.SubElement(agent, f"{{{ns}}}Othr"), f"{{{ns}}}Id").text = "NOTPROVIDED"
    ET.SubElement(info, f"{{{ns}}}ChrgBr").text = "SLEV"
    for payment in payments:
        tx = ET.SubElement(info, f"{{{ns}}}CdtTrfTxInf")
        ET.SubElement(ET.SubElement(tx, f"{{{ns}}}PmtId"), f"{{{ns}}}EndToEndId").text = f"AUSLAGE-{payment.pk}"
        amount = ET.SubElement(tx, f"{{{ns}}}Amt")
        ET.SubElement(amount, f"{{{ns}}}InstdAmt", Ccy="EUR").text = f"{payment.amount:.2f}"
        creditor_agent = ET.SubElement(ET.SubElement(tx, f"{{{ns}}}CdtrAgt"), f"{{{ns}}}FinInstnId")
        if payment.recipient_bic:
            ET.SubElement(creditor_agent, f"{{{ns}}}BIC").text = payment.recipient_bic.replace(" ", "").upper()
        else:
            ET.SubElement(ET.SubElement(creditor_agent, f"{{{ns}}}Othr"), f"{{{ns}}}Id").text = "NOTPROVIDED"
        ET.SubElement(ET.SubElement(tx, f"{{{ns}}}Cdtr"), f"{{{ns}}}Nm").text = payment.recipient_name[:70]
        ET.SubElement(ET.SubElement(ET.SubElement(tx, f"{{{ns}}}CdtrAcct"), f"{{{ns}}}Id"), f"{{{ns}}}IBAN").text = payment.recipient_iban
        ET.SubElement(ET.SubElement(tx, f"{{{ns}}}RmtInf"), f"{{{ns}}}Ustrd").text = payment.title[:140]
    cashbook.reimbursement_requests.filter(pk__in=[p.pk for p in payments]).update(sepa_exported_at=timezone.now())
    response = HttpResponse(ET.tostring(root, encoding="utf-8", xml_declaration=True), content_type="application/xml")
    response["Content-Disposition"] = f'attachment; filename="{slugify(cashbook.name)}-sepa-{timezone.localdate()}.xml"'
    return response
