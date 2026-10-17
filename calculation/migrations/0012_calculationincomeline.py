from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("calculation", "0011_eventcalculation_actual_income_manual")]

    operations = [
        migrations.CreateModel(
            name="CalculationIncomeLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(max_length=255)),
                ("planned_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("calculation", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="income_lines", to="calculation.eventcalculation")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
