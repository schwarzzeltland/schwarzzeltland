from django.db import migrations


def mark_manual_bank_entries_expected(apps, schema_editor):
    CashBookEntry = apps.get_model("cashbook", "CashBookEntry")
    CashBookEntry.objects.filter(
        source="manual",
        reconciliation_status="booked",
        bank_import_fingerprint="",
        bank_reconciled_at__isnull=True,
        cashbook__iban__gt="",
    ).update(reconciliation_status="expected")


def mark_manual_bank_entries_booked(apps, schema_editor):
    CashBookEntry = apps.get_model("cashbook", "CashBookEntry")
    CashBookEntry.objects.filter(
        source="manual",
        reconciliation_status="expected",
        bank_import_fingerprint="",
        bank_reconciled_at__isnull=True,
        cashbook__iban__gt="",
    ).update(reconciliation_status="booked")


class Migration(migrations.Migration):
    dependencies = [("cashbook", "0010_cashbookentry_eligible")]

    operations = [
        migrations.RunPython(
            mark_manual_bank_entries_expected,
            mark_manual_bank_entries_booked,
        ),
    ]
