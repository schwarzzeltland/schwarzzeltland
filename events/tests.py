from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from buildings.models import Material, StockMaterial
from events.models import PackedStockMaterial, Trip, TripMaterial

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
