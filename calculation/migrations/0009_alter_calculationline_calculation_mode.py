from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calculation", "0008_subsidyprofile_requirements_eventcalculation_education")]

    operations = [
        migrations.AlterField(
            model_name="calculationline",
            name="calculation_mode",
            field=models.CharField(
                choices=[
                    ("fixed", "Fixer Betrag"),
                    ("per_person", "Betrag pro Person"),
                    ("per_person_day", "Betrag pro Person und Tag"),
                ],
                default="fixed",
                max_length=20,
            ),
        ),
    ]
