# Generated by Django 5.0 on 2025-01-25 22:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0006_membership_event_manager'),
    ]

    operations = [
        migrations.AlterField(
            model_name='membership',
            name='admin',
            field=models.BooleanField(default=False, verbose_name='Admin'),
        ),
        migrations.AlterField(
            model_name='organization',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='users/', verbose_name='Bild'),
        ),
    ]
