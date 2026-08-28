import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


PREFIX = "enc:"


def _fernet():
    secret = settings.CALDAV_ENCRYPTION_SECRET
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value):
    if not value or value.startswith(PREFIX):
        return value
    return PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value):
    if not value or not value.startswith(PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken as error:
        raise ValueError("Das gespeicherte CalDAV-Passwort kann nicht entschlüsselt werden.") from error
