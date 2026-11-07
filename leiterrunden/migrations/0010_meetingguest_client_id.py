import uuid

from django.db import migrations, models


def populate_client_ids(apps, schema_editor):
    MeetingGuest = apps.get_model("leiterrunden", "MeetingGuest")
    for guest in MeetingGuest.objects.filter(client_id__isnull=True).iterator():
        guest.client_id = uuid.uuid4()
        guest.save(update_fields=["client_id"])


class Migration(migrations.Migration):
    dependencies = [("leiterrunden", "0009_meetingminutesitem_client_id")]

    operations = [
        migrations.AddField(
            model_name="meetingguest",
            name="client_id",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(populate_client_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="meetingguest",
            name="client_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
