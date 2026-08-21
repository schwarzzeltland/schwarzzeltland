from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("buildings", "0025_materialcontainer_stockmaterial_container_and_more")]

    operations = [
        migrations.CreateModel(
            name="StoragePlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Bezeichnung")),
                ("image", models.ImageField(upload_to="storage_plans/", verbose_name="Plan")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="storage_plans", to="main.organization")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="StorageArea",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Bereich")),
                ("x", models.DecimalField(decimal_places=3, max_digits=6, validators=[django.core.validators.MinValueValidator(0)])),
                ("y", models.DecimalField(decimal_places=3, max_digits=6, validators=[django.core.validators.MinValueValidator(0)])),
                ("width", models.DecimalField(decimal_places=3, max_digits=6, validators=[django.core.validators.MinValueValidator(0)])),
                ("height", models.DecimalField(decimal_places=3, max_digits=6, validators=[django.core.validators.MinValueValidator(0)])),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="areas", to="buildings.storageplan", verbose_name="Lagerplan")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="materialcontainer", name="storage_area",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="containers", to="buildings.storagearea", verbose_name="Bereich im Lagerplan"),
        ),
        migrations.AddField(
            model_name="stockmaterial", name="storage_area",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_items", to="buildings.storagearea", verbose_name="Bereich im Lagerplan"),
        ),
        migrations.AddConstraint(model_name="storageplan", constraint=models.UniqueConstraint(fields=("organization", "name"), name="unique_storage_plan_name_per_org")),
        migrations.AddConstraint(model_name="storagearea", constraint=models.UniqueConstraint(fields=("plan", "name"), name="unique_storage_area_name_per_plan")),
    ]
