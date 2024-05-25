from django.db import models
from django.db.models import CharField

from buildings.models import Construction


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
    type = models.IntegerField(choices=TYPES, null=True, blank=True, help_text="Typ des Platzes")
    description = CharField(max_length=1024, default="", blank=True)
    latitude = models.FloatField(default=00.000000, help_text="Latitude")
    longitude = models.FloatField(default=00.000000, help_text="Longitude")

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
    type = models.IntegerField(choices=TYPES, null=True, blank=True, help_text="Typ des Events")
    description = CharField(max_length=1024, default="", blank=True)
    start_date = models.DateTimeField("Startdatum")
    end_date = models.DateTimeField("Enddatum")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, null=True, blank=True)
    tn_count = models.IntegerField(default=0, help_text="TN Anzahl")

    def __str__(self):
        return self.name


class TripConstruction(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    construction = models.ForeignKey(Construction, on_delete=models.CASCADE)
    count = models.IntegerField(default=1)
