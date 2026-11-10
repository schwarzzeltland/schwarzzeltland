from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("cashbook", "0013_eventincome")]

    operations = [
        migrations.CreateModel(
            name="AdvanceBudgetTopUp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("booking_date", models.DateField(verbose_name="Buchungsdatum")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Betrag")),
                ("description", models.TextField(blank=True, verbose_name="Bemerkung")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("advance_budget", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="top_ups", to="cashbook.advancebudget", verbose_name="Vorschussbudget")),
                ("cashbook_entry", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="advance_budget_top_up", to="cashbook.cashbookentry", verbose_name="Kassenbucheintrag")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_advance_budget_top_ups", to=settings.AUTH_USER_MODEL, verbose_name="Erstellt von")),
            ],
            options={"ordering": ["booking_date", "id"]},
        ),
    ]
