from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cashbook", "0009_eventexpense_eligible")]

    operations = [
        migrations.CreateModel(
            name="EventSettlementEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("eligible", models.BooleanField(default=True, verbose_name="Förderfähig")),
                ("cashbook_entry", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="settlement_metadata", to="cashbook.cashbookentry")),
            ],
        ),
    ]
