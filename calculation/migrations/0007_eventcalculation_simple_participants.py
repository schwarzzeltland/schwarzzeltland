from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calculation", "0006_calculationline_calculation_mode")]
    operations = [
        migrations.AddField(model_name="eventcalculation", name="total_participants", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="eventcalculation", name="leader_count", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="eventcalculation", name="leader_discount_per_person", field=models.DecimalField(decimal_places=2, default=0, max_digits=8)),
    ]
