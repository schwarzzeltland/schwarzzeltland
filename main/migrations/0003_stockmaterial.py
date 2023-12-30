# Generated by Django 5.0 on 2023-12-30 20:10

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('buildings', '0002_alter_construction_description_and_more'),
        ('main', '0002_alter_membership_unique_together'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockMaterial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('count', models.IntegerField()),
                ('material', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='buildings.material')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.organization')),
            ],
        ),
    ]