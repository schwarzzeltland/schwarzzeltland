# Generated by Django 5.0.3 on 2024-05-25 21:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buildings', '0008_stockmaterial_storage_place'),
    ]

    operations = [
        migrations.AlterField(
            model_name='material',
            name='weight',
            field=models.DecimalField(blank=True, decimal_places=3, help_text='Gewicht in kg', max_digits=10, null=True),
        ),
    ]