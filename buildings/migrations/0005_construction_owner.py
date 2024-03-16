# Generated by Django 5.0 on 2024-03-16 18:51

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("buildings", "0004_construction_image_material_image"),
        ("main", "0005_organization_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="construction",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="main.organization",
            ),
        ),
    ]
