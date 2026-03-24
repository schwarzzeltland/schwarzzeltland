import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.utils._os import safe_join

from buildings.models import Construction, Material
from main.models import Organization


def _is_org_member(user, organization):
    if not user.is_authenticated or organization is None:
        return False
    return organization.members.filter(pk=user.pk).exists()


def _resolve_cached_source(path):
    path_obj = Path(path)
    parts = path_obj.parts
    if len(parts) < 4 or parts[0] != "CACHE" or parts[1] != "images":
        return None

    folder_name = parts[2]
    source_stem = parts[3]

    if folder_name not in {"constructions", "materials", "users"}:
        return None

    prefix = f"{folder_name}/"
    for candidate in _iter_known_paths_for_prefix(prefix):
        if Path(candidate).stem == source_stem:
            return candidate
    return None


def _iter_known_paths_for_prefix(prefix):
    if prefix == "constructions/":
        return Construction.objects.exclude(image="").exclude(image__isnull=True).values_list("image", flat=True)
    if prefix == "materials/":
        return Material.objects.exclude(image="").exclude(image__isnull=True).values_list("image", flat=True)
    if prefix == "users/":
        return Organization.objects.exclude(image="").exclude(image__isnull=True).values_list("image", flat=True)
    return []


def _has_access_to_media(user, source_path):
    if source_path.startswith("constructions/"):
        construction = Construction.objects.filter(image=source_path).select_related("owner").first()
        if construction is None:
            return False
        if construction.public or construction.owner is None:
            return True
        return _is_org_member(user, construction.owner)

    if source_path.startswith("materials/"):
        material = Material.objects.filter(image=source_path).select_related("owner").first()
        if material is None:
            return False
        if material.public or material.owner is None:
            return True
        return _is_org_member(user, material.owner)

    if source_path.startswith("users/"):
        organization = Organization.objects.filter(image=source_path).first()
        if organization is None:
            return False
        return _is_org_member(user, organization)

    return False


def serve_protected_media(request, path):
    normalized_path = path.replace("\\", "/").lstrip("/")
    source_path = normalized_path
    if normalized_path.startswith("CACHE/"):
        source_path = _resolve_cached_source(normalized_path)
        if source_path is None:
            raise Http404("Datei nicht gefunden.")

    if not _has_access_to_media(request.user, source_path):
        raise Http404("Datei nicht gefunden.")

    try:
        absolute_path = safe_join(settings.MEDIA_ROOT, normalized_path)
    except ValueError as exc:
        raise Http404("Ungültiger Pfad.") from exc

    file_path = Path(absolute_path)
    if not file_path.is_file():
        raise Http404("Datei nicht gefunden.")

    content_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(file_path.open("rb"), content_type=content_type)
