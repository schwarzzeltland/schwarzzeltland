from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import CharField, BooleanField
from django.db.models.signals import post_save
from django.dispatch import receiver

from buildings.models import Construction, Material, StockMaterial
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
    longitude = models.FloatField(default=00.000000, verbose_name="Längengrad")
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    public = BooleanField(default=False, verbose_name="Öffentlich")

    def __str__(self):
        return self.name


class Trip(models.Model):
    TYPE_CAMP = 0
    TYPE_DRIVE = 1
    TYPE_HAIK = 2
    TYPE_DAYTRIP = 3
    TYPE_RENTAL = 4

    TYPES = (
        (TYPE_CAMP, "Lager"),
        (TYPE_DRIVE, "Fahrt"),
        (TYPE_HAIK, "Haik"),
        (TYPE_DAYTRIP, "Tagesaktion"),
        (TYPE_RENTAL, "Material-Verleih")
    )
    name = CharField(max_length=255)
    description = CharField(max_length=1024, default="", blank=True, verbose_name="Beschreibung")
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    type = models.IntegerField(choices=TYPES, null=True, blank=True, verbose_name="Typ")
    start_date = models.DateTimeField("Startdatum")
    end_date = models.DateTimeField("Enddatum")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Ort")
    recipient_org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        verbose_name="Empfänger Organisation (Groß- / Kleinschreibung beachten!)",
        related_name="received_org", null=True, blank=True
    )
    recipientcode = models.CharField(blank=True, max_length=20,
                                     verbose_name="Empfängercode der empfangenden Organisation")
    planners = models.ManyToManyField(
        User,
        blank=True,
        related_name="planned_trips",
        verbose_name="Planer"
    )

    def __str__(self):
        return self.name


class TripConstruction(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    construction = models.ForeignKey(Construction, on_delete=models.CASCADE)
    count = models.IntegerField(default=0, verbose_name="Anzahl", validators=[MinValueValidator(0)])
    description = CharField(max_length=1024, default="", blank=True, verbose_name="Beschreibung")


class PackedMaterial(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='packed_materials')
    material_name = models.CharField(max_length=255)
    packed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.material_name} - {'Eingepackt' if self.packed else 'Nicht eingepackt'}"


class TripGroup(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    count = models.IntegerField(default=0, verbose_name="Anzahl", validators=[MinValueValidator(0)])
    name = CharField(max_length=1024, default="", blank=True, verbose_name="Gruppenname")


class TripMaterial(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    count = models.IntegerField(default=0, verbose_name="Anzahl", validators=[MinValueValidator(0)])
    description = CharField(max_length=1024, default="", blank=True, verbose_name="Beschreibung")
    reduced_from_stock = models.IntegerField(validators=[MinValueValidator(0)], default=0)
    previous_count = models.IntegerField(validators=[MinValueValidator(0)], default=0)


class ShoppingListItem(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="shoppinglist")
    stockmaterial = models.ForeignKey(StockMaterial, on_delete=models.CASCADE, related_name="shoppinglist", null=True,
                                      blank=True)
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    unit = models.CharField(max_length=50, blank=True)
    # Warengruppen
    GROUP_DRINKS = 0
    GROUP_CEREALS_BAKED = 1
    GROUP_FRUITS_VEGETABLES = 2
    GROUP_COOLED = 3
    GROUP_GRILL = 4
    GROUP_CANNED = 5
    GROUP_SNACKS = 6
    GROUP_HYGIENE = 7
    GROUP_TOOLS = 8
    GROUP_MATERIAL = 9
    GROUP_OTHER = 99

    GROUPS = (
        (GROUP_DRINKS, "Getränke"),
        (GROUP_CEREALS_BAKED, "Brot / Cerealien"),
        (GROUP_FRUITS_VEGETABLES, "Obst / Gemüse"),
        (GROUP_COOLED, "Kühlung"),
        (GROUP_GRILL, "Grillgut"),
        (GROUP_CANNED, "Konserven"),
        (GROUP_SNACKS, "Snacks"),
        (GROUP_HYGIENE, "Hygiene"),
        (GROUP_TOOLS, "Werkzeug"),
        (GROUP_MATERIAL, "Material"),
        (GROUP_OTHER, "Sonstiges"),
    )
    product_group = models.IntegerField(choices=GROUPS, null=True, blank=True, verbose_name="Warengruppe")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.amount} {self.unit})"


class TripVacancy(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="vacancies")
    name = models.CharField(max_length=200)
    arrival = models.DateTimeField(null=True, blank=True)
    departure = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.arrival} - {self.departure})"


class EventPlanningChecklistItem(models.Model):
    trip = models.ForeignKey(
        Trip, on_delete=models.CASCADE, related_name="checklist", null=True, blank=True
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="checklist", null=True, blank=True
    )
    title = models.CharField(max_length=2255)
    done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} ({'✓' if self.done else '✗'})"


@receiver(post_save, sender=Trip)
def create_default_checklist(sender, instance, created, **kwargs):
    if created:
        defaults = instance.organization.default_checklist or []
        for title in defaults:
            EventPlanningChecklistItem.objects.create(trip=instance, title=title)


class ProgrammItem(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="programm")
    name = models.CharField(max_length=200)
    short_description = models.CharField(max_length=200, default="", blank=True, verbose_name="Kurz-Beschreibung")
    description = CharField(max_length=2048, default="", blank=True, verbose_name="Beschreibung")
    TYPE_MEAL = 0
    TYPE_WORKSHOP = 1
    TYPE_SERVICE = 2
    TYPE_MEAL_SERVICE = 3
    TYPE_EVENING_PROGRAMM = 4
    TYPE_OTHER = 99

    TYPES = (
        (TYPE_MEAL, "Mahlzeit"),
        (TYPE_WORKSHOP, "Workshop"),
        (TYPE_SERVICE, "Dienst"),
        (TYPE_MEAL_SERVICE, "Mahlzeiten-Dienst"),
        (TYPE_EVENING_PROGRAMM, "Abendprogramm"),
        (TYPE_OTHER, "Sonstiges"),
    )
    type = models.IntegerField(choices=TYPES, null=True, verbose_name="Typ")
    start_time = models.DateTimeField(null=True, verbose_name="Startzeit")
    end_time = models.DateTimeField(null=True, verbose_name="Endzeit")
    visible_for_members = models.BooleanField(default=True,verbose_name="Sichtbar für Mitglieder")

    def __str__(self):
        return f"{self.name}"

        # ✅ CSS-Klasse für Typ

    def type_class(self):
        mapping = {
            self.TYPE_MEAL: "type-meal",
            self.TYPE_WORKSHOP: "type-workshop",
            self.TYPE_SERVICE: "type-service",
            self.TYPE_MEAL_SERVICE: "type-meal-service",
            self.TYPE_EVENING_PROGRAMM: "type-evening",
            self.TYPE_OTHER: "type-other",
        }
        return mapping.get(self.type, "type-other")
