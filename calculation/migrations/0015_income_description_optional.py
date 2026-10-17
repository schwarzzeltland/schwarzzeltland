from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calculation", "0014_calculationincomeline_actual_amount")]

    operations = [
        migrations.AlterField(
            model_name="calculationincomeline",
            name="description",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
