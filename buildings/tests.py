from django.test import TestCase
from django.contrib.auth.models import User

from buildings.models import Material, MaterialContainer, StockMaterial
from buildings.forms import MaterialContainerContentsForm, StockMaterialForm

# Create your tests here.


class MaterialContainerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="materialwart", password="pw")
        self.organization = self.user.organization_set.first()
        self.organization.membership_set.filter(user=self.user).update(material_manager=True)
        self.material = Material.objects.create(name="Doppelzeltbahn", owner=self.organization)
        self.stock = StockMaterial.objects.create(
            organization=self.organization, material=self.material, count=5,
            storage_place="Dachboden / 3 / JK1", condition_healthy=5,
        )
        self.container = MaterialContainer.objects.create(
            organization=self.organization, name="JK1", storage_place="Dachboden / 3",
        )
        self.stock.container = self.container
        self.stock.save(update_fields=["container"])
        self.client.login(username="materialwart", password="pw")

    def test_container_keeps_stock_available_and_derives_location(self):
        self.assertEqual(StockMaterial.objects.filter(material=self.material).count(), 1)
        self.assertEqual(StockMaterial.objects.filter(material=self.material).first().count, 5)
        self.assertEqual(self.stock.effective_storage_place, "Dachboden / 3 / JK1")
        self.assertEqual(self.stock.storage_place, "Dachboden / 3 / JK1")

    def test_changing_container_location_updates_stored_stock_location(self):
        self.container.storage_place = "Keller / Regal 2"
        self.container.save()
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.storage_place, "Keller / Regal 2 / JK1")

    def test_scan_selects_container_organization(self):
        response = self.client.get(f"/buildings/material/scan/{self.container.scan_code}/")
        self.assertRedirects(
            response,
            f"/buildings/material/containers/{self.container.pk}/?org={self.organization.pk}",
            fetch_redirect_response=False,
        )

    def test_qr_endpoint_returns_png(self):
        response = self.client.get(f"/buildings/material/containers/{self.container.pk}/qr/?org={self.organization.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))

    def test_selected_containers_can_be_exported_as_qr_pdf(self):
        second = MaterialContainer.objects.create(
            organization=self.organization,
            name="Sehr lange Doppelzeltbahnen-Materialkistenbezeichnung für den Dachboden",
            storage_place="Dachboden / Bereich 3 / hinteres großes Regal",
        )
        response = self.client.post(
            f"/buildings/material/containers/qr-sheet/?org={self.organization.pk}",
            {"containers": [self.container.pk, second.pk], "output_type": "with_contents"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_qr_creation_has_three_output_types_and_is_separate_from_list(self):
        response = self.client.get(f"/buildings/material/containers/qr-sheet/?org={self.organization.pk}")
        self.assertContains(response, "Nur QR-Code")
        self.assertContains(response, "QR-Code mit Kistenname und Lagerort")
        self.assertContains(response, "QR-Code mit Kistenname, Lagerort und Inhalt")
        self.assertContains(response, "Alle Kisten auswählen")
        self.assertContains(response, "Auswahl aufheben")
        response = self.client.get(f"/buildings/material/containers/?org={self.organization.pk}")
        self.assertContains(response, "QR-Codes erstellen")
        self.assertNotContains(response, "container-checkbox")

    def test_container_detail_links_to_stock_material(self):
        response = self.client.get(f"/buildings/material/containers/{self.container.pk}/?org={self.organization.pk}")
        self.assertContains(response, f"/buildings/material/edit/{self.stock.pk}/")

    def test_container_list_can_search_by_contained_material(self):
        other = MaterialContainer.objects.create(organization=self.organization, name="Werkzeugkiste")
        response = self.client.get(f"/buildings/material/containers/?org={self.organization.pk}&search=Doppelzeltbahn")
        self.assertContains(response, "JK1")
        self.assertNotContains(response, other.name)
        self.assertNotContains(response, "Gesamtmenge")

    def test_deleting_container_preserves_stock(self):
        response = self.client.post(f"/buildings/material/containers/{self.container.pk}/delete/?org={self.organization.pk}")
        self.assertEqual(response.status_code, 302)
        self.stock.refresh_from_db()
        self.assertIsNone(self.stock.container)

    def test_container_and_stock_selections_are_searchable_select_fields(self):
        contents_form = MaterialContainerContentsForm(organization=self.organization, container=self.container)
        self.assertEqual(contents_form.fields["stock_items"].widget.input_type, "select")
        self.assertIn("select2-stock-items", contents_form.fields["stock_items"].widget.attrs["class"])
        stock_form = StockMaterialForm(instance=self.stock, organization=self.organization)
        self.assertIn(self.container, stock_form.fields["container"].queryset)
        self.assertEqual(stock_form.fields["container"].label_from_instance(self.container), "JK1")

    def test_material_stock_form_uses_structured_card_layout(self):
        response = self.client.get(f"/buildings/material?org={self.organization.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Material einsortieren")
        self.assertContains(response, "Material suchen und auswählen")
        self.assertContains(response, "Bei Auswahl einer Kiste wird deren Lagerort automatisch")
