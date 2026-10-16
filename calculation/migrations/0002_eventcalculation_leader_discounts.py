from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calculation", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="eventcalculation",
            name="leader_discounts",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
    ]
