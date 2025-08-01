# Generated by Django 5.0 on 2025-07-09 07:11

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0026_remove_trip_reciepentcode_trip_recipientcode'),
        ('main', '0013_alter_message_created'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='recipient_org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='received_org', to='main.organization', verbose_name='Empfänger Organisation (Groß- / Kleinschreibung beachten!)'),
        ),
    ]
