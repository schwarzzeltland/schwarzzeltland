from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("cashbook", "0004_advancebudget_eventexpense")]

    operations = [
        migrations.AddField(
            model_name="advancebudget",
            name="advance_entry",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="advance_budget_payment", to="cashbook.cashbookentry", verbose_name="Auszahlung"),
        ),
    ]
