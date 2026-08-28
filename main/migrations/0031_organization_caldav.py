from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0030_alter_organization_default_checklist")]
    operations = [
        migrations.AddField(model_name="organization", name="caldav_calendar_url", field=models.URLField(blank=True, verbose_name="CalDAV-Kalender-URL")),
        migrations.AddField(model_name="organization", name="caldav_username", field=models.CharField(blank=True, max_length=255, verbose_name="CalDAV-Benutzername")),
        migrations.AddField(model_name="organization", name="caldav_password", field=models.CharField(blank=True, max_length=255, verbose_name="CalDAV-Passwort")),
    ]
