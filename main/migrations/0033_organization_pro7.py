from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0032_alter_organization_caldav_password")]
    operations = [migrations.AddField(model_name="organization", name="pro7", field=models.BooleanField(default=False))]
