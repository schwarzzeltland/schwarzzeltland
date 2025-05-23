# Generated by Django 5.0 on 2025-01-28 16:13

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0011_alter_location_description_alter_location_latitude_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TripGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('count', models.IntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Anzahl')),
                ('name', models.CharField(blank=True, default='', help_text='Unterteile deine Teilmnehmer in Gruppen, z.B. nach Alter oder nach Sippen', max_length=1024, verbose_name='Gruppenname')),
                ('trip', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='events.trip')),
            ],
        ),
    ]
