from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cashbook", "0008_cashbookreceiptrequest")]

    operations = [
        migrations.AddField(
            model_name="eventexpense",
            name="eligible",
            field=models.BooleanField(default=True, verbose_name="Förderfähig"),
        ),
    ]
