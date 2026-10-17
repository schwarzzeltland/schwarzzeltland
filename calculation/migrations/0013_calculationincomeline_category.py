from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calculation", "0012_calculationincomeline")]

    operations = [
        migrations.AddField(
            model_name="calculationincomeline",
            name="category",
            field=models.CharField(default="", max_length=255),
        ),
    ]
