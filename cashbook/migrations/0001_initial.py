from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import cashbook.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("events", "0045_alter_trip_description"),
        ("main", "0027_merge_20260324_2115"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CashBook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Name")),
                ("description", models.TextField(blank=True, verbose_name="Beschreibung")),
                ("currency", models.CharField(default="EUR", max_length=3, verbose_name="Währung")),
                ("opening_balance", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Startsaldo")),
                ("active", models.BooleanField(default=True, verbose_name="Aktiv")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cashbook_cashbooks", to="main.organization", verbose_name="Organisation")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="CashBookAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_type", models.CharField(choices=[("cashbook", "Kassenbuch"), ("entry", "Eintrag")], max_length=20, verbose_name="Zieltyp")),
                ("action", models.CharField(choices=[("create", "Erstellt"), ("update", "Bearbeitet"), ("delete", "Gelöscht")], max_length=20, verbose_name="Aktion")),
                ("label", models.CharField(max_length=255, verbose_name="Objekt")),
                ("changes", models.JSONField(blank=True, default=dict, verbose_name="Änderungen")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Zeitpunkt")),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cashbook_cashbook_audit_logs", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cashbook_audit_logs_v2", to="main.organization")),
            ],
            options={"verbose_name": "Kassenbuch-Änderung", "verbose_name_plural": "Kassenbuch-Änderungen", "ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="CashBookEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entry_number", models.PositiveIntegerField(blank=True, editable=False, null=True, verbose_name="Nummer")),
                ("entry_type", models.CharField(choices=[("income", "Einnahme"), ("expense", "Ausgabe")], max_length=10, verbose_name="Art")),
                ("booking_date", models.DateField(verbose_name="Buchungsdatum")),
                ("receipt_date", models.DateField(blank=True, null=True, verbose_name="Belegdatum")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Betrag")),
                ("title", models.CharField(max_length=255, verbose_name="Titel")),
                ("category", models.CharField(blank=True, max_length=255, verbose_name="Kategorie")),
                ("counterparty", models.CharField(blank=True, max_length=255, verbose_name="Zahlungspartner")),
                ("reference", models.CharField(blank=True, max_length=255, verbose_name="Belegnummer / Referenz")),
                ("description", models.TextField(blank=True, verbose_name="Beschreibung")),
                ("attachment", models.FileField(blank=True, null=True, upload_to=cashbook.models.cashbook_attachment_upload_to, verbose_name="Beleg")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cashbook", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="cashbook.cashbook", verbose_name="Kassenbuch")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cashbook_cashbook_entries", to=settings.AUTH_USER_MODEL, verbose_name="Erstellt von")),
                ("trip", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cashbook_cashbook_entries", to="events.trip", verbose_name="Veranstaltung")),
            ],
            options={"ordering": ["booking_date", "id"]},
        ),
        migrations.AddField(
            model_name="cashbookauditlog",
            name="cashbook",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="audit_logs", to="cashbook.cashbook"),
        ),
        migrations.AddField(
            model_name="cashbookauditlog",
            name="entry",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_logs", to="cashbook.cashbookentry"),
        ),
        migrations.AddConstraint(
            model_name="cashbookentry",
            constraint=models.UniqueConstraint(fields=("cashbook", "entry_number"), name="cashbook_unique_entry_number"),
        ),
    ]
