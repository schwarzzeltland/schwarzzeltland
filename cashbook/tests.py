from django.contrib.auth.models import User
from django.test import TestCase
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile

from cashbook.models import CashBook, CashBookAuditLog, CashBookEntry


class CashbookTests(TestCase):
    def setUp(self):
        self.owner_user = User.objects.create_user(username="owner", password="pw")
        self.owner_org = self.owner_user.organization_set.first()
        self.owner_org.pro5 = True
        self.owner_org.save(update_fields=["pro5"])
        membership = self.owner_org.membership_set.get(user=self.owner_user)
        membership.cashier_manager = True
        membership.save(update_fields=["cashier_manager"])

    def test_cashbook_entries_get_consecutive_numbers(self):
        cashbook = CashBook.objects.create(organization=self.owner_org, name="Hauptkasse")
        first_entry = CashBookEntry.objects.create(
            cashbook=cashbook,
            entry_type=CashBookEntry.TYPE_EXPENSE,
            booking_date="2026-03-24",
            amount="12.50",
            title="Erster Eintrag",
            created_by=self.owner_user,
        )
        second_entry = CashBookEntry.objects.create(
            cashbook=cashbook,
            entry_type=CashBookEntry.TYPE_INCOME,
            booking_date="2026-03-25",
            amount="20.00",
            title="Zweiter Eintrag",
            created_by=self.owner_user,
        )

        self.assertEqual(first_entry.entry_number, 1)
        self.assertEqual(second_entry.entry_number, 2)

    def test_cashbook_entry_changes_create_audit_log(self):
        cashbook = CashBook.objects.create(organization=self.owner_org, name="Hauptkasse")

        self.client.login(username="owner", password="pw")
        response = self.client.post(f"/cashbooks/{cashbook.pk}/entries/create/", {
            "entry_type": CashBookEntry.TYPE_EXPENSE,
            "booking_date": "2026-03-24",
            "receipt_date": "",
            "amount": "12.50",
            "title": "Audit-Test",
            "category": "Fahrt",
            "counterparty": "",
            "reference": "",
            "trip": "",
            "description": "",
        })

        self.assertEqual(response.status_code, 302)
        audit_log = CashBookAuditLog.objects.get(cashbook=cashbook, action=CashBookAuditLog.ACTION_CREATE)
        self.assertEqual(audit_log.target_type, CashBookAuditLog.TARGET_ENTRY)
        self.assertEqual(audit_log.actor, self.owner_user)
        self.assertEqual(audit_log.changes["title"], "Audit-Test")

    def test_cashbook_detail_uses_selection_start_balance_and_selection_total(self):
        cashbook = CashBook.objects.create(organization=self.owner_org, name="Hauptkasse", opening_balance="100.00")
        CashBookEntry.objects.create(
            cashbook=cashbook,
            entry_type=CashBookEntry.TYPE_INCOME,
            booking_date="2026-03-24",
            amount="30.00",
            title="Einnahme",
            created_by=self.owner_user,
        )
        CashBookEntry.objects.create(
            cashbook=cashbook,
            entry_type=CashBookEntry.TYPE_EXPENSE,
            booking_date="2026-03-25",
            amount="10.00",
            title="Ausgabe 1",
            created_by=self.owner_user,
        )
        CashBookEntry.objects.create(
            cashbook=cashbook,
            entry_type=CashBookEntry.TYPE_EXPENSE,
            booking_date="2026-03-26",
            amount="5.00",
            title="Ausgabe 2",
            created_by=self.owner_user,
        )

        self.client.login(username="owner", password="pw")
        response = self.client.get(f"/cashbooks/{cashbook.pk}/", {"entry_type": CashBookEntry.TYPE_EXPENSE})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selection_opening_balance"], Decimal("130.00"))
        self.assertEqual(response.context["filtered_balance"], Decimal("-15.00"))

    def test_attachment_name_uses_entry_number_and_title(self):
        cashbook = CashBook.objects.create(organization=self.owner_org, name="Hauptkasse")
        entry = CashBookEntry.objects.create(
            cashbook=cashbook,
            entry_type=CashBookEntry.TYPE_EXPENSE,
            booking_date="2026-03-24",
            amount="12.50",
            title="Bus Fahrt",
            attachment=SimpleUploadedFile("original.pdf", b"pdf-data", content_type="application/pdf"),
            created_by=self.owner_user,
        )

        attachment_name = entry.attachment.name.replace("\\", "/")
        self.assertIn("/1_bus-fahrt", attachment_name)
        self.assertTrue(attachment_name.endswith(".pdf"))

    def test_cashbook_pdf_export_returns_pdf(self):
        cashbook = CashBook.objects.create(organization=self.owner_org, name="Hauptkasse")
        CashBookEntry.objects.create(
            cashbook=cashbook,
            entry_type=CashBookEntry.TYPE_EXPENSE,
            booking_date="2026-03-24",
            amount="12.50",
            title="PDF-Test",
            created_by=self.owner_user,
        )

        self.client.login(username="owner", password="pw")
        response = self.client.get(f"/cashbooks/{cashbook.pk}/export/pdf/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
