from django.db import migrations, models

import main.models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0023_alter_cashbook_active_alter_cashbook_currency_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cashbookentry",
            name="attachment",
            field=models.FileField(blank=True, null=True, upload_to=main.models.cashbook_attachment_upload_to, verbose_name="Beleg"),
        ),
    ]
