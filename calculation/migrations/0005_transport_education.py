from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("calculation", "0004_calculationparticipantgroup")]
    operations = [
        migrations.CreateModel(name="CalculationEducationSession", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("topic", models.CharField(max_length=255)), ("hours", models.DecimalField(decimal_places=2, default=0, max_digits=6)), ("calculation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="education_sessions", to="calculation.eventcalculation"))]),
        migrations.CreateModel(name="CalculationTransport", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("mode", models.CharField(choices=[("bus", "Bus"), ("car", "PKW"), ("train", "Zug"), ("other", "Sonstiges")], default="other", max_length=10)), ("description", models.CharField(blank=True, max_length=255)), ("persons", models.PositiveIntegerField(default=0)), ("distance_km", models.DecimalField(decimal_places=1, default=0, max_digits=8)), ("rate_per_km", models.DecimalField(decimal_places=2, default=0, max_digits=8)), ("fixed_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)), ("actual_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)), ("calculation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transports", to="calculation.eventcalculation"))]),
    ]
