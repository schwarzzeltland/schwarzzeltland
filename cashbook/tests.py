from django.contrib.auth.models import User
from django.test import TestCase
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail

from cashbook.models import CashBook, CashBookAuditLog, CashBookEntry, ReimbursementRequest
from main.models import Membership


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

    def test_only_responsible_cashier_can_change_entries(self):
        responsible = self.owner_org.membership_set.get(user=self.owner_user)
        cashbook = CashBook.objects.create(organization=self.owner_org, name="Hauptkasse", responsible=responsible)
        other = User.objects.create_user(username="other", password="pw")
        Membership.objects.create(user=other, organization=self.owner_org, cashier_manager=True, admin=True)
        self.client.login(username="other", password="pw")
        edit_response = self.client.get(f"/cashbooks/{cashbook.pk}/edit/")
        self.assertEqual(edit_response.status_code, 200)
        response = self.client.post(f"/cashbooks/{cashbook.pk}/entries/create/", {
            "entry_type": "expense", "booking_date": "2026-08-09", "amount": "10.00", "title": "Nicht erlaubt",
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(cashbook.entries.exists())

    def test_reimbursement_is_integrated_and_exported_as_sepa(self):
        responsible = self.owner_org.membership_set.get(user=self.owner_user)
        cashbook = CashBook.objects.create(
            organization=self.owner_org, name="Hauptkasse", responsible=responsible,
            account_holder="Stamm Beispiel", iban="DE89370400440532013000", currency="EUR",
        )
        leader = User.objects.create_user(username="leader", password="pw", email="leader@example.org")
        Membership.objects.create(user=leader, organization=self.owner_org, leiterrundenmitglied=True)
        reimbursement = ReimbursementRequest.objects.create(
            cashbook=cashbook, requester=leader, title="Material", expense_date="2026-08-08", amount="42.50",
            attachment=SimpleUploadedFile("beleg.pdf", b"pdf", content_type="application/pdf"),
            recipient_name="Leiter Beispiel", recipient_iban="DE12500105170648489890",
        )
        old_attachment_name = reimbursement.attachment.name
        attachment_storage = reimbursement.attachment.storage
        self.assertTrue(attachment_storage.exists(old_attachment_name))
        self.client.login(username="owner", password="pw")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/cashbooks/reimbursements/{reimbursement.pk}/review/", {"decision": "approve", "review_note": "Geprüft"})
        self.assertEqual(response.status_code, 302)
        reimbursement.refresh_from_db()
        self.assertEqual(reimbursement.status, ReimbursementRequest.STATUS_APPROVED)
        self.assertEqual(reimbursement.cashbook_entry.amount, Decimal("42.50"))
        self.assertEqual(reimbursement.cashbook_entry.category, "Auslagenerstattung")
        self.assertNotEqual(reimbursement.attachment.name, old_attachment_name)
        self.assertEqual(reimbursement.attachment.name, reimbursement.cashbook_entry.attachment.name)
        self.assertTrue(reimbursement.attachment.name.startswith("cashbooks/"))
        self.assertFalse(attachment_storage.exists(old_attachment_name))
        self.assertTrue(attachment_storage.exists(reimbursement.attachment.name))
        self.assertEqual(mail.outbox[-1].to, ["leader@example.org"])
        self.assertIn("genehmigt", mail.outbox[-1].subject)
        self.assertIn("Auszahlungsanfrage geprüft", mail.outbox[-1].alternatives[0].content)
        response = self.client.get(f"/cashbooks/{cashbook.pk}/export/sepa/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml")
        self.assertIn(b"pain.001.001.03", response.content)
        self.assertIn(b"42.50", response.content)
        reimbursement.refresh_from_db()
        self.assertIsNotNone(reimbursement.sepa_exported_at)

    def test_new_request_notifies_responsible_and_leader_only_sees_own_requests(self):
        self.owner_user.email = "cashier@example.org"
        self.owner_user.save(update_fields=["email"])
        responsible = self.owner_org.membership_set.get(user=self.owner_user)
        cashbook = CashBook.objects.create(organization=self.owner_org, name="Hauptkasse", responsible=responsible)
        leader = User.objects.create_user(username="leader2", password="pw", email="leader2@example.org")
        Membership.objects.create(user=leader, organization=self.owner_org, leiterrundenmitglied=True)
        other_leader = User.objects.create_user(username="leader3", password="pw")
        Membership.objects.create(user=other_leader, organization=self.owner_org, leiterrundenmitglied=True)
        ReimbursementRequest.objects.create(
            cashbook=cashbook, requester=other_leader, title="Fremde Anfrage", expense_date="2026-08-08",
            amount="5.00", attachment=SimpleUploadedFile("fremd.pdf", b"pdf"), recipient_name="Andere", recipient_iban="DE12500105170648489890",
        )
        self.client.login(username="leader2", password="pw")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/cashbooks/reimbursements/create/", {
                "cashbook": cashbook.pk, "title": "Eigene Anfrage", "expense_date": "2026-08-09", "amount": "12.00",
                "description": "", "attachment": SimpleUploadedFile("beleg.pdf", b"pdf"),
                "recipient_name": "", "recipient_iban": "", "recipient_bic": "",
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(mail.outbox[-1].to, ["cashier@example.org"])
        self.assertIn("Neue Auszahlungsanfrage", mail.outbox[-1].subject)
        self.assertIn("Anfrage prüfen", mail.outbox[-1].alternatives[0].content)
        response = self.client.get("/cashbooks/reimbursements/")
        self.assertContains(response, "Eigene Anfrage")
        self.assertNotContains(response, "Fremde Anfrage")
        self.assertNotContains(response, "Zu den Kassenbüchern")
        own_request = ReimbursementRequest.objects.get(requester=leader, title="Eigene Anfrage")
        self.assertEqual(own_request.recipient_name, "leader2")
        self.assertEqual(own_request.recipient_iban, "")
        receipt_response = self.client.get(own_request.attachment.url)
        self.assertEqual(receipt_response.status_code, 200)
        self.client.login(username="owner", password="pw")
        receipt_response = self.client.get(own_request.attachment.url)
        self.assertEqual(receipt_response.status_code, 200)

    def test_request_requires_recipient_bank_data_for_cashbook_with_iban(self):
        responsible = self.owner_org.membership_set.get(user=self.owner_user)
        cashbook = CashBook.objects.create(
            organization=self.owner_org, name="Bankkonto", responsible=responsible,
            iban="DE89370400440532013000", account_holder="Organisation",
        )
        leader = User.objects.create_user(username="bankleader", password="pw")
        Membership.objects.create(user=leader, organization=self.owner_org, leiterrundenmitglied=True)
        self.client.login(username="bankleader", password="pw")
        response = self.client.post("/cashbooks/reimbursements/create/", {
            "cashbook": cashbook.pk, "title": "Auslage", "expense_date": "2026-08-09", "amount": "10.00",
            "attachment": SimpleUploadedFile("beleg.pdf", b"pdf"), "recipient_name": "", "recipient_iban": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "recipient_name", "Der Kontoinhaber ist für dieses Kassenbuch erforderlich.")
        self.assertFormError(response.context["form"], "recipient_iban", "Die IBAN ist für dieses Kassenbuch erforderlich.")
        self.assertFormError(response.context["form"], "recipient_bic", "Die BIC ist für dieses Kassenbuch erforderlich.")
