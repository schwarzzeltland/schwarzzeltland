from django.db import migrations, models
from main.secrets import encrypt_secret


def encrypt_existing_passwords(apps, schema_editor):
    Organization = apps.get_model("main", "Organization")
    for organization in Organization.objects.exclude(caldav_password="").iterator():
        organization.caldav_password = encrypt_secret(organization.caldav_password)
        organization.save(update_fields=["caldav_password"])


class Migration(migrations.Migration):
    dependencies = [("main", "0031_organization_caldav")]
    operations = [
        migrations.AlterField(model_name="organization", name="caldav_password", field=models.TextField(blank=True, verbose_name="CalDAV-Passwort")),
        migrations.RunPython(encrypt_existing_passwords, migrations.RunPython.noop),
    ]
