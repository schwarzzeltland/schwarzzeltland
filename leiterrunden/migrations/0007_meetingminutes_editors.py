from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_editors(apps, schema_editor):
    MeetingMinutes = apps.get_model("leiterrunden", "MeetingMinutes")
    for minutes in MeetingMinutes.objects.all().iterator():
        minutes.updated_by_id = minutes.created_by_id
        if minutes.published:
            minutes.published_by_id = minutes.created_by_id
        minutes.save(update_fields=["updated_by", "published_by"])


class Migration(migrations.Migration):
    dependencies = [("leiterrunden", "0006_meetingminutesitem_voting"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="meetingminutes", name="updated_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_meeting_minutes", to=settings.AUTH_USER_MODEL, verbose_name="Zuletzt bearbeitet von")),
        migrations.AddField(model_name="meetingminutes", name="published_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="published_meeting_minutes", to=settings.AUTH_USER_MODEL, verbose_name="Veröffentlicht von")),
        migrations.RunPython(backfill_editors, migrations.RunPython.noop),
    ]
