from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calculation", "0005_transport_education")]
    operations = [migrations.AddField(model_name="calculationline", name="calculation_mode", field=models.CharField(choices=[("fixed", "Fixer Betrag"), ("per_person", "Betrag pro Person")], default="fixed", max_length=12))]
