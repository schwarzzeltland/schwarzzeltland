# Generated by Django 5.0 on 2025-03-29 17:33

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0014_tripmaterial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trip',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='events.location', verbose_name='Ort'),
        ),
    ]
