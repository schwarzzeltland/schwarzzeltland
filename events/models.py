from django.db import models
from django.db.models import CharField

from buildings.models import Construction


# Create your models here.
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
    description = CharField(max_length=1024, default="", blank=True)
    start_date = models.DateTimeField("Startdatum")
    end_date = models.DateTimeField("Enddatum")
    tn_count = models.IntegerField(default=0, help_text="TN Anzahl")

    def __str__(self):
        return self.name


class TripConstruction(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    construction = models.ForeignKey(Construction, on_delete=models.CASCADE)
    count = models.IntegerField(default=1)
