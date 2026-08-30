from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("leiterrunden", "0007_meetingminutes_editors"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="MeetingMinutesItemCompletion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("completed", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="personal_completions", to="leiterrunden.meetingminutesitem")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meeting_item_completions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("item", "user"), name="unique_meeting_item_completion")]},
        ),
    ]
