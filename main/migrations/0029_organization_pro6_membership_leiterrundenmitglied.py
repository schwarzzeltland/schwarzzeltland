from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0028_delete_legacy_cashbook_models")]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="pro6",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="membership",
            name="leiterrundenmitglied",
            field=models.BooleanField(default=False, verbose_name="Leiterrundenmitglied"),
        ),
    ]
