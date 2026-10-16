from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("calculation", "0003_eventcalculation_participant_fees")]
    operations = [
        migrations.CreateModel(
            name="CalculationParticipantGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("count", models.PositiveIntegerField(default=0)),
                ("fee_per_person", models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ("discount_per_person", models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ("eligible_for_subsidy", models.BooleanField(default=True)),
                ("calculation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participant_groups", to="calculation.eventcalculation")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
