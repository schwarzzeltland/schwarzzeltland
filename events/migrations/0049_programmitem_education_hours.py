from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0048_eventplanningchecklistitem_responsible")]
    operations = [
        migrations.AddField(
            model_name="programmitem",
            name="education_hours",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name="Bildungsstunden"),
        ),
    ]
