from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import DecimalField, CharField, IntegerField, BooleanField

from main.models import Organization


class Material(models.Model):
    TYPE_ROOF = 0
    TYPE_PLANE = 1
    TYPE_POLE = 2
    TYPE_ROPE = 3
    TYPE_PEG = 4
    TYPE_KITCHEN = 5
    TYPE_CONSUME = 6

    TYPES = (
        (TYPE_ROOF, "Dachplane"),
        (TYPE_PLANE, "Zeltplane"),
        (TYPE_POLE, "Stange"),
        (TYPE_ROPE, "Seil"),
        (TYPE_PEG, "Hering"),
        (TYPE_KITCHEN, "Küchenmaterial"),
        (TYPE_CONSUME, "Verbrauchsmaterial"),
    )
    name = CharField(max_length=255)
    description = CharField(max_length=2048, default="", blank=True,verbose_name="Beschreibung")
    image = models.ImageField(upload_to="materials/", blank=True, null=True,verbose_name="Bild")
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    weight = DecimalField(max_digits=10, decimal_places=3, default=0,help_text="in kg", blank=True, null=True,verbose_name="Gewicht",validators=[MinValueValidator(0)])
    type = models.IntegerField(choices=TYPES, null=True, blank=True,verbose_name="Typ")
    length_min = DecimalField(max_digits=10, decimal_places=2,null=True, blank=True,verbose_name="Mindestlänge", help_text="in cm",validators=[MinValueValidator(0)])
    length_max = DecimalField(max_digits=10, decimal_places=2,null=True, blank=True,verbose_name="Maximallänge", help_text="in cm",validators=[MinValueValidator(0)])
    width = DecimalField(max_digits=10, decimal_places=2,null=True, blank=True,verbose_name="Breite", help_text="in cm",validators=[MinValueValidator(0)])
    public = BooleanField(default=False,verbose_name="Öffentlich")

    def __str__(self):
        return self.name


class StockMaterial(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    count = models.IntegerField(verbose_name="Anzahl",validators=[MinValueValidator(0)])
    storage_place = CharField(max_length=1024, default="", blank=True,verbose_name="Lagerort")
    condition_healthy=models.IntegerField(verbose_name="Davon in Ordnung",validators=[MinValueValidator(0)], default=0)
    condition_medium_healthy=models.IntegerField(verbose_name="Davon wartungsbedürftig",validators=[MinValueValidator(0)], default=0)
    condition_broke=models.IntegerField(verbose_name="Davon defekt",validators=[MinValueValidator(0)], default=0)
    material_condition_description=CharField(max_length=1024, default="",blank=True,verbose_name="Zustands-Beschreibung")
    temporary = models.BooleanField(default=False)  # für verliehenes Material
    valid_until = models.DateField(null=True, blank=True)
    def __str__(self):
        return f"{self.material.name} ({self.organization.name})"

class Construction(models.Model):
    name = CharField(max_length=255)
    description = CharField(max_length=1024, default="", blank=True,verbose_name="Beschreibung")
    sleep_place_count = IntegerField(null=True, blank=True,default=0 ,verbose_name="Schlafplatz-Anzahl",validators=[MinValueValidator(0)])
    covered_area = DecimalField(max_digits=10, decimal_places=2,null=True, blank=True,verbose_name="Überdachte Fläche", help_text="in m²",validators=[MinValueValidator(0)])
    required_space = DecimalField(max_digits=10, decimal_places=2,null=True, blank=True,verbose_name="Benötigte Fläche", help_text="in m²",validators=[MinValueValidator(0)])
    image = models.ImageField(upload_to="constructions/", blank=True, null=True,verbose_name="Bild")
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    public = BooleanField(default=False,verbose_name="Öffentlich")

    def __str__(self):
        return self.name


class ConstructionMaterial(models.Model):
    construction = models.ForeignKey(Construction, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    count = models.IntegerField(verbose_name="Anzahl",validators=[MinValueValidator(0)])
    storage_place = CharField(max_length=1024, default="", blank=True,verbose_name="Lagerort")
