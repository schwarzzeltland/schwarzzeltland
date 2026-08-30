from django.test import TestCase
from django.contrib.auth.models import User
from django.core import mail
from django.utils import timezone
from datetime import timedelta
import base64
from unittest.mock import MagicMock, patch

from buildings.models import Material, StockMaterial, StoragePlan, StorageArea
from events.models import PackedStockMaterial, Trip, TripMaterial, Location, EventPlanningChecklistItem
from events.forms import ImportLocationForm
from events.caldav import sync_trip_to_caldav
from main.secrets import decrypt_secret, encrypt_secret
from main.models import Membership
from main.tasks import send_due_checklist_items_today
from leiterrunden.models import MeetingMinutes, MeetingMinutesItemCompletion

# Create your tests here.


class TripMaterialPackingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="eventmanager", password="pw")
        self.organization = self.user.organization_set.first()
        self.organization.membership_set.filter(user=self.user).update(event_manager=True)
        self.material = Material.objects.create(name="Doppelzeltbahn", owner=self.organization)
        self.first_stock = StockMaterial.objects.create(organization=self.organization, material=self.material, count=5, storage_place="JK1", condition_healthy=5)
        self.second_stock = StockMaterial.objects.create(organization=self.organization, material=self.material, count=5, storage_place="JK2", condition_healthy=5)
        self.trip = Trip.objects.create(owner=self.organization, name="Testlager", start_date=timezone.now(), end_date=timezone.now() + timedelta(days=2))
        TripMaterial.objects.create(trip=self.trip, material=self.material, count=8)
        self.client.login(username="eventmanager", password="pw")

    def test_packing_stock_locations_turns_row_green_when_requirement_is_met(self):
        toggle_url = f"/events/change-packed-stock-material/?org={self.organization.pk}"
        response = self.client.post(toggle_url, {"trip_id": self.trip.pk, "stock_material_id": self.first_stock.pk, "packed": "true"})
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f"/events/trip/check_trip_material/{self.trip.pk}/?org={self.organization.pk}")
        material_row = response.context["available_materials"][0]
        self.assertEqual(material_row["packed_quantity"], 5)
        self.assertFalse(material_row["packed_sufficient"])

        self.client.post(toggle_url, {"trip_id": self.trip.pk, "stock_material_id": self.second_stock.pk, "packed": "true"})
        response = self.client.get(f"/events/trip/check_trip_material/{self.trip.pk}/?org={self.organization.pk}")
        material_row = response.context["available_materials"][0]
        self.assertEqual(material_row["packed_quantity"], 10)
        self.assertTrue(material_row["packed_sufficient"])
        self.assertContains(response, "table-success")
        self.assertEqual(PackedStockMaterial.objects.filter(trip=self.trip, packed=True).count(), 2)

    def test_packing_list_links_stock_to_highlighted_storage_plan(self):
        plan = StoragePlan.objects.create(organization=self.organization, name="Lager", image="storage_plans/lager.png")
        area = StorageArea.objects.create(plan=plan, name="Regal", x=0, y=0, width=10, height=10)
        self.first_stock.storage_area = area
        self.first_stock.save(update_fields=["storage_area"])

        response = self.client.get(f"/events/trip/check_trip_material/{self.trip.pk}/?org={self.organization.pk}")

        self.assertContains(response, f"/buildings/material/storage-plans/{plan.pk}/show/?area={area.pk}")
        self.assertContains(response, "Auf Lagerplan anzeigen")

    def test_import_location_uses_tom_select_and_keeps_groups(self):
        Location.objects.create(name="Öffentlicher Platz", owner=None, public=True)
        form = ImportLocationForm(organization=self.organization)

        self.assertIn("tom-select", form.fields["location"].widget.attrs["class"])
        self.assertEqual(form.fields["location"].choices[1][0], "Öffentliche Orte")

        response = self.client.get(f"/events/location?org={self.organization.pk}")
        self.assertContains(response, "tom-select.complete.min.js")
        self.assertContains(response, "Ort suchen und auswählen")
        self.assertNotContains(response, "select2.min.js")

    def test_trip_edit_uses_tom_select_for_location_constructions_and_material(self):
        response = self.client.get(f"/events/trip/edit/{self.trip.pk}/?org={self.organization.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tom-select.complete.min.js")
        self.assertContains(response, "Ort suchen")
        self.assertContains(response, "Konstruktion suchen")
        self.assertContains(response, "Material suchen")
        self.assertContains(response, "initializeTripSelects")
        self.assertNotContains(response, "select2.min.js")

    def test_default_checklist_due_dates_are_relative_to_trip_start(self):
        self.organization.default_checklist = [
            {"title": "Vorbereitung", "days_from_start": -7},
            {"title": "Am Start", "days_from_start": 0},
            {"title": "Nachbereitung", "days_from_start": 2},
            "Bestehendes To-do ohne Termin",
        ]
        self.organization.save(update_fields=["default_checklist"])
        start = timezone.now() + timedelta(days=30)

        trip = Trip.objects.create(
            owner=self.organization, name="Termin-Test", start_date=start, end_date=start + timedelta(days=3),
        )

        items = {item.title: item for item in EventPlanningChecklistItem.objects.filter(trip=trip)}
        self.assertEqual(items["Vorbereitung"].due_date, start - timedelta(days=7))
        self.assertEqual(items["Am Start"].due_date, start)
        self.assertEqual(items["Nachbereitung"].due_date, start + timedelta(days=2))
        self.assertIsNone(items["Bestehendes To-do ohne Termin"].due_date)

    def test_due_todo_notifies_only_responsible_or_all_planners_as_fallback(self):
        second_user = User.objects.create_user(username="zweiter-planer", email="zwei@example.test", password="pw")
        Membership.objects.create(user=second_user, organization=self.organization, event_manager=True)
        self.user.email = "eins@example.test"
        self.user.save(update_fields=["email"])
        self.trip.planners.add(self.user, second_user)
        due_date = timezone.now()
        EventPlanningChecklistItem.objects.create(trip=self.trip, title="Persönlich", due_date=due_date, responsible=second_user)

        send_due_checklist_items_today()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["zwei@example.test"])

        mail.outbox.clear()
        EventPlanningChecklistItem.objects.filter(title="Persönlich").update(done=True)
        EventPlanningChecklistItem.objects.create(trip=self.trip, title="Ohne Verantwortung", due_date=due_date)
        send_due_checklist_items_today()
        self.assertEqual(len(mail.outbox), 1)
        self.assertCountEqual(mail.outbox[0].to, ["eins@example.test", "zwei@example.test"])

    def test_todo_responsible_choices_are_limited_to_planners_and_material_managers(self):
        self.organization.pro3 = True
        self.organization.save(update_fields=["pro3"])
        planner = User.objects.create_user(username="auswahl-planer", password="pw")
        outsider = User.objects.create_user(username="keine-auswahl", password="pw")
        Membership.objects.create(user=planner, organization=self.organization, event_manager=True)
        Membership.objects.create(user=outsider, organization=self.organization)
        self.trip.planners.add(planner)

        trip_response = self.client.get(f"/events/trips/{self.trip.pk}/checklist/?org={self.organization.pk}")
        self.assertContains(trip_response, f'<option value="{planner.pk}">auswahl-planer</option>', html=False)
        self.assertNotContains(trip_response, f'<option value="{outsider.pk}">keine-auswahl</option>', html=False)

        material_response = self.client.get(f"/main/organization_material/checklist/?org={self.organization.pk}")
        self.assertContains(material_response, f'<option value="{self.user.pk}">eventmanager</option>', html=False)
        self.assertNotContains(material_response, f'<option value="{planner.pk}">auswahl-planer</option>', html=False)

        response = self.client.post(f"/events/trips/{self.trip.pk}/checklist/add/?org={self.organization.pk}", {"title": "Zugeordnet", "responsible": planner.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EventPlanningChecklistItem.objects.get(title="Zugeordnet").responsible, planner)

    def test_personal_todo_list_is_available_to_leiterrunden_member_and_shows_only_tops(self):
        self.organization.pro3 = True
        self.organization.pro6 = True
        self.organization.save(update_fields=["pro3", "pro6"])
        membership = self.organization.membership_set.get(user=self.user)
        membership.leiterrundenmitglied = True
        membership.event_manager = False
        membership.material_manager = False
        membership.save(update_fields=["leiterrundenmitglied", "event_manager", "material_manager"])
        EventPlanningChecklistItem.objects.create(trip=self.trip, title="Mein Veranstaltungs-To-do", responsible=self.user)
        minutes = MeetingMinutes.objects.create(organization=self.organization, title="Leiterrunde", meeting_date=timezone.localdate(), published=True, created_by=self.user)
        top = minutes.items.create(topic="Mein TOP", position=1)
        top.responsible_members.add(membership)

        response = self.client.get(f"/main/todos/?org={self.organization.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Mein Veranstaltungs-To-do")
        self.assertContains(response, "Mein TOP")
        self.assertNotContains(response, "<strong>Checklisten</strong>", html=False)

        toggle = self.client.post(f"/main/todos/meeting-items/{top.pk}/toggle/?org={self.organization.pk}")
        self.assertEqual(toggle.status_code, 200)
        self.assertTrue(MeetingMinutesItemCompletion.objects.get(item=top, user=self.user).completed)
        top.refresh_from_db()
        self.assertEqual(top.topic, "Mein TOP")

        open_top = minutes.items.create(topic="Noch offener TOP", position=2)
        open_top.responsible_members.add(membership)
        response = self.client.get(f"/main/todos/?org={self.organization.pk}")
        content = response.content.decode()
        self.assertLess(content.index("Noch offener TOP"), content.index("Mein TOP"))

    def test_personal_todo_list_for_material_manager_hides_event_and_leiterrunde_items(self):
        self.organization.pro3 = True
        self.organization.pro6 = True
        self.organization.save(update_fields=["pro3", "pro6"])
        membership = self.organization.membership_set.get(user=self.user)
        membership.event_manager = False
        membership.material_manager = True
        membership.leiterrundenmitglied = False
        membership.save(update_fields=["event_manager", "material_manager", "leiterrundenmitglied"])
        EventPlanningChecklistItem.objects.create(trip=self.trip, title="Fremdes Veranstaltungs-To-do", responsible=self.user)
        EventPlanningChecklistItem.objects.create(organization=self.organization, title="Mein Material-To-do", responsible=self.user)
        minutes = MeetingMinutes.objects.create(organization=self.organization, title="Leiterrunde", meeting_date=timezone.localdate(), published=True, created_by=self.user)
        top = minutes.items.create(topic="Fremder TOP", position=1)
        top.responsible_members.add(membership)

        response = self.client.get(f"/main/todos/?org={self.organization.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mein Material-To-do")
        self.assertNotContains(response, "Fremdes Veranstaltungs-To-do")
        self.assertNotContains(response, "Fremder TOP")
        self.assertNotContains(response, "<strong>Leiterrunden-TOPs</strong>", html=False)

    @patch("events.caldav.urlopen")
    def test_trip_is_created_updated_and_removed_in_configured_caldav_calendar(self, urlopen):
        urlopen.return_value = MagicMock(__enter__=MagicMock(), __exit__=MagicMock(return_value=False))
        self.organization.caldav_calendar_url = "https://calendar.example.test/calendars/team/events/"
        self.organization.caldav_username = "team"
        self.organization.caldav_password = encrypt_secret("secret")
        self.assertNotEqual(self.organization.caldav_password, "secret")
        self.assertEqual(decrypt_secret(self.organization.caldav_password), "secret")
        self.organization.save(update_fields=["caldav_calendar_url", "caldav_username", "caldav_password"])
        self.trip.sync_to_caldav = True
        self.trip.description = "Interne und nicht öffentliche Informationen"
        self.trip.location = Location.objects.create(name="Privater Treffpunkt", owner=self.organization)
        self.trip.save(update_fields=["sync_to_caldav", "description", "location"])

        self.assertTrue(sync_trip_to_caldav(self.trip))
        self.trip.refresh_from_db()
        uid = self.trip.caldav_uid
        first_request = urlopen.call_args.args[0]
        self.assertEqual(first_request.get_method(), "PUT")
        self.assertIn(uid, first_request.full_url)
        self.assertIn(b"SUMMARY:Testlager", first_request.data)
        self.assertEqual(base64.b64decode(first_request.headers["Authorization"].split()[1]), b"team:secret")
        self.assertNotIn(b"DESCRIPTION", first_request.data)
        self.assertNotIn(b"LOCATION", first_request.data)

        self.trip.name = "Aktualisiertes Lager"
        self.trip.save(update_fields=["name"])
        sync_trip_to_caldav(self.trip)
        self.assertEqual(self.trip.caldav_uid, uid)
        self.assertIn(uid, urlopen.call_args.args[0].full_url)

        self.trip.sync_to_caldav = False
        self.trip.save(update_fields=["sync_to_caldav"])
        sync_trip_to_caldav(self.trip)
        self.trip.refresh_from_db()
        self.assertEqual(urlopen.call_args.args[0].get_method(), "DELETE")
        self.assertEqual(self.trip.caldav_uid, "")
