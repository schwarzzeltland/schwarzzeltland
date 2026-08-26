from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("cashbook", "0003_alter_reimbursementrequest_recipient_iban_and_more"), ("events", "0045_alter_trip_description")]

    operations = [
        migrations.CreateModel(
            name="AdvanceBudget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Bezeichnung")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Budget")),
                ("settled_at", models.DateTimeField(blank=True, null=True, verbose_name="Abgerechnet am")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("assigned_to", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assigned_advance_budgets", to="main.membership", verbose_name="Zugewiesener Planer")),
                ("cashbook", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="advance_budgets", to="cashbook.cashbook", verbose_name="Zielkassenbuch")),
                ("settled_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="settled_advance_budgets", to=settings.AUTH_USER_MODEL, verbose_name="Abgerechnet von")),
                ("settlement_entry", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="advance_budget_settlement", to="cashbook.cashbookentry", verbose_name="Sammelbuchung")),
                ("trip", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="advance_budgets", to="events.trip", verbose_name="Veranstaltung")),
            ], options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="EventExpense",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("expense_date", models.DateField(verbose_name="Belegdatum")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Betrag")),
                ("title", models.CharField(max_length=255, verbose_name="Titel")),
                ("category", models.CharField(blank=True, max_length=255, verbose_name="Kategorie")),
                ("counterparty", models.CharField(blank=True, max_length=255, verbose_name="Zahlungspartner")),
                ("reference", models.CharField(blank=True, max_length=255, verbose_name="Belegnummer / Referenz")),
                ("description", models.TextField(blank=True, verbose_name="Beschreibung")),
                ("attachment", models.FileField(blank=True, null=True, upload_to="cashbooks/event-expenses/%Y/%m/", verbose_name="Beleg")),
                ("status", models.CharField(choices=[("pending", "Offen"), ("approved", "Freigegeben"), ("rejected", "Abgelehnt")], default="pending", max_length=10, verbose_name="Status")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
                ("advance_budget", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="expenses", to="cashbook.advancebudget", verbose_name="Vorschussbudget")),
                ("cashbook", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="event_expenses", to="cashbook.cashbook", verbose_name="Kassenbuch")),
                ("cashbook_entry", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="event_expense", to="cashbook.cashbookentry", verbose_name="Kassenbucheintrag")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="event_expenses", to=settings.AUTH_USER_MODEL, verbose_name="Erstellt von")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_event_expenses", to=settings.AUTH_USER_MODEL, verbose_name="Freigegeben von")),
                ("trip", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="event_expenses", to="events.trip", verbose_name="Veranstaltung")),
            ], options={"ordering": ["-expense_date", "-id"]},
        ),
    ]
