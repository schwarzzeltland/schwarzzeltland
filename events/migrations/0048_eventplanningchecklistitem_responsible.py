from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("events", "0047_trip_caldav"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="eventplanningchecklistitem", name="responsible", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="responsible_checklist_items", to=settings.AUTH_USER_MODEL, verbose_name="Verantwortlich")),
    ]
