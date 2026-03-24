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
    extension = Path(filename).suffix
    base_name = slugify(Path(filename).stem) or "beleg"
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
