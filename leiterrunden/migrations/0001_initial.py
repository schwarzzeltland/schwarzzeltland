from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [("main", "0029_organization_pro6_membership_leiterrundenmitglied"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="MeetingMinutes",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Titel")),
                ("meeting_date", models.DateField(verbose_name="Sitzungsdatum")),
                ("introduction", models.TextField(blank=True, verbose_name="Einleitung / allgemeine Notizen")),
                ("published", models.BooleanField(default=False, verbose_name="An Leiterrunde veröffentlichen")),
                ("published_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_meeting_minutes", to=settings.AUTH_USER_MODEL, verbose_name="Erstellt von")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meeting_minutes", to="main.organization", verbose_name="Organisation")),
            ],
            options={"verbose_name": "Leiterrunden-Protokoll", "verbose_name_plural": "Leiterrunden-Protokolle", "ordering": ["-meeting_date", "-id"]},
        ),
        migrations.CreateModel(
            name="MeetingMinutesItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("topic", models.CharField(max_length=255, verbose_name="Tagesordnungspunkt")),
                ("notes", models.TextField(blank=True, verbose_name="Notizen / Beschluss")),
                ("responsible", models.CharField(blank=True, max_length=255, verbose_name="Verantwortlich")),
                ("due_date", models.DateField(blank=True, null=True, verbose_name="Fällig am")),
                ("position", models.PositiveIntegerField(default=0)),
                ("minutes", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="leiterrunden.meetingminutes")),
            ],
            options={"verbose_name": "Protokollpunkt", "verbose_name_plural": "Protokollpunkte", "ordering": ["position", "id"]},
        ),
    ]
