from django.test import TestCase
from django.contrib.auth.models import User

from buildings.models import Material, MaterialContainer, StockMaterial, StoragePlan, StorageArea, Construction
from buildings.forms import AddMaterialStockForm, ConstructionMaterialForm, MaterialContainerContentsForm, \
    StockMaterialForm, MaterialContainerForm, ImportConstructionForm
from buildings.views import _load_qr_pdf_font

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

    def test_qr_pdf_font_supports_german_characters(self):
        font = _load_qr_pdf_font(18)
        self.assertIsNotNone(font.getmask("Küchenkiste auf dem Dachboden – groß").getbbox())

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
        self.assertIn("tom-select-location", stock_form.fields["storage_area"].widget.attrs["class"])

    def test_new_material_can_be_created_inside_container(self):
        response = self.client.post(f"/buildings/material/create?org={self.organization.pk}", {
            "name": "Neue Plane",
            "description": "",
            "count": 3,
            "location_type": "container",
            "container": self.container.pk,
            "storage_place": "",
            "storage_area": "",
            "weight": "0",
        })

        self.assertEqual(response.status_code, 302)
        stock = StockMaterial.objects.get(material__name="Neue Plane", organization=self.organization)
        self.assertEqual(stock.container, self.container)
        self.assertEqual(stock.storage_place, self.container.stock_storage_place)

    def test_storage_plan_area_can_be_assigned_and_highlighted(self):
        plan = StoragePlan.objects.create(organization=self.organization, name="Dachboden", image="storage_plans/dachboden.png")
        response = self.client.post(
            f"/buildings/material/storage-plans/{plan.pk}/?org={self.organization.pk}",
            {"name": "Regal links", "x": "10", "y": "20", "width": "30", "height": "15"},
        )
        self.assertEqual(response.status_code, 302)
        area = plan.areas.get(name="Regal links")
        self.container.storage_area = area
        self.container.save()
        self.stock.storage_area = area
        self.stock.save()

        container_response = self.client.get(f"/buildings/material/containers/{self.container.pk}/?org={self.organization.pk}")
        plan_response = self.client.get(f"/buildings/material/storage-plans/{plan.pk}/?org={self.organization.pk}&area={area.pk}")
        show_response = self.client.get(f"/buildings/material/storage-plans/{plan.pk}/show/?org={self.organization.pk}&area={area.pk}")

        self.assertContains(container_response, "Auf Lagerplan anzeigen")
        self.assertContains(container_response, f"/buildings/material/storage-plans/{plan.pk}/show/")
        self.assertContains(plan_response, "storage-area-active")
        self.assertContains(plan_response, "Regal links")
        self.assertContains(plan_response, 'draggable="false"')
        self.assertContains(plan_response, "dragstart")
        self.assertContains(plan_response, "max-height:70vh")
        self.assertContains(show_response, "storage-highlight")
        self.assertContains(show_response, "max-height:75vh")
        self.assertContains(show_response, "@media(max-width:576px)")
        self.assertContains(show_response, ".storage-highlight span{display:none}")
        self.assertNotContains(show_response, "Neuen Bereich speichern")
        self.assertNotContains(show_response, "Plan löschen")

    def test_storage_plan_delete_uses_confirmation_view(self):
        plan = StoragePlan.objects.create(organization=self.organization, name="Zu löschen", image="storage_plans/delete.png")

        confirmation = self.client.get(f"/buildings/material/storage-plans/{plan.pk}/delete/?org={self.organization.pk}")

        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, "wirklich gelöscht werden")
        self.assertTrue(StoragePlan.objects.filter(pk=plan.pk).exists())

        response = self.client.post(f"/buildings/material/storage-plans/{plan.pk}/delete/?org={self.organization.pk}")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(StoragePlan.objects.filter(pk=plan.pk).exists())

    def test_storage_area_choices_are_limited_to_current_organization(self):
        own_plan = StoragePlan.objects.create(organization=self.organization, name="Eigen", image="storage_plans/eigen.png")
        own_area = StorageArea.objects.create(plan=own_plan, name="Eigenes Regal", x=0, y=0, width=10, height=10)
        other_user = User.objects.create_user(username="anderes-lager", password="pw")
        other_org = other_user.organization_set.first()
        other_plan = StoragePlan.objects.create(organization=other_org, name="Fremd", image="storage_plans/fremd.png")
        other_area = StorageArea.objects.create(plan=other_plan, name="Fremdes Regal", x=0, y=0, width=10, height=10)

        stock_form = StockMaterialForm(instance=self.stock, organization=self.organization)
        container_form = MaterialContainerForm(instance=self.container, organization=self.organization)

        self.assertIn(own_area, stock_form.fields["storage_area"].queryset)
        self.assertNotIn(other_area, stock_form.fields["storage_area"].queryset)
        self.assertIn(own_area, container_form.fields["storage_area"].queryset)
        self.assertNotIn(other_area, container_form.fields["storage_area"].queryset)

    def test_stock_location_choice_keeps_only_selected_location_type(self):
        plan = StoragePlan.objects.create(organization=self.organization, name="Lager", image="storage_plans/lager.png")
        area = StorageArea.objects.create(plan=plan, name="Regal A", x=0, y=0, width=10, height=10)
        form = StockMaterialForm({
            "count": 5,
            "location_type": "plan",
            "storage_place": "Alter Text",
            "container": self.container.pk,
            "storage_area": area.pk,
            "condition_healthy": 5,
            "condition_medium_healthy": 0,
            "condition_broke": 0,
            "material_condition_description": "",
        }, instance=self.stock, organization=self.organization)

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertIsNone(saved.container)
        self.assertEqual(saved.storage_area, area)
        self.assertEqual(saved.storage_place, "Lager / Regal A")

    def test_container_location_choice_uses_free_text_or_plan_but_not_both(self):
        plan = StoragePlan.objects.create(organization=self.organization, name="Lager", image="storage_plans/lager.png")
        area = StorageArea.objects.create(plan=plan, name="Regal B", x=0, y=0, width=10, height=10)
        form = MaterialContainerForm({
            "name": self.container.name,
            "description": "",
            "location_type": "free",
            "storage_place": "Keller links",
            "storage_area": area.pk,
        }, instance=self.container, organization=self.organization)

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertIsNone(saved.storage_area)
        self.assertEqual(saved.storage_place, "Keller links")

    def test_material_stock_form_uses_structured_card_layout(self):
        response = self.client.get(f"/buildings/material?org={self.organization.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Material einsortieren")
        self.assertContains(response, "Einsortieren schließen")
        self.assertContains(response, 'data-close-label="Einsortieren schließen"')
        self.assertContains(response, "Material suchen und auswählen")
        self.assertContains(response, "tom-select-location")
        self.assertContains(response, "tom-select.complete.min.js")
        self.assertContains(response, "dropdownParent: 'body'")
        self.assertNotContains(response, "select2.min.js")
        self.assertContains(response, "Bei Auswahl einer Kiste wird deren Lagerort automatisch")
        self.assertContains(response, "Art des Lagerorts")
        self.assertContains(response, "Bereich im Lagerplan")
        self.assertContains(response, "Freier Lagerort")

    def test_add_own_construction_uses_tom_select_and_keeps_option_groups(self):
        own = Construction.objects.create(owner=self.organization, name="Eigene Jurte")
        basic = Construction.objects.create(owner=None, name="Grundjurte")
        form = ImportConstructionForm(organization=self.organization)

        self.assertIn("tom-select", form.fields["construction"].widget.attrs["class"])
        self.assertEqual(form.fields["construction"].choices[1][0], "Eigene Konstruktionen")
        self.assertEqual(form.fields["construction"].choices[2][0], "Grundkonstruktionen")

        response = self.client.get(f"/buildings/construction?org={self.organization.pk}")
        self.assertContains(response, own.name)
        self.assertContains(response, basic.name)
        self.assertContains(response, "tom-select.complete.min.js")
        self.assertNotContains(response, "select2.min.js")

    def test_ownerless_private_material_is_basic_material_in_tom_selects(self):
        basic = Material.objects.create(owner=None, public=False, name="Grundplane")

        for form in (
            AddMaterialStockForm(organization=self.organization),
            ConstructionMaterialForm(organization=self.organization),
        ):
            material_field = form.fields["material"]
            self.assertIn("tom-select", material_field.widget.attrs["class"])
            self.assertIn(basic, material_field.queryset)
            self.assertIn((basic.id, basic.name), material_field.choices[2][1])

        response = self.client.get(f"/buildings/construction/edit/?org={self.organization.pk}")
        self.assertContains(response, basic.name)
        self.assertContains(response, "tom-select.complete.min.js")
        self.assertNotContains(response, "select2.min.js")

    def test_material_list_groups_stock_locations_by_material(self):
        StockMaterial.objects.create(
            organization=self.organization, material=self.material, count=16,
            storage_place="Dachboden / 2", condition_healthy=14,
            condition_medium_healthy=1, condition_broke=1,
        )
        response = self.client.get(f"/buildings/material?org={self.organization.pk}")
        group = next(group for group in response.context["material_groups"] if group["material"] == self.material)
        self.assertEqual(group["total_count"], 21)
        self.assertEqual(group["condition_healthy"], 19)
        self.assertEqual(group["condition_medium_healthy"], 1)
        self.assertEqual(group["condition_broke"], 1)
        self.assertEqual(len(group["stocks"]), 2)

    def test_single_stock_group_displays_location_in_overview(self):
        response = self.client.get(f"/buildings/material?org={self.organization.pk}")
        self.assertContains(response, self.stock.effective_storage_place)
        self.assertNotContains(response, "1 Lagerorte")
        self.assertContains(response, f'/buildings/material/edit/{self.stock.pk}/')
        self.assertContains(response, f'/buildings/material/delete/{self.stock.pk}/')

    def test_material_overview_links_stock_location_to_highlighted_plan(self):
        plan = StoragePlan.objects.create(organization=self.organization, name="Lager", image="storage_plans/lager.png")
        area = StorageArea.objects.create(plan=plan, name="Regal C", x=0, y=0, width=10, height=10)
        self.container.storage_area = area
        self.container.save()

        response = self.client.get(f"/buildings/material?org={self.organization.pk}")

        self.assertContains(response, f"/buildings/material/storage-plans/{plan.pk}/show/?area={area.pk}")
        self.assertContains(response, "Auf Lagerplan anzeigen")
