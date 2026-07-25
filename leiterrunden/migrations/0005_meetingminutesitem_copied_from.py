from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("leiterrunden", "0004_meetingminutesacceptance"),
    ]

    operations = [
        migrations.AddField(
            model_name="meetingminutesitem",
            name="copied_from",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="copies",
                to="leiterrunden.meetingminutesitem",
                verbose_name="Kopiert von",
            ),
        ),
    ]
