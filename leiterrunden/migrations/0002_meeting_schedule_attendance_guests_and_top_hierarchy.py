from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("leiterrunden", "0001_initial")]

    operations = [
        migrations.AddField(model_name="meetingminutes", name="meeting_start", field=models.DateTimeField(blank=True, null=True, verbose_name="Sitzungsbeginn")),
        migrations.AddField(model_name="meetingminutes", name="meeting_end", field=models.DateTimeField(blank=True, null=True, verbose_name="Sitzungsende")),
        migrations.AddField(model_name="meetingminutesitem", name="parent", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="leiterrunden.meetingminutesitem", verbose_name="Übergeordneter TOP")),
        migrations.AddField(model_name="meetingminutesitem", name="responsible_members", field=models.ManyToManyField(blank=True, related_name="assigned_meeting_minutes_items", to="main.membership", verbose_name="Verantwortliche")),
        migrations.CreateModel(name="MeetingGuest", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=255, verbose_name="Name")),
            ("note", models.CharField(blank=True, max_length=500, verbose_name="Notiz")),
            ("minutes", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="guests", to="leiterrunden.meetingminutes")),
        ]),
        migrations.CreateModel(name="MeetingAttendance", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("present", models.BooleanField(default=False)),
            ("note", models.CharField(blank=True, max_length=500, verbose_name="Notiz")),
            ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meeting_attendances", to="main.membership")),
            ("minutes", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attendances", to="leiterrunden.meetingminutes")),
        ], options={"ordering": ["membership__user__username"]}),
        migrations.AddConstraint(model_name="meetingattendance", constraint=models.UniqueConstraint(fields=("minutes", "membership"), name="unique_minutes_attendance")),
    ]
