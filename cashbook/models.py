from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Max
from django.utils import timezone
from django.utils.text import slugify


def cashbook_attachment_upload_to(instance, filename):
    organization_slug = slugify(instance.cashbook.organization.name) or f"organization-{instance.cashbook.organization_id}"
    cashbook_slug = slugify(instance.cashbook.name) or f"cashbook-{instance.cashbook_id}"
    booking_date = instance.booking_date or timezone.localdate()
    if isinstance(booking_date, str):
        booking_date = date.fromisoformat(booking_date)
    extension = Path(filename).suffix
    title_slug = slugify(instance.title) or "buchung"
    number = instance.entry_number or "neu"
    base_name = f"{number}_{title_slug}"
    return (
        f"cashbooks/{organization_slug}/{cashbook_slug}/"
        f"{booking_date.year:04d}/{booking_date.month:02d}/"
        f"{base_name}{extension}"
    )


class CashBook(models.Model):
    organization = models.ForeignKey("main.Organization", on_delete=models.CASCADE, related_name="cashbook_cashbooks", verbose_name="Organisation")
    name = models.CharField(max_length=255, verbose_name="Name")
    description = models.TextField(blank=True, verbose_name="Beschreibung")
    currency = models.CharField(max_length=3, default="EUR", verbose_name="Währung")
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Startsaldo")
    active = models.BooleanField(default=True, verbose_name="Aktiv")
    responsible = models.ForeignKey(
        "main.Membership", on_delete=models.PROTECT, null=True, blank=True,
        related_name="responsible_cashbooks", verbose_name="Verantwortlicher Kassenwart",
    )
    account_holder = models.CharField(max_length=70, blank=True, verbose_name="Kontoinhaber")
    iban = models.CharField(max_length=34, blank=True, verbose_name="IBAN")
    bic = models.CharField(max_length=11, blank=True, verbose_name="BIC")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.organization.name})"

    @property
    def current_balance(self):
        total = self.opening_balance
        for entry in self.entries.all():
            total += entry.signed_amount
        return total


class CashBookEntry(models.Model):
    TYPE_INCOME = "income"
    TYPE_EXPENSE = "expense"
    TYPE_CHOICES = (
        (TYPE_INCOME, "Einnahme"),
        (TYPE_EXPENSE, "Ausgabe"),
    )

    cashbook = models.ForeignKey(CashBook, on_delete=models.CASCADE, related_name="entries", verbose_name="Kassenbuch")
    entry_number = models.PositiveIntegerField(verbose_name="Nummer", editable=False, null=True, blank=True)
    trip = models.ForeignKey("events.Trip", on_delete=models.SET_NULL, null=True, blank=True, related_name="cashbook_cashbook_entries", verbose_name="Veranstaltung")
    entry_type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name="Art")
    booking_date = models.DateField(verbose_name="Buchungsdatum")
    receipt_date = models.DateField(verbose_name="Belegdatum", null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Betrag")
    title = models.CharField(max_length=255, verbose_name="Titel")
    category = models.CharField(max_length=255, blank=True, verbose_name="Kategorie")
    counterparty = models.CharField(max_length=255, blank=True, verbose_name="Zahlungspartner")
    reference = models.CharField(max_length=255, blank=True, verbose_name="Belegnummer / Referenz")
    description = models.TextField(blank=True, verbose_name="Beschreibung")
    attachment = models.FileField(upload_to=cashbook_attachment_upload_to, blank=True, null=True, verbose_name="Beleg")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="cashbook_cashbook_entries", verbose_name="Erstellt von")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["booking_date", "id"]
        constraints = [
            models.UniqueConstraint(fields=["cashbook", "entry_number"], name="cashbook_unique_entry_number"),
        ]

    def save(self, *args, **kwargs):
        if self.entry_number is None and self.cashbook_id:
            last_number = self.cashbook.entries.aggregate(max_number=Max("entry_number"))["max_number"] or 0
            self.entry_number = last_number + 1
        super().save(*args, **kwargs)

    def __str__(self):
        if self.entry_number:
            return f"#{self.entry_number} {self.title} ({self.get_entry_type_display()})"
        return f"{self.title} ({self.get_entry_type_display()})"

    @property
    def attachment_filename(self):
        if not self.attachment:
            return ""
        return Path(self.attachment.name).name

    @property
    def signed_amount(self):
        if self.entry_type == self.TYPE_EXPENSE:
            return -self.amount
        return self.amount


class CashBookAuditLog(models.Model):
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_CHOICES = (
        (ACTION_CREATE, "Erstellt"),
        (ACTION_UPDATE, "Bearbeitet"),
        (ACTION_DELETE, "Gelöscht"),
    )
    TARGET_CASHBOOK = "cashbook"
    TARGET_ENTRY = "entry"
    TARGET_CHOICES = (
        (TARGET_CASHBOOK, "Kassenbuch"),
        (TARGET_ENTRY, "Eintrag"),
    )

    organization = models.ForeignKey("main.Organization", on_delete=models.CASCADE, related_name="cashbook_audit_logs_v2")
    cashbook = models.ForeignKey(CashBook, on_delete=models.CASCADE, related_name="audit_logs", null=True, blank=True)
    entry = models.ForeignKey(CashBookEntry, on_delete=models.SET_NULL, related_name="audit_logs", null=True, blank=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="cashbook_cashbook_audit_logs")
    target_type = models.CharField(max_length=20, choices=TARGET_CHOICES, verbose_name="Zieltyp")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name="Aktion")
    label = models.CharField(max_length=255, verbose_name="Objekt")
    changes = models.JSONField(default=dict, blank=True, verbose_name="Änderungen")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Zeitpunkt")

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Kassenbuch-Änderung"
        verbose_name_plural = "Kassenbuch-Änderungen"

    def __str__(self):
        return f"{self.get_action_display()} {self.label}"


class AdvanceBudget(models.Model):
    trip = models.ForeignKey("events.Trip", on_delete=models.CASCADE, related_name="advance_budgets", verbose_name="Veranstaltung")
    cashbook = models.ForeignKey(CashBook, on_delete=models.PROTECT, related_name="advance_budgets", verbose_name="Zielkassenbuch")
    assigned_to = models.ForeignKey("main.Membership", on_delete=models.PROTECT, related_name="assigned_advance_budgets", verbose_name="Zugewiesener Planer")
    name = models.CharField(max_length=255, verbose_name="Bezeichnung")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Budget")
    settled_at = models.DateTimeField(null=True, blank=True, verbose_name="Abgerechnet am")
    settled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="settled_advance_budgets", verbose_name="Abgerechnet von")
    advance_entry = models.OneToOneField(CashBookEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="advance_budget_payment", verbose_name="Auszahlung")
    settlement_entry = models.OneToOneField(CashBookEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="advance_budget_settlement", verbose_name="Sammelbuchung")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    @property
    def spent_amount(self):
        return sum(expense.amount for expense in self.expenses.exclude(status=EventExpense.STATUS_REJECTED))

    @property
    def remaining_amount(self):
        return self.amount - self.spent_amount


class EventExpense(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = ((STATUS_PENDING, "Offen"), (STATUS_APPROVED, "Freigegeben"), (STATUS_REJECTED, "Abgelehnt"))

    trip = models.ForeignKey("events.Trip", on_delete=models.CASCADE, related_name="event_expenses", verbose_name="Veranstaltung")
    cashbook = models.ForeignKey(CashBook, on_delete=models.PROTECT, null=True, blank=True, related_name="event_expenses", verbose_name="Kassenbuch")
    advance_budget = models.ForeignKey(AdvanceBudget, on_delete=models.PROTECT, null=True, blank=True, related_name="expenses", verbose_name="Vorschussbudget")
    expense_date = models.DateField(verbose_name="Belegdatum")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Betrag")
    title = models.CharField(max_length=255, verbose_name="Titel")
    category = models.CharField(max_length=255, blank=True, verbose_name="Kategorie")
    counterparty = models.CharField(max_length=255, blank=True, verbose_name="Zahlungspartner")
    reference = models.CharField(max_length=255, blank=True, verbose_name="Belegnummer / Referenz")
    description = models.TextField(blank=True, verbose_name="Beschreibung")
    attachment = models.FileField(upload_to="cashbooks/event-expenses/%Y/%m/", verbose_name="Beleg")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name="Status")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="event_expenses", verbose_name="Erstellt von")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_event_expenses", verbose_name="Freigegeben von")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    cashbook_entry = models.OneToOneField(CashBookEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="event_expense", verbose_name="Kassenbucheintrag")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date", "-id"]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.cashbook_id and self.advance_budget_id:
            raise ValidationError("Bitte genau eine Zahlungsquelle auswählen.")
        if self.cashbook_id and self.cashbook.organization_id != self.trip.owner_id:
            raise ValidationError("Das Kassenbuch gehört nicht zur Organisation der Veranstaltung.")
        if self.advance_budget_id and self.advance_budget.trip_id != self.trip_id:
            raise ValidationError("Das Vorschussbudget gehört nicht zu dieser Veranstaltung.")


class ReimbursementRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = ((STATUS_PENDING, "Offen"), (STATUS_APPROVED, "Genehmigt"), (STATUS_REJECTED, "Abgelehnt"))

    cashbook = models.ForeignKey(CashBook, on_delete=models.CASCADE, related_name="reimbursement_requests", verbose_name="Kassenbuch")
    requester = models.ForeignKey(User, on_delete=models.PROTECT, related_name="cashbook_reimbursement_requests", verbose_name="Antragsteller")
    title = models.CharField(max_length=255, verbose_name="Auslage")
    expense_date = models.DateField(verbose_name="Belegdatum")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Betrag")
    description = models.TextField(blank=True, verbose_name="Beschreibung")
    attachment = models.FileField(upload_to="cashbooks/reimbursements/%Y/%m/", verbose_name="Beleg")
    recipient_name = models.CharField(max_length=70, blank=True, verbose_name="Kontoinhaber")
    recipient_iban = models.CharField(max_length=34, blank=True, verbose_name="IBAN")
    recipient_bic = models.CharField(max_length=11, blank=True, verbose_name="BIC")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name="Status")
    review_note = models.TextField(blank=True, verbose_name="Prüfvermerk")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_reimbursement_requests")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    sepa_exported_at = models.DateTimeField(null=True, blank=True)
    cashbook_entry = models.OneToOneField(CashBookEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="reimbursement_request")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} – {self.amount} {self.cashbook.currency}"
