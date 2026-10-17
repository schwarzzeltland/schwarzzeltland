from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0049_programmitem_education_hours")]

    operations = [
        migrations.AddField(
            model_name="tripvacancy",
            name="eligible",
            field=models.BooleanField(default=True, verbose_name="Förderfähig"),
        ),
    ]
