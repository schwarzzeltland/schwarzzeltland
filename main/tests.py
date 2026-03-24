import shutil
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from buildings.models import Construction

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

    def test_cached_public_construction_thumbnail_inherits_access(self):
        source_path = "constructions/public-thumb.jpg"
        cache_path = "CACHE/images/constructions/public-thumb/preview.webp"
        self._write_media_file(source_path)
        self._write_media_file(cache_path)
        Construction.objects.create(name="Public Thumb", owner=self.owner_org, public=True, image=source_path)

        response = self.client.get(f"/uploads/{cache_path}")

        self.assertEqual(response.status_code, 200)
