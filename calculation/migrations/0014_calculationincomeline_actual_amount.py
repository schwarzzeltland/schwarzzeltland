from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calculation", "0013_calculationincomeline_category")]

    operations = [
        migrations.AddField(
            model_name="calculationincomeline",
            name="actual_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
    ]
