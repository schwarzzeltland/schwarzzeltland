from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("leiterrunden", "0002_meeting_schedule_attendance_guests_and_top_hierarchy"),
    ]

    operations = [
        migrations.AddField(
            model_name="meetingminutes",
            name="replaces",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="replacement",
                to="leiterrunden.meetingminutes",
                verbose_name="Ersetzt Protokoll",
            ),
        ),
    ]
