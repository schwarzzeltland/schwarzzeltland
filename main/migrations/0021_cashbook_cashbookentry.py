from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0045_alter_trip_description"),
        ("main", "0020_membership_knowledge_manager"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="pro5",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="CashBook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("currency", models.CharField(default="EUR", max_length=3)),
                ("opening_balance", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cashbooks", to="main.organization")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="CashBookEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entry_type", models.CharField(choices=[("income", "Einnahme"), ("expense", "Ausgabe")], max_length=10)),
                ("booking_date", models.DateField(verbose_name="Buchungsdatum")),
                ("receipt_date", models.DateField(blank=True, null=True, verbose_name="Belegdatum")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("title", models.CharField(max_length=255, verbose_name="Titel")),
                ("category", models.CharField(blank=True, max_length=255, verbose_name="Kategorie")),
                ("counterparty", models.CharField(blank=True, max_length=255, verbose_name="Gegenpartei")),
                ("reference", models.CharField(blank=True, max_length=255, verbose_name="Referenz")),
                ("description", models.TextField(blank=True, verbose_name="Beschreibung")),
                ("attachment", models.FileField(blank=True, null=True, upload_to="cashbooks/", verbose_name="Beleg")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cashbook", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="main.cashbook")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cashbook_entries", to=settings.AUTH_USER_MODEL)),
                ("trip", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cashbook_entries", to="events.trip")),
            ],
            options={"ordering": ["booking_date", "id"]},
        ),
    ]
