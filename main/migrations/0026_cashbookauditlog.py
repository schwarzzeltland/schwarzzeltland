from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0025_cashbookentry_entry_number"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CashBookAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_type", models.CharField(choices=[("cashbook", "Kassenbuch"), ("entry", "Eintrag")], max_length=20, verbose_name="Zieltyp")),
                ("action", models.CharField(choices=[("create", "Erstellt"), ("update", "Bearbeitet"), ("delete", "Gelöscht")], max_length=20, verbose_name="Aktion")),
                ("label", models.CharField(max_length=255, verbose_name="Objekt")),
                ("changes", models.JSONField(blank=True, default=dict, verbose_name="Änderungen")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Zeitpunkt")),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cashbook_audit_logs", to=settings.AUTH_USER_MODEL)),
                ("cashbook", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="audit_logs", to="main.cashbook")),
                ("entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_logs", to="main.cashbookentry")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cashbook_audit_logs", to="main.organization")),
            ],
            options={
                "verbose_name": "Kassenbuch-Änderung",
                "verbose_name_plural": "Kassenbuch-Änderungen",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
