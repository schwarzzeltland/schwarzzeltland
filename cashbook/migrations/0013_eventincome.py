from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("cashbook", "0012_alter_cashbookreceiptrequest_entry_and_more")]

    operations = [
        migrations.CreateModel(
            name="EventIncome",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("income_date", models.DateField(verbose_name="Einnahmedatum")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Betrag")),
                ("title", models.CharField(max_length=255, verbose_name="Titel")),
                ("category", models.CharField(blank=True, max_length=255, verbose_name="Kategorie")),
                ("counterparty", models.CharField(blank=True, max_length=255, verbose_name="Zahlung von")),
                ("reference", models.CharField(blank=True, max_length=255, verbose_name="Referenz")),
                ("description", models.TextField(blank=True, verbose_name="Beschreibung")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("advance_budget", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="incomes", to="cashbook.advancebudget", verbose_name="Vorschussbudget")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="event_incomes", to=settings.AUTH_USER_MODEL, verbose_name="Erstellt von")),
                ("trip", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="event_incomes", to="events.trip", verbose_name="Veranstaltung")),
            ],
            options={"ordering": ["-income_date", "-id"]},
        ),
    ]
