from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leiterrunden", "0005_meetingminutesitem_copied_from")]

    operations = [
        migrations.AddField(model_name="meetingminutesitem", name="voting_enabled", field=models.BooleanField(default=False, verbose_name="Abstimmung erfassen")),
        migrations.AddField(model_name="meetingminutesitem", name="votes_yes", field=models.PositiveIntegerField(default=0, verbose_name="Ja-Stimmen")),
        migrations.AddField(model_name="meetingminutesitem", name="votes_no", field=models.PositiveIntegerField(default=0, verbose_name="Nein-Stimmen")),
        migrations.AddField(model_name="meetingminutesitem", name="votes_abstain", field=models.PositiveIntegerField(default=0, verbose_name="Enthaltungen")),
    ]
