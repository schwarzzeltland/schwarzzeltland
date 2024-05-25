# Generated by Django 5.0 on 2024-05-25 15:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0002_tripconstruction'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='type',
            field=models.IntegerField(blank=True, choices=[(0, 'Lager'), (1, 'Fahrt'), (2, 'Haik'), (3, 'Tagesaktion')], help_text='Typ des Events', null=True),
        ),
    ]