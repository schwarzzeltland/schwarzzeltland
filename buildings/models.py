from django.db import models
from django.db.models import DecimalField, CharField, IntegerField, BooleanField

from main.models import Organization


class Material(models.Model):
    TYPE_ROOF = 0
    TYPE_PLANE = 1
    TYPE_POLE = 2
    TYPE_ROPE = 3
    TYPE_PEG = 4

    TYPES = (
        (TYPE_ROOF, "Dachplane"),
        (TYPE_PLANE, "Zeltplane"),
        (TYPE_POLE, "Stange"),
        (TYPE_ROPE, "Seil"),
        (TYPE_PEG, "Hering"),
    )
    name = CharField(max_length=255)
    description = CharField(max_length=1024, default="", blank=True)
    image = models.ImageField(upload_to="materials/", blank=True, null=True)
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    weight = DecimalField(max_digits=10, decimal_places=3, help_text="Gewicht in kg", blank=True, null=True)
    type = models.IntegerField(choices=TYPES, null=True, blank=True, help_text="Typ des Materials")
    length_min = DecimalField(max_digits=10, decimal_places=2,null=True, blank=True)
    length_max = DecimalField(max_digits=10, decimal_places=2,null=True, blank=True)
    width = DecimalField(max_digits=10, decimal_places=2,null=True, blank=True)
    public = BooleanField(default=False)

    def __str__(self):
        return self.name


class StockMaterial(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    count = models.IntegerField()
    storage_place = CharField(max_length=1024, default="", blank=True)


class Construction(models.Model):
    name = CharField(max_length=255)
    description = CharField(max_length=1024, default="", blank=True)
    sleep_place_count = DecimalField(max_digits=10, decimal_places=2,null=True, blank=True)
    covered_area = DecimalField(max_digits=10, decimal_places=2,null=True, blank=True)
    required_space = DecimalField(max_digits=10, decimal_places=2,null=True, blank=True)
    image = models.ImageField(upload_to="constructions/", blank=True, null=True)
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    public = BooleanField(default=False)

    def __str__(self):
        return self.name


class ConstructionMaterial(models.Model):
    construction = models.ForeignKey(Construction, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    count = models.IntegerField()
    storage_place = CharField(max_length=1024, default="", blank=True)
