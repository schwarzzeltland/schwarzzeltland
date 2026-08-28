from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0046_packedstockmaterial")]
    operations = [
        migrations.AddField(model_name="trip", name="sync_to_caldav", field=models.BooleanField(default=False, verbose_name="Mit Organisationskalender synchronisieren")),
        migrations.AddField(model_name="trip", name="caldav_uid", field=models.CharField(blank=True, editable=False, max_length=255)),
    ]
