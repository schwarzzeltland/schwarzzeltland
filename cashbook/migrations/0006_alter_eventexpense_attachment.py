from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cashbook", "0005_advancebudget_advance_entry")]

    operations = [
        migrations.AlterField(
            model_name="eventexpense",
            name="attachment",
            field=models.FileField(upload_to="cashbooks/event-expenses/%Y/%m/", verbose_name="Beleg"),
        ),
    ]
