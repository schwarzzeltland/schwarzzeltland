from django.db import migrations, models


def assign_entry_numbers(apps, schema_editor):
    CashBookEntry = apps.get_model("main", "CashBookEntry")
    cashbook_ids = (
        CashBookEntry.objects.order_by()
        .values_list("cashbook_id", flat=True)
        .distinct()
    )
    for cashbook_id in cashbook_ids:
        entries = CashBookEntry.objects.filter(cashbook_id=cashbook_id).order_by("booking_date", "id")
        for index, entry in enumerate(entries, start=1):
            CashBookEntry.objects.filter(pk=entry.pk).update(entry_number=index)


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0024_alter_cashbookentry_attachment"),
    ]

    operations = [
        migrations.AddField(
            model_name="cashbookentry",
            name="entry_number",
            field=models.PositiveIntegerField(blank=True, editable=False, null=True, verbose_name="Nummer"),
        ),
        migrations.RunPython(assign_entry_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="cashbookentry",
            name="entry_number",
            field=models.PositiveIntegerField(editable=False, verbose_name="Nummer"),
        ),
        migrations.AddConstraint(
            model_name="cashbookentry",
            constraint=models.UniqueConstraint(fields=("cashbook", "entry_number"), name="unique_cashbook_entry_number"),
        ),
    ]
