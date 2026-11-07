from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from leiterrunden.models import MeetingMinutes, MeetingMinutesAcceptance, MeetingMinutesItem
from leiterrunden.tasks import send_due_meeting_minutes_items_today
from main.models import Membership


class MeetingMinutesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="leitung", password="pw", email="leitung@example.test")
        self.organization = self.user.organization_set.first(); self.organization.pro6 = True; self.organization.save(update_fields=["pro6"])
        self.membership = self.organization.membership_set.get(user=self.user); self.membership.leiterrundenmitglied = True; self.membership.save(update_fields=["leiterrundenmitglied"])

    def _post_data(self, action="save"):
        return {"title": "Juli-Sitzung", "meeting_start": "2026-07-22T19:00", "meeting_end": "2026-07-22T21:00", "introduction": "Notizen", "action": action,
            "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "0", "items-MIN_NUM_FORMS": "0", "items-MAX_NUM_FORMS": "1000", "items-0-parent": "", "items-0-topic": "Sommerlager", "items-0-notes": "Material prüfen", "items-0-due_date": "", "items-0-position": "",
            "guests-TOTAL_FORMS": "1", "guests-INITIAL_FORMS": "0", "guests-MIN_NUM_FORMS": "0", "guests-MAX_NUM_FORMS": "1000", "guests-0-name": "", "guests-0-note": "", f"attendance_{self.membership.id}": "on", f"attendance_note_{self.membership.id}": "pünktlich"}

    def test_draft_can_be_saved(self):
        self.client.login(username="leitung", password="pw")
        response = self.client.post(reverse("meeting_minutes_create"), self._post_data())
        self.assertEqual(response.status_code, 302)
        minutes = MeetingMinutes.objects.get()
        self.assertFalse(minutes.published)
        self.assertEqual(minutes.updated_by, self.user)
        self.assertIsNone(minutes.published_by)
        self.assertContains(self.client.get(reverse("meeting_minutes_list")), "Zuletzt bearbeitet von leitung")

    def test_changed_form_can_be_autosaved_without_creating_duplicate_drafts(self):
        self.client.login(username="leitung", password="pw")
        response = self.client.post(reverse("meeting_minutes_autosave_create"), self._post_data())
        self.assertEqual(response.status_code, 200)
        minutes = MeetingMinutes.objects.get()
        self.assertFalse(minutes.published)
        self.assertEqual(response.json()["pk"], minutes.pk)
        self.assertEqual(response.json()["detail_url"], reverse("meeting_minutes_detail", args=[minutes.pk]))
        self.assertEqual(response.json()["item_ids"], {"items-0": minutes.items.get().pk})

        data = self._post_data()
        data["title"] = "Automatisch aktualisiert"
        data["items-INITIAL_FORMS"] = "1"
        data["items-0-id"] = str(minutes.items.get().pk)
        response = self.client.post(reverse("meeting_minutes_autosave_edit", args=[minutes.pk]), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MeetingMinutes.objects.count(), 1)
        minutes.refresh_from_db()
        self.assertEqual(minutes.title, "Automatisch aktualisiert")
        self.assertEqual(minutes.items.count(), 1)

    def test_existing_top_notes_can_be_changed_by_repeated_autosaves(self):
        self.client.login(username="leitung", password="pw")
        first_response = self.client.post(reverse("meeting_minutes_autosave_create"), self._post_data())
        minutes = MeetingMinutes.objects.get()
        item = minutes.items.get()
        data = self._post_data()
        data["items-INITIAL_FORMS"] = "1"
        data["items-0-id"] = str(first_response.json()["item_ids"]["items-0"])

        for notes in ("Beschluss geändert", "Beschluss erneut geändert"):
            data["items-0-notes"] = notes
            response = self.client.post(reverse("meeting_minutes_autosave_edit", args=[minutes.pk]), data)
            self.assertEqual(response.status_code, 200, response.content)

        item.refresh_from_db()
        self.assertEqual(item.notes, "Beschluss erneut geändert")

    def test_autosave_repairs_initial_forms_without_ids(self):
        self.client.login(username="leitung", password="pw")
        first_response = self.client.post(reverse("meeting_minutes_autosave_create"), self._post_data())
        minutes = MeetingMinutes.objects.get()
        data = self._post_data()
        data.update({
            "items-TOTAL_FORMS": "3",
            "items-INITIAL_FORMS": "3",
            "items-0-id": str(first_response.json()["item_ids"]["items-0"]),
            "items-1-id": "",
            "items-1-parent": "",
            "items-1-topic": "Neuer TOP 2",
            "items-1-notes": "",
            "items-1-due_date": "",
            "items-1-position": "2",
            "items-2-id": "",
            "items-2-parent": "",
            "items-2-topic": "Neuer TOP 3",
            "items-2-notes": "",
            "items-2-due_date": "",
            "items-2-position": "3",
        })

        response = self.client.post(reverse("meeting_minutes_autosave_edit", args=[minutes.pk]), data)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(list(minutes.items.order_by("position").values_list("topic", flat=True)), ["Sommerlager", "Neuer TOP 2", "Neuer TOP 3"])

    def test_autosave_returns_field_errors_for_invalid_draft(self):
        self.client.login(username="leitung", password="pw")
        data = self._post_data()
        data["items-0-topic"] = ""

        response = self.client.post(reverse("meeting_minutes_autosave_create"), data)

        self.assertEqual(response.status_code, 422)
        self.assertIn("items-0-topic", response.json()["errors"])
        self.assertIn("TOP 1 – Tagesordnungspunkt", response.json()["errors"]["items-0-topic"][0])
        self.assertFalse(MeetingMinutes.objects.exists())

    def test_autosave_returns_hidden_formset_management_errors(self):
        self.client.login(username="leitung", password="pw")
        data = self._post_data()
        del data["items-TOTAL_FORMS"]

        response = self.client.post(reverse("meeting_minutes_autosave_create"), data)

        self.assertEqual(response.status_code, 422)
        self.assertIn("items-TOTAL_FORMS", response.json()["errors"])
        self.assertFalse(MeetingMinutes.objects.exists())

    def test_first_autosave_ignores_new_top_deleted_before_another_is_added(self):
        self.client.login(username="leitung", password="pw")
        data = self._post_data()
        data.update({
            "items-TOTAL_FORMS": "2",
            "items-0-topic": "",
            "items-0-DELETE": "on",
            "items-1-parent": "",
            "items-1-topic": "Neuer TOP",
            "items-1-notes": "",
            "items-1-due_date": "",
            "items-1-position": "1",
        })

        response = self.client.post(reverse("meeting_minutes_autosave_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MeetingMinutesItem.objects.get().topic, "Neuer TOP")

    def test_autosave_does_not_report_errors_from_deleted_unsaved_forms(self):
        self.client.login(username="leitung", password="pw")
        data = self._post_data()
        data["title"] = ""
        data["items-0-topic"] = ""
        data["items-0-DELETE"] = "on"
        data["guests-0-name"] = ""
        data["guests-0-DELETE"] = "on"

        response = self.client.post(reverse("meeting_minutes_autosave_create"), data)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(set(response.json()["errors"]), {"title"})

    def test_autosave_updates_new_item_ids_in_open_form(self):
        self.client.login(username="leitung", password="pw")

        response = self.client.get(reverse("meeting_minutes_create"))

        self.assertContains(response, "Object.entries(result.item_ids||{})")
        self.assertContains(response, "id_items-INITIAL_FORMS")
        self.assertContains(response, "form.addEventListener('submit',async event=>")
        self.assertContains(response, "if(!await savePromise)return")
        self.assertContains(response, "HTMLFormElement.prototype.submit.call(form)")
        self.assertContains(response, 'id="save-minutes-draft"')
        self.assertContains(response, "window.location.href=form.dataset.detailUrl")
        self.assertContains(response, "window.location.assign(form.dataset.detailUrl)")
        self.assertContains(response, "field.disabled=true")
        self.assertContains(response, "function compactGuestForms()")
        self.assertContains(response, "const guestCards=compactGuestForms()")
        self.assertContains(response, "function compactTopForms()")
        self.assertContains(response, "const topCards=compactTopForms()")
        self.assertContains(response, "function ownTopFields(card,selector)")
        self.assertContains(response, 'id="autosave-error"')
        self.assertContains(response, "window.location.replace(result.edit_url)")

    def test_draft_can_be_saved_after_initial_autosave_without_duplicate_items(self):
        self.client.login(username="leitung", password="pw")
        autosave = self.client.post(reverse("meeting_minutes_autosave_create"), self._post_data())
        minutes = MeetingMinutes.objects.get()
        data = self._post_data("save")
        data["items-INITIAL_FORMS"] = "1"
        data["items-0-id"] = str(autosave.json()["item_ids"]["items-0"])

        response = self.client.post(reverse("meeting_minutes_edit", args=[minutes.pk]), data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(MeetingMinutes.objects.count(), 1)
        self.assertEqual(minutes.items.count(), 1)

    def test_minutes_can_be_published_after_initial_autosave_without_duplicates(self):
        self.client.login(username="leitung", password="pw")
        autosave = self.client.post(reverse("meeting_minutes_autosave_create"), self._post_data())
        minutes = MeetingMinutes.objects.get()
        data = self._post_data("publish")
        data["items-INITIAL_FORMS"] = "1"
        data["items-0-id"] = str(autosave.json()["item_ids"]["items-0"])

        response = self.client.post(reverse("meeting_minutes_edit", args=[minutes.pk]), data)

        self.assertEqual(response.status_code, 302)
        minutes.refresh_from_db()
        self.assertTrue(minutes.published)
        self.assertEqual(MeetingMinutes.objects.count(), 1)
        self.assertEqual(minutes.items.count(), 1)

    def test_new_guest_is_not_duplicated_when_draft_is_saved_after_autosave(self):
        self.client.login(username="leitung", password="pw")
        data = self._post_data()
        data["guests-0-name"] = "Alex"
        data["guests-0-note"] = "Gast"
        autosave = self.client.post(reverse("meeting_minutes_autosave_create"), data)
        minutes = MeetingMinutes.objects.get()
        data["guests-INITIAL_FORMS"] = "1"
        data["guests-0-id"] = str(autosave.json()["guest_ids"]["guests-0"])
        data["items-INITIAL_FORMS"] = "1"
        data["items-0-id"] = str(autosave.json()["item_ids"]["items-0"])

        response = self.client.post(reverse("meeting_minutes_edit", args=[minutes.pk]), data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(minutes.guests.values_list("name", flat=True)), ["Alex"])

    def test_new_top_after_autosave_can_be_autosaved_and_saved_as_draft(self):
        self.client.login(username="leitung", password="pw")
        first_autosave = self.client.post(reverse("meeting_minutes_autosave_create"), self._post_data())
        minutes = MeetingMinutes.objects.get()
        data = self._post_data()
        data["items-INITIAL_FORMS"] = "1"
        data["items-0-id"] = str(first_autosave.json()["item_ids"]["items-0"])
        data["items-TOTAL_FORMS"] = "2"
        data.update({
            "items-1-parent": "",
            "items-1-parent_reference": "",
            "items-1-topic": "Neuer TOP",
            "items-1-notes": "Nach Autosave ergänzt",
            "items-1-due_date": "",
            "items-1-position": "2",
        })
        second_autosave = self.client.post(reverse("meeting_minutes_autosave_edit", args=[minutes.pk]), data)
        data["items-INITIAL_FORMS"] = "2"
        data["items-1-id"] = str(second_autosave.json()["item_ids"]["items-1"])

        response = self.client.post(reverse("meeting_minutes_edit", args=[minutes.pk]), data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(minutes.items.values_list("topic", flat=True)), ["Sommerlager", "Neuer TOP"])

    def test_top_deleted_by_autosave_is_not_recreated_when_draft_is_saved(self):
        self.client.login(username="leitung", password="pw")
        data = self._post_data()
        data["items-TOTAL_FORMS"] = "2"
        data.update({
            "items-1-parent": "",
            "items-1-topic": "Wird gelöscht",
            "items-1-notes": "",
            "items-1-due_date": "",
            "items-1-position": "2",
        })
        self.client.post(reverse("meeting_minutes_create"), data)
        minutes = MeetingMinutes.objects.get()
        remaining, deleted = list(minutes.items.all())
        data["items-INITIAL_FORMS"] = "2"
        data["items-0-id"] = str(remaining.pk)
        data["items-1-id"] = str(deleted.pk)
        data["items-1-DELETE"] = "on"
        autosave = self.client.post(reverse("meeting_minutes_autosave_edit", args=[minutes.pk]), data)
        self.assertEqual(autosave.status_code, 200)
        self.assertEqual(list(minutes.items.values_list("topic", flat=True)), ["Sommerlager"])

        compacted = self._post_data()
        compacted["items-INITIAL_FORMS"] = "1"
        compacted["items-0-id"] = str(remaining.pk)
        response = self.client.post(reverse("meeting_minutes_edit", args=[minutes.pk]), compacted)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(minutes.items.values_list("topic", flat=True)), ["Sommerlager"])

    def test_deleted_top_stays_hidden_when_another_field_is_invalid(self):
        self.client.login(username="leitung", password="pw")
        self.client.post(reverse("meeting_minutes_create"), self._post_data())
        minutes = MeetingMinutes.objects.get()
        item = minutes.items.get()
        data = self._post_data()
        data["meeting_end"] = "2026-07-22T18:00"
        data["items-INITIAL_FORMS"] = "1"
        data["items-0-id"] = str(item.pk)
        data["items-0-DELETE"] = "on"

        response = self.client.post(reverse("meeting_minutes_edit", args=[minutes.pk]), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Das Sitzungsende darf nicht vor dem Beginn liegen.")
        self.assertNotContains(response, "Sommerlager")

    def test_autosave_switches_form_to_edit_url_without_action_field_collision(self):
        self.client.login(username="leitung", password="pw")

        response = self.client.get(reverse("meeting_minutes_create"))

        self.assertContains(response, "form.setAttribute('action',result.edit_url)")
        self.assertNotContains(response, "form.action=result.edit_url")

    def test_publish_and_accept_require_confirmation_modals(self):
        self.client.login(username="leitung", password="pw")

        create_response = self.client.get(reverse("meeting_minutes_create"))
        self.assertContains(create_response, 'data-bs-target="#publish-minutes-modal"')
        self.assertContains(create_response, "Möchtest du dieses Protokoll wirklich veröffentlichen?")

        self.client.post(reverse("meeting_minutes_create"), self._post_data("publish"))
        minutes = MeetingMinutes.objects.get()
        detail_response = self.client.get(reverse("meeting_minutes_detail", args=[minutes.pk]))
        self.assertContains(detail_response, 'data-bs-target="#accept-minutes-modal"')
        self.assertContains(detail_response, 'form="accept-minutes-form"')
        self.assertContains(detail_response, "Möchtest du bestätigen, dass du dieses Protokoll geprüft hast")

    def test_vote_sum_must_not_exceed_present_eligible_voters(self):
        other_user = User.objects.create_user(username="zweite-leitung", password="pw")
        Membership.objects.create(user=other_user, organization=self.organization, leiterrundenmitglied=True)
        self.client.login(username="leitung", password="pw")
        data = self._post_data()
        data.update({
            "items-0-voting_enabled": "on",
            "items-0-votes_yes": "2",
            "items-0-votes_no": "0",
            "items-0-votes_abstain": "0",
        })

        response = self.client.post(reverse("meeting_minutes_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "darf die Anzahl der anwesenden Stimmberechtigten (1) nicht überschreiten")
        self.assertFalse(MeetingMinutes.objects.exists())

        data["items-0-votes_yes"] = "1"
        response = self.client.post(reverse("meeting_minutes_create"), data)
        self.assertEqual(response.status_code, 302)
        minutes = MeetingMinutes.objects.get()
        self.assertEqual(minutes.items.get().votes_yes, 1)
        detail = self.client.get(reverse("meeting_minutes_detail", args=[minutes.pk]))
        pdf_html = render_to_string("leiterrunden/meeting_minutes_pdf.html", {"minutes": minutes, "minutes_tree": detail.context["minutes_tree"], "acceptance_rows": []})
        self.assertIn("Abstimmung:", pdf_html)
        self.assertIn("1 Ja", pdf_html)

    def test_detail_and_pdf_show_absent_members(self):
        absent_user = User.objects.create_user(username="abwesend", password="pw")
        absent_membership = Membership.objects.create(user=absent_user, organization=self.organization, leiterrundenmitglied=True)
        self.client.login(username="leitung", password="pw")
        self.client.post(reverse("meeting_minutes_create"), self._post_data("publish"))
        minutes = MeetingMinutes.objects.get()

        detail = self.client.get(reverse("meeting_minutes_detail", args=[minutes.pk]))
        self.assertContains(detail, "Abwesend")
        self.assertContains(detail, absent_membership.user.username)
        pdf_html = render_to_string("leiterrunden/meeting_minutes_pdf.html", {"minutes": minutes, "minutes_tree": detail.context["minutes_tree"], "acceptance_rows": detail.context["acceptance_rows"]})
        self.assertIn("Abwesend", pdf_html)
        self.assertIn(absent_membership.user.username, pdf_html)

    def test_edit_form_does_not_add_an_empty_top(self):
        self.client.login(username="leitung", password="pw")
        self.client.post(reverse("meeting_minutes_create"), self._post_data())
        minutes = MeetingMinutes.objects.get()

        response = self.client.get(reverse("meeting_minutes_edit", args=[minutes.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["formset"].total_form_count(), minutes.items.count())
        self.assertEqual(
            response.context["guest_formset"].total_form_count(),
            minutes.guests.count(),
        )
        self.assertContains(
            response,
            f'name="items-TOTAL_FORMS" value="{minutes.items.count()}"',
            html=False,
        )
        self.assertContains(
            response,
            f'name="guests-TOTAL_FORMS" value="{minutes.guests.count()}"',
            html=False,
        )

    def test_invalid_form_keeps_three_unsaved_top_levels_connected(self):
        self.client.login(username="leitung", password="pw")
        data = self._post_data("publish")
        data.update({
            "meeting_end": "2026-07-22T18:00",
            "items-TOTAL_FORMS": "3",
            "items-0-parent_reference": "",
            "items-1-parent": "",
            "items-1-parent_reference": "items-0",
            "items-1-topic": "Unter-TOP",
            "items-1-notes": "",
            "items-1-due_date": "",
            "items-1-position": "2",
            "items-2-parent": "",
            "items-2-parent_reference": "items-1",
            "items-2-topic": "Unter-Unter-TOP",
            "items-2-notes": "",
            "items-2-due_date": "",
            "items-2-position": "3",
        })

        response = self.client.post(reverse("meeting_minutes_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["formset"].forms[1]["parent_reference"].value(), "items-0")
        self.assertEqual(response.context["formset"].forms[2]["parent_reference"].value(), "items-1")
        self.assertContains(response, "cardsByReference.get(parentReference)")
        self.assertFalse(MeetingMinutes.objects.exists())
        self.assertContains(response, "Gast hinzufügen")
        self.assertContains(response, "Gast entfernen")

    def test_parent_top_with_child_can_be_deleted_and_replaced(self):
        self.client.login(username="leitung", password="pw")
        self.client.post(reverse("meeting_minutes_create"), self._post_data())
        minutes = MeetingMinutes.objects.get()
        parent = minutes.items.get()
        child = MeetingMinutesItem.objects.create(
            minutes=minutes,
            parent=parent,
            topic="Unterpunkt",
            position=2,
        )
        data = self._post_data()
        data.update({
            "items-TOTAL_FORMS": "3",
            "items-INITIAL_FORMS": "2",
            "items-0-id": str(parent.pk),
            "items-0-DELETE": "on",
            "items-1-id": str(child.pk),
            "items-1-DELETE": "on",
            "items-2-parent": "",
            "items-2-parent_reference": "",
            "items-2-topic": "Neuer TOP",
            "items-2-notes": "Neu angelegt",
            "items-2-due_date": "",
            "items-2-position": "1",
        })

        response = self.client.post(reverse("meeting_minutes_edit", args=[minutes.pk]), data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(minutes.items.values_list("topic", flat=True)), ["Neuer TOP"])

    def test_due_date_is_loaded_again_in_edit_form(self):
        self.client.login(username="leitung", password="pw")
        data = self._post_data()
        data["items-0-due_date"] = "2026-08-15"
        self.client.post(reverse("meeting_minutes_create"), data)
        minutes = MeetingMinutes.objects.get()

        response = self.client.get(reverse("meeting_minutes_edit", args=[minutes.pk]))

        self.assertEqual(minutes.items.get().due_date.isoformat(), "2026-08-15")
        self.assertContains(response, 'value="2026-08-15"', html=False)

    def test_minutes_list_can_be_searched_and_filtered(self):
        self.client.login(username="leitung", password="pw")
        self.client.post(reverse("meeting_minutes_create"), self._post_data())

        response = self.client.get(
            reverse("meeting_minutes_list"),
            {"q": "Sommerlager", "status": "draft", "date_from": "2026-07-01", "date_to": "2026-07-31"},
        )
        self.assertContains(response, "Juli-Sitzung")

        response = self.client.get(reverse("meeting_minutes_list"), {"q": "nicht vorhanden"})
        self.assertNotContains(response, "Juli-Sitzung")
        self.assertContains(response, "Keine Protokolle entsprechen den gewählten Filtern.")

    def test_due_top_notifications_use_responsible_members_or_full_leiterrunde(self):
        other_user = User.objects.create_user(
            username="verantwortlich",
            password="pw",
            email="verantwortlich@example.test",
        )
        other_membership = Membership.objects.create(
            user=other_user,
            organization=self.organization,
            leiterrundenmitglied=True,
        )
        self.client.login(username="leitung", password="pw")
        data = self._post_data("publish")
        data["items-0-due_date"] = timezone.localdate().isoformat()
        self.client.post(reverse("meeting_minutes_create"), data)
        minutes = MeetingMinutes.objects.get()
        responsible_item = minutes.items.get()
        responsible_item.responsible_members.add(other_membership)
        minutes.items.create(
            topic="Gemeinsame Aufgabe",
            notes="Alle informieren",
            due_date=timezone.localdate(),
            position=2,
        )
        draft = MeetingMinutes.objects.create(
            organization=self.organization,
            title="Nicht veröffentlichen",
            meeting_date=timezone.localdate(),
            created_by=self.user,
        )
        draft.items.create(
            topic="Entwurfsaufgabe",
            due_date=timezone.localdate(),
        )
        mail.outbox.clear()

        sent_count = send_due_meeting_minutes_items_today()

        self.assertEqual(sent_count, 2)
        messages_by_subject = {message.subject: message for message in mail.outbox}
        self.assertEqual(
            messages_by_subject["⏰ Heute fällig: Sommerlager"].to,
            ["verantwortlich@example.test"],
        )
        self.assertCountEqual(
            messages_by_subject["⏰ Heute fällig: Gemeinsame Aufgabe"].to,
            ["leitung@example.test", "verantwortlich@example.test"],
        )
        self.assertNotIn("Entwurfsaufgabe", " ".join(messages_by_subject))

    def test_published_minutes_are_locked_and_exportable(self):
        absent_user = User.objects.create_user(username="abwesend", password="pw", email="abwesend@example.test")
        Membership.objects.create(user=absent_user, organization=self.organization, leiterrundenmitglied=True)
        self.client.login(username="leitung", password="pw")
        self.assertEqual(self.client.post(reverse("meeting_minutes_create"), self._post_data("publish")).status_code, 302)
        minutes = MeetingMinutes.objects.get(); self.assertTrue(minutes.published); self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(minutes.published_by, self.user)
        self.assertContains(self.client.get(reverse("meeting_minutes_detail", args=[minutes.pk])), "Veröffentlicht von: leitung")
        self.assertCountEqual(mail.outbox[0].to, ["leitung@example.test", "abwesend@example.test"])
        self.assertIn("Protokoll prüfen und annehmen", mail.outbox[0].alternatives[0][0])
        self.assertEqual(self.client.get(reverse("meeting_minutes_edit", args=[minutes.pk])).status_code, 302)
        pdf = self.client.get(reverse("meeting_minutes_pdf", args=[minutes.pk])); self.assertEqual(pdf.status_code, 200); self.assertEqual(pdf["Content-Type"], "application/pdf"); self.assertEqual(pdf["Content-Disposition"], 'attachment; filename="juli-sitzung.pdf"')

    def test_acceptance_requires_majority_and_all_responsible_members(self):
        memberships = [self.membership]
        for index in range(2, 5):
            user = User.objects.create_user(
                username=f"leitung{index}",
                password="pw",
                email=f"leitung{index}@example.test",
            )
            memberships.append(
                Membership.objects.create(
                    user=user,
                    organization=self.organization,
                    leiterrundenmitglied=True,
                )
            )
        self.client.login(username="leitung", password="pw")
        self.client.post(reverse("meeting_minutes_create"), self._post_data("publish"))
        minutes = MeetingMinutes.objects.get()
        minutes.items.get().responsible_members.add(memberships[1])

        response = self.client.post(reverse("meeting_minutes_accept", args=[minutes.pk]))
        self.assertRedirects(response, reverse("meeting_minutes_detail", args=[minutes.pk]))
        for membership in (memberships[2], memberships[3]):
            MeetingMinutesAcceptance.objects.create(minutes=minutes, membership=membership)

        self.assertFalse(minutes.accepted)
        MeetingMinutesAcceptance.objects.create(minutes=minutes, membership=memberships[1])
        self.assertTrue(minutes.accepted)

    def test_minutes_can_be_duplicated_as_draft(self):
        self.client.login(username="leitung", password="pw")
        self.client.post(reverse("meeting_minutes_create"), self._post_data("publish"))
        source = MeetingMinutes.objects.get()
        response = self.client.post(reverse("meeting_minutes_duplicate", args=[source.pk]))
        duplicate = MeetingMinutes.objects.exclude(pk=source.pk).get()
        self.assertRedirects(response, reverse("meeting_minutes_edit", args=[duplicate.pk]))
        self.assertEqual(duplicate.title, "Juli-Sitzung – Duplikat")
        self.assertFalse(duplicate.published)
        self.assertIsNone(duplicate.replaces)
        self.assertEqual(duplicate.items.count(), source.items.count())
        self.assertEqual(duplicate.attendances.count(), source.attendances.count())

    def test_published_minutes_can_be_revised_with_history(self):
        self.client.login(username="leitung", password="pw")
        original_data = self._post_data("publish")
        original_data["guests-0-name"] = "Gastperson"
        original_data["guests-0-note"] = "Beratung"
        self.client.post(reverse("meeting_minutes_create"), original_data)
        source = MeetingMinutes.objects.get()
        response = self.client.post(reverse("meeting_minutes_revise", args=[source.pk]))
        revision = MeetingMinutes.objects.get(replaces=source)
        self.assertRedirects(response, reverse("meeting_minutes_edit", args=[revision.pk]))
        self.assertFalse(source.changed)
        self.assertEqual(revision.items.get().copied_from, source.items.get())

        data = self._post_data("publish")
        data["title"] = "Juli-Sitzung (korrigiert)"
        data["items-0-notes"] = "Material vollständig geprüft"
        data["items-0-due_date"] = "2026-08-15"
        data["items-INITIAL_FORMS"] = "1"
        data["items-0-id"] = str(revision.items.get().pk)
        data["guests-INITIAL_FORMS"] = "1"
        data["guests-0-id"] = str(revision.guests.get().pk)
        data["guests-0-name"] = "Gastperson"
        data["guests-0-note"] = "Beratung"
        self.client.post(reverse("meeting_minutes_edit", args=[revision.pk]), data)
        source.refresh_from_db()
        revision.refresh_from_db()
        self.assertTrue(revision.published)
        self.assertTrue(source.changed)
        detail = self.client.get(reverse("meeting_minutes_detail", args=[revision.pk]))
        self.assertContains(detail, "Neue Version")
        self.assertContains(detail, "Notizen/Beschluss:")
        pdf_html = render_to_string(
            "leiterrunden/meeting_minutes_pdf.html",
            {
                "minutes": revision,
                "minutes_tree": detail.context["minutes_tree"],
                "acceptance_rows": detail.context["acceptance_rows"],
            },
        )
        self.assertIn("Gastperson", pdf_html)
        self.assertIn("Neue Version", pdf_html)
        self.assertIn("Material vollständig geprüft", pdf_html)
        self.assertIn("Fällig am:", pdf_html)
        self.assertIn("15.08.2026", pdf_html)
