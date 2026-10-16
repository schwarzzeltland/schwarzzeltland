from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calculation", "0002_eventcalculation_leader_discounts")]
    operations = [
        migrations.AddField(model_name="eventcalculation", name="participant_fee", field=models.DecimalField(decimal_places=2, default=0, max_digits=8)),
        migrations.AddField(model_name="eventcalculation", name="non_member_participants", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="eventcalculation", name="non_member_fee", field=models.DecimalField(decimal_places=2, default=0, max_digits=8)),
    ]
