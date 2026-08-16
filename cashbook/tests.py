from django.contrib.auth.models import User
from django.test import TestCase
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail

from cashbook.models import CashBook, CashBookAuditLog, CashBookEntry, ReimbursementRequest
from events.models import Trip
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

    def test_cashbook_list_places_inactive_cashbooks_at_the_bottom(self):
        inactive = CashBook.objects.create(organization=self.owner_org, name="A inaktiv", active=False)
        active = CashBook.objects.create(organization=self.owner_org, name="Z aktiv", active=True)
        self.client.login(username="owner", password="pw")

        response = self.client.get("/cashbooks/")

        listed_ids = [row["cashbook"].pk for row in response.context["cashbooks_with_balances"]]
        self.assertLess(listed_ids.index(active.pk), listed_ids.index(inactive.pk))

    def test_csv_import_action_is_only_shown_for_cashbook_with_iban(self):
        responsible = self.owner_org.membership_set.get(user=self.owner_user)
        without_iban = CashBook.objects.create(
            organization=self.owner_org, name="Bar", responsible=responsible,
        )
        with_iban = CashBook.objects.create(
            organization=self.owner_org, name="Bank", responsible=responsible,
            iban="DE89370400440532013000",
        )
        self.client.login(username="owner", password="pw")

        response = self.client.get(f"/cashbooks/{without_iban.pk}/")
        self.assertNotContains(response, "Kontoumsätze importieren")
        self.assertNotContains(response, "SEPA-Überweisungen exportieren")
        response = self.client.get(f"/cashbooks/{with_iban.pk}/")
        self.assertContains(response, "Kontoumsätze importieren")
        self.assertContains(response, "SEPA-Überweisungen exportieren")

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
        self.assertEqual(response.context["current_balance"], Decimal("115.00"))
        displayed_entries = [entry for entry, _ in response.context["running_rows"]]
        self.assertEqual([entry.title for entry in displayed_entries], ["Ausgabe 2", "Ausgabe 1"])
        self.assertContains(response, "Aktueller Saldo des Kassenbuchs")
        self.assertContains(response, "Weitere Aktionen")

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

    def test_cashbook_entry_exposes_attachment_filename_for_pdf_export(self):
        cashbook = CashBook.objects.create(organization=self.owner_org, name="Hauptkasse")
        entry = CashBookEntry.objects.create(
            cashbook=cashbook,
            entry_type=CashBookEntry.TYPE_EXPENSE,
            booking_date="2026-03-24",
            amount="12.50",
            title="Langer Belegname",
            attachment=SimpleUploadedFile("rechnung.pdf", b"pdf-data", content_type="application/pdf"),
            created_by=self.owner_user,
        )

        self.assertEqual(entry.attachment_filename, "1_langer-belegname.pdf")

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

    def test_csv_transactions_are_previewed_adjusted_and_selected_before_import(self):
        responsible = self.owner_org.membership_set.get(user=self.owner_user)
        cashbook = CashBook.objects.create(
            organization=self.owner_org,
            name="Bankkonto",
            responsible=responsible,
            iban="DE89 3704 0044 0532 0130 00",
        )
        trip = Trip.objects.create(
            owner=self.owner_org,
            name="Sommerlager",
            start_date="2026-08-01T10:00:00Z",
            end_date="2026-08-15T10:00:00Z",
        )
        csv_content = (
            "IBAN Auftragskonto;BIC Auftragskonto;Buchungstag;Zusatzfeld;Valutadatum;"
            "Name Zahlungsbeteiligter;Buchungstext;Verwendungszweck;Betrag;"
            "Saldo nach Buchung;Glaeubiger ID;Mandatsreferenz\n"
            "DE89370400440532013000;COBADEFFXXX;09.08.26;ignorieren;08.08.26;"
            "Bäckerei;Kartenzahlung;Verpflegung;-12,50;987,50;;\n"
            "DE89370400440532013000;COBADEFFXXX;10.08.2026;ignorieren;10.08.2026;"
            "Förderverein;Überweisung;Spende;100,00;1087,50;DE98ZZZ09999999999;MANDAT-1\n"
        )
        self.client.login(username="owner", password="pw")

        preview = self.client.post(f"/cashbooks/{cashbook.pk}/import/csv/", {
            "action": "preview",
            "csv_file": SimpleUploadedFile("umsatz.csv", csv_content.encode("utf-8"), content_type="text/csv"),
        })

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(len(preview.context["row_formset"].forms), 2)
        self.assertContains(preview, 'name="transactions-0-booking_date" value="2026-08-09"')
        self.assertContains(preview, 'name="transactions-0-value_date" value="2026-08-08"')
        self.assertContains(preview, "stimmt nicht mit dem errechneten Saldo")
        self.assertEqual(preview.context["row_formset"].forms[0].expected_balance, Decimal("-12.50"))
        self.assertFalse(cashbook.entries.exists())
        commit = self.client.post(f"/cashbooks/{cashbook.pk}/import/csv/", {
            "action": "commit",
            "verification_token": preview.context["verification_token"],
            "transactions-TOTAL_FORMS": "2",
            "transactions-INITIAL_FORMS": "0",
            "transactions-MIN_NUM_FORMS": "0",
            "transactions-MAX_NUM_FORMS": "1000",
            "transactions-0-include": "on",
            "transactions-0-booking_date": "2026-08-09",
            "transactions-0-value_date": "2026-08-08",
            "transactions-0-entry_type": CashBookEntry.TYPE_EXPENSE,
            "transactions-0-amount": "13.00",
            "transactions-0-title": "Angepasster Einkauf",
            "transactions-0-counterparty": "Bäckerei",
            "transactions-0-purpose": "Verpflegung",
            "transactions-0-balance_after": "987.50",
            "transactions-0-creditor_id": "",
            "transactions-0-mandate_reference": "",
            "transactions-0-trip": str(trip.pk),
            "transactions-1-booking_date": "2026-08-10",
            "transactions-1-value_date": "2026-08-10",
            "transactions-1-entry_type": CashBookEntry.TYPE_INCOME,
            "transactions-1-amount": "100.00",
            "transactions-1-title": "Überweisung",
            "transactions-1-counterparty": "Förderverein",
            "transactions-1-purpose": "Spende",
            "transactions-1-balance_after": "1087.50",
            "transactions-1-creditor_id": "DE98ZZZ09999999999",
            "transactions-1-mandate_reference": "MANDAT-1",
        })

        self.assertRedirects(commit, f"/cashbooks/{cashbook.pk}/")
        entry = cashbook.entries.get()
        self.assertEqual(entry.title, "Angepasster Einkauf")
        self.assertEqual(entry.amount, Decimal("13.00"))
        self.assertEqual(entry.entry_type, CashBookEntry.TYPE_EXPENSE)
        self.assertEqual(entry.trip, trip)
        self.assertIn("Valutadatum: 08.08.2026", entry.description)
        self.assertIn("Saldo nach Buchung: 987.50", entry.description)
        self.assertTrue(CashBookAuditLog.objects.get(entry=entry).changes["CSV-Import"])

    def test_csv_import_rejects_different_account_iban(self):
        responsible = self.owner_org.membership_set.get(user=self.owner_user)
        cashbook = CashBook.objects.create(
            organization=self.owner_org, name="Bankkonto", responsible=responsible,
            iban="DE89370400440532013000",
        )
        csv_content = (
            "IBAN Auftragskonto;BIC Auftragskonto;Buchungstag;Valutadatum;Name Zahlungsbeteiligter;"
            "Buchungstext;Verwendungszweck;Betrag;Saldo nach Buchung;Glaeubiger ID;Mandatsreferenz\n"
            "DE12500105170648489890;INGDDEFFXXX;09.08.2026;09.08.2026;Test;Zahlung;Test;-1,00;99,00;;\n"
        )
        self.client.login(username="owner", password="pw")

        response = self.client.post(f"/cashbooks/{cashbook.pk}/import/csv/", {
            "action": "preview",
            "csv_file": SimpleUploadedFile("umsatz.csv", csv_content.encode("utf-8"), content_type="text/csv"),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "stimmt nicht mit der Kassenbuch-IBAN überein")
        self.assertIsNone(response.context["row_formset"])
        self.assertFalse(cashbook.entries.exists())

    def test_csv_import_marks_existing_transaction_as_duplicate_and_unchecks_it(self):
        responsible = self.owner_org.membership_set.get(user=self.owner_user)
        cashbook = CashBook.objects.create(
            organization=self.owner_org, name="Bankkonto", responsible=responsible,
            iban="DE89370400440532013000",
        )
        CashBookEntry.objects.create(
            cashbook=cashbook,
            entry_type=CashBookEntry.TYPE_EXPENSE,
            booking_date="2026-08-09",
            amount="12.50",
            title="Kartenzahlung",
            counterparty="Bäckerei",
            category="Kontoumsatz",
            description="Verpflegung\nValutadatum: 08.08.2026\nSaldo nach Buchung: 987.50 EUR",
            created_by=self.owner_user,
        )
        csv_content = (
            "IBAN Auftragskonto;BIC Auftragskonto;Buchungstag;Valutadatum;Name Zahlungsbeteiligter;"
            "Buchungstext;Verwendungszweck;Betrag;Saldo nach Buchung;Glaeubiger ID;Mandatsreferenz\n"
            "DE89370400440532013000;COBADEFFXXX;09.08.2026;08.08.2026;Bäckerei;"
            "Kartenzahlung;Verpflegung;-12,50;987,50;;\n"
        )
        self.client.login(username="owner", password="pw")

        response = self.client.post(f"/cashbooks/{cashbook.pk}/import/csv/", {
            "action": "preview",
            "csv_file": SimpleUploadedFile("umsatz.csv", csv_content.encode("utf-8"), content_type="text/csv"),
        })

        row_form = response.context["row_formset"].forms[0]
        self.assertEqual(response.status_code, 200)
        self.assertTrue(row_form.initial["is_duplicate"])
        self.assertFalse(row_form["include"].value())
        self.assertContains(response, "Möglicher doppelter Import")
        self.assertContains(response, "wurde deshalb nicht vorausgewählt")

    def test_cashbook_csv_export_uses_current_filters(self):
        cashbook = CashBook.objects.create(organization=self.owner_org, name="Filterkasse")
        CashBookEntry.objects.create(
            cashbook=cashbook, entry_type=CashBookEntry.TYPE_INCOME,
            booking_date="2026-08-01", amount="20.00", title="Nur Einnahme",
            created_by=self.owner_user,
        )
        CashBookEntry.objects.create(
            cashbook=cashbook, entry_type=CashBookEntry.TYPE_EXPENSE,
            booking_date="2026-08-02", amount="5.00", title="Nur Ausgabe",
            created_by=self.owner_user,
        )
        self.client.login(username="owner", password="pw")

        response = self.client.get(
            f"/cashbooks/{cashbook.pk}/export/csv/",
            {"entry_type": CashBookEntry.TYPE_EXPENSE},
        )

        content = response.content.decode()
        self.assertIn("Nur Ausgabe", content)
        self.assertNotIn("Nur Einnahme", content)

    def test_csv_import_assigns_entry_numbers_in_booking_date_order(self):
        responsible = self.owner_org.membership_set.get(user=self.owner_user)
        cashbook = CashBook.objects.create(
            organization=self.owner_org, name="Bankkonto", responsible=responsible,
            iban="DE89370400440532013000",
        )
        csv_content = (
            "IBAN Auftragskonto;BIC Auftragskonto;Buchungstag;Valutadatum;Name Zahlungsbeteiligter;"
            "Buchungstext;Verwendungszweck;Betrag;Saldo nach Buchung;Glaeubiger ID;Mandatsreferenz\n"
            "DE89370400440532013000;COBADEFFXXX;10.08.2026;10.08.2026;Spät;Spätere Buchung;;10,00;20,00;;\n"
            "DE89370400440532013000;COBADEFFXXX;09.08.2026;09.08.2026;Früh;Frühere Buchung;;10,00;10,00;;\n"
        )
        self.client.login(username="owner", password="pw")
        preview = self.client.post(f"/cashbooks/{cashbook.pk}/import/csv/", {
            "action": "preview",
            "csv_file": SimpleUploadedFile("umsatz.csv", csv_content.encode("utf-8"), content_type="text/csv"),
        })
        formset = preview.context["row_formset"]
        post_data = {
            "action": "commit",
            "verification_token": preview.context["verification_token"],
            "transactions-TOTAL_FORMS": "2",
            "transactions-INITIAL_FORMS": "0",
            "transactions-MIN_NUM_FORMS": "0",
            "transactions-MAX_NUM_FORMS": "1000",
        }
        for index, form in enumerate(formset.forms):
            for field_name, value in form.initial.items():
                if field_name == "is_duplicate" or value is None:
                    continue
                post_data[f"transactions-{index}-{field_name}"] = "on" if value is True else value

        response = self.client.post(f"/cashbooks/{cashbook.pk}/import/csv/", post_data)

        self.assertEqual(response.status_code, 302)
        numbered_entries = list(cashbook.entries.order_by("entry_number").values_list("entry_number", "title"))
        self.assertEqual(numbered_entries, [(1, "Frühere Buchung"), (2, "Spätere Buchung")])

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

    def test_responsible_cashier_can_open_approved_request_bank_details(self):
        responsible = self.owner_org.membership_set.get(user=self.owner_user)
        cashbook = CashBook.objects.create(organization=self.owner_org, name="Hauptkasse", responsible=responsible)
        leader = User.objects.create_user(username="leader-details", password="pw")
        Membership.objects.create(user=leader, organization=self.owner_org, leiterrundenmitglied=True)
        reimbursement = ReimbursementRequest.objects.create(
            cashbook=cashbook, requester=leader, title="Materialeinkauf", expense_date="2026-08-08",
            amount="42.50", attachment=SimpleUploadedFile("beleg.pdf", b"pdf"),
            recipient_name="Leiter Beispiel", recipient_iban="DE12500105170648489890",
            recipient_bic="INGDDEFFXXX", status=ReimbursementRequest.STATUS_APPROVED,
        )
        self.client.login(username="owner", password="pw")

        overview = self.client.get("/cashbooks/reimbursements/")
        detail = self.client.get(f"/cashbooks/reimbursements/{reimbursement.pk}/review/")

        self.assertContains(overview, "Überweisungsdaten")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Leiter Beispiel")
        self.assertContains(detail, "DE12500105170648489890")
        self.assertContains(detail, "INGDDEFFXXX")
        self.assertNotContains(detail, "Entscheidung speichern")

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
