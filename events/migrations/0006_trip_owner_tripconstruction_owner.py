# Generated by Django 5.0 on 2025-01-12 17:53

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0005_trip_location_alter_location_type'),
        ('main', '0005_organization_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='owner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='main.organization'),
        ),
        migrations.AddField(
            model_name='tripconstruction',
            name='owner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='main.organization'),
        ),
    ]
