from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("leiterrunden", "0003_meetingminutes_replaces"),
        ("main", "0029_organization_pro6_membership_leiterrundenmitglied"),
    ]

    operations = [
        migrations.CreateModel(
            name="MeetingMinutesAcceptance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("accepted_at", models.DateTimeField(auto_now_add=True)),
                (
                    "membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="meeting_minutes_acceptances",
                        to="main.membership",
                    ),
                ),
                (
                    "minutes",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="acceptances",
                        to="leiterrunden.meetingminutes",
                    ),
                ),
            ],
            options={
                "verbose_name": "Protokollannahme",
                "verbose_name_plural": "Protokollannahmen",
                "ordering": ["accepted_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="meetingminutesacceptance",
            constraint=models.UniqueConstraint(
                fields=("minutes", "membership"),
                name="unique_minutes_acceptance",
            ),
        ),
    ]
