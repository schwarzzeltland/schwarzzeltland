import main.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0029_organization_pro6_membership_leiterrundenmitglied")]

    operations = [
        migrations.AlterField(
            model_name="organization",
            name="default_checklist",
            field=models.JSONField(blank=True, default=main.models.default_checklist_items, verbose_name="Standard-To-dos bei neuen Veranstaltungen"),
        ),
    ]
