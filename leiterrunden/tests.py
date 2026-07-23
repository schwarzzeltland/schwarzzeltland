from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from leiterrunden.models import MeetingMinutes, MeetingMinutesAcceptance
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
        self.assertFalse(MeetingMinutes.objects.get().published)

    def test_edit_form_does_not_add_an_empty_top(self):
        self.client.login(username="leitung", password="pw")
        self.client.post(reverse("meeting_minutes_create"), self._post_data())
        minutes = MeetingMinutes.objects.get()

        response = self.client.get(reverse("meeting_minutes_edit", args=[minutes.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["formset"].total_form_count(), minutes.items.count())
        self.assertContains(
            response,
            f'name="items-TOTAL_FORMS" value="{minutes.items.count()}"',
            html=False,
        )

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
        self.assertCountEqual(mail.outbox[0].to, ["leitung@example.test", "abwesend@example.test"])
        self.assertIn("Protokoll prüfen und annehmen", mail.outbox[0].alternatives[0][0])
        self.assertEqual(self.client.get(reverse("meeting_minutes_edit", args=[minutes.pk])).status_code, 302)
        pdf = self.client.get(reverse("meeting_minutes_pdf", args=[minutes.pk])); self.assertEqual(pdf.status_code, 200); self.assertEqual(pdf["Content-Type"], "application/pdf")

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
        self.client.post(reverse("meeting_minutes_create"), self._post_data("publish"))
        source = MeetingMinutes.objects.get()
        response = self.client.post(reverse("meeting_minutes_revise", args=[source.pk]))
        revision = MeetingMinutes.objects.get(replaces=source)
        self.assertRedirects(response, reverse("meeting_minutes_edit", args=[revision.pk]))
        self.assertFalse(source.changed)

        data = self._post_data("publish")
        data["title"] = "Juli-Sitzung (korrigiert)"
        data["items-INITIAL_FORMS"] = "1"
        data["items-0-id"] = str(revision.items.get().pk)
        self.client.post(reverse("meeting_minutes_edit", args=[revision.pk]), data)
        source.refresh_from_db()
        revision.refresh_from_db()
        self.assertTrue(revision.published)
        self.assertTrue(source.changed)
