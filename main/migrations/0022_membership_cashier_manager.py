from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0021_cashbook_cashbookentry"),
    ]

    operations = [
        migrations.AddField(
            model_name="membership",
            name="cashier_manager",
            field=models.BooleanField(default=False, verbose_name="Kassenwart"),
        ),
    ]
