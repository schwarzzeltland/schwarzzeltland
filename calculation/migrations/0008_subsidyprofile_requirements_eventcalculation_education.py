from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calculation", "0007_eventcalculation_simple_participants")]

    operations = [
        migrations.AddField(model_name="subsidyprofile", name="education_qs_exempt_from_minimum_days", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="subsidyprofile", name="minimum_eligible_participants", field=models.PositiveIntegerField(default=7)),
        migrations.AddField(model_name="subsidyprofile", name="minimum_event_days", field=models.PositiveIntegerField(default=2)),
        migrations.AddField(model_name="eventcalculation", name="is_education_or_qs", field=models.BooleanField(default=False)),
    ]
