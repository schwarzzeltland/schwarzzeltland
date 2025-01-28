from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import CharField, BooleanField

from buildings.models import Construction
from main.models import Organization


# Create your models here.

class Location(models.Model):
    TYPE_HOUSE = 0
    TYPE_CAMPGROUNDSCOUT = 1
    TYPE_CAMPGROUND = 2
    TYPE_FREESPACE = 3
    TYPE_PRIVATEPLACE = 4

    TYPES = (
        (TYPE_HOUSE, "Haus"),
        (TYPE_CAMPGROUNDSCOUT, "Pfadfinderzeltplatz"),
        (TYPE_CAMPGROUND, "Campingplatz"),
        (TYPE_FREESPACE, "Freier Platz"),
        (TYPE_PRIVATEPLACE, "Privater Platz")
    )
    name = CharField(max_length=255)
    type = models.IntegerField(choices=TYPES, null=True, blank=True, verbose_name="Typ")
    description = CharField(max_length=1024, default="", blank=True, verbose_name="Beschreibung")
    latitude = models.FloatField(default=00.000000, verbose_name="Breitengrad")
    longitude = models.FloatField(default=00.000000,  verbose_name="Längengrad")
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    public = BooleanField(default=False, verbose_name="Öffentlich")

    def __str__(self):
        return self.name


class Trip(models.Model):
    TYPE_CAMP = 0
    TYPE_DRIVE = 1
    TYPE_HAIK = 2
    TYPE_DAYTRIP = 3

    TYPES = (
        (TYPE_CAMP, "Lager"),
        (TYPE_DRIVE, "Fahrt"),
        (TYPE_HAIK, "Haik"),
        (TYPE_DAYTRIP, "Tagesaktion")
    )
    name = CharField(max_length=255)
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    type = models.IntegerField(choices=TYPES, null=True, blank=True, verbose_name="Typ")
    description = CharField(max_length=1024, default="", blank=True, verbose_name="Beschreibung")
    start_date = models.DateTimeField("Startdatum")
    end_date = models.DateTimeField("Enddatum")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class TripConstruction(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    construction = models.ForeignKey(Construction, on_delete=models.CASCADE)
    count = models.IntegerField(default=0,verbose_name="Anzahl",validators=[MinValueValidator(0)])
    description = CharField(max_length=1024, default="", blank=True,verbose_name="Beschreibung")


class PackedMaterial(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='packed_materials')
    material_name = models.CharField(max_length=255)
    packed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.material_name} - {'Eingepackt' if self.packed else 'Nicht eingepackt'}"

class TripGroup(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    count = models.IntegerField(default=0,verbose_name="Anzahl",validators=[MinValueValidator(0)])
    name = CharField(max_length=1024, default="", blank=True,verbose_name="Gruppenname")

