# Generated by Django 5.0 on 2025-01-11 15:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buildings', '0010_construction_covered_area_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='construction',
            name='covered_area',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name='construction',
            name='required_space',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name='construction',
            name='sleep_place_count',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name='material',
            name='length_max',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name='material',
            name='length_min',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name='material',
            name='width',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
    ]
