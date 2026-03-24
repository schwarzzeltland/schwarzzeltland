from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cashbook", "0001_initial"),
        ("main", "0027_merge_20260324_2115"),
    ]

    operations = [
        migrations.DeleteModel(name="CashBookAuditLog"),
        migrations.DeleteModel(name="CashBookEntry"),
        migrations.DeleteModel(name="CashBook"),
    ]
