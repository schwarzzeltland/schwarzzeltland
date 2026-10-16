from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calculation", "0010_eventcalculation_guest_subsidies")]

    operations = [
        migrations.AddField(
            model_name="eventcalculation",
            name="actual_income_manual",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
    ]
