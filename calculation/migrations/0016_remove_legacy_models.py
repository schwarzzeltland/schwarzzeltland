from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("calculation", "0015_income_description_optional")]

    operations = [
        migrations.DeleteModel(name="CalculationParticipantGroup"),
        migrations.DeleteModel(name="CalculationTransport"),
    ]
