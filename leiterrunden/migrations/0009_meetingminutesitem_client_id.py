import uuid

from django.db import migrations, models


def populate_client_ids(apps, schema_editor):
    MeetingMinutesItem = apps.get_model("leiterrunden", "MeetingMinutesItem")
    for item in MeetingMinutesItem.objects.filter(client_id__isnull=True).iterator():
        item.client_id = uuid.uuid4()
        item.save(update_fields=["client_id"])


class Migration(migrations.Migration):
    dependencies = [("leiterrunden", "0008_meetingminutesitemcompletion")]

    operations = [
        migrations.AddField(
            model_name="meetingminutesitem",
            name="client_id",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(populate_client_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="meetingminutesitem",
            name="client_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
