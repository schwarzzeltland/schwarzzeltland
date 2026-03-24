from django.contrib.auth.models import User
from django.test import TestCase

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
        response = self.client.post(f"/main/cashbooks/{cashbook.pk}/entries/create/", {
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
