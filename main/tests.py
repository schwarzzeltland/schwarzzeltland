import shutil
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from buildings.models import Construction, StoragePlan
from cashbook.models import CashBook, CashBookEntry
from main.forms import OrganizationForm

TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ProtectedMediaTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.owner_user = User.objects.create_user(username="owner", password="pw")
        self.other_user = User.objects.create_user(username="other", password="pw")

        self.owner_org = self.owner_user.organization_set.first()
        self.other_org = self.other_user.organization_set.first()

    def _write_media_file(self, relative_path, content=b"file-data"):
        file_path = Path(self.settings.MEDIA_ROOT) / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

    @property
    def settings(self):
        from django.conf import settings
        return settings

    def test_public_construction_image_is_accessible_anonymously(self):
        image_path = "constructions/public.jpg"
        self._write_media_file(image_path)
        Construction.objects.create(name="Public", owner=self.owner_org, public=True, image=image_path)

        response = self.client.get(f"/uploads/{image_path}")

        self.assertEqual(response.status_code, 200)

    def test_private_construction_image_requires_membership(self):
        image_path = "constructions/private.jpg"
        self._write_media_file(image_path)
        Construction.objects.create(name="Private", owner=self.owner_org, public=False, image=image_path)

        anonymous_response = self.client.get(f"/uploads/{image_path}")
        self.assertEqual(anonymous_response.status_code, 404)

        self.client.login(username="owner", password="pw")
        member_response = self.client.get(f"/uploads/{image_path}")
        self.assertEqual(member_response.status_code, 200)

    def test_organization_image_is_not_public(self):
        image_path = "users/org.jpg"
        self._write_media_file(image_path)
        self.owner_org.image = image_path
        self.owner_org.save(update_fields=["image"])

        anonymous_response = self.client.get(f"/uploads/{image_path}")
        self.assertEqual(anonymous_response.status_code, 404)

        self.client.login(username="other", password="pw")
        outsider_response = self.client.get(f"/uploads/{image_path}")
        self.assertEqual(outsider_response.status_code, 404)

        self.client.login(username="owner", password="pw")
        member_response = self.client.get(f"/uploads/{image_path}")
        self.assertEqual(member_response.status_code, 200)

    def test_storage_plan_image_is_accessible_only_to_organization_members(self):
        image_path = "storage_plans/lager.png"
        self._write_media_file(image_path, b"plan-image")
        StoragePlan.objects.create(organization=self.owner_org, name="Lager", image=image_path)

        anonymous_response = self.client.get(f"/uploads/{image_path}")
        self.assertEqual(anonymous_response.status_code, 404)

        self.client.login(username="other", password="pw")
        outsider_response = self.client.get(f"/uploads/{image_path}")
        self.assertEqual(outsider_response.status_code, 404)

        self.client.login(username="owner", password="pw")
        member_response = self.client.get(f"/uploads/{image_path}")
        self.assertEqual(member_response.status_code, 200)

    def test_cached_public_construction_thumbnail_inherits_access(self):
        source_path = "constructions/public-thumb.jpg"
        cache_path = "CACHE/images/constructions/public-thumb/preview.webp"
        self._write_media_file(source_path)
        self._write_media_file(cache_path)
        Construction.objects.create(name="Public Thumb", owner=self.owner_org, public=True, image=source_path)

        response = self.client.get(f"/uploads/{cache_path}")

        self.assertEqual(response.status_code, 200)

    def test_cashbook_list_requires_pro5(self):
        self.client.login(username="owner", password="pw")

        response = self.client.get("/cashbooks/")

        self.assertEqual(response.status_code, 403)

        self.owner_org.pro5 = True
        self.owner_org.save(update_fields=["pro5"])
        owner_membership = self.owner_org.membership_set.get(user=self.owner_user)
        owner_membership.cashier_manager = True
        owner_membership.save(update_fields=["cashier_manager"])

        response = self.client.get("/cashbooks/")

        self.assertEqual(response.status_code, 200)

    def test_leiterrundenmitglied_role_is_available_with_pro5(self):
        self.owner_org.pro5 = True
        self.owner_org.pro6 = False
        self.owner_org.save(update_fields=["pro5", "pro6"])
        self.client.login(username="owner", password="pw")

        response = self.client.get("/main/organization")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leiterrundenmitglied")
        self.assertContains(response, 'name="leiterrundenmitglied"')

    def test_leiterrundenmitglied_role_is_available_with_pro6(self):
        self.owner_org.pro5 = False
        self.owner_org.pro6 = True
        self.owner_org.save(update_fields=["pro5", "pro6"])
        self.client.login(username="owner", password="pw")

        response = self.client.get("/main/organization")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leiterrundenmitglied")
        self.assertContains(response, 'name="leiterrundenmitglied"')

    def test_organization_form_parses_default_todo_day_offsets(self):
        form = OrganizationForm({
            "name": self.owner_org.name,
            "recipientcode": self.owner_org.recipientcode,
            "default_checklist": "Anmeldung schließen | -14\nMaterial packen | -1\nNachbereitung | 3\nOhne Termin",
        }, instance=self.owner_org)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["default_checklist"], [
            {"title": "Anmeldung schließen", "days_from_start": -14},
            {"title": "Material packen", "days_from_start": -1},
            {"title": "Nachbereitung", "days_from_start": 3},
            {"title": "Ohne Termin", "days_from_start": None},
        ])

    def test_cashbook_attachment_requires_cashier_membership(self):
        attachment_path = "cashbooks/receipt.pdf"
        self._write_media_file(attachment_path)
        self.owner_org.pro5 = True
        self.owner_org.save(update_fields=["pro5"])
        owner_membership = self.owner_org.membership_set.get(user=self.owner_user)
        owner_membership.cashier_manager = True
        owner_membership.save(update_fields=["cashier_manager"])
        cashbook = CashBook.objects.create(organization=self.owner_org, name="Hauptkasse")
        CashBookEntry.objects.create(
            cashbook=cashbook,
            entry_type=CashBookEntry.TYPE_EXPENSE,
            booking_date="2026-03-24",
            amount="12.50",
            title="Testbeleg",
            attachment=attachment_path,
            created_by=self.owner_user,
        )

        anonymous_response = self.client.get(f"/uploads/{attachment_path}")
        self.assertEqual(anonymous_response.status_code, 404)

        self.client.login(username="other", password="pw")
        outsider_response = self.client.get(f"/uploads/{attachment_path}")
        self.assertEqual(outsider_response.status_code, 404)

        self.client.login(username="owner", password="pw")
        cashier_response = self.client.get(f"/uploads/{attachment_path}")
        self.assertEqual(cashier_response.status_code, 200)

    def test_public_help_remains_available_anonymously(self):
        response = self.client.get("/main/help")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Was heißt das im Detail?")
        self.assertNotContains(response, "Diese Dokumentation ist auf eure freigeschalteten Funktionen")

    def test_authenticated_help_is_organization_and_feature_specific(self):
        self.owner_org.pro2 = True
        self.owner_org.pro6 = True
        self.owner_org.save(update_fields=["pro2", "pro6"])
        self.client.login(username="owner", password="pw")

        response = self.client.get(f"/main/help?org={self.owner_org.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Hilfe für {self.owner_org.name}")
        self.assertContains(response, "Materialkisten und QR-Codes")
        self.assertContains(response, "Lagerpläne")
        self.assertContains(response, 'id="vakanzen"', html=False)
        self.assertContains(response, 'id="protokolle"', html=False)
        self.assertNotContains(response, 'id="einkauf"', html=False)
        self.assertNotContains(response, 'id="programm"', html=False)
        self.assertNotContains(response, "Rezeptzutaten bündeln")
